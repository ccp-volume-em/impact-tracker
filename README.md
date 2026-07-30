# impact-tracker

Weekly automated impact tracking for [CCP-volumeEM](https://github.com/ccp-volume-em).

A GitHub Actions workflow polls three sources every Monday, appends a snapshot to `data/history.json`, and publishes a report to this repo's wiki.

## Sources polled

| Source | Endpoint | Auth |
|---|---|---|
| GitHub org | `api.github.com/orgs/ccp-volume-em/repos` | none (uses `GITHUB_TOKEN` if available to raise rate limit) |
| Zenodo community | `zenodo.org/api/records?communities=ccp-volume-em` | none |
| YouTube channel | `youtube.googleapis.com/youtube/v3/*` | `YOUTUBE_API_KEY` secret required |

## What gets tracked

- **GitHub org**: per-repo stars, forks, watchers, open issues, size, last push, plus aggregate commits and lines added/deleted
- **Zenodo community**: per-record views, unique views, downloads, unique downloads, plus estimated bytes served
- **YouTube channel**: channel subs + total views, per-video views/likes/comments, plus view-weighted watch hours
- **Quay.io images**: per-image pulls, tags, size, last modified
- **Team commits**: per team member, total public commits + commits outside the CCP-volumeEM org

All sources are configured in `config.json` — edit that to add/remove repos, images, or usernames without touching Python.

## Output

- `data/history.json` — append-only time series (one entry per poll), committed on each run
- Wiki page **Impact** — regenerated each run with totals, week-over-week deltas, Mermaid trend charts, and per-source tables

## Running locally

```bash
pip install -r requirements.txt
export YOUTUBE_API_KEY=...  # optional
python scripts/poll_impact.py
python scripts/render_wiki.py
# open wiki_output/Impact.md
```

## Setup

See [SETUP.md](SETUP.md).
