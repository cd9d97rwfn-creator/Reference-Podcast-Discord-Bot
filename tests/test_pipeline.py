from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_bot.downloader import DownloadResult
from reference_bot.episodes import Episode
from reference_bot.macwhisper import MacWhisperTranscriptionResult
from reference_bot.pipeline import _resolved_limit, run_pipeline
from reference_bot.storage import mark_audio_downloaded, upsert_episodes


class PipelineTests(unittest.TestCase):
    def test_resolved_limit_preserves_zero(self) -> None:
        self.assertEqual(_resolved_limit(0, 5), 0)
        self.assertEqual(_resolved_limit(None, 5), 5)

    def test_run_pipeline_downloads_transcribes_and_exports_indexed_note(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database_path = str(root / "episodes.sqlite3")
            audio_path = root / "audio" / "episode.mp3"
            transcript_path = root / "transcripts" / "episode.txt"
            note_dir = root / "Inbox" / "Podcast Import" / "transcripts"
            summary_dir = root / "Inbox" / "Podcast Import" / "episodes"
            audio_path.parent.mkdir()
            transcript_path.parent.mkdir()
            audio_path.write_bytes(b"fake audio")
            transcript_path.write_text("[00:01] transcript", encoding="utf-8")
            episode = Episode(
                guid="episode-1",
                title="Episode",
                published_at="Mon, 01 Jun 2026 00:00:00 +0800",
                episode_url=None,
                audio_url="https://example.com/audio.mp3",
                description=None,
            )

            def sync_feed(feed_url: str, database_path: str) -> int:
                upsert_episodes(database_path, [episode])
                return 1

            with patch("reference_bot.pipeline.sync_rss", side_effect=sync_feed):
                with patch(
                    "reference_bot.pipeline.download_episode_audio",
                    return_value=DownloadResult(episode=episode, local_path=audio_path, error=None),
                ) as download:
                    with patch(
                        "reference_bot.pipeline.transcribe_episode_audio",
                        return_value=MacWhisperTranscriptionResult(
                            episode=episode,
                            transcript_path=transcript_path,
                            error=None,
                        ),
                    ) as transcribe:
                        result = run_pipeline(
                            feed_url="https://example.com/feed.xml",
                            database_path=database_path,
                            audio_dir=str(root / "audio"),
                            transcripts_dir=str(root / "transcripts"),
                            obsidian_transcripts_dir=str(note_dir),
                            download_limit=1,
                            transcribe_limit=1,
                            export_limit=1,
                            obsidian_episodes_dir=str(summary_dir),
                            mw_bin="mw",
                            model="whisperkit:openai_whisper-small",
                            persist=True,
                        )

            download.assert_called_once()
            transcribe.assert_called_once()
            self.assertEqual(result.rss_episodes_seen, 1)
            self.assertEqual(result.audio_downloaded, 1)
            self.assertEqual(result.audio_deleted, 0)
            self.assertEqual(result.transcribed, 1)
            self.assertEqual(result.transcript_notes_exported, 1)
            self.assertEqual(result.transcripts_indexed, 1)

            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    """
                    SELECT
                        audio_local_path,
                        transcript_local_path,
                        obsidian_transcript_path,
                        obsidian_transcript_status
                    FROM episodes
                    WHERE guid = ?
                    """,
                    ("episode-1",),
                ).fetchone()

            self.assertEqual(row[0], str(audio_path))
            self.assertEqual(row[1], str(transcript_path))
            self.assertIsNotNone(row[2])
            self.assertEqual(row[3], "indexed")
            self.assertIn("[00:01] transcript", Path(row[2]).read_text(encoding="utf-8"))

            with sqlite3.connect(database_path) as connection:
                chunk_count = connection.execute("SELECT COUNT(*) FROM transcript_chunks").fetchone()[0]
                summary_note_path = connection.execute(
                    "SELECT summary_note_path FROM episode_summaries WHERE episode_guid = ?",
                    ("episode-1",),
                ).fetchone()[0]

            self.assertEqual(chunk_count, 1)
            self.assertTrue(summary_note_path.startswith(str(summary_dir)))

    def test_run_pipeline_can_delete_audio_after_successful_transcription(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database_path = str(root / "episodes.sqlite3")
            audio_path = root / "audio" / "episode.mp3"
            transcript_path = root / "transcripts" / "episode.txt"
            note_dir = root / "Inbox" / "Podcast Import" / "transcripts"
            audio_path.parent.mkdir()
            transcript_path.parent.mkdir()
            audio_path.write_bytes(b"fake audio")
            transcript_path.write_text("transcript", encoding="utf-8")
            episode = Episode(
                guid="episode-1",
                title="Episode",
                published_at="Mon, 01 Jun 2026 00:00:00 +0800",
                episode_url=None,
                audio_url="https://example.com/audio.mp3",
                description=None,
            )

            def sync_feed(feed_url: str, database_path: str) -> int:
                upsert_episodes(database_path, [episode])
                return 1

            with patch("reference_bot.pipeline.sync_rss", side_effect=sync_feed), patch(
                "reference_bot.pipeline.download_episode_audio",
                return_value=DownloadResult(episode=episode, local_path=audio_path, error=None),
            ), patch(
                "reference_bot.pipeline.transcribe_episode_audio",
                return_value=MacWhisperTranscriptionResult(
                    episode=episode,
                    transcript_path=transcript_path,
                    error=None,
                ),
            ):
                result = run_pipeline(
                    feed_url="https://example.com/feed.xml",
                    database_path=database_path,
                    audio_dir=str(root / "audio"),
                    transcripts_dir=str(root / "transcripts"),
                    obsidian_transcripts_dir=str(note_dir),
                    download_limit=1,
                    transcribe_limit=1,
                    export_limit=1,
                    delete_audio_after_transcription=True,
                )

            self.assertEqual(result.audio_deleted, 1)
            self.assertFalse(audio_path.exists())
            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    "SELECT audio_local_path, audio_deleted_at, transcript_local_path FROM episodes WHERE guid = ?",
                    ("episode-1",),
                ).fetchone()

            self.assertEqual(row[0], str(audio_path))
            self.assertIsNotNone(row[1])
            self.assertEqual(row[2], str(transcript_path))

    def test_run_pipeline_exports_already_transcribed_episode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database_path = str(root / "episodes.sqlite3")
            audio_path = root / "audio" / "episode.mp3"
            transcript_path = root / "transcripts" / "episode.txt"
            note_dir = root / "Inbox" / "Podcast Import" / "transcripts"
            audio_path.parent.mkdir()
            transcript_path.parent.mkdir()
            audio_path.write_bytes(b"fake audio")
            transcript_path.write_text("existing transcript", encoding="utf-8")
            episode = Episode(
                guid="episode-1",
                title="Episode",
                published_at=None,
                episode_url=None,
                audio_url="https://example.com/audio.mp3",
                description=None,
            )
            upsert_episodes(database_path, [episode])
            mark_audio_downloaded(database_path, "episode-1", str(audio_path))

            with sqlite3.connect(database_path) as connection:
                connection.execute(
                    "UPDATE episodes SET transcript_local_path = ? WHERE guid = ?",
                    (str(transcript_path), "episode-1"),
                )

            with patch("reference_bot.pipeline.sync_rss", return_value=1):
                result = run_pipeline(
                    feed_url="https://example.com/feed.xml",
                    database_path=database_path,
                    audio_dir=str(root / "audio"),
                    transcripts_dir=str(root / "transcripts"),
                    obsidian_transcripts_dir=str(note_dir),
                    download_limit=1,
                    transcribe_limit=1,
                    export_limit=1,
                )

            self.assertEqual(result.audio_downloaded, 0)
            self.assertEqual(result.transcribed, 0)
            self.assertEqual(result.transcript_notes_exported, 1)
            self.assertEqual(result.transcripts_indexed, 1)

    def test_run_pipeline_can_skip_promotional_downloads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database_path = str(root / "episodes.sqlite3")
            promo = Episode(
                guid="promo",
                title="【母親節團購】優惠活動",
                published_at="Tue, 02 Jun 2026 00:00:00 +0800",
                episode_url=None,
                audio_url="https://example.com/promo.mp3",
                description=None,
            )
            formal = Episode(
                guid="formal",
                title="EP.1《正式集數》",
                published_at="Mon, 01 Jun 2026 00:00:00 +0800",
                episode_url=None,
                audio_url="https://example.com/formal.mp3",
                description=None,
            )

            def sync_feed(feed_url: str, database_path: str) -> int:
                upsert_episodes(database_path, [promo, formal])
                return 2

            with patch("reference_bot.pipeline.sync_rss", side_effect=sync_feed), patch(
                "reference_bot.pipeline.download_episode_audio",
                return_value=DownloadResult(
                    episode=formal,
                    local_path=root / "audio" / "formal.mp3",
                    error=None,
                ),
            ) as download:
                result = run_pipeline(
                    feed_url="https://example.com/feed.xml",
                    database_path=database_path,
                    audio_dir=str(root / "audio"),
                    transcripts_dir=str(root / "transcripts"),
                    obsidian_transcripts_dir=str(root / "Inbox" / "Podcast Import" / "transcripts"),
                    download_limit=1,
                    transcribe_limit=0,
                    export_limit=1,
                    skip_promotional=True,
                )

            download.assert_called_once()
            self.assertEqual(download.call_args.args[0].guid, "formal")
            self.assertEqual(result.audio_downloaded, 1)

    def test_run_pipeline_can_download_formal_episodes_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database_path = str(root / "episodes.sqlite3")
            special = Episode(
                guid="special",
                title="城市特輯：理想的工作",
                published_at="Tue, 02 Jun 2026 00:00:00 +0800",
                episode_url=None,
                audio_url="https://example.com/special.mp3",
                description=None,
            )
            formal = Episode(
                guid="formal",
                title="EP.1《正式集數》",
                published_at="Mon, 01 Jun 2026 00:00:00 +0800",
                episode_url=None,
                audio_url="https://example.com/formal.mp3",
                description=None,
            )

            def sync_feed(feed_url: str, database_path: str) -> int:
                upsert_episodes(database_path, [special, formal])
                return 2

            with patch("reference_bot.pipeline.sync_rss", side_effect=sync_feed), patch(
                "reference_bot.pipeline.download_episode_audio",
                return_value=DownloadResult(
                    episode=formal,
                    local_path=root / "audio" / "formal.mp3",
                    error=None,
                ),
            ) as download:
                result = run_pipeline(
                    feed_url="https://example.com/feed.xml",
                    database_path=database_path,
                    audio_dir=str(root / "audio"),
                    transcripts_dir=str(root / "transcripts"),
                    obsidian_transcripts_dir=str(root / "Inbox" / "Podcast Import" / "transcripts"),
                    download_limit=1,
                    transcribe_limit=0,
                    export_limit=1,
                    formal_episodes_only=True,
                )

            download.assert_called_once()
            self.assertEqual(download.call_args.args[0].guid, "formal")
            self.assertEqual(result.audio_downloaded, 1)

    def test_run_pipeline_treats_embedded_episode_number_as_formal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database_path = str(root / "episodes.sqlite3")
            special_numbered = Episode(
                guid="special-numbered",
                title="【聯名特企SP9】EP.300《正式編號特企》",
                published_at="Tue, 02 Jun 2026 00:00:00 +0800",
                episode_url=None,
                audio_url="https://example.com/special-numbered.mp3",
                description=None,
            )

            def sync_feed(feed_url: str, database_path: str) -> int:
                upsert_episodes(database_path, [special_numbered])
                return 1

            with patch("reference_bot.pipeline.sync_rss", side_effect=sync_feed), patch(
                "reference_bot.pipeline.download_episode_audio",
                return_value=DownloadResult(
                    episode=special_numbered,
                    local_path=root / "audio" / "special-numbered.mp3",
                    error=None,
                ),
            ) as download:
                result = run_pipeline(
                    feed_url="https://example.com/feed.xml",
                    database_path=database_path,
                    audio_dir=str(root / "audio"),
                    transcripts_dir=str(root / "transcripts"),
                    obsidian_transcripts_dir=str(root / "Inbox" / "Podcast Import" / "transcripts"),
                    download_limit=1,
                    transcribe_limit=0,
                    export_limit=1,
                    formal_episodes_only=True,
                )

            download.assert_called_once()
            self.assertEqual(download.call_args.args[0].guid, "special-numbered")
            self.assertEqual(result.audio_downloaded, 1)

    def test_run_pipeline_stops_transcription_batch_on_quota_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database_path = str(root / "episodes.sqlite3")
            audio_dir = root / "audio"
            audio_dir.mkdir()
            first_audio = audio_dir / "first.mp3"
            second_audio = audio_dir / "second.mp3"
            first_audio.write_bytes(b"first")
            second_audio.write_bytes(b"second")
            first = Episode(
                guid="first",
                title="EP.1《第一集》",
                published_at="Tue, 02 Jun 2026 00:00:00 +0800",
                episode_url=None,
                audio_url="https://example.com/first.mp3",
                description=None,
            )
            second = Episode(
                guid="second",
                title="EP.2《第二集》",
                published_at="Mon, 01 Jun 2026 00:00:00 +0800",
                episode_url=None,
                audio_url="https://example.com/second.mp3",
                description=None,
            )
            upsert_episodes(database_path, [first, second])
            mark_audio_downloaded(database_path, "first", str(first_audio))
            mark_audio_downloaded(database_path, "second", str(second_audio))

            with patch("reference_bot.pipeline.sync_rss", return_value=2), patch(
                "reference_bot.pipeline.transcribe_episode_audio",
                return_value=MacWhisperTranscriptionResult(
                    episode=first,
                    transcript_path=None,
                    error="You exceeded your current quota, please check your plan and billing details.",
                ),
            ) as transcribe:
                result = run_pipeline(
                    feed_url="https://example.com/feed.xml",
                    database_path=database_path,
                    audio_dir=str(audio_dir),
                    transcripts_dir=str(root / "transcripts"),
                    obsidian_transcripts_dir=str(root / "Inbox" / "Podcast Import" / "transcripts"),
                    download_limit=0,
                    transcribe_limit=2,
                    export_limit=1,
                )

            transcribe.assert_called_once()
            self.assertEqual(result.transcription_failed, 1)


if __name__ == "__main__":
    unittest.main()
