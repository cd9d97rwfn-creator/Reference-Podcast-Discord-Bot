from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import sqlite3

from reference_bot.concept_map_eval import evaluate_concept_map


@dataclass(frozen=True)
class HealthCheck:
    status: str
    name: str
    detail: str


@dataclass(frozen=True)
class HealthReport:
    checks: list[HealthCheck]

    @property
    def ok(self) -> bool:
        return all(check.status != "FAIL" for check in self.checks)


def run_healthcheck(
    *,
    database_path: str,
    min_episodes: int = 50,
    min_summaries: int = 50,
    min_transcript_episodes: int = 50,
    min_eval_pass: int = 12,
    run_eval: bool = True,
) -> HealthReport:
    checks: list[HealthCheck] = []
    path = Path(database_path)

    if not path.exists():
        checks.append(HealthCheck("FAIL", "database", f"missing: {database_path}"))
        checks.extend(_environment_checks())
        return HealthReport(checks)

    checks.append(HealthCheck("OK", "database", f"found: {database_path}"))

    try:
        counts = _database_counts(path)
    except sqlite3.Error as exc:
        checks.append(HealthCheck("FAIL", "database", f"cannot read SQLite database: {exc}"))
        checks.extend(_environment_checks())
        return HealthReport(checks)

    checks.append(
        _threshold_check(
            "episodes",
            counts["episodes"],
            min_episodes,
            "episodes in SQLite",
        )
    )
    checks.append(
        _threshold_check(
            "summaries",
            counts["episode_summaries"],
            min_summaries,
            "structured episode summaries",
        )
    )
    checks.append(
        _threshold_check(
            "transcript_index",
            counts["transcript_episodes"],
            min_transcript_episodes,
            "episodes with transcript chunks",
        )
    )
    checks.append(
        _positive_check(
            "book_index",
            counts["book_mentions"],
            "book mentions indexed",
        )
    )
    checks.append(
        _positive_check(
            "concept_index",
            counts["concept_mentions"],
            "concept mentions indexed",
        )
    )
    checks.append(
        _positive_check(
            "concept_map",
            counts["concept_clusters"],
            "concept clusters indexed",
        )
    )
    checks.append(
        _positive_check(
            "concept_relationships",
            counts["concept_relationships"],
            "concept relationships indexed",
        )
    )

    if run_eval:
        results = evaluate_concept_map(str(path), limit=8)
        passed = sum(1 for result in results if result.status == "PASS")
        status = "OK" if passed >= min_eval_pass else "FAIL"
        checks.append(
            HealthCheck(
                status,
                "concept_map_eval",
                f"{passed}/{len(results)} PASS, minimum {min_eval_pass}",
            )
        )
    else:
        checks.append(HealthCheck("WARN", "concept_map_eval", "skipped"))

    checks.extend(_environment_checks())
    return HealthReport(checks)


def format_health_report(report: HealthReport) -> str:
    heading = "Healthcheck: OK" if report.ok else "Healthcheck: FAIL"
    lines = [heading, ""]
    for check in report.checks:
        lines.append(f"[{check.status}] {check.name}: {check.detail}")
    return "\n".join(lines)


def _database_counts(path: Path) -> dict[str, int]:
    with sqlite3.connect(path) as connection:
        return {
            "episodes": _count(connection, "episodes"),
            "episode_summaries": _count(connection, "episode_summaries"),
            "transcript_episodes": _count_distinct(connection, "transcript_chunks", "episode_guid"),
            "book_mentions": _count(connection, "book_mentions"),
            "concept_mentions": _count(connection, "concept_mentions"),
            "concept_clusters": _count(connection, "concept_clusters"),
            "concept_relationships": _count(connection, "concept_relationships"),
        }


def _count(connection: sqlite3.Connection, table_name: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])


def _count_distinct(connection: sqlite3.Connection, table_name: str, column_name: str) -> int:
    return int(
        connection.execute(
            f"SELECT COUNT(DISTINCT {column_name}) FROM {table_name}"
        ).fetchone()[0]
    )


def _threshold_check(name: str, value: int, minimum: int, label: str) -> HealthCheck:
    status = "OK" if value >= minimum else "FAIL"
    return HealthCheck(status, name, f"{value} {label}, minimum {minimum}")


def _positive_check(name: str, value: int, label: str) -> HealthCheck:
    status = "OK" if value > 0 else "FAIL"
    return HealthCheck(status, name, f"{value} {label}")


def _environment_checks() -> list[HealthCheck]:
    checks = [
        _required_secret_check("DISCORD_TOKEN", "required to run the Discord bot"),
        _optional_value_check("DISCORD_GUILD_ID", "optional; useful for faster slash command sync"),
        _optional_value_check("DATABASE_PATH", "optional; defaults to data/episodes.sqlite3"),
        _optional_value_check("OPENAI_API_KEY", "optional; enables LLM answer synthesis"),
        _optional_value_check("PODCAST_RSS_URL", "optional for bot runtime; required for RSS refresh"),
    ]
    return checks


def _required_secret_check(name: str, detail: str) -> HealthCheck:
    value = os.getenv(name, "").strip()
    if not value or value.startswith("replace-with"):
        return HealthCheck("FAIL", name, f"missing or placeholder; {detail}")
    return HealthCheck("OK", name, f"set; {detail}")


def _optional_value_check(name: str, detail: str) -> HealthCheck:
    value = os.getenv(name, "").strip()
    if not value or value.startswith("replace-with"):
        return HealthCheck("WARN", name, f"not set; {detail}")
    return HealthCheck("OK", name, f"set; {detail}")


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(description="Check whether the podcast bot is ready for beta deployment.")
    parser.add_argument("--database-path", default=os.getenv("DATABASE_PATH", "data/episodes.sqlite3"))
    parser.add_argument("--min-episodes", type=int, default=50)
    parser.add_argument("--min-summaries", type=int, default=50)
    parser.add_argument("--min-transcript-episodes", type=int, default=50)
    parser.add_argument("--min-eval-pass", type=int, default=12)
    parser.add_argument("--skip-eval", action="store_true")
    args = parser.parse_args()

    report = run_healthcheck(
        database_path=args.database_path,
        min_episodes=args.min_episodes,
        min_summaries=args.min_summaries,
        min_transcript_episodes=args.min_transcript_episodes,
        min_eval_pass=args.min_eval_pass,
        run_eval=not args.skip_eval,
    )
    print(format_health_report(report))
    raise SystemExit(0 if report.ok else 1)


if __name__ == "__main__":
    main()
