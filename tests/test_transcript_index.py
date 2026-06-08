from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_bot.episodes import Episode
from reference_bot.storage import (
    mark_transcript_imported,
    mark_transcript_note_exported,
    search_transcript_chunks,
    upsert_episodes,
)
from reference_bot.transcript_index import index_transcripts, transcript_chunks


class TranscriptIndexTests(unittest.TestCase):
    def test_transcript_chunks_splits_text_with_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            transcript_path = root / "transcript.txt"
            transcript_path.write_text("abcdefghijklmnopqrstuvwxyz", encoding="utf-8")

            chunks = transcript_chunks(
                transcript=_indexed_transcript(str(transcript_path)),
                chunk_size=10,
                chunk_overlap=2,
            )

            self.assertEqual(chunks, ["abcdefghij", "ijklmnopqr", "qrstuvwxyz"])

    def test_transcript_chunks_preserves_paragraph_breaks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            transcript_path = Path(temporary_directory) / "transcript.txt"
            transcript_path.write_text("第一段。\n\n第二段。\n第三段。", encoding="utf-8")

            chunks = transcript_chunks(
                transcript=_indexed_transcript(str(transcript_path)),
                chunk_size=50,
                chunk_overlap=2,
            )

            self.assertIn("第一段。\n\n第二段。", chunks[0])

    def test_index_transcripts_stores_chunks_for_search(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database_path = str(root / "episodes.sqlite3")
            transcript_path = root / "transcript.txt"
            transcript_path.write_text("品質管理讓系統更穩定。教練創造對話空間。", encoding="utf-8")
            upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="episode-1",
                        title="Episode",
                        published_at=None,
                        episode_url=None,
                        audio_url=None,
                        description=None,
                    )
                ],
            )
            mark_transcript_imported(database_path, "episode-1", str(transcript_path))
            mark_transcript_note_exported(
                database_path,
                "episode-1",
                "Inbox/Podcast Import/transcripts/episode.md",
            )

            indexed_count = index_transcripts(database_path, limit=10, chunk_size=12, chunk_overlap=2)
            results = search_transcript_chunks(database_path, "教練", limit=10)

            self.assertEqual(indexed_count, 1)
            self.assertEqual(len(results), 1)
            self.assertIn("教練", results[0].chunk_text)

            with sqlite3.connect(database_path) as connection:
                chunk_count = connection.execute("SELECT COUNT(*) FROM transcript_chunks").fetchone()[0]

            self.assertGreater(chunk_count, 1)


def _indexed_transcript(transcript_path: str):
    from reference_bot.episodes import IndexedTranscript

    return IndexedTranscript(
        episode=Episode(
            guid="episode-1",
            title="Episode",
            published_at=None,
            episode_url=None,
            audio_url=None,
            description=None,
        ),
        transcript_local_path=transcript_path,
        obsidian_transcript_path=None,
    )


if __name__ == "__main__":
    unittest.main()
