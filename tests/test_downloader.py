from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_bot.downloader import audio_filename, download_episode_audio
from reference_bot.episodes import Episode


class DownloaderTests(unittest.TestCase):
    def test_audio_filename_uses_date_hash_title_and_audio_extension(self) -> None:
        episode = Episode(
            guid="episode-guid",
            title="EP.375《三種真實》 feat. 侯籽名",
            published_at="Fri, 29 May 2026 09:30:00 GMT",
            episode_url=None,
            audio_url="https://example.com/audio/rssFileVip.mp3?timestamp=123",
            description=None,
        )

        filename = audio_filename(episode)

        self.assertTrue(filename.startswith("2026-05-29-"))
        self.assertTrue(filename.endswith(".mp3"))
        self.assertIn("三種真實", filename)

    def test_download_episode_audio_copies_file_url_to_audio_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.mp3"
            source.write_bytes(b"fake audio")
            audio_dir = root / "audio"
            episode = Episode(
                guid="episode-guid",
                title="Episode",
                published_at="Fri, 29 May 2026 09:30:00 GMT",
                episode_url=None,
                audio_url=source.as_uri(),
                description=None,
            )

            result = download_episode_audio(episode, str(audio_dir))

            self.assertTrue(result.succeeded)
            self.assertIsNotNone(result.local_path)
            self.assertEqual(result.local_path.read_bytes(), b"fake audio")

    def test_download_episode_audio_returns_error_for_missing_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            audio_dir = root / "audio"
            episode = Episode(
                guid="episode-guid",
                title="Episode",
                published_at="Fri, 29 May 2026 09:30:00 GMT",
                episode_url=None,
                audio_url=(root / "missing.mp3").as_uri(),
                description=None,
            )

            result = download_episode_audio(episode, str(audio_dir))

            self.assertFalse(result.succeeded)
            self.assertIsNone(result.local_path)
            self.assertIsNotNone(result.error)
