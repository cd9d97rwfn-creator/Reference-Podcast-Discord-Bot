from __future__ import annotations

import argparse
from email.utils import parsedate_to_datetime
import os
import sqlite3
from pathlib import Path

from reference_bot.config import load_rss_settings
from reference_bot.episodes import Episode, IndexedTranscript, TranscribedEpisode
from reference_bot.obsidian import export_transcript_note
from reference_bot.storage import (
    initialize_database,
    mark_transcript_imported,
    mark_transcript_note_exported,
    replace_transcript_chunks,
)
from reference_bot.transcript_index import transcript_chunks
from reference_bot.transcript_polish import DEFAULT_POLISH_CHARS, DEFAULT_POLISH_MODEL, polish_transcript_file


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    settings = load_rss_settings()

    parser = argparse.ArgumentParser(description="Polish OpenAI direct transcripts for punctuation and paragraphs.")
    parser.add_argument("--database-path", default=settings.database_path)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--model", default=os.getenv("OPENAI_POLISH_MODEL", DEFAULT_POLISH_MODEL))
    parser.add_argument("--chunk-chars", type=int, default=int(os.getenv("OPENAI_POLISH_CHARS", str(DEFAULT_POLISH_CHARS))))
    parser.add_argument("--transcripts-dir", default=os.getenv("OBSIDIAN_TRANSCRIPTS_DIR", "Inbox/Podcast Import/transcripts"))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--skip-promotional", action="store_true")
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required. Add it to your .env file.")

    episodes = _openai_direct_transcripts(
        args.database_path,
        limit=args.limit,
        skip_promotional=args.skip_promotional,
    )
    print(f"OpenAI direct transcripts selected: {len(episodes)}", flush=True)
    for transcript in episodes:
        source_path = Path(transcript.transcript_local_path)
        print(f"Polishing: {transcript.episode.title}", flush=True)
        result = polish_transcript_file(
            source_path=source_path,
            api_key=api_key,
            model=args.model,
            chunk_chars=args.chunk_chars,
            overwrite=args.overwrite,
        )
        if result.chunks_polished == 0:
            print(f"  cleaned exists: {result.cleaned_path}", flush=True)
        else:
            print(f"  cleaned: {result.cleaned_path} ({result.chunks_polished} chunks)", flush=True)

        mark_transcript_imported(args.database_path, transcript.episode.guid, str(result.cleaned_path))
        transcribed = TranscribedEpisode(
            episode=transcript.episode,
            transcript_local_path=str(result.cleaned_path),
        )
        note_path = export_transcript_note(transcribed, args.transcripts_dir)
        mark_transcript_note_exported(args.database_path, transcript.episode.guid, str(note_path))

        indexed = IndexedTranscript(
            episode=transcript.episode,
            transcript_local_path=str(result.cleaned_path),
            obsidian_transcript_path=str(note_path),
        )
        chunks = transcript_chunks(indexed)
        replace_transcript_chunks(args.database_path, indexed, chunks)
        print(f"  transcript note: {note_path}", flush=True)
        print(f"  indexed chunks: {len(chunks)}", flush=True)


def _openai_direct_transcripts(
    database_path: str,
    limit: int,
    skip_promotional: bool = False,
) -> list[IndexedTranscript]:
    if limit < 1:
        raise ValueError("limit must be greater than 0.")

    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT guid, title, published_at, episode_url, audio_url, description, transcript_local_path, obsidian_transcript_path
            FROM episodes
            WHERE transcript_local_path LIKE '%openai-direct%'
                AND transcript_local_path NOT LIKE '%cleaned%'
            """,
        ).fetchall()

    transcripts = [
        IndexedTranscript(
            episode=Episode(
                guid=row[0],
                title=row[1],
                published_at=row[2],
                episode_url=row[3],
                audio_url=row[4],
                description=row[5],
            ),
            transcript_local_path=row[6],
            obsidian_transcript_path=row[7],
        )
        for row in rows
    ]
    if skip_promotional:
        transcripts = [
            transcript
            for transcript in transcripts
            if not _is_promotional_title(transcript.episode.title)
        ]
    return sorted(transcripts, key=lambda item: _episode_sort_key(item.episode.published_at), reverse=True)[
        :limit
    ]


def _is_promotional_title(title: str) -> bool:
    return any(marker in title for marker in ["團購", "報名", "活動", "超限時"])


def _episode_sort_key(published_at: str | None):
    if not published_at:
        return parsedate_to_datetime("Thu, 01 Jan 1970 00:00:00 GMT")
    try:
        return parsedate_to_datetime(published_at)
    except (TypeError, ValueError):
        return parsedate_to_datetime("Thu, 01 Jan 1970 00:00:00 GMT")


if __name__ == "__main__":
    main()
