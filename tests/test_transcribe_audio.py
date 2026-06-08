from __future__ import annotations

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
from reference_bot.macwhisper import MacWhisperTranscriptionResult
from reference_bot.storage import mark_audio_downloaded, upsert_episodes
from reference_bot.transcribe_audio import main


class TranscribeAudioTests(unittest.TestCase):
    def test_transcribe_audio_marks_successful_transcript_import(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database_path = str(root / "episodes.sqlite3")
            audio_path = root / "episode.mp3"
            transcript_path = root / "transcripts" / "episode.txt"
            audio_path.write_bytes(b"fake audio")
            transcript_path.parent.mkdir()
            transcript_path.write_text("transcript", encoding="utf-8")
            upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="episode-1",
                        title="Episode",
                        published_at="Mon, 01 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url="https://example.com/audio.mp3",
                        description=None,
                    )
                ],
            )
            mark_audio_downloaded(database_path, "episode-1", str(audio_path))

            with patch(
                "reference_bot.transcribe_audio.load_rss_settings",
                return_value=RssSettings(
                    podcast_rss_url="https://example.com/feed.xml",
                    database_path=database_path,
                ),
            ):
                with patch(
                    "reference_bot.transcribe_audio.transcribe_episode_audio",
                    return_value=MacWhisperTranscriptionResult(
                        episode=Episode(
                            guid="episode-1",
                            title="Episode",
                            published_at=None,
                            episode_url=None,
                            audio_url=None,
                            description=None,
                        ),
                        transcript_path=transcript_path,
                        error=None,
                    ),
                ) as transcribe:
                    with patch(
                        "sys.argv",
                        [
                            "reference-transcribe-audio",
                            "--transcripts-dir",
                            str(root / "transcripts"),
                            "--mw-bin",
                            "/usr/local/bin/mw",
                            "--model",
                            "whisperkit:openai_whisper-small",
                            "--persist",
                            "--limit",
                            "1",
                        ],
                    ):
                        with redirect_stdout(StringIO()):
                            main()

            transcribe.assert_called_once()
            call_kwargs = transcribe.call_args.kwargs
            self.assertEqual(call_kwargs["audio_local_path"], str(audio_path))
            self.assertEqual(call_kwargs["mw_bin"], "/usr/local/bin/mw")
            self.assertEqual(call_kwargs["model"], "whisperkit:openai_whisper-small")
            self.assertTrue(call_kwargs["persist"])

            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    """
                    SELECT transcript_local_path, transcribed_at, transcription_error
                    FROM episodes
                    WHERE guid = ?
                    """,
                    ("episode-1",),
                ).fetchone()

            self.assertEqual(row[0], str(transcript_path))
            self.assertIsNotNone(row[1])
            self.assertIsNone(row[2])


if __name__ == "__main__":
    unittest.main()
