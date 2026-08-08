# 引書店 Discord Bot

Discord bot and podcast metadata importer for the 引書店 podcast.

## Setup

1. Create a virtual environment with Python 3.12.
2. Install the package:

```bash
pip install -e .
```

3. Copy `.env.example` to `.env` and fill in `DISCORD_TOKEN` and `PODCAST_RSS_URL`.
4. Run the bot:

```bash
reference-bot
```

## Current Discord Conversation

See [Discord user guide](docs/discord-user-guide.md) for a short user-facing explanation.

- Send the bot a direct message, or mention it in a server and ask a natural-language question such as `@引書店機器人 375集在講什麼`.
- Slash commands are intentionally removed.
- Enable **Message Content Intent** for the bot in the Discord Developer Portal.

## RSS Sync

Sync podcast episode metadata from the configured RSS feed into SQLite:

```bash
reference-sync-rss
```

The default database path is `data/episodes.sqlite3`. You can override it with `DATABASE_PATH` in `.env`.

Run the automated import pipeline:

```bash
reference-run-pipeline --limit 1
```

The pipeline runs RSS sync, downloads pending audio, transcribes downloaded audio with MacWhisper, exports Obsidian transcript notes, marks exported notes as indexed, and indexes transcript chunks for search. Use `--download-limit`, `--transcribe-limit`, and `--export-limit` to tune each stage independently.

To use OpenAI direct transcription and OpenAI structured summaries:

```bash
reference-run-pipeline --limit 1 --transcription-provider openai --openai-summary
```

This uses `ffmpeg` to split long audio into small M4A chunks for OpenAI's audio transcription API, then exports a transcript note and an episode summary note with `Corrections` and `Feedback Log` sections for later human review. The splitter uses `FFMPEG_BIN` when set, then `ffmpeg` from `PATH`, then the bundled `imageio-ffmpeg` binary as a fallback.

Run the production refresh command used by scheduled automation:

```bash
reference-refresh-corpus --limit 3
```

This syncs RSS, downloads and transcribes pending formal episodes with OpenAI, exports transcript and summary notes, deletes downloaded audio after successful transcription, rebuilds book/concept indexes and the concept map, then runs a data-only healthcheck.

The GitHub Actions workflow `.github/workflows/podcast-refresh.yml` runs this command daily and can also be triggered manually. When `data/episodes.sqlite3` changes, the workflow commits and pushes the refreshed database back to the repository so the deployed bot can be rebuilt from the updated corpus. Configure these repository secrets:

- `PODCAST_RSS_URL`
- `OPENAI_API_KEY`

To let this Mac produce and deploy new corpus updates locally without manual pushes, see [Local Automation](docs/local-automation.md). The local job runs `reference-local-refresh-deploy`, commits `data/episodes.sqlite3`, pushes to GitHub, and lets the cloud service redeploy from that push.

List the latest imported episodes:

```bash
reference-list-episodes --limit 10
```

List episodes that have an audio URL but have not been downloaded yet:

```bash
reference-list-downloads --limit 10
```

Download pending audio files:

```bash
reference-download-audio --limit 1 --audio-dir data/audio
```

List downloaded episodes that are waiting for transcription:

```bash
reference-list-transcriptions --limit 10
```

Transcribe downloaded audio with the MacWhisper CLI:

```bash
reference-transcribe-audio --limit 1 --transcripts-dir data/transcripts
```

MacWhisper 13.20 or newer includes the `mw` command-line tool. The bot uses `mw` from `PATH` when available, then falls back to `/Applications/MacWhisper.app/Contents/MacOS/mw`. It runs `mw transcribe AUDIO_FILE` and saves stdout as a transcript file. You can override the executable and model with `MACWHISPER_BIN`, `MACWHISPER_MODEL`, `--mw-bin`, or `--model`.

MacWhisper's current CLI prints transcript text only. Generated transcript notes are marked with `transcript_has_timestamps: "false"` until a timestamp-capable export path is added.

Shared transcript policy: podcast ASR may still use OpenAI direct transcription when quality is better for episode terminology, but transcript polishing follows the shared Traditional Chinese transcript agent rules: faithful cleanup, Taiwan Traditional Chinese, readable punctuation and paragraphs, removable non-semantic filler, no summary or rewrite. General standalone audio/video files should be processed in `/Users/marctsai/Documents/音檔轉完美正體中文逐字稿機器人` first.

Import an existing transcript exported from MacWhisper:

```bash
reference-import-transcript --episode-guid EPISODE_GUID --transcript-path /path/to/transcript.txt
```

Delete the downloaded audio after a transcript is imported:

```bash
reference-import-transcript --episode-guid EPISODE_GUID --transcript-path /path/to/transcript.txt --delete-audio
```

Export imported transcripts to Obsidian transcript notes:

```bash
reference-export-transcripts --limit 10
```

The default transcript note folder is `Inbox/Podcast Import/transcripts`, so generated notes stay in a bot-managed import area instead of mixing directly into personal long-term notes. You can override it with `OBSIDIAN_TRANSCRIPTS_DIR` in `.env` or `--transcripts-dir`.

Exported transcript notes are marked as `status: indexed` in YAML frontmatter and in SQLite. They are available to the bot without manual approval. A later organization step can copy or move notes into personal folders without blocking Discord search.

Index exported transcripts for search:

```bash
reference-index-transcripts --limit 10
```

Search indexed transcript chunks:

```bash
reference-search-transcripts 品質 --limit 5
```

Build concept clusters and relationships from indexed summaries:

```bash
reference-index-concept-map --limit 100
```

Show a cross-episode concept map:

```bash
reference-map-concepts 財富 --limit 8
```

Evaluate concept-map retrieval quality:

```bash
reference-eval-concept-map --limit 8
```

Run the beta readiness check before deployment:

```bash
reference-healthcheck
```

The healthcheck verifies the SQLite database, indexed summaries, transcript chunks, book/concept indexes, concept-map coverage, the default 15-case concept-map eval threshold, and required runtime environment variables. For beta launch, the default gate is at least 50 episodes, 50 summaries, 50 transcript-indexed episodes, and at least 12/15 concept-map eval cases passing.

Generate conservative episode summaries:

```bash
reference-generate-summaries --limit 10
```

Generate OpenAI structured episode summaries:

```bash
reference-generate-openai-summaries --limit 10
```

This milestone exports transcript notes only. It does not call MacWhisper, generate episode summaries, extract book/concept indexes, or build search commands yet.

## Tests

```bash
python -m unittest discover -s tests
```

## Cloud Deployment Notes

The bot can stay online in the cloud as long as the runtime has:

- `DISCORD_TOKEN`
- `DATABASE_PATH` pointing to the deployed SQLite file
- `PODCAST_RSS_URL` if the cloud instance will also refresh RSS/pipeline data
- `OPENAI_API_KEY` enables LLM answer synthesis; without it, conversation uses the structured conservative fallback

Run `reference-healthcheck` after copying or mounting the SQLite database. Do not deploy raw audio files unless the cloud instance is responsible for transcription; the Discord query bot only needs the database and package code.
