from __future__ import annotations

import argparse

from reference_bot.concept_map import concept_map, format_concept_map
from reference_bot.config import load_rss_settings


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    settings = load_rss_settings()

    parser = argparse.ArgumentParser(description="Show a cross-episode concept map.")
    parser.add_argument("query")
    parser.add_argument("--database-path", default=settings.database_path)
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()

    result = concept_map(args.database_path, query=args.query, limit=args.limit)
    print(format_concept_map(args.database_path, result))


if __name__ == "__main__":
    main()
