# Setup

## One-time steps

**1. Create the repo.**

On GitHub, create `ccp-volume-em/impact-tracker` (public is fine — nothing sensitive is committed). Do not initialize with a README; you'll push these files in step 3.

**2. Enable the wiki.**

Repo → Settings → Features → tick **Wikis**. Then click the **Wiki** tab and create the very first page (call it `Home`, any content). This is required because you cannot `git push` to an uninitialized wiki. After the first workflow run, the `Impact` page appears alongside `Home`.

**3. Push this project.**

```bash
cd impact-tracker
git init
git add .
git commit -m "Initial impact tracker"
git branch -M main
git remote add origin git@github.com:ccp-volume-em/impact-tracker.git
git push -u origin main
```

**4. (Optional) Add the YouTube API key.**

Get a free key: <https://console.cloud.google.com/apis/credentials>

- Create Credentials → API key
- APIs & Services → Library → search "YouTube Data API v3" → Enable
- (Recommended) Restrict the key to just the YouTube Data API v3

Then in the repo: Settings → Secrets and variables → Actions → New repository secret. Name: `YOUTUBE_API_KEY`. Value: the key.

Without this secret the workflow still runs — YouTube is simply skipped.

**5. Verify.**

Repo → Actions → **Weekly impact poll** → **Run workflow**. First run should:

- Commit `data/history.json` with the first snapshot
- Push `Impact.md` to the wiki

Open the **Wiki** tab and check the `Impact` page. Trends chart appears once you have two or more polls.

## Ongoing

- Runs automatically every Monday at 08:00 UTC.
- To force an extra run: Actions → Weekly impact poll → Run workflow.
- To change cadence, edit the `cron:` line in `.github/workflows/impact.yml`.

## Adding sources later

- **Quay.io** container pulls: extendable — the poller has room for a `poll_quay()` function. Public API: `https://quay.io/api/v1/repository/<org>/<image>` returns pull counts.
- **Squarespace analytics**: needs the Squarespace Analytics API (Business plan or above); if you have that, an API key can be added the same way as `YOUTUBE_API_KEY`.
- **LinkedIn**: no useful public engagement API; would require manual monthly entry.
