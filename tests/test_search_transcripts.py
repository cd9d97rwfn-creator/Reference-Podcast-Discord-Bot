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
from reference_bot.search_transcripts import main
from reference_bot.storage import (
    mark_transcript_imported,
    mark_transcript_note_exported,
    replace_transcript_chunks,
    list_indexed_transcripts,
    upsert_episodes,
)


class SearchTranscriptsTests(unittest.TestCase):
    def test_search_transcripts_prints_matching_episode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="episode-1",
                        title="品質管理這一集",
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
            replace_transcript_chunks(database_path, transcript, ["這段提到品質管理和系統。"])

            output = StringIO()
            with patch(
                "reference_bot.search_transcripts.load_rss_settings",
                return_value=RssSettings(
                    podcast_rss_url="https://example.com/feed.xml",
                    database_path=database_path,
                ),
            ):
                with patch("sys.argv", ["reference-search-transcripts", "品質", "--limit", "1"]):
                    with redirect_stdout(output):
                        main()

            self.assertIn("Results: 1", output.getvalue())
            self.assertIn("品質管理這一集", output.getvalue())
            self.assertIn("這段提到品質管理", output.getvalue())


if __name__ == "__main__":
    unittest.main()
