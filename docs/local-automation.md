# Local Automation

This machine can act as the production corpus builder:

1. Run RSS refresh on a schedule.
2. Download and transcribe pending formal episodes.
3. Generate transcript notes, summary notes, book/concept indexes, and concept maps.
4. Commit `data/episodes.sqlite3`.
5. Push to GitHub.
6. Let the cloud service redeploy from the pushed commit, or call `RENDER_DEPLOY_HOOK_URL` when set.

## Requirements

The scheduled folder must be a Git checkout with a working `origin` remote and push credentials.

Required `.env` values:

```bash
PODCAST_RSS_URL=...
OPENAI_API_KEY=...
```

Optional `.env` values:

```bash
REFERENCE_REFRESH_LIMIT=3
REFERENCE_DEPLOY_REMOTE=origin
REFERENCE_DEPLOY_BRANCH=main
RENDER_DEPLOY_HOOK_URL=...
```

If Render auto-deploy is enabled for the GitHub repo, `RENDER_DEPLOY_HOOK_URL` is not needed. A normal `git push` is enough.

## Run Once

```bash
reference-local-refresh-deploy --limit 3
```

The command pulls latest changes, refreshes the corpus, commits `data/episodes.sqlite3` if it changed, pushes to GitHub, and optionally calls the Render deploy hook.

## Install Daily LaunchAgent

```bash
scripts/install_local_refresh_launchd.sh
```

Default schedule: daily at 06:10 local time.

Useful overrides:

```bash
REFERENCE_REFRESH_HOUR=7 REFERENCE_REFRESH_MINUTE=30 scripts/install_local_refresh_launchd.sh
REFERENCE_REFRESH_LIMIT=1 scripts/install_local_refresh_launchd.sh
REFERENCE_PYTHON_BIN=/path/to/python3 scripts/install_local_refresh_launchd.sh
```

Logs:

```text
data/local-refresh.log
data/local-refresh.err.log
```

Run the scheduled job immediately:

```bash
launchctl start com.marctsai.reference-bot.refresh
```

Uninstall:

```bash
scripts/uninstall_local_refresh_launchd.sh
```

## Important

Do not commit raw audio or transcript scratch files. The deployable corpus is `data/episodes.sqlite3`.
