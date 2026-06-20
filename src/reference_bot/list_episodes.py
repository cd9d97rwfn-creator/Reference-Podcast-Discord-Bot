from __future__ import annotations

import argparse

from reference_bot.config import load_rss_settings
from reference_bot.storage import count_episodes, list_episodes


def main() -> None:
    settings = load_rss_settings()

    parser = argparse.ArgumentParser(description="List imported podcast episodes.")
    parser.add_argument("--database-path", default=settings.database_path)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    episodes = list_episodes(args.database_path, limit=args.limit)
    total_count = count_episodes(args.database_path)

    print(f"Database: {args.database_path}")
    print(f"Total episodes: {total_count}")
    print()

    if not episodes:
        print("No episodes found. Run reference-sync-rss first.")
        return

    for index, episode in enumerate(episodes, start=1):
        has_audio = "yes" if episode.audio_url else "no"
        published_at = episode.published_at or "unknown date"
        print(f"{index}. {episode.title}")
        print(f"   published_at: {published_at}")
        print(f"   audio_url: {has_audio}")


if __name__ == "__main__":
    main()
