from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_bot.episodes import Episode, IndexedTranscript
from reference_bot.storage import (
    get_episode_summary_by_number,
    mark_transcript_imported,
    mark_transcript_note_exported,
    upsert_episodes,
)
from reference_bot.summary import build_episode_summary, generate_episode_summaries


class SummaryTests(unittest.TestCase):
    def test_build_episode_summary_uses_title_topic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            transcript_path = Path(temporary_directory) / "transcript.txt"
            transcript_path.write_text("這是一段逐字稿開頭。", encoding="utf-8")
            episode = Episode(
                guid="episode-375",
                title="EP.375《三種真實》feat. 來賓＿『點一盞燈』",
                published_at=None,
                episode_url=None,
                audio_url=None,
                description=None,
            )

            summary = build_episode_summary(
                IndexedTranscript(
                    episode=episode,
                    transcript_local_path=str(transcript_path),
                    obsidian_transcript_path=None,
                )
            )

        self.assertIn("三種真實", summary.one_sentence_summary)
        self.assertIn("三種真實", summary.topics)
        self.assertIn("點一盞燈", summary.topics)

    def test_generate_episode_summaries_stores_summary_and_note(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database_path = str(root / "episodes.sqlite3")
            transcript_path = root / "transcript.txt"
            summaries_dir = root / "Inbox" / "Podcast Import" / "episodes"
            transcript_path.write_text("這是一段逐字稿開頭。", encoding="utf-8")
            upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="episode-375",
                        title="EP.375《三種真實》",
                        published_at=None,
                        episode_url=None,
                        audio_url=None,
                        description=None,
                    )
                ],
            )
            mark_transcript_imported(database_path, "episode-375", str(transcript_path))
            mark_transcript_note_exported(
                database_path,
                "episode-375",
                "Inbox/Podcast Import/transcripts/ep375.md",
            )

            generated_count = generate_episode_summaries(
                database_path=database_path,
                summaries_dir=str(summaries_dir),
                limit=10,
            )
            summary = get_episode_summary_by_number(database_path, 375)

            self.assertEqual(generated_count, 1)
            self.assertIsNotNone(summary)
            assert summary is not None
            self.assertIn("三種真實", summary.one_sentence_summary)
            self.assertIsNotNone(summary.summary_note_path)
            self.assertTrue(Path(summary.summary_note_path or "").is_file())


if __name__ == "__main__":
    unittest.main()
