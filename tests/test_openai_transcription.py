from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_bot.episodes import Episode
from reference_bot.openai_transcription import _ffmpeg_path, transcribe_episode_audio_openai


class OpenAITranscriptionTests(unittest.TestCase):
    def test_transcribe_episode_audio_openai_writes_combined_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            audio_path = root / "audio.mp3"
            chunk_1 = root / "chunks" / "chunk-000.m4a"
            chunk_2 = root / "chunks" / "chunk-001.m4a"
            audio_path.write_bytes(b"audio")
            chunk_1.parent.mkdir()
            chunk_1.write_bytes(b"chunk 1")
            chunk_2.write_bytes(b"chunk 2")
            episode = Episode(
                guid="episode-329",
                title="EP.329《納瓦爾寶典》",
                published_at="Fri, 13 Jun 2025 13:00:00 GMT",
                episode_url=None,
                audio_url=None,
                description=None,
            )

            with patch(
                "reference_bot.openai_transcription.split_audio_for_openai",
                return_value=[chunk_1, chunk_2],
            ) as split_audio:
                with patch(
                    "reference_bot.openai_transcription.transcribe_audio_file",
                    side_effect=["第一段", "第二段"],
                ) as transcribe_file:
                    result = transcribe_episode_audio_openai(
                        episode=episode,
                        audio_local_path=str(audio_path),
                        transcripts_dir=str(root / "transcripts"),
                        api_key="test-key",
                        model="gpt-4o-mini-transcribe",
                    )

            self.assertTrue(result.succeeded)
            assert result.transcript_path is not None
            transcript_text = result.transcript_path.read_text(encoding="utf-8")
            self.assertIn("第一段", transcript_text)
            self.assertIn("第二段", transcript_text)
            self.assertIn("openai-direct", result.transcript_path.name)
            split_audio.assert_called_once()
            self.assertEqual(transcribe_file.call_count, 2)

    def test_ffmpeg_path_prefers_configured_binary(self) -> None:
        with patch.dict("os.environ", {"FFMPEG_BIN": "/opt/homebrew/bin/ffmpeg"}):
            self.assertEqual(_ffmpeg_path(), "/opt/homebrew/bin/ffmpeg")

    def test_ffmpeg_path_uses_path_binary_before_imageio(self) -> None:
        with patch.dict("os.environ", {"FFMPEG_BIN": ""}):
            with patch("reference_bot.openai_transcription.shutil.which", return_value="/usr/local/bin/ffmpeg"):
                self.assertEqual(_ffmpeg_path(), "/usr/local/bin/ffmpeg")

    def test_ffmpeg_path_falls_back_to_imageio_ffmpeg(self) -> None:
        with patch.dict("os.environ", {"FFMPEG_BIN": ""}):
            with patch("reference_bot.openai_transcription.shutil.which", return_value=None):
                with patch(
                    "imageio_ffmpeg.get_ffmpeg_exe",
                    return_value="/bundled/ffmpeg",
                ):
                    self.assertEqual(_ffmpeg_path(), "/bundled/ffmpeg")


if __name__ == "__main__":
    unittest.main()
