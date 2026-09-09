from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_bot.announcements import (
    format_episode_announcement,
    publish_pending_episode_announcements,
)
from reference_bot.episodes import Episode, EpisodeSummary
from reference_bot.storage import mark_transcript_imported, upsert_episode_summary, upsert_episodes


class _FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class AnnouncementTests(unittest.TestCase):
    def test_format_episode_announcement_uses_template_and_limits_core_argument(self) -> None:
        summary = _summary(key_point="這是一段超過五十個字的核心論述" * 5)

        message = format_episode_announcement(summary)

        self.assertIn("喵～～～新一集的EP.407上架囉", message)
        self.assertIn("[Spotify]", message)
        self.assertIn("[Apple Podcast]", message)
        self.assertIn("這集的主題是建立可持續的工作節奏", message)
        core = message.split("引引最喜歡的地方是", 1)[1].split("，一起來聽聽看喵～", 1)[0]
        self.assertLessEqual(len(core), 50)

    def test_publish_marks_pending_announcement_sent_and_does_not_repeat(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            summary = _summary()
            upsert_episodes(database_path, [summary.episode])
            mark_transcript_imported(database_path, summary.episode.guid, "episode.txt")
            upsert_episode_summary(database_path, summary)

            with patch(
                "reference_bot.announcements.request.urlopen",
                return_value=_FakeResponse(),
            ) as urlopen:
                first_result = publish_pending_episode_announcements(
                    database_path=database_path,
                    discord_token="secret-token",
                    channel_id=123,
                )
                second_result = publish_pending_episode_announcements(
                    database_path=database_path,
                    discord_token="secret-token",
                    channel_id=123,
                )

            self.assertEqual(first_result, (1, 0))
            self.assertEqual(second_result, (0, 0))
            self.assertEqual(urlopen.call_count, 1)
            outgoing_request = urlopen.call_args.args[0]
            payload = json.loads(outgoing_request.data.decode("utf-8"))
            self.assertIn("EP.407", payload["content"])
            self.assertEqual(payload["allowed_mentions"], {"parse": []})
            self.assertEqual(outgoing_request.get_header("Authorization"), "Bot secret-token")

            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    "SELECT announcement_status, announcement_sent_at, announcement_error FROM episodes"
                ).fetchone()
            self.assertEqual(row[0], "sent")
            self.assertIsNotNone(row[1])
            self.assertIsNone(row[2])

    def test_reimporting_existing_transcript_does_not_queue_new_announcement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            summary = _summary()
            upsert_episodes(database_path, [summary.episode])
            mark_transcript_imported(database_path, summary.episode.guid, "first.txt")
            upsert_episode_summary(database_path, summary)

            with patch("reference_bot.announcements.request.urlopen", return_value=_FakeResponse()):
                publish_pending_episode_announcements(
                    database_path=database_path,
                    discord_token="secret-token",
                    channel_id=123,
                )

            mark_transcript_imported(database_path, summary.episode.guid, "corrected.txt")
            with patch("reference_bot.announcements.request.urlopen") as urlopen:
                result = publish_pending_episode_announcements(
                    database_path=database_path,
                    discord_token="secret-token",
                    channel_id=123,
                )

            self.assertEqual(result, (0, 0))
            urlopen.assert_not_called()


def _summary(*, key_point: str = "穩定的小步前進，比短期燃燒更能累積真正的成果。") -> EpisodeSummary:
    return EpisodeSummary(
        episode=Episode(
            guid="episode-407",
            title="EP.407《工作的節奏》",
            published_at="Mon, 07 Sep 2026 00:00:00 +0800",
            episode_url="https://example.com/episode-407",
            audio_url="https://example.com/episode-407.mp3",
            description=None,
        ),
        one_sentence_summary="這集討論如何建立可以長久維持的工作方式。",
        key_points=[key_point],
        topics=["建立可持續的工作節奏"],
        summary_note_path=None,
        generated_by="openai_structured_v1",
    )


if __name__ == "__main__":
    unittest.main()
