from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_bot.episodes import Episode
from reference_bot.healthcheck import format_health_report, run_healthcheck
from reference_bot.storage import initialize_database, upsert_episodes


class HealthcheckTests(unittest.TestCase):
    def test_healthcheck_passes_when_thresholds_and_required_env_are_met(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            episode = Episode(
                guid="episode-1",
                title="EP.1《測試》",
                published_at="Fri, 01 May 2026 00:00:00 +0800",
                episode_url=None,
                audio_url=None,
                description=None,
            )
            upsert_episodes(database_path, [episode])
            with sqlite3.connect(database_path) as connection:
                connection.execute(
                    """
                    INSERT INTO episode_summaries (
                        episode_guid,
                        one_sentence_summary,
                        key_points_text,
                        topics_text,
                        generated_by
                    )
                    VALUES ('episode-1', '摘要', '重點', '主題', 'test')
                    """
                )
                connection.execute(
                    """
                    INSERT INTO transcript_chunks (
                        episode_guid,
                        chunk_index,
                        chunk_text,
                        transcript_local_path
                    )
                    VALUES ('episode-1', 0, '逐字稿', 'ep1.txt')
                    """
                )
                connection.execute(
                    "INSERT INTO book_mentions VALUES ('episode-1', '書', 'referenced', 'evidence', CURRENT_TIMESTAMP)"
                )
                connection.execute(
                    "INSERT INTO concept_mentions VALUES ('episode-1', '概念', 'referenced', 'evidence', CURRENT_TIMESTAMP)"
                )
                connection.execute(
                    """
                    INSERT INTO concept_clusters
                    VALUES ('episode-1', '概念', '概念', 'referenced', 'evidence', CURRENT_TIMESTAMP)
                    """
                )
                connection.execute(
                    """
                    INSERT INTO concept_relationships
                    VALUES ('episode-1', '概念', 'expands_on', '延伸概念', 'evidence', CURRENT_TIMESTAMP)
                    """
                )

            with patch.dict("os.environ", {"DISCORD_TOKEN": "token"}, clear=True):
                report = run_healthcheck(
                    database_path=database_path,
                    min_episodes=1,
                    min_summaries=1,
                    min_transcript_episodes=1,
                    run_eval=False,
                )

        self.assertTrue(report.ok)
        self.assertIn("Healthcheck: OK", format_health_report(report))

    def test_healthcheck_fails_when_database_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "missing.sqlite3")
            with patch.dict("os.environ", {"DISCORD_TOKEN": "token"}, clear=True):
                report = run_healthcheck(database_path=database_path, run_eval=False)

        self.assertFalse(report.ok)
        self.assertIn("[FAIL] database", format_health_report(report))

    def test_healthcheck_fails_when_required_token_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            initialize_database(database_path)
            with patch.dict("os.environ", {}, clear=True):
                report = run_healthcheck(
                    database_path=database_path,
                    min_episodes=0,
                    min_summaries=0,
                    min_transcript_episodes=0,
                    run_eval=False,
                )

        self.assertFalse(report.ok)
        self.assertIn("[FAIL] DISCORD_TOKEN", format_health_report(report))


if __name__ == "__main__":
    unittest.main()
