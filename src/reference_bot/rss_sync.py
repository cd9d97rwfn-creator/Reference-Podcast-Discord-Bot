from __future__ import annotations

import argparse
import logging

from reference_bot.config import load_rss_settings
from reference_bot.rss import parse_feed
from reference_bot.storage import count_episodes, upsert_episodes


LOGGER = logging.getLogger(__name__)


def sync_rss(feed_url: str, database_path: str) -> int:
    episodes = parse_feed(feed_url)
    stored_count = upsert_episodes(database_path, episodes)
    total_count = count_episodes(database_path)
    LOGGER.info("Stored %s RSS episodes. Database now has %s episodes.", stored_count, total_count)
    return stored_count


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = load_rss_settings()

    parser = argparse.ArgumentParser(description="Sync podcast episode metadata from RSS.")
    parser.add_argument("--feed-url", default=settings.podcast_rss_url)
    parser.add_argument("--database-path", default=settings.database_path)
    args = parser.parse_args()

    sync_rss(feed_url=args.feed_url, database_path=args.database_path)


if __name__ == "__main__":
    main()
