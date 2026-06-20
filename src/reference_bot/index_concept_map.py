from __future__ import annotations

import argparse

from reference_bot.concept_map import index_concept_map
from reference_bot.config import load_rss_settings


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    settings = load_rss_settings()

    parser = argparse.ArgumentParser(description="Build concept clusters and relationships.")
    parser.add_argument("--database-path", default=settings.database_path)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    episodes, clusters, relationships = index_concept_map(args.database_path, limit=args.limit)
    print(f"Episode concept maps indexed: {episodes}")
    print(f"Concept clusters indexed: {clusters}")
    print(f"Concept relationships indexed: {relationships}")


if __name__ == "__main__":
    main()
