from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_bot.config import RssSettings
from reference_bot.episodes import Episode
from reference_bot.import_transcript import main
from reference_bot.storage import mark_audio_downloaded, upsert_episodes


class ImportTranscriptTests(unittest.TestCase):
    def test_import_transcript_updates_episode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database_path = str(root / "episodes.sqlite3")
            transcript_path = root / "transcript.txt"
            transcript_path.write_text("hello transcript", encoding="utf-8")
            upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="episode-1",
                        title="Episode",
                        published_at=None,
                        episode_url=None,
                        audio_url="https://example.com/audio.mp3",
                        description=None,
                    )
                ],
            )

            with patch(
                "reference_bot.import_transcript.load_rss_settings",
                return_value=RssSettings(
                    podcast_rss_url="https://example.com/feed.xml",
                    database_path=database_path,
                ),
            ):
                with patch(
                    "sys.argv",
                    [
                        "reference-import-transcript",
                        "--episode-guid",
                        "episode-1",
                        "--transcript-path",
                        str(transcript_path),
                    ],
                ):
                    with redirect_stdout(StringIO()):
                        main()

            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    "SELECT transcript_local_path, transcribed_at FROM episodes WHERE guid = ?",
                    ("episode-1",),
                ).fetchone()

            self.assertEqual(row[0], str(transcript_path))
            self.assertIsNotNone(row[1])

    def test_import_transcript_exits_for_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")

            with patch(
                "reference_bot.import_transcript.load_rss_settings",
                return_value=RssSettings(
                    podcast_rss_url="https://example.com/feed.xml",
                    database_path=database_path,
                ),
            ):
                with patch(
                    "sys.argv",
                    [
                        "reference-import-transcript",
                        "--episode-guid",
                        "episode-1",
                        "--transcript-path",
                        str(Path(temporary_directory) / "missing.txt"),
                    ],
                ):
                    with redirect_stderr(StringIO()):
                        with self.assertRaises(SystemExit) as context:
                            main()

            self.assertEqual(context.exception.code, 1)

    def test_import_transcript_deletes_audio_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database_path = str(root / "episodes.sqlite3")
            transcript_path = root / "transcript.txt"
            audio_path = root / "audio.mp3"
            transcript_path.write_text("hello transcript", encoding="utf-8")
            audio_path.write_bytes(b"fake audio")
            upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="episode-1",
                        title="Episode",
                        published_at=None,
                        episode_url=None,
                        audio_url="https://example.com/audio.mp3",
                        description=None,
                    )
                ],
            )
            mark_audio_downloaded(database_path, "episode-1", str(audio_path))

            with patch(
                "reference_bot.import_transcript.load_rss_settings",
                return_value=RssSettings(
                    podcast_rss_url="https://example.com/feed.xml",
                    database_path=database_path,
                ),
            ):
                with patch(
                    "sys.argv",
                    [
                        "reference-import-transcript",
                        "--episode-guid",
                        "episode-1",
                        "--transcript-path",
                        str(transcript_path),
                        "--delete-audio",
                    ],
                ):
                    with redirect_stdout(StringIO()):
                        main()

            self.assertFalse(audio_path.exists())
            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    """
                    SELECT transcript_local_path, audio_deleted_at, audio_delete_error
                    FROM episodes
                    WHERE guid = ?
                    """,
                    ("episode-1",),
                ).fetchone()

            self.assertEqual(row[0], str(transcript_path))
            self.assertIsNotNone(row[1])
            self.assertIsNone(row[2])
