from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_bot.bot_process import bot_status, start_bot, stop_bot


class BotProcessTests(unittest.TestCase):
    def test_start_bot_writes_pid_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            pid_file = Path(temporary_directory) / "bot.pid"
            log_file = Path(temporary_directory) / "bot.log"
            process = Mock()
            process.pid = 12345

            with patch("reference_bot.bot_process.subprocess.Popen", return_value=process), patch(
                "reference_bot.bot_process._is_bot_process",
                return_value=False,
            ):
                pid = start_bot(pid_file=str(pid_file), log_file=str(log_file), cwd=temporary_directory)

            self.assertEqual(pid, 12345)
            self.assertEqual(pid_file.read_text(encoding="utf-8").strip(), "12345")
            self.assertTrue(log_file.exists())

    def test_start_bot_reuses_existing_running_pid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            pid_file = Path(temporary_directory) / "bot.pid"
            log_file = Path(temporary_directory) / "bot.log"
            pid_file.write_text("111\n", encoding="utf-8")

            with patch("reference_bot.bot_process._is_bot_process", return_value=True), patch(
                "reference_bot.bot_process.subprocess.Popen"
            ) as popen:
                pid = start_bot(pid_file=str(pid_file), log_file=str(log_file), cwd=temporary_directory)

            self.assertEqual(pid, 111)
            popen.assert_not_called()

    def test_stop_bot_removes_stale_pid_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            pid_file = Path(temporary_directory) / "bot.pid"
            pid_file.write_text("222\n", encoding="utf-8")

            with patch("reference_bot.bot_process._is_bot_process", return_value=False):
                stopped = stop_bot(pid_file=str(pid_file))

            self.assertFalse(stopped)
            self.assertFalse(pid_file.exists())

    def test_status_reports_running_pid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            pid_file = Path(temporary_directory) / "bot.pid"
            pid_file.write_text("333\n", encoding="utf-8")

            with patch("reference_bot.bot_process._is_bot_process", return_value=True):
                self.assertTrue(bot_status(pid_file=str(pid_file)))


if __name__ == "__main__":
    unittest.main()
