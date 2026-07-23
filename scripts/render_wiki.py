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
            f"| [{title[:80]}]({url}) | {fmt(r.get('views', 0))} | {fmt(r.get('unique_views', 0))} | "
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
            f"| [{title[:80]}]({v['url']}) | {fmt(v.get('views', 0))} | "
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

    # trend series
    trend_dates = [p["date"] for p in polls[-12:]]
    trend_series = {
        "GH stars": [totals(p)["stars"] for p in polls[-12:]],
        "Zenodo downloads": [totals(p)["zenodo_downloads"] for p in polls[-12:]],
        "YouTube views": [totals(p)["youtube_views"] for p in polls[-12:]],
    }

    parts: list[str] = []
    parts.append(f"# CCP-volumeEM Impact\n")
    parts.append(f"_Last polled: **{latest['date']}** · {len(polls)} poll(s) in history_\n")
    parts.append("## Totals\n")
    parts.append(totals_table(cur_totals, prev_totals))

    if len(polls) > 1:
        parts.append("\n## Trends (last 12 polls)\n")
        chart = mermaid_line("Impact over time", trend_dates, trend_series)
        if chart:
            parts.append(chart)

    parts.append("\n## GitHub repos\n")
    parts.append(gh_table(latest.get("github", {}).get("repos", []) or []))

    parts.append("\n## Zenodo records\n")
    parts.append(zn_table(latest.get("zenodo", {}).get("records", []) or []))

    parts.append("\n## YouTube videos\n")
    yt = latest.get("youtube") or {}
    parts.append(yt_table(yt.get("videos", []) or []))

    parts.append("\n---\n_Auto-generated by the [impact tracker workflow](../actions). Sources: "
                 "[GitHub](https://github.com/ccp-volume-em), "
                 "[Zenodo](https://zenodo.org/communities/ccp-volume-em/), "
                 "[YouTube](https://www.youtube.com/@CCP-volumeEM)._\n")

    OUT.write_text("\n".join(parts))
    print(f"Wrote {OUT} ({len(polls)} polls)")


if __name__ == "__main__":
    build()
