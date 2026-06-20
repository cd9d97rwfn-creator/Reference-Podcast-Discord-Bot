from __future__ import annotations

import argparse
import os
import sqlite3

from reference_bot.config import load_rss_settings
from reference_bot.macwhisper import default_macwhisper_bin, transcribe_episode_audio
from reference_bot.storage import (
    initialize_database,
    list_pending_transcriptions,
    mark_transcript_imported,
    mark_transcription_failed,
)


def main() -> None:
    settings = load_rss_settings()

    parser = argparse.ArgumentParser(description="Transcribe downloaded audio with MacWhisper.")
    parser.add_argument("--database-path", default=settings.database_path)
    parser.add_argument("--transcripts-dir", default=os.getenv("TRANSCRIPTS_DIR", "data/transcripts"))
    parser.add_argument("--mw-bin", default=os.getenv("MACWHISPER_BIN", default_macwhisper_bin()))
    parser.add_argument("--model", default=os.getenv("MACWHISPER_MODEL"))
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=None)
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()

    episodes = list_pending_transcriptions(args.database_path, limit=args.limit)
    audio_paths = _audio_local_paths(args.database_path)
    print(f"Pending transcriptions selected: {len(episodes)}")

    for episode in episodes:
        print(f"Transcribing: {episode.title}")
        audio_local_path = audio_paths.get(episode.guid)
        if not audio_local_path:
            error = "Episode has no audio_local_path."
            mark_transcription_failed(args.database_path, episode.guid, error)
            print(f"  failed: {error}")
            continue

        result = transcribe_episode_audio(
            episode=episode,
            audio_local_path=audio_local_path,
            transcripts_dir=args.transcripts_dir,
            mw_bin=args.mw_bin,
            model=args.model,
            persist=args.persist,
            timeout_seconds=args.timeout_seconds,
        )

        if result.succeeded and result.transcript_path is not None:
            mark_transcript_imported(args.database_path, episode.guid, str(result.transcript_path))
            print(f"  saved: {result.transcript_path}")
            continue

        error = result.error or "Unknown transcription error."
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
