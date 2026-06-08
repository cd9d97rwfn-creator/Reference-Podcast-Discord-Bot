from __future__ import annotations

import argparse

from reference_bot.concept_index import index_summary_mentions
from reference_bot.config import load_rss_settings


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    settings = load_rss_settings()

    parser = argparse.ArgumentParser(description="Index book and concept mentions from episode summaries.")
    parser.add_argument("--database-path", default=settings.database_path)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    episodes, books, concepts = index_summary_mentions(args.database_path, limit=args.limit)
    print(f"Episode summaries indexed: {episodes}")
    print(f"Book mentions indexed: {books}")
    print(f"Concept mentions indexed: {concepts}")


if __name__ == "__main__":
    main()
