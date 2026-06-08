from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_bot.config import RssSettings
from reference_bot.episodes import Episode
from reference_bot.export_transcripts import main
from reference_bot.storage import mark_transcript_imported, upsert_episodes


class ExportTranscriptsTests(unittest.TestCase):
    def test_export_transcripts_writes_note_and_marks_episode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database_path = str(root / "episodes.sqlite3")
            transcript_path = root / "transcript.txt"
            output_dir = root / "Podcast" / "引書店" / "transcripts"
            transcript_path.write_text("[00:01] transcript text", encoding="utf-8")
            upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="episode-1",
                        title="Episode",
                        published_at="Mon, 01 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url=None,
                        description=None,
                    )
                ],
            )
            mark_transcript_imported(database_path, "episode-1", str(transcript_path))

            with patch(
                "reference_bot.export_transcripts.load_rss_settings",
                return_value=RssSettings(
                    podcast_rss_url="https://example.com/feed.xml",
                    database_path=database_path,
                ),
            ):
                with patch(
                    "sys.argv",
                    [
                        "reference-export-transcripts",
                        "--transcripts-dir",
                        str(output_dir),
                        "--limit",
                        "1",
                    ],
                ):
                    with redirect_stdout(StringIO()):
                        main()

            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    """
                    SELECT
                        obsidian_transcript_path,
                        obsidian_transcript_status,
                        obsidian_transcript_exported_at
                    FROM episodes
                    WHERE guid = ?
                    """,
                    ("episode-1",),
                ).fetchone()

            self.assertIsNotNone(row[0])
            self.assertEqual(row[1], "indexed")
            self.assertIsNotNone(row[2])
            note_path = Path(row[0])
            self.assertTrue(note_path.is_file())
            self.assertIn("[00:01] transcript text", note_path.read_text(encoding="utf-8"))

    def test_export_transcripts_defaults_to_inbox_import_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database_path = str(root / "episodes.sqlite3")
            transcript_path = root / "transcript.txt"
            transcript_path.write_text("indexed transcript", encoding="utf-8")
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

            with patch(
                "reference_bot.export_transcripts.load_rss_settings",
                return_value=RssSettings(
                    podcast_rss_url="https://example.com/feed.xml",
                    database_path=database_path,
                ),
            ):
                with patch.dict("os.environ", {}, clear=True):
                    current_directory = Path.cwd()
                    try:
                        os.chdir(root)
                        with patch("sys.argv", ["reference-export-transcripts", "--limit", "1"]):
                            with redirect_stdout(StringIO()):
                                main()
                    finally:
                        os.chdir(current_directory)

            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    "SELECT obsidian_transcript_path FROM episodes WHERE guid = ?",
                    ("episode-1",),
                ).fetchone()

            self.assertIn("Inbox/Podcast Import/transcripts", row[0])


if __name__ == "__main__":
    unittest.main()
