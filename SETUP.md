# Setup

Steps to get the stats card generating for real, both locally and in CI.

## 1. Create a Personal Access Token (PAT)

The script needs a token with access to your commit/contribution history,
including private repos (to count private commits and private LOC), stars,
followers, etc.

1. Go to **GitHub → Settings → Developer settings → Personal access tokens**.
2. You can use either type:
   - **Fine-grained token** (recommended): under *Repository access* choose
     "All repositories" (or at least all repos you want counted), and grant
     these **Repository permissions**:
     - `Contents: Read-only`
     - `Metadata: Read-only`
     And this **Account permission**:
     - `Followers: Read-only` (if offered; otherwise a classic token is
       simpler, see below)
   - **Classic token** (simplest, works reliably with the GraphQL API used
     here): scopes needed:
     - `repo` — full control of private repositories (needed to read
       private repo languages, pushed dates and contributor stats for LOC)
     - `read:user` — read profile info (follower count)
     - `read:org` (optional) — only needed if you want contributed repos
       inside orgs counted accurately

   Classic tokens are the ones documented to work with all the GraphQL
   fields used here (`contributionsCollection`, `repositoriesContributedTo`,
   etc.), so if you hit permission errors with a fine-grained token, switch
   to classic.

3. Set an expiration you're comfortable with (you'll need to rotate the
   secret when it expires — GitHub will email you beforehand).
4. Copy the token now, you won't be able to see it again.

## 2. Add it as a repository secret

1. In `AgustinGonzalez1/AgustinGonzalez1` go to **Settings → Secrets and
   variables → Actions → New repository secret**.
2. Name: `ACCESS_TOKEN`
3. Value: the token you just copied.
4. Save.

The workflow at `.github/workflows/main.yml` already reads it via
`secrets.ACCESS_TOKEN` and exposes it to `today.py` as the `ACCESS_TOKEN`
environment variable — no further wiring needed.

## 3. Enable Actions on the repo

Since this is your special `username/username` profile repo, Actions is
usually enabled by default, but double check:

**Settings → Actions → General → Actions permissions** → allow actions to
run, and under **Workflow permissions** select **"Read and write
permissions"** (required so the workflow can `git push` the updated SVGs
back to the repo).

## 4. Run it locally to test (Linux)

```bash
cd readme   # this project's folder
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Sanity check the rendering without hitting the GitHub API:
python3 today.py --mock

# Real run, against your account:
export ACCESS_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
python3 today.py
```

This writes/updates `dark_mode.svg`, `light_mode.svg`, and
`cache/loc_cache.json` + `cache/framework_cache.json` + `cache/last_stats.json`
in the project root. Open the SVGs directly in a browser to check the layout:

```bash
xdg-open dark_mode.svg
```

The first real run will be slow-ish (it scans contributor stats and
`package.json` for every repo you own **and** every repo you've committed
to elsewhere, to compute lines of code and detect frameworks). Subsequent
runs are much faster because `cache/loc_cache.json` and
`cache/framework_cache.json` both skip any repo whose `pushedAt` timestamp
hasn't changed since the last scan.

Note: because "Lines of Code" and "Most Popular" now include repos you've
committed to but don't own, both numbers can be a bit larger than before
this changed — that's intentional, it's meant to reflect all your real
code, not just your own repos.

## 5. Push to GitHub

Commit everything (including the `cache/` folder — that's what makes reruns
fast both locally and in Actions) and push to `AgustinGonzalez1/AgustinGonzalez1`
on the `main` branch. The README embeds the SVGs from that exact path, so
keep the filenames (`dark_mode.svg`, `light_mode.svg`) and branch (`main`)
as-is, or update the URLs in `README.md` if you rename anything.

## 6. Trigger the workflow

- It runs automatically every 12 hours (`cron: "0 */12 * * *"`).
- To run it on demand: **Actions tab → "Update profile stats" → Run
  workflow**.

## Troubleshooting

- **403 / rate limit errors**: the script already retries with backoff and
  sleeps until the rate-limit reset when it hits a hard limit — just let it
  run, or check the Action logs for how long it's sleeping.
- **`ACCESS_TOKEN environment variable is not set`**: the secret name in
  the repo doesn't match, or you forgot to `export ACCESS_TOKEN=...`
  locally.
- **GraphQL permission errors on `contributionsCollection` or
  `repositoriesContributedTo`**: your token is missing scopes — see step 1,
  prefer a classic token with `repo` + `read:user`.
- **Workflow runs but never pushes**: check "Workflow permissions" is set
  to "Read and write" (step 3) — otherwise `git push` fails silently
  as a permissions error in the logs.
