from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import sys
import threading
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from reference_bot.bot import main


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in {"/", "/health"}:
            self._send_text("ok\n")
            return

        if self.path == "/diag":
            self._send_json(_deployment_diagnostics())
            return

        if self.path == "/diag.txt":
            self._send_text(_deployment_diagnostics_text())
            return

        if self.path not in {"/", "/health"}:
            self.send_response(404)
            self.end_headers()
            return

    def _send_text(self, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def _deployment_diagnostics() -> dict[str, object]:
    database_path = os.getenv("DATABASE_PATH", "data/episodes.sqlite3").strip() or "data/episodes.sqlite3"
    path = Path(database_path)
    guild_ids = os.getenv("DISCORD_GUILD_IDS", "").strip()
    legacy_guild_id = os.getenv("DISCORD_GUILD_ID", "").strip()
    commit = os.getenv("RENDER_GIT_COMMIT") or os.getenv("RENDER_COMMIT") or ""

    diagnostics: dict[str, object] = {
        "status": "ok",
        "database_path": database_path,
        "database_exists": path.exists(),
        "database_size_bytes": path.stat().st_size if path.exists() else 0,
        "discord_guild_ids_configured": _configured_guild_count(guild_ids or legacy_guild_id),
        "discord_guild_ids_source": "DISCORD_GUILD_IDS" if guild_ids else "DISCORD_GUILD_ID" if legacy_guild_id else "global",
        "render_git_commit": commit[:12] if commit else "",
    }

    if path.exists():
        try:
            diagnostics["counts"] = _database_counts(path)
        except sqlite3.Error as exc:
            diagnostics["status"] = "error"
            diagnostics["database_error"] = str(exc)
    return diagnostics


def _deployment_diagnostics_text() -> str:
    diagnostics = _deployment_diagnostics()
    lines = [
        f"status: {diagnostics['status']}",
        f"database_path: {diagnostics['database_path']}",
        f"database_exists: {diagnostics['database_exists']}",
        f"database_size_bytes: {diagnostics['database_size_bytes']}",
        f"discord_guild_ids_configured: {diagnostics['discord_guild_ids_configured']}",
        f"discord_guild_ids_source: {diagnostics['discord_guild_ids_source']}",
        f"render_git_commit: {diagnostics['render_git_commit']}",
    ]
    counts = diagnostics.get("counts")
    if isinstance(counts, dict):
        lines.append("counts:")
        for key, value in counts.items():
            lines.append(f"  {key}: {value}")
    if "database_error" in diagnostics:
        lines.append(f"database_error: {diagnostics['database_error']}")
    return "\n".join(lines) + "\n"


def _database_counts(path: Path) -> dict[str, int]:
    with sqlite3.connect(path) as connection:
        return {
            "episodes": _count(connection, "episodes"),
            "episode_summaries": _count(connection, "episode_summaries"),
            "transcript_episodes": _count_distinct(connection, "transcript_chunks", "episode_guid"),
            "transcript_chunks": _count(connection, "transcript_chunks"),
            "book_mentions": _count(connection, "book_mentions"),
            "concept_mentions": _count(connection, "concept_mentions"),
            "concept_clusters": _count(connection, "concept_clusters"),
            "concept_relationships": _count(connection, "concept_relationships"),
        }


def _count(connection: sqlite3.Connection, table_name: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])


def _count_distinct(connection: sqlite3.Connection, table_name: str, column_name: str) -> int:
    return int(connection.execute(f"SELECT COUNT(DISTINCT {column_name}) FROM {table_name}").fetchone()[0])


def _configured_guild_count(raw_value: str) -> int:
    if not raw_value:
        return 0
    return len([item for item in raw_value.split(",") if item.strip()])


def start_health_server() -> None:
    port = int(os.getenv("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()


if __name__ == "__main__":
    start_health_server()
    main()
