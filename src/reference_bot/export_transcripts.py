from __future__ import annotations

import argparse
import os

from reference_bot.config import load_rss_settings
from reference_bot.obsidian import DEFAULT_TRANSCRIPTS_DIR, export_transcript_note
from reference_bot.storage import (
    list_pending_transcript_exports,
    mark_transcript_note_export_failed,
    mark_transcript_note_exported,
)


def main() -> None:
    settings = load_rss_settings()

    parser = argparse.ArgumentParser(description="Export imported transcripts to Obsidian notes.")
    parser.add_argument("--database-path", default=settings.database_path)
    parser.add_argument(
        "--transcripts-dir",
        default=os.getenv("OBSIDIAN_TRANSCRIPTS_DIR", DEFAULT_TRANSCRIPTS_DIR),
    )
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    candidates = list_pending_transcript_exports(args.database_path, limit=args.limit)
    print(f"Pending transcript exports selected: {len(candidates)}")

    for candidate in candidates:
        episode = candidate.episode
        print(f"Exporting: {episode.title}")
        try:
            note_path = export_transcript_note(candidate, args.transcripts_dir)
        except Exception as exc:
            mark_transcript_note_export_failed(args.database_path, episode.guid, str(exc))
            print(f"  failed: {exc}")
            continue

        mark_transcript_note_exported(args.database_path, episode.guid, str(note_path))
        print(f"  saved: {note_path}")


if __name__ == "__main__":
    main()
