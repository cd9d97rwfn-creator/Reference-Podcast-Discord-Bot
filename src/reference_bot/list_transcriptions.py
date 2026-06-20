from __future__ import annotations

import argparse
import sqlite3

from reference_bot.config import load_rss_settings
from reference_bot.storage import initialize_database, list_pending_transcriptions


def main() -> None:
    settings = load_rss_settings()

    parser = argparse.ArgumentParser(description="List downloaded episodes waiting for transcription.")
    parser.add_argument("--database-path", default=settings.database_path)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    episodes = list_pending_transcriptions(args.database_path, limit=args.limit)

    print(f"Database: {args.database_path}")
    print(f"Pending transcriptions shown: {len(episodes)}")
    print()

    if not episodes:
        print("No pending transcriptions found.")
        return

    local_paths = _audio_local_paths(args.database_path)
    for index, episode in enumerate(episodes, start=1):
        published_at = episode.published_at or "unknown date"
        print(f"{index}. {episode.title}")
        print(f"   guid: {episode.guid}")
        print(f"   published_at: {published_at}")
        print(f"   audio_local_path: {local_paths.get(episode.guid, 'unknown')}")


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
