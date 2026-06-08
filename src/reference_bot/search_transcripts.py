from __future__ import annotations

import argparse

from reference_bot.config import load_rss_settings
from reference_bot.storage import search_transcript_chunks


def main() -> None:
    settings = load_rss_settings()

    parser = argparse.ArgumentParser(description="Search indexed transcript chunks.")
    parser.add_argument("query")
    parser.add_argument("--database-path", default=settings.database_path)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    results = search_transcript_chunks(
        database_path=args.database_path,
        query=args.query,
        limit=args.limit,
    )
    print(f"Results: {len(results)}")
    print()

    if not results:
        print("No transcript chunks matched.")
        return

    for index, result in enumerate(results, start=1):
        print(f"{index}. {result.episode.title}")
        print(f"   guid: {result.episode.guid}")
        print(f"   chunk_index: {result.chunk_index}")
        if result.obsidian_transcript_path:
            print(f"   note: {result.obsidian_transcript_path}")
        print(f"   excerpt: {_excerpt(result.chunk_text, args.query)}")


def _excerpt(text: str, query: str, radius: int = 80) -> str:
    match_index = text.lower().find(query.lower())
    if match_index < 0:
        return text[: radius * 2].strip()

    start = max(0, match_index - radius)
    end = min(len(text), match_index + len(query) + radius)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"


if __name__ == "__main__":
    main()
