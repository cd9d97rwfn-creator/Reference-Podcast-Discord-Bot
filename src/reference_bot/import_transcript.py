from __future__ import annotations

import argparse
from pathlib import Path
import sys

from reference_bot.config import load_rss_settings
from reference_bot.storage import (
    get_audio_local_path,
    mark_audio_delete_failed,
    mark_audio_deleted,
    mark_transcript_imported,
)


def main() -> None:
    settings = load_rss_settings()

    parser = argparse.ArgumentParser(description="Import an existing transcript file for an episode.")
    parser.add_argument("--database-path", default=settings.database_path)
    parser.add_argument("--episode-guid", required=True)
    parser.add_argument("--transcript-path", required=True)
    parser.add_argument("--delete-audio", action="store_true")
    args = parser.parse_args()

    transcript_path = Path(args.transcript_path).expanduser()
    if not transcript_path.is_file():
        print(f"Transcript file does not exist: {transcript_path}", file=sys.stderr)
        raise SystemExit(1)

    updated = mark_transcript_imported(
        database_path=args.database_path,
        guid=args.episode_guid,
        transcript_local_path=str(transcript_path),
    )
    if not updated:
        print(f"Episode guid not found: {args.episode_guid}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Imported transcript for episode: {args.episode_guid}")
    print(f"Transcript path: {transcript_path}")

    if args.delete_audio:
        _delete_audio(args.database_path, args.episode_guid)


def _delete_audio(database_path: str, episode_guid: str) -> None:
    audio_local_path = get_audio_local_path(database_path, episode_guid)
    if not audio_local_path:
        error = "Episode has no audio_local_path to delete."
        mark_audio_delete_failed(database_path, episode_guid, error)
        print(f"Audio delete skipped: {error}", file=sys.stderr)
        raise SystemExit(1)

    audio_path = Path(audio_local_path)
    try:
        if audio_path.exists():
            audio_path.unlink()
        mark_audio_deleted(database_path, episode_guid)
        print(f"Deleted audio file: {audio_path}")
    except OSError as exc:
        mark_audio_delete_failed(database_path, episode_guid, str(exc))
        print(f"Failed to delete audio file: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
