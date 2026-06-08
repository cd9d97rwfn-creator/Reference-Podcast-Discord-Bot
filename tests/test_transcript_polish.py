from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_bot.transcript_polish import cleaned_transcript_path, polish_transcript_file


class TranscriptPolishTests(unittest.TestCase):
    def test_cleaned_transcript_path_adds_cleaned_suffix(self) -> None:
        source_path = Path("data/transcripts/episode-openai-direct.txt")

        self.assertEqual(
            cleaned_transcript_path(source_path),
            Path("data/transcripts/episode-openai-direct-cleaned.txt"),
        )

    def test_polish_transcript_file_writes_cleaned_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "episode-openai-direct.txt"
            source_path.write_text("哈囉大家好這是一段逐字稿", encoding="utf-8")

            with patch("reference_bot.transcript_polish.chat_completion_text", return_value="哈囉，大家好。這是一段逐字稿。"):
                result = polish_transcript_file(
                    source_path=source_path,
                    api_key="test-key",
                    chunk_chars=1000,
                )

            self.assertEqual(result.chunks_polished, 1)
            self.assertEqual(result.cleaned_path.name, "episode-openai-direct-cleaned.txt")
            self.assertIn("哈囉，大家好。", result.cleaned_path.read_text(encoding="utf-8"))
            self.assertTrue((Path(temporary_directory) / "episode-openai-direct-cleaned-parts-1000").exists())

    def test_polish_transcript_file_skips_existing_cleaned_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "episode-openai-direct.txt"
            cleaned_path = Path(temporary_directory) / "episode-openai-direct-cleaned.txt"
            source_path.write_text("raw", encoding="utf-8")
            cleaned_path.write_text("cleaned", encoding="utf-8")

            result = polish_transcript_file(source_path=source_path, api_key="test-key")

            self.assertEqual(result.chunks_polished, 0)
            self.assertEqual(result.cleaned_path, cleaned_path)


if __name__ == "__main__":
    unittest.main()
