# Setup guide

Follow this once to get your own tracker running. Estimated time: 10 minutes.

## Prerequisites

- A GitHub account (personal or organisation)
- A Google account (only if you want to track YouTube — free tier, no credit card)
- Basic familiarity with git

## 1. Create your repo from the template

You have two ways:

**A. Use as a GitHub template (recommended)** — on the [source repo](https://github.com/ccp-volume-em/impact-tracker), click **Use this template** → **Create a new repository**. Name it e.g. `myproject-impact-tracker`, keep it public (free CI minutes and public wiki).

**B. Clone manually**:
```bash
git clone https://github.com/ccp-volume-em/impact-tracker.git myproject-impact-tracker
cd myproject-impact-tracker
rm -rf .git
git init && git add . && git commit -m "Initial commit from impact-tracker template"
git remote add origin git@github.com:<your-org>/<your-repo>.git
git branch -M main
git push -u origin main
```

Either way, at the end you have your own repo on GitHub.

## 2. Edit `config.json`

Open `config.json` at the repo root. Every field is explained below.

```json
{
  "github_org": "your-org",
  "zenodo_community": "your-community-slug",
  "youtube_handle": "YourChannelHandle",
  "team_members": ["gh-username-1", "gh-username-2"],
  "external_scope": {
    "orgs": ["other-org-you-contribute-to"],
    "repos": ["owner/repo1", "owner/repo2"]
  },
  "quay_images": [
    "namespace/image1",
    "namespace/image2"
  ]
}
```

### Field reference

| Field | Required | Example | Notes |
|---|---|---|---|
| `github_org` | yes | `"ccp-volume-em"` | The GitHub org whose repos are the "home" section of the report. |
| `zenodo_community` | yes | `"ccp-volume-em"` | Zenodo community slug — the last segment of `https://zenodo.org/communities/<slug>/`. Set to `""` (empty string) to skip Zenodo. |
| `youtube_handle` | yes | `"CCP-volumeEM"` | YouTube handle without the `@`. From `https://www.youtube.com/@<handle>`. Set to `""` to skip YouTube. Requires the `YOUTUBE_API_KEY` secret (step 4). |
| `team_members` | yes (may be empty) | `["martlj", "folterj"]` | GitHub usernames whose external commits you want counted. Case-insensitive. |
| `external_scope.orgs` | no | `["volume-em"]` | Additional GitHub orgs to check for team-member commits. Only repos with at least one team-member commit appear in the report. |
| `external_scope.repos` | no | `["rosalindfranklininstitute/mib-container"]` | Individual repos (owner/name) to always include, regardless of team activity. |
| `quay_images` | no | `["rosalindfranklininstitute/mib-container"]` | Public Quay.io images to track. Empty array skips Quay entirely. |

**To skip a source entirely**: set string fields to `""` and lists to `[]`. The poller detects empty configuration and skips silently.

Commit and push your `config.json`.

## 3. Enable the wiki

GitHub Actions can push to the wiki only if the wiki has already been initialised.

1. In your repo, go to **Settings** → **Features** → tick **Wikis** if it isn't already.
2. Click the **Wiki** tab in the top navigation.
3. Click **Create the first page**. Any title and content works — a one-line "Home" page is fine. Save.

Without this manual first page, the workflow's push to the wiki will fail with `remote: repository not found` or a similar 404 the first time.

## 4. (Optional) YouTube API key

Skip this section if `youtube_handle` is empty in your config.

The YouTube Data API v3 is free for our use case (~50 quota units per poll; free tier allows 10,000/day).

**a. Sign in to Google Cloud Console**. Go to <https://console.cloud.google.com/>. Any Google account works — Gmail, Workspace, or an institutional Google account. No credit card required for the free tier.

**b. Create a project**. Top navbar → project dropdown → **New Project** → give it a name (e.g. `impact-tracker`) → **Create**. Wait a few seconds; select the new project in the dropdown.

**c. Enable the API**. Go to <https://console.cloud.google.com/apis/library/youtube.googleapis.com> (make sure your new project is selected in the top bar) → **Enable**.

**d. Create an API key**. Go to **APIs & Services** → **Credentials** → **+ Create Credentials** → **API key**. In the dialog that appears:

- **Name**: something descriptive (e.g. `impact-tracker-youtube`).
- **Select API restrictions** dropdown: tick only **YouTube Data API v3**. (If the dropdown is empty, step (c) didn't take effect — re-check the project is selected and the API is enabled.)
- **Authenticate API calls through a service account**: leave **unticked**. (That's only for Vertex AI / Gemini.)
- **Application restrictions**: leave **None**. (Actions runners have variable IPs; IP restriction would break scheduling.)

Click **Create**. The next dialog shows the actual key string starting with `AIzaSy...`. Copy it now — you'll paste it in the next step.

## 5. Add the API key as a repo secret

Even if you're not using YouTube, no secrets are strictly required for the workflow to run — GitHub provides `GITHUB_TOKEN` automatically. If you are using YouTube:

1. Go to your repo → **Settings** → **Secrets and variables** → **Actions**.
2. Click **New repository secret**.
3. **Name**: `YOUTUBE_API_KEY` (exact spelling — the workflow reads this name).
4. **Secret**: paste the key from step 4d.
5. **Add secret**.

## 6. First run

1. **Actions** tab → in the sidebar select **Daily impact poll** → **Run workflow** → **main** → **Run workflow**.
2. Wait ~5 minutes. The run should end green with two commits and a wiki push.
3. Open the **Wiki** tab → click **Impact**. You should see totals, per-source tables, and a "Team activity" line.

## Ongoing

- Runs automatically every day at **06:13 UTC**. Change the cron in `.github/workflows/impact.yml` if you want a different time. (GitHub Actions cron drifts — offset from the top of the hour for reliability.)
- To trigger an extra run at any time: Actions → Daily impact poll → Run workflow.
- To change what's tracked: edit `config.json`, commit, push. The next run picks it up.
- The workflow commits `data/history.json` to your repo each run — if you're working locally, `git pull --rebase` before pushing your own changes, or set `git config pull.rebase true` once so it happens automatically.

## Troubleshooting

**"Zenodo probe: HTTP 400 — Page size cannot be greater than 25"**: this means unauthenticated Zenodo. The scripts already cap at 25 — this shouldn't happen with current code. If it does, check you're on the latest `main`.

**"Quay: HTTP 400 — X-Requested-With header"**: fixed in current code by sending that header. If it recurs, Quay changed their WAF; open an issue.

**"YouTube: 403 quota exceeded"**: unlikely (~50 units per poll of 10k daily), but if you're polling many videos daily, request a quota increase in Google Cloud Console.

**Team commits missing**: the `search/commits` endpoint needs an authenticated request. `GITHUB_TOKEN` provided by the runner is enough. If you're running locally, `export GITHUB_TOKEN=ghp_...`.

**Wiki not updating**: check step 3 — the wiki must have been initialised with at least one page manually before Actions can push.

**Scheduled run didn't fire**: GitHub Actions cron can silently drop runs during peak load. Offset the minute to something unusual (e.g. `13 6 * * *` for 06:13 UTC), which we already do. If it still misses, try `47 6 * * *`.

## What runs where

- `scripts/poll_impact.py` — fetches data from all configured sources, appends to `data/history.json`.
- `scripts/render_wiki.py` — reads `data/history.json`, writes `wiki_output/Impact.md`.
- `.github/workflows/impact.yml` — runs both scripts daily, commits `history.json` to the repo, pushes `Impact.md` to the wiki.
- `config.json` — the only file you routinely edit.
