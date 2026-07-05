from __future__ import annotations

from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from start import _deployment_diagnostics, _deployment_diagnostics_text


class StartDiagnosticsTests(unittest.TestCase):
    def test_deployment_diagnostics_reports_database_counts_without_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "episodes.sqlite3"
            self._create_database(database_path)

            with patch.dict(
                "os.environ",
                {
                    "DATABASE_PATH": str(database_path),
                    "DISCORD_GUILD_IDS": "111, 222",
                    "DISCORD_TOKEN": "secret-token",
                    "OPENAI_API_KEY": "secret-key",
                    "RENDER_GIT_COMMIT": "abcdef1234567890",
                },
                clear=True,
            ):
                diagnostics = _deployment_diagnostics()

        self.assertEqual(diagnostics["status"], "ok")
        self.assertEqual(diagnostics["database_path"], str(database_path))
        self.assertTrue(diagnostics["database_exists"])
        self.assertEqual(diagnostics["discord_guild_ids_configured"], 2)
        self.assertEqual(diagnostics["discord_guild_ids_source"], "DISCORD_GUILD_IDS")
        self.assertEqual(diagnostics["render_git_commit"], "abcdef123456")
        self.assertEqual(diagnostics["counts"]["episodes"], 1)
        self.assertEqual(diagnostics["counts"]["transcript_chunks"], 2)
        self.assertNotIn("secret-token", str(diagnostics))
        self.assertNotIn("secret-key", str(diagnostics))
        self.assertNotIn("111", str(diagnostics))

    def test_deployment_diagnostics_text_is_human_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "missing.sqlite3"
            with patch.dict("os.environ", {"DATABASE_PATH": str(database_path)}, clear=True):
                text = _deployment_diagnostics_text()

        self.assertIn("status: ok", text)
        self.assertIn("database_exists: False", text)
        self.assertIn("discord_guild_ids_configured: 0", text)

    @staticmethod
    def _create_database(database_path: Path) -> None:
        with sqlite3.connect(database_path) as connection:
            connection.execute("CREATE TABLE episodes (guid TEXT PRIMARY KEY)")
            connection.execute("CREATE TABLE episode_summaries (episode_guid TEXT PRIMARY KEY)")
            connection.execute("CREATE TABLE transcript_chunks (episode_guid TEXT, chunk_index INTEGER)")
            connection.execute("CREATE TABLE book_mentions (episode_guid TEXT, name TEXT)")
            connection.execute("CREATE TABLE concept_mentions (episode_guid TEXT, name TEXT)")
            connection.execute("CREATE TABLE concept_clusters (episode_guid TEXT, cluster_name TEXT)")
            connection.execute("CREATE TABLE concept_relationships (episode_guid TEXT, source_name TEXT)")
            connection.execute("INSERT INTO episodes VALUES ('episode-1')")
            connection.execute("INSERT INTO episode_summaries VALUES ('episode-1')")
            connection.executemany(
                "INSERT INTO transcript_chunks VALUES ('episode-1', ?)",
                [(0,), (1,)],
            )
            connection.execute("INSERT INTO book_mentions VALUES ('episode-1', 'book')")
            connection.execute("INSERT INTO concept_mentions VALUES ('episode-1', 'concept')")
            connection.execute("INSERT INTO concept_clusters VALUES ('episode-1', 'cluster')")
            connection.execute("INSERT INTO concept_relationships VALUES ('episode-1', 'source')")


if __name__ == "__main__":
    unittest.main()
