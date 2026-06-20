from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


DEFAULT_PID_FILE = "data/reference-bot.pid"
DEFAULT_LOG_FILE = "data/reference-bot.log"
BOT_COMMAND_MARKER = "reference_bot.bot"


def start_bot(
    *,
    pid_file: str = DEFAULT_PID_FILE,
    log_file: str = DEFAULT_LOG_FILE,
    cwd: str | None = None,
) -> int:
    pid_path = Path(pid_file)
    log_path = Path(log_file)
    existing_pid = _read_pid(pid_path)
    if existing_pid and _is_bot_process(existing_pid):
        print(f"Bot already running with PID {existing_pid}.")
        print(f"Log: {log_path}")
        return existing_pid

    if existing_pid:
        print(f"Removing stale PID file for PID {existing_pid}.")
        pid_path.unlink(missing_ok=True)

    pid_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    log_handle = log_path.open("ab")
    process = subprocess.Popen(
        [sys.executable, "-m", BOT_COMMAND_MARKER],
        cwd=cwd or Path.cwd(),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    log_handle.close()
    pid_path.write_text(f"{process.pid}\n", encoding="utf-8")
    print(f"Started bot with PID {process.pid}.")
    print(f"PID file: {pid_path}")
    print(f"Log: {log_path}")
    return process.pid


def stop_bot(*, pid_file: str = DEFAULT_PID_FILE, timeout_seconds: float = 10) -> bool:
    pid_path = Path(pid_file)
    pid = _read_pid(pid_path)
    if pid is None:
        print("Bot is not running: PID file not found.")
        return False

    if not _is_bot_process(pid):
        print(f"Bot is not running: stale PID file found for PID {pid}.")
        pid_path.unlink(missing_ok=True)
        return False

    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _is_running(pid):
            pid_path.unlink(missing_ok=True)
            print(f"Stopped bot PID {pid}.")
            return True
        time.sleep(0.2)

    os.kill(pid, signal.SIGKILL)
    pid_path.unlink(missing_ok=True)
    print(f"Force-stopped bot PID {pid}.")
    return True


def bot_status(*, pid_file: str = DEFAULT_PID_FILE, log_file: str = DEFAULT_LOG_FILE) -> bool:
    pid = _read_pid(Path(pid_file))
    if pid and _is_bot_process(pid):
        print(f"Bot is running with PID {pid}.")
        print(f"Log: {log_file}")
        return True

    if pid:
        print(f"Bot is not running. Stale PID file points to PID {pid}.")
    else:
        print("Bot is not running.")
    return False


def run_main() -> None:
    args = _parser().parse_args()
    start_bot(pid_file=args.pid_file, log_file=args.log_file)


def stop_main() -> None:
    args = _parser().parse_args()
    stop_bot(pid_file=args.pid_file)


def status_main() -> None:
    args = _parser().parse_args()
    bot_status(pid_file=args.pid_file, log_file=args.log_file)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the Reference Bookstore Discord bot process.")
    parser.add_argument("--pid-file", default=os.getenv("REFERENCE_BOT_PID_FILE", DEFAULT_PID_FILE))
    parser.add_argument("--log-file", default=os.getenv("REFERENCE_BOT_LOG_FILE", DEFAULT_LOG_FILE))
    return parser


def _read_pid(pid_path: Path) -> int | None:
    try:
        raw = pid_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _is_bot_process(pid: int) -> bool:
    return _is_running(pid)
