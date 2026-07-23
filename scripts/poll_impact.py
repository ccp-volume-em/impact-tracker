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
import sys
from datetime import date
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
HISTORY = REPO_ROOT / "data" / "history.json"

GH_ORG = "ccp-volume-em"
ZENODO_COMMUNITY = "ccp-volume-em"
YT_HANDLE = "CCP-volumeEM"

TODAY = date.today().isoformat()
UA = {"User-Agent": "ccp-volumeem-impact-tracker/1.0"}
TIMEOUT = 30


def _get(url: str, headers: dict[str, str] | None = None) -> Any:
    r = requests.get(url, headers={**UA, **(headers or {})}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


# ---------- GitHub ----------
def poll_github() -> list[dict]:
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
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
                }
            )
        if len(batch) < 100:
            break
        page += 1
    return repos


# ---------- Zenodo ----------
def poll_zenodo() -> list[dict]:
    records: list[dict] = []
    page = 1
    while True:
        data = _get(
            f"https://zenodo.org/api/records?communities={ZENODO_COMMUNITY}&size=100&page={page}"
        )
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            break
        for r in hits:
            stats = r.get("stats", {}) or {}
            md = r.get("metadata", {}) or {}
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
                }
            )
        if len(hits) < 100:
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
            params={"part": "statistics,snippet", "id": ",".join(batch), "key": api_key},
            headers=UA, timeout=TIMEOUT,
        ).json()
        for v in vids.get("items", []):
            s = v.get("statistics", {}) or {}
            sn = v.get("snippet", {}) or {}
            videos.append(
                {
                    "id": v["id"],
                    "url": f"https://www.youtube.com/watch?v={v['id']}",
                    "title": sn.get("title", ""),
                    "published_at": sn.get("publishedAt"),
                    "views": int(s.get("viewCount", 0)),
                    "likes": int(s.get("likeCount", 0)),
                    "comments": int(s.get("commentCount", 0)),
                }
            )
    return channel, videos


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

    history = load_history()
    history["polls"].append(
        {
            "date": TODAY,
            "github": {"repos": gh},
            "zenodo": {"records": zn},
            "youtube": {"channel": yt_channel, "videos": yt_videos} if yt_channel else None,
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
