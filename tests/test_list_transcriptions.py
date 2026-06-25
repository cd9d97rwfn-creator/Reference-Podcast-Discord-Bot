from __future__ import annotations

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
from reference_bot.list_transcriptions import main
from reference_bot.storage import mark_audio_downloaded, upsert_episodes


class ListTranscriptionsTests(unittest.TestCase):
    def test_list_transcriptions_prints_episode_guid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="episode-guid",
                        title="Episode",
                        published_at="Fri, 29 May 2026 09:30:00 GMT",
                        episode_url=None,
                        audio_url="https://example.com/audio.mp3",
                        description=None,
                    )
                ],
            )
            mark_audio_downloaded(database_path, "episode-guid", "data/audio/episode.mp3")

            output = StringIO()
            with patch(
                "reference_bot.list_transcriptions.load_rss_settings",
                return_value=RssSettings(
                    podcast_rss_url="https://example.com/feed.xml",
                    database_path=database_path,
                ),
            ):
                with patch("sys.argv", ["reference-list-transcriptions", "--limit", "1"]):
                    with redirect_stdout(output):
                        main()

            self.assertIn("guid: episode-guid", output.getvalue())
