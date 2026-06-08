from __future__ import annotations

import argparse

from reference_bot.concept_map import index_concept_map
from reference_bot.concept_map_eval import evaluate_concept_map, format_eval_results
from reference_bot.config import load_rss_settings


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    settings = load_rss_settings()

    parser = argparse.ArgumentParser(description="Evaluate concept-map retrieval quality.")
    parser.add_argument("--database-path", default=settings.database_path)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--index-limit", type=int, default=100)
    parser.add_argument("--skip-reindex", action="store_true")
    args = parser.parse_args()

    if not args.skip_reindex:
        episodes, clusters, relationships = index_concept_map(
            args.database_path,
            limit=args.index_limit,
        )
        print(
            "Indexed concept map: "
            f"episodes={episodes} clusters={clusters} relationships={relationships}"
        )
        print()

    results = evaluate_concept_map(args.database_path, limit=args.limit)
    print(format_eval_results(results))


if __name__ == "__main__":
    main()
