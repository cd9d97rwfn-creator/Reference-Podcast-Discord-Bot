from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_bot.episodes import BookMention, ConceptMention, Episode, EpisodeSummary
from reference_bot.storage import (
    count_episodes,
    get_audio_local_path,
    initialize_database,
    list_episodes,
    list_indexed_episodes,
    list_indexed_transcripts,
    list_pending_downloads,
    list_pending_transcript_exports,
    list_pending_transcriptions,
    mark_audio_download_failed,
    mark_audio_downloaded,
    mark_audio_delete_failed,
    mark_audio_deleted,
    mark_transcript_imported,
    mark_transcript_note_export_failed,
    mark_transcript_note_exported,
    mark_transcription_failed,
    replace_transcript_chunks,
    replace_book_mentions,
    replace_concept_mentions,
    search_book_mentions,
    search_concept_mentions,
    search_transcript_chunks,
    search_episode_summaries,
    upsert_episodes,
    upsert_episode_summary,
)


class StorageTests(unittest.TestCase):
    def test_upsert_episodes_inserts_episode_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")

            stored_count = upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="episode-1",
                        title="第一集",
                        published_at="Mon, 01 Jun 2026 00:00:00 +0800",
                        episode_url="https://example.com/episodes/1",
                        audio_url="https://example.com/audio/1.mp3",
                        description="Episode description",
                    )
                ],
            )

            self.assertEqual(stored_count, 1)
            self.assertEqual(count_episodes(database_path), 1)

            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    "SELECT guid, title, audio_url FROM episodes"
                ).fetchone()

            self.assertEqual(row, ("episode-1", "第一集", "https://example.com/audio/1.mp3"))

    def test_upsert_episodes_updates_existing_episode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            original_episode = Episode(
                guid="episode-1",
                title="Old title",
                published_at=None,
                episode_url=None,
                audio_url=None,
                description=None,
            )
            updated_episode = Episode(
                guid="episode-1",
                title="New title",
                published_at=None,
                episode_url=None,
                audio_url=None,
                description=None,
            )

            upsert_episodes(database_path, [original_episode])
            upsert_episodes(database_path, [updated_episode])

            with sqlite3.connect(database_path) as connection:
                row = connection.execute("SELECT title FROM episodes").fetchone()

            self.assertEqual(count_episodes(database_path), 1)
            self.assertEqual(row, ("New title",))

    def test_initialize_database_adds_audio_download_tracking_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")

            initialize_database(database_path)

            with sqlite3.connect(database_path) as connection:
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(episodes)").fetchall()
                }

            self.assertIn("audio_local_path", columns)
            self.assertIn("audio_downloaded_at", columns)
            self.assertIn("audio_download_error", columns)
            self.assertIn("audio_deleted_at", columns)
            self.assertIn("audio_delete_error", columns)
            self.assertIn("transcript_local_path", columns)
            self.assertIn("transcribed_at", columns)
            self.assertIn("transcription_error", columns)
            self.assertIn("obsidian_transcript_path", columns)
            self.assertIn("obsidian_transcript_status", columns)
            self.assertIn("obsidian_transcript_exported_at", columns)
            self.assertIn("obsidian_transcript_export_error", columns)

            chunk_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(transcript_chunks)").fetchall()
            }
            self.assertIn("episode_guid", chunk_columns)
            self.assertIn("chunk_index", chunk_columns)
            self.assertIn("chunk_text", chunk_columns)

    def test_initialize_database_migrates_existing_episode_table(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")

            with sqlite3.connect(database_path) as connection:
                connection.execute(
                    """
                    CREATE TABLE episodes (
                        guid TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        published_at TEXT,
                        episode_url TEXT,
                        audio_url TEXT,
                        description TEXT,
                        first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

            initialize_database(database_path)

            with sqlite3.connect(database_path) as connection:
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(episodes)").fetchall()
                }

            self.assertIn("audio_local_path", columns)
            self.assertIn("audio_downloaded_at", columns)
            self.assertIn("audio_download_error", columns)
            self.assertIn("audio_deleted_at", columns)
            self.assertIn("audio_delete_error", columns)
            self.assertIn("transcript_local_path", columns)
            self.assertIn("transcribed_at", columns)
            self.assertIn("transcription_error", columns)
            self.assertIn("obsidian_transcript_path", columns)
            self.assertIn("obsidian_transcript_status", columns)
            self.assertIn("obsidian_transcript_exported_at", columns)
            self.assertIn("obsidian_transcript_export_error", columns)

            chunk_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(transcript_chunks)").fetchall()
            }
            self.assertIn("episode_guid", chunk_columns)
            self.assertIn("chunk_index", chunk_columns)
            self.assertIn("chunk_text", chunk_columns)

    def test_list_episodes_returns_latest_episodes_first(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="episode-1",
                        title="Old episode",
                        published_at="Mon, 01 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url=None,
                        description=None,
                    ),
                    Episode(
                        guid="episode-2",
                        title="New episode",
                        published_at="Tue, 02 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url="https://example.com/audio/2.mp3",
                        description=None,
                    ),
                ],
            )

            episodes = list_episodes(database_path, limit=1)

            self.assertEqual(len(episodes), 1)
            self.assertEqual(episodes[0].title, "New episode")
            self.assertEqual(episodes[0].audio_url, "https://example.com/audio/2.mp3")

    def test_list_episodes_sorts_rfc_822_dates_chronologically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="episode-2022",
                        title="2022 episode",
                        published_at="Wed, 25 May 2022 17:53:37 GMT",
                        episode_url=None,
                        audio_url=None,
                        description=None,
                    ),
                    Episode(
                        guid="episode-2025",
                        title="2025 episode",
                        published_at="Wed, 23 Apr 2025 07:00:00 GMT",
                        episode_url=None,
                        audio_url=None,
                        description=None,
                    ),
                ],
            )

            episodes = list_episodes(database_path, limit=1)

            self.assertEqual(episodes[0].title, "2025 episode")

    def test_list_episodes_rejects_non_positive_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")

            with self.assertRaisesRegex(ValueError, "limit"):
                list_episodes(database_path, limit=0)

    def test_list_pending_downloads_only_returns_episodes_with_audio_url_and_no_local_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="ready",
                        title="Ready",
                        published_at="Tue, 02 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url="https://example.com/audio/ready.mp3",
                        description=None,
                    ),
                    Episode(
                        guid="missing-audio",
                        title="Missing audio",
                        published_at="Wed, 03 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url=None,
                        description=None,
                    ),
                    Episode(
                        guid="downloaded",
                        title="Downloaded",
                        published_at="Thu, 04 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url="https://example.com/audio/downloaded.mp3",
                        description=None,
                    ),
                ],
            )

            with sqlite3.connect(database_path) as connection:
                connection.execute(
                    "UPDATE episodes SET audio_local_path = ? WHERE guid = ?",
                    ("data/audio/downloaded.mp3", "downloaded"),
                )

            episodes = list_pending_downloads(database_path, limit=10)

            self.assertEqual([episode.guid for episode in episodes], ["ready"])

    def test_list_pending_downloads_prefers_episode_number_when_dates_are_unreliable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="ep-41",
                        title="EP.41「行為」",
                        published_at="Tue, 02 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url="https://example.com/audio/41.mp3",
                        description=None,
                    ),
                    Episode(
                        guid="ep-376",
                        title="EP.376《不反應的練習》",
                        published_at="Mon, 01 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url="https://example.com/audio/376.mp3",
                        description=None,
                    ),
                ],
            )

            episodes = list_pending_downloads(database_path, limit=2)

            self.assertEqual([episode.guid for episode in episodes], ["ep-376", "ep-41"])

    def test_list_pending_downloads_reads_embedded_episode_number_for_sorting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="ep-41",
                        title="EP.41「行為」",
                        published_at="Tue, 02 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url="https://example.com/audio/41.mp3",
                        description=None,
                    ),
                    Episode(
                        guid="special-300",
                        title="【聯名特企SP9】EP.300《正式編號特企》",
                        published_at="Mon, 01 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url="https://example.com/audio/300.mp3",
                        description=None,
                    ),
                ],
            )

            episodes = list_pending_downloads(database_path, limit=2)

            self.assertEqual([episode.guid for episode in episodes], ["special-300", "ep-41"])

    def test_list_pending_downloads_excludes_deleted_audio(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="deleted",
                        title="Deleted",
                        published_at="Tue, 02 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url="https://example.com/audio/deleted.mp3",
                        description=None,
                    )
                ],
            )

            mark_audio_deleted(database_path, "deleted")

            self.assertEqual(list_pending_downloads(database_path, limit=10), [])

    def test_list_pending_downloads_rejects_non_positive_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")

            with self.assertRaisesRegex(ValueError, "limit"):
                list_pending_downloads(database_path, limit=0)

    def test_mark_audio_downloaded_updates_download_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
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

            mark_audio_download_failed(database_path, "episode-1", "old error")
            mark_audio_downloaded(database_path, "episode-1", "data/audio/episode.mp3")

            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    """
                    SELECT audio_local_path, audio_downloaded_at, audio_download_error
                    FROM episodes
                    WHERE guid = ?
                    """,
                    ("episode-1",),
                ).fetchone()

            self.assertEqual(row[0], "data/audio/episode.mp3")
            self.assertIsNotNone(row[1])
            self.assertIsNone(row[2])

    def test_mark_audio_download_failed_updates_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
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

            mark_audio_download_failed(database_path, "episode-1", "network timeout")

            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    "SELECT audio_download_error FROM episodes WHERE guid = ?",
                    ("episode-1",),
                ).fetchone()

            self.assertEqual(row, ("network timeout",))

    def test_get_audio_local_path_returns_path_for_episode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
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
            mark_audio_downloaded(database_path, "episode-1", "data/audio/episode.mp3")

            self.assertEqual(get_audio_local_path(database_path, "episode-1"), "data/audio/episode.mp3")

    def test_mark_audio_deleted_updates_delete_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="episode-1",
                        title="Episode",
                        published_at=None,
                        episode_url="https://example.com/episode",
                        audio_url="https://example.com/audio.mp3",
                        description=None,
                    )
                ],
            )
            mark_audio_delete_failed(database_path, "episode-1", "old error")

            mark_audio_deleted(database_path, "episode-1")

            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    """
                    SELECT audio_deleted_at, audio_delete_error
                    FROM episodes
                    WHERE guid = ?
                    """,
                    ("episode-1",),
                ).fetchone()

            self.assertIsNotNone(row[0])
            self.assertIsNone(row[1])

    def test_mark_audio_delete_failed_updates_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="episode-1",
                        title="Episode",
                        published_at=None,
                        episode_url="https://example.com/episode",
                        audio_url="https://example.com/audio.mp3",
                        description=None,
                    )
                ],
            )

            mark_audio_delete_failed(database_path, "episode-1", "permission denied")

            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    "SELECT audio_delete_error FROM episodes WHERE guid = ?",
                    ("episode-1",),
                ).fetchone()

            self.assertEqual(row, ("permission denied",))

    def test_list_pending_transcriptions_only_returns_downloaded_untranscribed_episodes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="downloaded",
                        title="Downloaded",
                        published_at="Tue, 02 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url="https://example.com/audio/downloaded.mp3",
                        description=None,
                    ),
                    Episode(
                        guid="not-downloaded",
                        title="Not downloaded",
                        published_at="Wed, 03 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url="https://example.com/audio/not-downloaded.mp3",
                        description=None,
                    ),
                    Episode(
                        guid="transcribed",
                        title="Transcribed",
                        published_at="Thu, 04 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url="https://example.com/audio/transcribed.mp3",
                        description=None,
                    ),
                ],
            )

            mark_audio_downloaded(database_path, "downloaded", "data/audio/downloaded.mp3")
            mark_audio_downloaded(database_path, "transcribed", "data/audio/transcribed.mp3")
            with sqlite3.connect(database_path) as connection:
                connection.execute(
                    "UPDATE episodes SET transcript_local_path = ? WHERE guid = ?",
                    ("data/transcripts/transcribed.md", "transcribed"),
                )

            episodes = list_pending_transcriptions(database_path, limit=10)

            self.assertEqual([episode.guid for episode in episodes], ["downloaded"])

    def test_list_pending_transcriptions_prefers_episode_number_when_dates_are_unreliable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="ep-41",
                        title="EP.41「行為」",
                        published_at="Tue, 02 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url="https://example.com/audio/41.mp3",
                        description=None,
                    ),
                    Episode(
                        guid="ep-362",
                        title="EP.362《隨機騙局(下)》",
                        published_at="Mon, 01 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url="https://example.com/audio/362.mp3",
                        description=None,
                    ),
                ],
            )
            mark_audio_downloaded(database_path, "ep-41", "data/audio/41.mp3")
            mark_audio_downloaded(database_path, "ep-362", "data/audio/362.mp3")

            episodes = list_pending_transcriptions(database_path, limit=2)

            self.assertEqual([episode.guid for episode in episodes], ["ep-362", "ep-41"])

    def test_list_pending_transcriptions_rejects_non_positive_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")

            with self.assertRaisesRegex(ValueError, "limit"):
                list_pending_transcriptions(database_path, limit=0)

    def test_mark_transcript_imported_updates_transcription_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
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
            with sqlite3.connect(database_path) as connection:
                connection.execute(
                    "UPDATE episodes SET transcription_error = ? WHERE guid = ?",
                    ("old error", "episode-1"),
                )

            updated = mark_transcript_imported(
                database_path,
                "episode-1",
                "data/transcripts/episode-1.txt",
            )

            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    """
                    SELECT transcript_local_path, transcribed_at, transcription_error
                    FROM episodes
                    WHERE guid = ?
                    """,
                    ("episode-1",),
                ).fetchone()

            self.assertTrue(updated)
            self.assertEqual(row[0], "data/transcripts/episode-1.txt")
            self.assertIsNotNone(row[1])
            self.assertIsNone(row[2])

    def test_mark_transcript_imported_resets_transcript_export_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
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
            mark_transcript_note_exported(
                database_path,
                "episode-1",
                "Podcast/引書店/transcripts/old.md",
            )

            mark_transcript_imported(
                database_path,
                "episode-1",
                "data/transcripts/new.txt",
            )

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

            self.assertEqual(row, (None, None, None))

    def test_mark_transcript_imported_returns_false_for_unknown_guid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")

            updated = mark_transcript_imported(
                database_path,
                "missing-guid",
                "data/transcripts/missing.txt",
            )

            self.assertFalse(updated)

    def test_mark_transcription_failed_updates_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
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

            mark_transcription_failed(database_path, "episode-1", "MacWhisper failed")

            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    "SELECT transcription_error FROM episodes WHERE guid = ?",
                    ("episode-1",),
                ).fetchone()

            self.assertEqual(row, ("MacWhisper failed",))

    def test_list_pending_transcript_exports_only_returns_unexported_transcripts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="ready",
                        title="Ready",
                        published_at="Tue, 02 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url=None,
                        description=None,
                    ),
                    Episode(
                        guid="not-transcribed",
                        title="Not transcribed",
                        published_at="Wed, 03 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url=None,
                        description=None,
                    ),
                    Episode(
                        guid="exported",
                        title="Exported",
                        published_at="Thu, 04 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url=None,
                        description=None,
                    ),
                ],
            )
            mark_transcript_imported(database_path, "ready", "data/transcripts/ready.txt")
            mark_transcript_imported(database_path, "exported", "data/transcripts/exported.txt")
            mark_transcript_note_exported(
                database_path,
                "exported",
                "Podcast/引書店/transcripts/exported.md",
            )

            exports = list_pending_transcript_exports(database_path, limit=10)

            self.assertEqual([item.episode.guid for item in exports], ["ready"])
            self.assertEqual(exports[0].transcript_local_path, "data/transcripts/ready.txt")

    def test_list_pending_transcript_exports_rejects_non_positive_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")

            with self.assertRaisesRegex(ValueError, "limit"):
                list_pending_transcript_exports(database_path, limit=0)

    def test_mark_transcript_note_exported_updates_export_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
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
            mark_transcript_note_export_failed(database_path, "episode-1", "old error")

            mark_transcript_note_exported(
                database_path,
                "episode-1",
                "Podcast/引書店/transcripts/episode.md",
            )

            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    """
                    SELECT
                        obsidian_transcript_path,
                        obsidian_transcript_status,
                        obsidian_transcript_exported_at,
                        obsidian_transcript_export_error
                    FROM episodes
                    WHERE guid = ?
                    """,
                    ("episode-1",),
                ).fetchone()

            self.assertEqual(row[0], "Podcast/引書店/transcripts/episode.md")
            self.assertEqual(row[1], "indexed")
            self.assertIsNotNone(row[2])
            self.assertIsNone(row[3])

    def test_mark_transcript_note_export_failed_updates_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
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

            mark_transcript_note_export_failed(database_path, "episode-1", "missing transcript")

            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    """
                    SELECT obsidian_transcript_export_error
                    FROM episodes
                    WHERE guid = ?
                    """,
                    ("episode-1",),
                ).fetchone()

            self.assertEqual(row, ("missing transcript",))

    def test_list_indexed_transcripts_returns_unindexed_indexed_transcripts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="indexed",
                        title="Indexed",
                        published_at="Tue, 02 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url=None,
                        description=None,
                    ),
                    Episode(
                        guid="not-exported",
                        title="Not exported",
                        published_at="Wed, 03 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url=None,
                        description=None,
                    ),
                ],
            )
            mark_transcript_imported(database_path, "indexed", "data/transcripts/indexed.txt")
            mark_transcript_imported(database_path, "not-exported", "data/transcripts/missing.txt")
            mark_transcript_note_exported(
                database_path,
                "indexed",
                "Inbox/Podcast Import/transcripts/indexed.md",
            )

            transcripts = list_indexed_transcripts(database_path, limit=10)

            self.assertEqual([item.episode.guid for item in transcripts], ["indexed"])
            self.assertEqual(transcripts[0].transcript_local_path, "data/transcripts/indexed.txt")

    def test_list_indexed_episodes_returns_exported_episodes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="indexed",
                        title="Indexed",
                        published_at="Tue, 02 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url=None,
                        description=None,
                    ),
                    Episode(
                        guid="plain",
                        title="Plain",
                        published_at="Wed, 03 Jun 2026 00:00:00 +0800",
                        episode_url=None,
                        audio_url=None,
                        description=None,
                    ),
                ],
            )
            mark_transcript_imported(database_path, "indexed", "data/transcripts/indexed.txt")
            mark_transcript_note_exported(
                database_path,
                "indexed",
                "Inbox/Podcast Import/transcripts/indexed.md",
            )

            episodes = list_indexed_episodes(database_path, limit=10)

            self.assertEqual([episode.guid for episode in episodes], ["indexed"])

    def test_replace_and_search_transcript_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
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
            mark_transcript_imported(database_path, "episode-1", "data/transcripts/episode.txt")
            mark_transcript_note_exported(
                database_path,
                "episode-1",
                "Inbox/Podcast Import/transcripts/episode.md",
            )
            transcript = list_indexed_transcripts(database_path, limit=1)[0]

            stored_count = replace_transcript_chunks(
                database_path,
                transcript,
                ["第一段提到品質管理", "第二段提到教練"],
            )
            results = search_transcript_chunks(database_path, "品質", limit=10)

            self.assertEqual(stored_count, 2)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].episode.guid, "episode-1")
            self.assertEqual(results[0].chunk_index, 0)
            self.assertIn("品質管理", results[0].chunk_text)

    def test_search_transcript_chunks_expands_natural_language_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="episode-369",
                        title="EP.369《終結職業倦怠》",
                        published_at=None,
                        episode_url=None,
                        audio_url=None,
                        description=None,
                    )
                ],
            )
            mark_transcript_imported(database_path, "episode-369", "data/transcripts/ep369.txt")
            mark_transcript_note_exported(
                database_path,
                "episode-369",
                "Inbox/Podcast Import/transcripts/ep369.md",
            )
            transcript = list_indexed_transcripts(database_path, limit=1)[0]
            replace_transcript_chunks(
                database_path,
                transcript,
                ["這段逐字稿討論職業倦怠與工作壓力。"],
            )

            results = search_transcript_chunks(database_path, "身心耗竭", limit=10)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].episode.guid, "episode-369")

    def test_search_transcript_chunks_rejects_empty_query(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")

            with self.assertRaisesRegex(ValueError, "query"):
                search_transcript_chunks(database_path, "  ", limit=10)

    def test_search_episode_summaries_matches_summary_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            episode = Episode(
                guid="episode-369",
                title="EP.369《終結職業倦怠》",
                published_at=None,
                episode_url=None,
                audio_url=None,
                description=None,
            )
            upsert_episodes(database_path, [episode])
            upsert_episode_summary(
                database_path,
                EpisodeSummary(
                    episode=episode,
                    one_sentence_summary="本集探討職業倦怠的成因。",
                    key_points=["理想與現實的矛盾會加劇職業倦怠。"],
                    topics=["職業倦怠"],
                    summary_note_path="Inbox/Podcast Import/episodes/ep369.md",
                    generated_by="openai_structured_v1",
                ),
            )

            questions = [
                "有沒有聊過職業倦怠？",
                "有沒有跟職業倦怠相關",
                "有沒有討論職業倦怠",
            ]

            for question in questions:
                with self.subTest(question=question):
                    results = search_episode_summaries(database_path, question, limit=10)
                    self.assertEqual([summary.episode.guid for summary in results], ["episode-369"])

    def test_search_episode_summaries_ignores_generic_concept_words(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            wealth_episode = Episode(
                guid="episode-372",
                title="EP.372《財富階梯》",
                published_at="Fri, 08 May 2026 00:00:00 +0800",
                episode_url=None,
                audio_url=None,
                description=None,
            )
            generic_episode = Episode(
                guid="episode-1",
                title="EP.1《其他主題》",
                published_at="Fri, 01 May 2026 00:00:00 +0800",
                episode_url=None,
                audio_url=None,
                description=None,
            )
            upsert_episodes(database_path, [wealth_episode, generic_episode])
            upsert_episode_summary(
                database_path,
                EpisodeSummary(
                    episode=wealth_episode,
                    one_sentence_summary="本集討論財富階梯與財富守護。",
                    key_points=["財富累積與心態是重要主軸。"],
                    topics=["財富"],
                    summary_note_path="Inbox/Podcast Import/episodes/ep372.md",
                    generated_by="openai_structured_v1",
                ),
            )
            upsert_episode_summary(
                database_path,
                EpisodeSummary(
                    episode=generic_episode,
                    one_sentence_summary="本集整理幾個人生概念。",
                    key_points=["這裡只有概念這個泛詞。"],
                    topics=["概念"],
                    summary_note_path="Inbox/Podcast Import/episodes/ep001.md",
                    generated_by="openai_structured_v1",
                ),
            )

            results = search_episode_summaries(database_path, "財富相關的書或概念有哪些集？", limit=10)

            self.assertEqual([summary.episode.guid for summary in results], ["episode-372"])

    def test_search_episode_summaries_expands_natural_language_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            episode = Episode(
                guid="episode-369",
                title="EP.369《終結職業倦怠》",
                published_at=None,
                episode_url=None,
                audio_url=None,
                description=None,
            )
            upsert_episodes(database_path, [episode])
            upsert_episode_summary(
                database_path,
                EpisodeSummary(
                    episode=episode,
                    one_sentence_summary="本集探討職業倦怠的成因。",
                    key_points=["職業倦怠是一種光譜狀態。"],
                    topics=["職業倦怠"],
                    summary_note_path="Inbox/Podcast Import/episodes/ep369.md",
                    generated_by="openai_structured_v1",
                ),
            )

            results = search_episode_summaries(database_path, "哪幾集有聊到身心耗竭？", limit=10)

            self.assertEqual([summary.episode.guid for summary in results], ["episode-369"])

    def test_replace_and_search_book_and_concept_mentions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            episode = Episode(
                guid="episode-329",
                title="EP.329《納瓦爾寶典》",
                published_at=None,
                episode_url=None,
                audio_url=None,
                description=None,
            )
            upsert_episodes(database_path, [episode])

            book_count = replace_book_mentions(
                database_path,
                episode.guid,
                [
                    BookMention(
                        episode=episode,
                        name="納瓦爾寶典",
                        mention_level="main_focus",
                        evidence="整集主軸。",
                    )
                ],
            )
            concept_count = replace_concept_mentions(
                database_path,
                episode.guid,
                [
                    ConceptMention(
                        episode=episode,
                        name="槓桿運用",
                        mention_level="discussed",
                        evidence="討論如何不只用時間換錢。",
                    )
                ],
            )

            book_results = search_book_mentions(database_path, "有沒有介紹納瓦爾寶典？", limit=10)
            concept_results = search_concept_mentions(database_path, "有沒有聊過財富槓桿？", limit=10)

            self.assertEqual(book_count, 1)
            self.assertEqual(concept_count, 1)
            self.assertEqual(book_results[0].name, "納瓦爾寶典")
            self.assertEqual(concept_results[0].name, "槓桿運用")

    def test_search_mentions_expands_natural_language_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            wealth_episode = Episode(
                guid="episode-372",
                title="EP.372《財富階梯》",
                published_at=None,
                episode_url=None,
                audio_url=None,
                description=None,
            )
            boundary_episode = Episode(
                guid="episode-339",
                title="EP.339《心理界限》",
                published_at=None,
                episode_url=None,
                audio_url=None,
                description=None,
            )
            upsert_episodes(database_path, [wealth_episode, boundary_episode])
            replace_book_mentions(
                database_path,
                wealth_episode.guid,
                [
                    BookMention(
                        episode=wealth_episode,
                        name="財富階梯",
                        mention_level="main_focus",
                        evidence="討論財富累積與財富守護。",
                    )
                ],
            )
            replace_concept_mentions(
                database_path,
                boundary_episode.guid,
                [
                    ConceptMention(
                        episode=boundary_episode,
                        name="心理界限",
                        mention_level="main_focus",
                        evidence="討論關係中的界限。",
                    )
                ],
            )

            book_results = search_book_mentions(database_path, "有沒有致富相關的集？", limit=10)
            concept_results = search_concept_mentions(database_path, "哪集有講邊界感？", limit=10)

            self.assertEqual([mention.episode.guid for mention in book_results], ["episode-372"])
            self.assertEqual([mention.episode.guid for mention in concept_results], ["episode-339"])
