from __future__ import annotations

import argparse

from reference_bot.config import load_rss_settings
from reference_bot.summary import DEFAULT_EPISODE_SUMMARIES_DIR, generate_episode_summaries


def main() -> None:
    settings = load_rss_settings()

    parser = argparse.ArgumentParser(description="Generate conservative episode summaries.")
    parser.add_argument("--database-path", default=settings.database_path)
    parser.add_argument("--summaries-dir", default=DEFAULT_EPISODE_SUMMARIES_DIR)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    generated_count = generate_episode_summaries(
        database_path=args.database_path,
        summaries_dir=args.summaries_dir,
        limit=args.limit,
    )
    print(f"Generated episode summaries: {generated_count}")


if __name__ == "__main__":
    main()
