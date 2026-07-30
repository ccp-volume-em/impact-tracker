"""
Poll CCP-volumeEM impact sources and append a snapshot to data/history.json.

Sources:
  - GitHub org (public) — repos with stars/forks/watchers/open_issues/pushed_at
  - Zenodo community (public) — records with views/downloads
  - YouTube channel (needs YOUTUBE_API_KEY) — channel + per-video stats

history.json shape:
  {
    "polls": [
      {
        "date": "2026-07-27",
        "github": {"repos": [ ... ]},
        "zenodo": {"records": [ ... ]},
        "youtube": {"channel": {...}, "videos": [ ... ]}
      }, ...
    ]
  }
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
HISTORY = REPO_ROOT / "data" / "history.json"
CONFIG = json.loads((REPO_ROOT / "config.json").read_text())

GH_ORG: str = CONFIG["github_org"]
ZENODO_COMMUNITY: str = CONFIG["zenodo_community"]
YT_HANDLE: str = CONFIG["youtube_handle"]
TEAM_MEMBERS: list[str] = CONFIG.get("team_members", [])
QUAY_IMAGES: list[str] = CONFIG.get("quay_images", [])
EXTERNAL_SCOPE: dict = CONFIG.get("external_scope", {"orgs": [], "repos": []})

TODAY = date.today().isoformat()
UA = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) impact-tracker/1.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
TIMEOUT = 30


def _get(url: str, headers: dict[str, str] | None = None) -> Any:
    r = requests.get(url, headers={**UA, **(headers or {})}, timeout=TIMEOUT)
    if not r.ok:
        # Surface the response body — many APIs (Zenodo/InvenioRDM included)
        # return a JSON explanation of what was wrong with the request.
        body = r.text[:500].replace("\n", " ")
        print(f"    HTTP {r.status_code} body: {body}", flush=True)
    r.raise_for_status()
    return r.json()


# ---------- GitHub ----------
def _gh_headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _gh_contributor_stats(owner: str, repo: str) -> tuple[int, int, int]:
    """Return (commits, lines_added, lines_deleted) for a repo.

    The contributors-stats endpoint returns 202 while GitHub computes the
    aggregate; retry a few times, then give up quietly (returning zeros).
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/stats/contributors"
    for attempt in range(5):
        r = requests.get(url, headers={**UA, **_gh_headers()}, timeout=TIMEOUT)
        if r.status_code == 202:
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 204:  # empty repo
            return (0, 0, 0)
        r.raise_for_status()
        data = r.json()
        commits = sum(c.get("total", 0) for c in data)
        added = sum(w.get("a", 0) for c in data for w in c.get("weeks", []))
        deleted = sum(w.get("d", 0) for c in data for w in c.get("weeks", []))
        return commits, added, deleted
    print(f"    {repo}: contributor stats not ready after retries", flush=True)
    return (0, 0, 0)


def poll_github() -> list[dict]:
    headers = _gh_headers()
    repos: list[dict] = []
    page = 1
    while True:
        batch = _get(
            f"https://api.github.com/orgs/{GH_ORG}/repos?per_page=100&page={page}",
            headers=headers,
        )
        if not batch:
            break
        for r in batch:
            commits, added, deleted = _gh_contributor_stats(GH_ORG, r["name"])
            repos.append(
                {
                    "name": r["name"],
                    "url": r["html_url"],
                    "stars": r.get("stargazers_count", 0),
                    "forks": r.get("forks_count", 0),
                    "watchers": r.get("subscribers_count", r.get("watchers_count", 0)),
                    "open_issues": r.get("open_issues_count", 0),
                    "size_kb": r.get("size", 0),
                    "pushed_at": r.get("pushed_at"),
                    "archived": r.get("archived", False),
                    "description": r.get("description"),
                    "commits": commits,
                    "lines_added": added,
                    "lines_deleted": deleted,
                }
            )
        if len(batch) < 100:
            break
        page += 1
    return repos


