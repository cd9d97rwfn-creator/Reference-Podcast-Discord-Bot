from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_bot.local_refresh_deploy import local_refresh_deploy


class LocalRefreshDeployTests(unittest.TestCase):
    def test_local_refresh_deploy_requires_git_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(RuntimeError, "not a Git checkout"):
                local_refresh_deploy(
                    repo_dir=temporary_directory,
                    feed_url="https://example.com/rss",
                    database_path="data/episodes.sqlite3",
                    audio_dir="data/audio",
                    transcripts_dir="data/transcripts",
                    obsidian_transcripts_dir="Inbox/Podcast Import/transcripts",
                    obsidian_episodes_dir="Inbox/Podcast Import/episodes",
                    limit=1,
                    openai_api_key="test-key",
                )

    def test_local_refresh_deploy_commits_and_pushes_database_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_path = Path(temporary_directory)
            (repo_path / ".git").mkdir()
            calls: list[list[str]] = []

            def fake_run(command, cwd, check=True, text=False, stdout=None):
                calls.append(command)

                class Result:
                    returncode = 0
                    stdout = "main\n"

                if command[:3] == ["git", "diff", "--cached"]:
                    Result.returncode = 1
                return Result()

            with patch("reference_bot.local_refresh_deploy.refresh_corpus"), patch(
                "reference_bot.local_refresh_deploy.subprocess.run",
                side_effect=fake_run,
            ):
                result = local_refresh_deploy(
                    repo_dir=str(repo_path),
                    feed_url="https://example.com/rss",
                    database_path="data/episodes.sqlite3",
                    audio_dir="data/audio",
                    transcripts_dir="data/transcripts",
                    obsidian_transcripts_dir="Inbox/Podcast Import/transcripts",
                    obsidian_episodes_dir="Inbox/Podcast Import/episodes",
                    limit=1,
                    openai_api_key="test-key",
                )

            self.assertTrue(result.changed)
            self.assertTrue(result.committed)
            self.assertTrue(result.pushed)
            self.assertIn(["git", "add", "data/episodes.sqlite3"], calls)
            self.assertIn(["git", "commit", "-m", "Refresh podcast corpus"], calls)
            self.assertIn(["git", "push", "origin", "HEAD:main"], calls)

    def test_local_refresh_deploy_resolves_paths_from_repo_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_path = Path(temporary_directory)
            (repo_path / ".git").mkdir()

            def fake_run(command, cwd, check=True, text=False, stdout=None):
                class Result:
                    returncode = 0
                    stdout = "main\n"

                if command[:3] == ["git", "diff", "--cached"]:
                    Result.returncode = 0
                return Result()

            with patch("reference_bot.local_refresh_deploy.refresh_corpus") as refresh, patch(
                "reference_bot.local_refresh_deploy.subprocess.run",
                side_effect=fake_run,
            ):
                local_refresh_deploy(
                    repo_dir=str(repo_path),
                    feed_url="https://example.com/rss",
                    database_path="data/episodes.sqlite3",
                    audio_dir="data/audio",
                    transcripts_dir="data/transcripts",
                    obsidian_transcripts_dir="Inbox/Podcast Import/transcripts",
                    obsidian_episodes_dir="Inbox/Podcast Import/episodes",
                    limit=1,
                    openai_api_key="test-key",
                )

            kwargs = refresh.call_args.kwargs
            self.assertEqual(
                Path(kwargs["database_path"]),
                (repo_path / "data/episodes.sqlite3").resolve(),
            )
            self.assertEqual(Path(kwargs["audio_dir"]), (repo_path / "data/audio").resolve())


if __name__ == "__main__":
    unittest.main()
