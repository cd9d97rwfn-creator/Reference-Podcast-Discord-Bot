from __future__ import annotations

import argparse

from reference_bot.config import load_rss_settings
from reference_bot.transcript_index import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    index_transcripts,
)


def main() -> None:
    settings = load_rss_settings()

    parser = argparse.ArgumentParser(description="Index exported transcript notes for search.")
    parser.add_argument("--database-path", default=settings.database_path)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--chunk-overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
    args = parser.parse_args()

    indexed_count = index_transcripts(
        database_path=args.database_path,
        limit=args.limit,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )
    print(f"Indexed transcripts: {indexed_count}")


if __name__ == "__main__":
    main()