# ---------- Zenodo ----------
def _zenodo_probe() -> str:
    """Return the URL template (with {page}) that yields the most records."""
    templates = [
        # dedicated community endpoint, all versions
        f"https://zenodo.org/api/communities/{ZENODO_COMMUNITY}/records?all_versions=true&size=25&page={{page}}",
        # legacy filter, all versions
        f"https://zenodo.org/api/records?communities={ZENODO_COMMUNITY}&all_versions=true&size=25&page={{page}}",
        # dedicated community endpoint, latest only
        f"https://zenodo.org/api/communities/{ZENODO_COMMUNITY}/records?size=25&page={{page}}",
        # legacy filter, latest only
        f"https://zenodo.org/api/records?communities={ZENODO_COMMUNITY}&size=25&page={{page}}",
    ]
    best = (0, templates[0])
    for tmpl in templates:
        url = tmpl.format(page=1)
        try:
            data = _get(url)
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            print(f"  Zenodo probe: {url} -> HTTP {code}")
            continue
        total = ((data.get("hits") or {}).get("total")) or 0
        # InvenioRDM sometimes returns {"value": N, "relation": "eq"} for total
        if isinstance(total, dict):
            total = total.get("value", 0)
        print(f"  Zenodo probe: {url} -> total={total}")
        if total > best[0]:
            best = (total, tmpl)
    print(f"  Zenodo probe: chose template with total={best[0]}")
    return best[1]


def poll_zenodo() -> list[dict]:
    records: list[dict] = []
    tmpl = _zenodo_probe()
    page = 1
    while True:
        data = _get(tmpl.format(page=page))
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            break
        for r in hits:
            stats = r.get("stats", {}) or {}
            md = r.get("metadata", {}) or {}
            files = r.get("files", []) or []
            total_bytes = sum(f.get("size", 0) for f in files)
            records.append(
                {
                    "id": r.get("id"),
                    "doi": md.get("doi"),
                    "title": md.get("title"),
                    "publication_date": md.get("publication_date"),
                    "url": r.get("links", {}).get("self_html"),
                    "views": stats.get("views", 0),
                    "unique_views": stats.get("unique_views", 0),
                    "downloads": stats.get("downloads", 0),
                    "unique_downloads": stats.get("unique_downloads", 0),
                    "version_downloads": stats.get("version_downloads", 0),
                    "num_files": len(files),
                    "total_bytes": total_bytes,
                }
            )
        if len(hits) < 25:
            break
        page += 1
    return records


# ---------- YouTube ----------
def poll_youtube(api_key: str) -> tuple[dict, list[dict]]:
    ch = requests.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={"part": "statistics,contentDetails,snippet", "forHandle": f"@{YT_HANDLE}", "key": api_key},
        headers=UA, timeout=TIMEOUT,
    ).json()
    if not ch.get("items"):
        raise RuntimeError(f"YouTube channel @{YT_HANDLE} not found")
    item = ch["items"][0]
    channel = {
        "id": item["id"],
        "title": item["snippet"]["title"],
        "subscribers": int(item["statistics"].get("subscriberCount", 0)),
        "total_views": int(item["statistics"].get("viewCount", 0)),
        "video_count": int(item["statistics"].get("videoCount", 0)),
    }
    uploads_pl = item["contentDetails"]["relatedPlaylists"]["uploads"]

    video_ids: list[str] = []
    page_token = ""
    while True:
        params = {"part": "contentDetails", "playlistId": uploads_pl, "maxResults": 50, "key": api_key}
        if page_token:
            params["pageToken"] = page_token
        pl = requests.get(
            "https://www.googleapis.com/youtube/v3/playlistItems",
            params=params, headers=UA, timeout=TIMEOUT,
        ).json()
        video_ids.extend(i["contentDetails"]["videoId"] for i in pl.get("items", []))
        page_token = pl.get("nextPageToken")
        if not page_token:
            break

    videos: list[dict] = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        vids = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "statistics,snippet,contentDetails", "id": ",".join(batch), "key": api_key},
            headers=UA, timeout=TIMEOUT,
        ).json()
        for v in vids.get("items", []):
            s = v.get("statistics", {}) or {}
            sn = v.get("snippet", {}) or {}
            cd = v.get("contentDetails", {}) or {}
            videos.append(
                {
                    "id": v["id"],
                    "url": f"https://www.youtube.com/watch?v={v['id']}",
                    "title": sn.get("title", ""),
                    "published_at": sn.get("publishedAt"),
                    "views": int(s.get("viewCount", 0)),
                    "likes": int(s.get("likeCount", 0)),
                    "comments": int(s.get("commentCount", 0)),
                    "duration_seconds": _iso8601_duration_to_seconds(cd.get("duration", "PT0S")),
                }
            )
    return channel, videos


