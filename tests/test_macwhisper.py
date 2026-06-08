from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_bot.episodes import Episode
from reference_bot.macwhisper import APP_BUNDLE_MW_PATH, default_macwhisper_bin, transcribe_episode_audio


class MacWhisperTests(unittest.TestCase):
    def test_transcribe_episode_audio_writes_stdout_to_transcript_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            audio_path = root / "episode.mp3"
            transcripts_dir = root / "transcripts"
            audio_path.write_bytes(b"fake audio")
            episode = Episode(
                guid="episode-1",
                title="第一集：測試",
                published_at="Mon, 01 Jun 2026 00:00:00 +0800",
                episode_url=None,
                audio_url=None,
                description=None,
            )

            with patch("subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess(
                    args=["mw", "transcribe", str(audio_path)],
                    returncode=0,
                    stdout="[00:01] transcript text\n",
                    stderr="Transcribing: 100%",
                )

                result = transcribe_episode_audio(
                    episode=episode,
                    audio_local_path=str(audio_path),
                    transcripts_dir=str(transcripts_dir),
                    mw_bin="mw",
                    model="whisperkit:openai_whisper-small",
                    persist=True,
                )

            self.assertTrue(result.succeeded)
            self.assertIsNotNone(result.transcript_path)
            self.assertIn("[00:01] transcript text", result.transcript_path.read_text(encoding="utf-8"))
            run.assert_called_once_with(
                [
                    "mw",
                    "transcribe",
                    "--model",
                    "whisperkit:openai_whisper-small",
                    "--persist",
                    str(audio_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=None,
            )

    def test_transcribe_episode_audio_returns_error_when_audio_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            result = transcribe_episode_audio(
                episode=Episode(
                    guid="episode-1",
                    title="Episode",
                    published_at=None,
                    episode_url=None,
                    audio_url=None,
                    description=None,
                ),
                audio_local_path=str(root / "missing.mp3"),
                transcripts_dir=str(root / "transcripts"),
            )

            self.assertFalse(result.succeeded)
            self.assertIn("Audio file does not exist", result.error or "")

    def test_transcribe_episode_audio_returns_error_when_mw_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            audio_path = root / "episode.mp3"
            audio_path.write_bytes(b"fake audio")

            with patch("subprocess.run", side_effect=FileNotFoundError):
                result = transcribe_episode_audio(
                    episode=Episode(
                        guid="episode-1",
                        title="Episode",
                        published_at=None,
                        episode_url=None,
                        audio_url=None,
                        description=None,
                    ),
                    audio_local_path=str(audio_path),
                    transcripts_dir=str(root / "transcripts"),
                    mw_bin="mw",
                )

            self.assertFalse(result.succeeded)
            self.assertEqual(result.error, "MacWhisper CLI not found: mw")

    def test_default_macwhisper_bin_falls_back_to_app_bundle(self) -> None:
        with patch("shutil.which", return_value=None):
            with patch("pathlib.Path.is_file", return_value=True):
                self.assertEqual(default_macwhisper_bin(), APP_BUNDLE_MW_PATH)


if __name__ == "__main__":
    unittest.main()
