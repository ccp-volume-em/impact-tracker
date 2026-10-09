# impact-tracker

A GitHub Actions template for automatically tracking community/project impact across GitHub, Zenodo, YouTube, and Quay.io. Runs on a daily schedule, appends a snapshot to a time-series file in the repo, and publishes a report to the repo's wiki.

Originally built for [CCP-volumeEM](https://github.com/ccp-volume-em) — but everything is driven by a single `config.json`, so any group can clone this and adapt it in a few minutes.

## What gets tracked

| Source | Metric | Auth needed |
|---|---|---|
| **GitHub org** | Per-repo stars, forks, watchers, open issues, aggregate commits, lines added/deleted | None (runner token used to raise rate limits) |
| **GitHub team members** | Public commits by named users across a configurable scope (your org, other orgs, individual repos) | None |
| **Zenodo community** | Per-record views, downloads, estimated bytes served | None |
| **YouTube channel** | Channel subs, per-video views/likes/comments, view-weighted watch hours | Free YouTube Data API v3 key |
| **Quay.io images** | Per-image pulls (estimated from Quay's event counts over the last ~90 days; see `quay_events_per_pull` in [SETUP.md](SETUP.md)), tags, size, last modified | None |

## Output

- **`data/history.json`** — append-only time series, one entry per run. Committed to `main` on each poll.
- **Wiki `Impact` page** — regenerated each run with totals, deltas compared to the same time last week, and per-source tables.

Polling is daily, so the delta column is not a change-since-last-poll figure: it compares the latest snapshot against the poll from roughly seven days earlier (the nearest one within two days, so a dropped scheduled run doesn't blank the column). Until the history covers a full week, the column shows `—`.

## Make your own

See **[SETUP.md](SETUP.md)** — 10-minute walkthrough covering repo creation, wiki initialisation, YouTube API key, and configuration.

## Running locally (optional)

```bash
pip install -r requirements.txt
export YOUTUBE_API_KEY=...       # optional
export GITHUB_TOKEN=ghp_...      # optional; raises GitHub rate limit
python scripts/poll_impact.py
python scripts/render_wiki.py
# see wiki_output/Impact.md
```
