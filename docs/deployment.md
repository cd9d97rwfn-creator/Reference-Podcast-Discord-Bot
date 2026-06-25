# Cloud Deployment

The beta cloud runtime only needs the package code, `data/episodes.sqlite3`, and environment variables. Do not deploy raw audio files.

## Readiness Gate

Run this locally before deploying:

```bash
reference-healthcheck
```

Current beta target:

- 50+ podcast episodes in SQLite
- 50+ structured summaries
- 50+ transcript-indexed episodes
- 12/15 or better concept-map eval pass rate
- `DISCORD_TOKEN` set in the target environment

## Docker Build

Build the bot image:

```bash
docker build -t reference-discord-bot .
```

Run it locally with environment variables:

```bash
docker run --rm \
  --env DISCORD_TOKEN="$DISCORD_TOKEN" \
  --env DISCORD_GUILD_ID="$DISCORD_GUILD_ID" \
  --env PODCAST_RSS_URL="$PODCAST_RSS_URL" \
  --env OPENAI_API_KEY="$OPENAI_API_KEY" \
  reference-discord-bot
```

If `/ask` should work without LLM synthesis, omit `OPENAI_API_KEY`; the bot will use the structured conservative fallback.

## Files Included

The Docker image includes:

- `src/`
- `pyproject.toml`
- `README.md`
- `data/episodes.sqlite3`

The Docker image excludes:

- `.env`
- `data/audio/`
- `data/transcripts/`
- logs and PID files
- Obsidian import folders
- test caches and Python bytecode

## Cloud Runtime

Use a worker/background service, not a web service. The start command is:

```bash
reference-bot
```

Set these environment variables in the cloud dashboard:

- `DISCORD_TOKEN`
- `DATABASE_PATH=/app/data/episodes.sqlite3`
- `DISCORD_GUILD_ID` for faster slash-command sync during beta
- `PODCAST_RSS_URL` if the cloud service will later run refresh jobs
- `OPENAI_API_KEY` only if LLM synthesis is enabled

After deployment, check logs for:

```text
Synced slash commands
```

Then test in Discord:

```text
/ping
/ask 財富或資產累積相關的集數
```

## Add the Bot to the 引書店 Discord

In the Discord Developer Portal:

1. Open the bot application.
2. Copy the Application ID.
3. Create an invite URL with these OAuth2 scopes:
   - `bot`
   - `applications.commands`
4. Use a minimal bot permission set:
   - Send Messages
   - View Channels, if the server does not grant it through existing roles
5. Open the invite URL while logged into a Discord account that can manage the 引書店 server.
6. Select the 引書店 Discord server and authorize the bot.

Invite URL template:

```text
https://discord.com/oauth2/authorize?client_id=YOUR_APPLICATION_ID&permissions=2048&integration_type=0&scope=bot+applications.commands
```

Replace `YOUR_APPLICATION_ID` with the application ID from Discord Developer Portal.

For beta testing, set `DISCORD_GUILD_ID` to the 引書店 server ID in the cloud environment. This makes slash command sync faster and keeps the command rollout scoped to that server while testing.

## Scheduled Corpus Refresh

The bot runtime should not depend on manual local pushes for new episodes. GitHub Actions owns the refresh loop:

1. `.github/workflows/podcast-refresh.yml` runs daily at 05:30 Asia/Taipei and can be triggered manually.
2. The workflow runs `reference-refresh-corpus --limit 3`.
3. The command syncs RSS, downloads pending formal episodes, transcribes with OpenAI, exports transcript and summary notes, rebuilds indexes, and deletes downloaded audio after successful transcription.
4. If `data/episodes.sqlite3` changed, the workflow commits and pushes it back to the repository.
5. The cloud deployment should rebuild/redeploy from that push.

Set these GitHub repository secrets:

- `PODCAST_RSS_URL`
- `OPENAI_API_KEY`

Keep these files out of git:

- `data/audio/`
- `data/transcripts/`
- `.openai-audio-chunks/`
- `.env`

Only `data/episodes.sqlite3` is committed as the deployed query corpus.

## Local Scheduled Refresh

If this Mac should be the corpus builder, use `reference-local-refresh-deploy` instead of relying on manual pushes:

```bash
reference-local-refresh-deploy --limit 3
```

That command refreshes the corpus, commits `data/episodes.sqlite3`, pushes to GitHub, and optionally calls `RENDER_DEPLOY_HOOK_URL`.

Install the daily LaunchAgent:

```bash
scripts/install_local_refresh_launchd.sh
```

See [Local Automation](local-automation.md) for logs, schedule overrides, and uninstall instructions.
