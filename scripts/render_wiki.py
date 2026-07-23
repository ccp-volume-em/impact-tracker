"""
Read data/history.json and render a single Impact.md into wiki_output/ for
GitHub Actions to push to the repo's wiki.

Layout of the generated page:
  - Header + last poll date
  - Totals cards (as a compact table)
  - Week-over-week deltas (with arrows)
  - Trend charts (Mermaid xychart-beta — renders natively on GitHub wikis)
  - GitHub repos table (latest snapshot)
  - Zenodo records table (latest snapshot)
  - YouTube videos table (latest snapshot)
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HISTORY = REPO_ROOT / "data" / "history.json"
OUT_DIR = REPO_ROOT / "wiki_output"
OUT = OUT_DIR / "Impact.md"


def fmt(n) -> str:
    try:
        return f"{int(n):,}"
    except Exception:
        return str(n or 0)


def fmt_bytes(b: int) -> str:
    for unit, div in [("TB", 1e12), ("GB", 1e9), ("MB", 1e6), ("kB", 1e3)]:
        if b >= div:
            return f"{b / div:,.2f} {unit}"
    return f"{b} B"


def fmt_hours(seconds: int) -> str:
    hours = seconds / 3600
    if hours >= 1:
        return f"{hours:,.1f} h"
    return f"{seconds / 60:,.1f} min"


def delta(cur: int | None, prev: int | None) -> str:
    if prev is None or cur is None:
        return ""
    d = cur - prev
    if d == 0:
        return " (=)"
    arrow = "▲" if d > 0 else "▼"
    return f" ({arrow}{abs(d):,})"


def totals(poll: dict) -> dict:
    if not poll:
        return {}
    gh_repos = poll.get("github", {}).get("repos", []) or []
    zn = poll.get("zenodo", {}).get("records", []) or []
    yt = poll.get("youtube") or {}
    yt_ch = yt.get("channel") or {}
    yt_vids = yt.get("videos", []) or []
    return {
        "repos": len(gh_repos),
        "stars": sum(r.get("stars", 0) for r in gh_repos),
        "forks": sum(r.get("forks", 0) for r in gh_repos),
        "zenodo_records": len(zn),
        "zenodo_views": sum(r.get("views", 0) for r in zn),
        "zenodo_downloads": sum(r.get("downloads", 0) for r in zn),
        "youtube_videos": len(yt_vids) or yt_ch.get("video_count", 0),
        "youtube_views": sum(v.get("views", 0) for v in yt_vids) or yt_ch.get("total_views", 0),
        "youtube_subs": yt_ch.get("subscribers", 0),
    }


def totals_table(cur: dict, prev: dict | None) -> str:
    rows = [
        ("GitHub repos", cur["repos"], (prev or {}).get("repos")),
        ("GitHub stars", cur["stars"], (prev or {}).get("stars")),
        ("GitHub forks", cur["forks"], (prev or {}).get("forks")),
        ("Zenodo records", cur["zenodo_records"], (prev or {}).get("zenodo_records")),
        ("Zenodo views", cur["zenodo_views"], (prev or {}).get("zenodo_views")),
        ("Zenodo downloads", cur["zenodo_downloads"], (prev or {}).get("zenodo_downloads")),
        ("YouTube videos", cur["youtube_videos"], (prev or {}).get("youtube_videos")),
        ("YouTube views", cur["youtube_views"], (prev or {}).get("youtube_views")),
        ("YouTube subscribers", cur["youtube_subs"], (prev or {}).get("youtube_subs")),
    ]
    lines = ["| Metric | Value | Δ vs. previous |", "|---|---:|---:|"]
    for label, val, prv in rows:
        lines.append(f"| {label} | {fmt(val)} | {delta(val, prv).strip() or '—'} |")
    return "\n".join(lines)


def mermaid_line(title: str, dates: list[str], series: dict[str, list[int]]) -> str:
    """A Mermaid xychart-beta with one line per series (Mermaid v10+ syntax)."""
    if not dates or not any(series.values()):
        return ""
    y_max = max((max(v) for v in series.values() if v), default=0) or 1
    lines = [
        "```mermaid",
        "xychart-beta",
        f"    title \"{title}\"",
        f"    x-axis [{', '.join(dates)}]",
        f"    y-axis \"count\" 0 --> {int(y_max * 1.1) + 1}",
    ]
    for label, values in series.items():
        lines.append(f"    line \"{label}\" [{', '.join(str(v) for v in values)}]")
    lines.append("```")
    return "\n".join(lines)


def gh_table(repos: list[dict]) -> str:
    if not repos:
        return "_No repos._"
    repos = sorted(repos, key=lambda r: r.get("stars", 0), reverse=True)
    lines = [
        "| Repo | Stars | Forks | Watchers | Open issues | Last push |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for r in repos:
        name = f"[{r['name']}]({r['url']})"
        pushed = (r.get("pushed_at") or "")[:10]
        lines.append(
            f"| {name} | {fmt(r.get('stars', 0))} | {fmt(r.get('forks', 0))} | "
            f"{fmt(r.get('watchers', 0))} | {fmt(r.get('open_issues', 0))} | {pushed} |"
        )
    return "\n".join(lines)


def zn_table(records: list[dict]) -> str:
    if not records:
        return "_No Zenodo records._"
    records = sorted(records, key=lambda r: r.get("downloads", 0), reverse=True)
    lines = [
        "| Record | Views | Unique views | Downloads | Unique downloads | Published |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for r in records:
        title = (r.get("title") or f"Record {r.get('id')}").replace("|", "\\|")
        url = r.get("url") or f"https://zenodo.org/records/{r.get('id')}"
        lines.append(
            f"| [{title}]({url}) | {fmt(r.get('views', 0))} | {fmt(r.get('unique_views', 0))} | "
            f"{fmt(r.get('downloads', 0))} | {fmt(r.get('unique_downloads', 0))} | "
            f"{r.get('publication_date') or ''} |"
        )
    return "\n".join(lines)


def yt_table(videos: list[dict]) -> str:
    if not videos:
        return "_No YouTube videos (or API key not configured)._"
    videos = sorted(videos, key=lambda v: v.get("views", 0), reverse=True)
    lines = [
        "| Video | Views | Likes | Comments | Published |",
        "|---|---:|---:|---:|---|",
    ]
    for v in videos:
        title = (v.get("title") or v["id"]).replace("|", "\\|")
        pub = (v.get("published_at") or "")[:10]
        lines.append(
            f"| [{title}]({v['url']}) | {fmt(v.get('views', 0))} | "
            f"{fmt(v.get('likes', 0))} | {fmt(v.get('comments', 0))} | {pub} |"
        )
    return "\n".join(lines)


def build() -> None:
    if not HISTORY.exists():
        history = {"polls": []}
    else:
        history = json.loads(HISTORY.read_text())
    polls = history.get("polls", [])

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not polls:
        OUT.write_text(
            "# CCP-volumeEM Impact\n\n"
            "_No polls recorded yet. The weekly workflow will populate this page._\n\n"
            "Sources:\n"
            "- https://github.com/ccp-volume-em\n"
            "- https://zenodo.org/communities/ccp-volume-em/\n"
            "- https://www.youtube.com/@CCP-volumeEM\n"
        )
        print(f"Wrote empty {OUT}")
        return

    latest = polls[-1]
    prev = polls[-2] if len(polls) >= 2 else None
    cur_totals = totals(latest)
    prev_totals = totals(prev) if prev else None

    parts: list[str] = []
    parts.append(f"# CCP-volumeEM Impact\n")
    parts.append(f"_Last polled: **{latest['date']}** · {len(polls)} poll(s) in history_\n")
    parts.append("## Totals\n")
    parts.append(totals_table(cur_totals, prev_totals))

    gh_repos = latest.get("github", {}).get("repos", []) or []
    zn_records = latest.get("zenodo", {}).get("records", []) or []
    yt = latest.get("youtube") or {}
    yt_videos = yt.get("videos", []) or []

    # ---- summary lines ----
    gh_commits = sum(r.get("commits", 0) for r in gh_repos)
    gh_added = sum(r.get("lines_added", 0) for r in gh_repos)
    gh_deleted = sum(r.get("lines_deleted", 0) for r in gh_repos)

    # Zenodo download volume: each record's `downloads` field is a count of
    # file-level downloads. We approximate served bytes as
    # downloads × average_file_size for that record. This is an estimate,
    # not the ground-truth transfer volume.
    zn_bytes = 0
    for r in zn_records:
        n_files = max(r.get("num_files", 0) or 0, 1)
        avg_size = (r.get("total_bytes", 0) or 0) / n_files
        zn_bytes += int((r.get("downloads", 0) or 0) * avg_size)

    # YouTube "view-weighted content duration" = sum(views × video length).
    # This is not real watch time (that requires OAuth to the channel), but
    # it's the closest public proxy.
    yt_view_seconds = sum(
        (v.get("views", 0) or 0) * (v.get("duration_seconds", 0) or 0) for v in yt_videos
    )

    parts.append("\n## GitHub repos\n")
    parts.append(
        f"_Aggregate activity across all repos: **{fmt(gh_commits)}** commits · "
        f"**+{fmt(gh_added)}** / **−{fmt(gh_deleted)}** lines._\n"
    )
    parts.append(gh_table(gh_repos))

    parts.append("\n## Zenodo records\n")
    parts.append(
        f"_Estimated data served: **{fmt_bytes(zn_bytes)}** "
        f"(downloads × average file size per record)._\n"
    )
    parts.append(zn_table(zn_records))

    parts.append("\n## YouTube videos\n")
    if yt_videos:
        parts.append(
            f"_View-weighted content duration: **{fmt_hours(yt_view_seconds)}** "
            f"(views × video length; not actual watch time)._\n"
        )
    parts.append(yt_table(yt_videos))

    parts.append("\n---\n_Auto-generated by the [impact tracker workflow](../actions). Sources: "
                 "[GitHub](https://github.com/ccp-volume-em), "
                 "[Zenodo](https://zenodo.org/communities/ccp-volume-em/), "
                 "[YouTube](https://www.youtube.com/@CCP-volumeEM)._\n")

    OUT.write_text("\n".join(parts))
    print(f"Wrote {OUT} ({len(polls)} polls)")


if __name__ == "__main__":
    build()
