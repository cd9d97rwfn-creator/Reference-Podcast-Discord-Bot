from __future__ import annotations

import argparse
import os
import sqlite3

from reference_bot.config import load_rss_settings
from reference_bot.openai_transcription import (
    DEFAULT_OPENAI_TRANSCRIPTION_MODEL,
    DEFAULT_TRANSCRIPTION_PROMPT,
    transcribe_episode_audio_openai,
)
from reference_bot.storage import (
    initialize_database,
    list_pending_transcriptions,
    mark_transcript_imported,
    mark_transcription_failed,
)


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    settings = load_rss_settings()

    parser = argparse.ArgumentParser(description="Transcribe downloaded audio with OpenAI.")
    parser.add_argument("--database-path", default=settings.database_path)
    parser.add_argument("--transcripts-dir", default=os.getenv("TRANSCRIPTS_DIR", "data/transcripts"))
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--model", default=os.getenv("OPENAI_TRANSCRIBE_MODEL", DEFAULT_OPENAI_TRANSCRIPTION_MODEL))
    parser.add_argument("--language", default=os.getenv("OPENAI_TRANSCRIBE_LANGUAGE", "zh"))
    parser.add_argument("--prompt", default=os.getenv("OPENAI_TRANSCRIBE_PROMPT", DEFAULT_TRANSCRIPTION_PROMPT))
    parser.add_argument("--chunk-seconds", type=int, default=int(os.getenv("OPENAI_TRANSCRIBE_CHUNK_SECONDS", "240")))
    parser.add_argument("--bitrate", default=os.getenv("OPENAI_TRANSCRIBE_BITRATE", "24k"))
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--chunks-dir", default=os.getenv("OPENAI_AUDIO_CHUNKS_DIR", ".openai-audio-chunks"))
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required. Add it to your .env file.")

    audio_paths = _audio_local_paths(args.database_path)
    episodes = list_pending_transcriptions(args.database_path, limit=args.limit)
    print(f"Pending OpenAI transcriptions selected: {len(episodes)}")

    for episode in episodes:
        audio_local_path = audio_paths.get(episode.guid)
        if not audio_local_path:
            mark_transcription_failed(args.database_path, episode.guid, "Episode has no audio_local_path.")
            print(f"Skipping {episode.title}: no audio_local_path")
            continue

        print(f"Transcribing with OpenAI: {episode.title}")
        result = transcribe_episode_audio_openai(
            episode=episode,
            audio_local_path=audio_local_path,
            transcripts_dir=args.transcripts_dir,
            api_key=api_key,
            model=args.model,
            language=args.language,
            prompt=args.prompt,
            chunk_seconds=args.chunk_seconds,
            bitrate=args.bitrate,
            timeout_seconds=args.timeout_seconds,
            chunks_dir=args.chunks_dir,
        )
        if result.succeeded and result.transcript_path is not None:
            mark_transcript_imported(args.database_path, episode.guid, str(result.transcript_path))
            print(f"  saved: {result.transcript_path}")
            continue

        error = result.error or "Unknown OpenAI transcription error."
        mark_transcription_failed(args.database_path, episode.guid, error)
        print(f"  failed: {error}")


def _audio_local_paths(database_path: str) -> dict[str, str]:
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT guid, audio_local_path
            FROM episodes
            WHERE audio_local_path IS NOT NULL
                AND TRIM(audio_local_path) != ''
            """
        ).fetchall()

    return {row[0]: row[1] for row in rows}


if __name__ == "__main__":
    main()