_ISO8601_DUR = re.compile(
    r"^P"
    r"(?:(?P<days>\d+)D)?"
    r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?"
    r"$"
)


# ---------- Quay.io ----------
def poll_quay(images: list[str]) -> list[dict]:
    """Fetch per-image metadata from quay.io for each 'namespace/name' entry.

    The public endpoint returns metadata including tags. Pull counts are exposed
    via the `stats` field when the repo owner has enabled them; when they aren't,
    we still capture size, tag count, and last-modified.
    """
    rows: list[dict] = []
    for image in images:
        if "/" not in image:
            print(f"    Quay: skipping malformed entry {image!r}", flush=True)
            continue
        ns, name = image.split("/", 1)
        try:
            data = _get(
                f"https://quay.io/api/v1/repository/{ns}/{name}?includeStats=true&includeTags=true",
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            print(f"    Quay: {image} -> HTTP {code}")
            continue
        tags = data.get("tags") or {}
        # pulls appears in a couple of places depending on plan/ownership
        pulls = (
            (data.get("stats") or {}).get("pulls")
            or data.get("popularity")
            or 0
        )
        # sum size across tags (each tag has size for the image at that tag)
        total_size = sum((t.get("size") or 0) for t in tags.values())
        last_modified = data.get("last_modified") or max(
            (t.get("last_modified") or "" for t in tags.values()), default=""
        )
        rows.append(
            {
                "image": image,
                "url": f"https://quay.io/repository/{ns}/{name}",
                "is_public": data.get("is_public"),
                "description": data.get("description"),
                "pulls": int(pulls) if isinstance(pulls, (int, float)) else 0,
                "num_tags": len(tags),
                "total_size_bytes": total_size,
                "last_modified": last_modified,
            }
        )
    return rows


# ---------- Team commits (across configured external scope) ----------
def poll_team_commits(usernames: list[str], scope: dict) -> list[dict]:
    """Public commits per team member within the configured scope.

    The scope is {"orgs": [...], "repos": [...]}. GitHub's /search/commits
    doesn't OR `repo:` qualifiers within a single query, so we issue one
    query per (user, scope-entry) and sum. Search API allows 30 req/min
    authenticated; we throttle to stay well under.
    """
    if not usernames:
        return []
    scopes: list[tuple[str, str]] = []
    for org in scope.get("orgs", []) or []:
        scopes.append(("org", org))
    for repo in scope.get("repos", []) or []:
        scopes.append(("repo", repo))
    if not scopes:
        print("    Team commits: no scope configured, skipping")
        return []

    headers = {
        **_gh_headers(),
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    rows: list[dict] = []
    for u in usernames:
        per_scope: dict[str, int] = {}
        total = 0
        for qualifier, value in scopes:
            q = f"author:{u} {qualifier}:{value}"
            try:
                r = requests.get(
                    "https://api.github.com/search/commits",
                    params={"q": q, "per_page": 1},
                    headers={**UA, **headers},
                    timeout=TIMEOUT,
                )
            except requests.RequestException as e:
                print(f"    Team commits: {u} in {qualifier}:{value} -> {e}")
                continue
            if not r.ok:
                print(
                    f"    Team commits: {u} in {qualifier}:{value} -> HTTP {r.status_code} "
                    f"{r.text[:200]}"
                )
                continue
            n = r.json().get("total_count", 0)
            per_scope[f"{qualifier}:{value}"] = n
            total += n
            # Search API is 30 rpm; ~2.2s keeps us at ~27 rpm across all users.
            time.sleep(2.2)
        rows.append(
            {
                "username": u,
                "url": f"https://github.com/{u}",
                "total_commits": total,
                "per_scope": per_scope,
            }
        )
    return rows


def _iso8601_duration_to_seconds(s: str) -> int:
    """Parse a YouTube ISO-8601 duration (e.g. 'PT1H12M34S') to seconds."""
    if not s:
        return 0
    m = _ISO8601_DUR.match(s)
    if not m:
        return 0
    return (
        int(m.group("days") or 0) * 86400
        + int(m.group("hours") or 0) * 3600
        + int(m.group("minutes") or 0) * 60
        + int(m.group("seconds") or 0)
    )


# ---------- Storage ----------
def load_history() -> dict:
    if HISTORY.exists():
        return json.loads(HISTORY.read_text())
    return {"polls": []}


def save_history(h: dict) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    HISTORY.write_text(json.dumps(h, indent=2, default=str))


def main() -> int:
    print(f"[{TODAY}] Polling CCP-volumeEM impact sources...")
    errors: list[str] = []

    try:
        gh = poll_github()
        print(f"  GitHub: {len(gh)} repos, {sum(r['stars'] for r in gh)} total stars")
    except Exception as e:
        errors.append(f"GitHub: {e}")
        gh = []

    try:
        zn = poll_zenodo()
        print(f"  Zenodo: {len(zn)} records, {sum(r['downloads'] for r in zn)} total downloads")
    except Exception as e:
        errors.append(f"Zenodo: {e}")
        zn = []

    yt_channel: dict | None = None
    yt_videos: list[dict] = []
    yt_key = os.environ.get("YOUTUBE_API_KEY")
    if yt_key:
        try:
            yt_channel, yt_videos = poll_youtube(yt_key)
            print(f"  YouTube: {yt_channel['video_count']} videos, {yt_channel['subscribers']} subscribers")
        except Exception as e:
            errors.append(f"YouTube: {e}")
    else:
        print("  YouTube: skipped (YOUTUBE_API_KEY not set)")

    try:
        quay = poll_quay(QUAY_IMAGES) if QUAY_IMAGES else []
        if QUAY_IMAGES:
            print(f"  Quay: {len(quay)} images, {sum(q.get('pulls', 0) for q in quay)} total pulls")
    except Exception as e:
        errors.append(f"Quay: {e}")
        quay = []

    try:
        team = poll_team_commits(TEAM_MEMBERS, EXTERNAL_SCOPE) if TEAM_MEMBERS else []
        if TEAM_MEMBERS:
            print(f"  Team commits: {len(team)} members, {sum(t.get('total_commits', 0) for t in team)} commits in scope")
    except Exception as e:
        errors.append(f"Team commits: {e}")
        team = []

    history = load_history()
    history["polls"].append(
        {
            "date": TODAY,
            "github": {"repos": gh},
            "zenodo": {"records": zn},
            "youtube": {"channel": yt_channel, "videos": yt_videos} if yt_channel else None,
            "quay": {"images": quay},
            "team_commits": {"members": team},
        }
    )
    save_history(history)
    print(f"Wrote {HISTORY} ({len(history['polls'])} poll(s) in history)")

    if errors:
        print("\nErrors encountered:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        # Non-fatal if we got at least one source
        if not gh and not zn and not yt_videos:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
