from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_bot.episodes import Episode, TranscribedEpisode
from reference_bot.obsidian import export_transcript_note


class ObsidianExportTests(unittest.TestCase):
    def test_export_transcript_note_writes_frontmatter_and_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            transcript_path = root / "transcript.txt"
            output_dir = root / "Podcast" / "引書店" / "transcripts"
            transcript_path.write_text("[00:01] hello transcript", encoding="utf-8")

            note_path = export_transcript_note(
                TranscribedEpisode(
                    episode=Episode(
                        guid="episode-1",
                        title="第一集：測試",
                        published_at="Mon, 01 Jun 2026 00:00:00 +0800",
                        episode_url="https://example.com/episode",
                        audio_url="https://example.com/audio.mp3",
                        description=None,
                    ),
                    transcript_local_path=str(transcript_path),
                ),
                str(output_dir),
            )

            content = note_path.read_text(encoding="utf-8")

            self.assertTrue(note_path.is_file())
            self.assertIn("type: \"podcast_transcript\"", content)
            self.assertIn("status: \"indexed\"", content)
            self.assertIn("podcast: \"引書店\"", content)
            self.assertIn("title: \"第一集：測試\"", content)
            self.assertIn("transcript_has_timestamps: \"false\"", content)
            self.assertIn("Episode note: [[2026-06-01", content)
            self.assertIn("[00:01] hello transcript", content)

    def test_export_transcript_note_does_not_overwrite_existing_note(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            transcript_path = root / "transcript.txt"
            output_dir = root / "transcripts"
            output_dir.mkdir()
            transcript_path.write_text("new transcript", encoding="utf-8")

            candidate = TranscribedEpisode(
                episode=Episode(
                    guid="episode-1",
                    title="Episode",
                    published_at=None,
                    episode_url=None,
                    audio_url=None,
                    description=None,
                ),
                transcript_local_path=str(transcript_path),
            )
            first_path = export_transcript_note(candidate, str(output_dir))
            first_path.write_text("existing note", encoding="utf-8")

            second_path = export_transcript_note(candidate, str(output_dir))

            self.assertNotEqual(first_path, second_path)
            self.assertEqual(first_path.read_text(encoding="utf-8"), "existing note")
            self.assertIn("new transcript", second_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
