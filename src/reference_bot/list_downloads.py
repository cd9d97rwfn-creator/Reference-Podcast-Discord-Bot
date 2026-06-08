from __future__ import annotations

import argparse

from reference_bot.config import load_rss_settings
from reference_bot.storage import list_pending_downloads


def main() -> None:
    settings = load_rss_settings()

    parser = argparse.ArgumentParser(description="List episodes that are ready for audio download.")
    parser.add_argument("--database-path", default=settings.database_path)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    episodes = list_pending_downloads(args.database_path, limit=args.limit)

    print(f"Database: {args.database_path}")
    print(f"Pending downloads shown: {len(episodes)}")
    print()

    if not episodes:
        print("No pending downloads found.")
        return

    for index, episode in enumerate(episodes, start=1):
        published_at = episode.published_at or "unknown date"
        print(f"{index}. {episode.title}")
        print(f"   published_at: {published_at}")
        print(f"   audio_url: {episode.audio_url}")


if __name__ == "__main__":
    main()
