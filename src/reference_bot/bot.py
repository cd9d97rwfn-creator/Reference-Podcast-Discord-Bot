from __future__ import annotations

import asyncio
import logging
import os
import re
import sqlite3
import threading
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable

import discord
from discord import app_commands

LOGGER = logging.getLogger("reference_bot")
DISCORD_MESSAGE_LIMIT = 1900


def _env_database_path() -> str:
    configured = os.getenv("DATABASE_PATH", "episodes.sqlite3")
    path = Path(configured)
    if path.exists():
        return str(path)

    # Compatibility with the Docker image and older project layout.
    fallbacks = [Path("/app/data/episodes.sqlite3"), Path("data/episodes.sqlite3"), Path("episodes.sqlite3")]
    for fallback in fallbacks:
        if fallback.exists():
            return str(fallback)
    return configured


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_env_database_path())
    connection.row_factory = sqlite3.Row
    return connection


def _truncate(value: str, limit: int = DISCORD_MESSAGE_LIMIT) -> str:
    value = value.strip()
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _published_timestamp(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _episode_number_from_title(title: str) -> int | None:
    match = re.search(r"(?:EP\.?|第)\s*(\d{1,4})", title, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _episode_number_from_question(question: str) -> int | None:
    patterns = [r"第\s*(\d{1,4})\s*集", r"(?:EP\.?|episode)\s*(\d{1,4})", r"^(\d{1,4})\s*集"]
    for pattern in patterns:
        match = re.search(pattern, question, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _format_episode_summary_answer(question: str, episode_number: int, summary: object | None) -> str:
    del question
    if summary is None:
        return f"目前找不到第 {episode_number} 集的摘要資料。你可以改用 `/mentioned` 搜尋關鍵字。"
    if isinstance(summary, sqlite3.Row):
        key_points = [line.strip(" -") for line in (summary["key_points_text"] or "").splitlines() if line.strip()]
        lines = [summary["title"], "", summary["one_sentence_summary"]]
        if key_points:
            lines.extend(["", "重點：", *[f"- {point}" for point in key_points[:5]]])
        return _truncate("\n".join(lines))
    return f"第 {episode_number} 集有資料，但目前無法格式化摘要。"


def _fallback_transcript_query(question: str) -> str:
    cleaned = re.sub(r"[？?！!，,。\.、：:；;（）()\[\]{}]", " ", question)
    # Chinese questions often contain no spaces, so remove conversational wrappers
    # as substrings instead of relying only on word splitting.
    stop_phrases = (
        "有沒有", "是否", "請問", "可以", "幫我", "想知道", "曾經", "節目中",
        "討論過", "討論", "聊過", "聊到", "介紹過", "介紹", "提過", "提到",
        "相關的", "相關", "內容", "集數", "哪一集", "哪些集", "這一集",
        "這集", "一集", "這本書", "這本", "本書", "書籍", "這個概念",
        "這個主題", "這個", "podcast", "Podcast",
    )
    for phrase in stop_phrases:
        cleaned = cleaned.replace(phrase, " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or question.strip()


def _query_variants(query: str) -> list[str]:
    cleaned = _fallback_transcript_query(query)
    variants = [cleaned]
    normalized = cleaned.lower()
    if "慣習" in cleaned or "habitus" in normalized:
        variants.extend(["慣習", "habitus", "Habitus"])
    if "文化資本" in cleaned:
        variants.extend(["文化資本", "七種資本", "慣習"])

    unique: list[str] = []
    for variant in variants:
        variant = variant.strip()
        if variant and variant not in unique:
            unique.append(variant)
    return unique or [query.strip()]


def _merge_rows_by_episode(rows_by_query: Iterable[list[sqlite3.Row]]) -> list[sqlite3.Row]:
    seen: set[str] = set()
    merged: list[sqlite3.Row] = []
    for rows in rows_by_query:
        for row in rows:
            if "name" in row.keys():
                key = f"{row['title']}:{row['name']}"
            elif "guid" in row.keys():
                key = row["guid"]
            else:
                key = f"{row['title']}:{len(merged)}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(row)
    return merged


def _excerpt_around_query(text: str, query: str, context: int = 130) -> str:
    compact = " ".join(text.split())
    terms = _query_variants(query)
    lowered = compact.lower()
    index = -1
    match_length = 0
    for term in terms:
        term_index = lowered.find(term.lower())
        if term_index >= 0 and (index < 0 or term_index < index):
            index = term_index
            match_length = len(term)
    if index < 0:
        return compact[: context * 2].rstrip()
    start = max(0, index - context)
    end = min(len(compact), index + match_length + context)
    prefix = "..." if start else ""
    suffix = "..." if end < len(compact) else ""
    return f"{prefix}{compact[start:end].strip()}{suffix}"


def _first_result_per_episode(results: Iterable[object]) -> list[object]:
    seen: set[str] = set()
    unique: list[object] = []
    for result in results:
        guid = getattr(getattr(result, "episode", None), "guid", None) or getattr(result, "episode_guid", None)
        if guid in seen:
            continue
        if guid:
            seen.add(guid)
        unique.append(result)
    return unique


def _like_query(query: str) -> str:
    return f"%{query.strip()}%"


def _recent_episodes(limit: int) -> list[sqlite3.Row]:
    with _connect() as connection:
        rows = list(connection.execute("SELECT title, published_at, episode_url FROM episodes"))
    rows.sort(key=lambda row: _published_timestamp(row["published_at"]), reverse=True)
    return rows[:limit]


def _search_episode_summaries(query: str, limit: int = 5) -> list[sqlite3.Row]:
    like = _like_query(query)
    with _connect() as connection:
        return list(
            connection.execute(
                """
                SELECT e.guid, e.title, e.episode_url, e.published_at,
                       s.one_sentence_summary, s.key_points_text, s.topics_text
                FROM episode_summaries s
                JOIN episodes e ON e.guid = s.episode_guid
                WHERE e.title LIKE ? COLLATE NOCASE
                   OR s.one_sentence_summary LIKE ? COLLATE NOCASE
                   OR s.key_points_text LIKE ? COLLATE NOCASE
                   OR s.topics_text LIKE ? COLLATE NOCASE
                LIMIT ?
                """,
                (like, like, like, like, limit),
            )
        )


def _summary_by_episode_number(number: int) -> sqlite3.Row | None:
    with _connect() as connection:
        rows = list(
            connection.execute(
                """
                SELECT e.title, e.episode_url, s.one_sentence_summary, s.key_points_text, s.topics_text
                FROM episode_summaries s
                JOIN episodes e ON e.guid = s.episode_guid
                """
            )
        )
    for row in rows:
        if _episode_number_from_title(row["title"]) == number:
            return row
    return None


def _search_mentions(table: str, query: str, limit: int = 8) -> list[sqlite3.Row]:
    if table not in {"book_mentions", "concept_mentions"}:
        raise ValueError("unsupported mention table")
    like = _like_query(query)
    with _connect() as connection:
        return list(
            connection.execute(
                f"""
                SELECT e.title, e.episode_url, m.name, m.mention_level, m.evidence
                FROM {table} m
                JOIN episodes e ON e.guid = m.episode_guid
                WHERE m.name LIKE ? COLLATE NOCASE
                   OR m.evidence LIKE ? COLLATE NOCASE
                   OR e.title LIKE ? COLLATE NOCASE
                LIMIT ?
                """,
                (like, like, like, limit),
            )
        )


def _search_transcripts(query: str, limit: int = 6) -> list[sqlite3.Row]:
    like = _like_query(query)
    with _connect() as connection:
        return list(
            connection.execute(
                """
                SELECT e.guid, e.title, e.episode_url, t.chunk_text
                FROM transcript_chunks t
                JOIN episodes e ON e.guid = t.episode_guid
                WHERE t.chunk_text LIKE ? COLLATE NOCASE
                   OR e.title LIKE ? COLLATE NOCASE
                LIMIT ?
                """,
                (like, like, limit),
            )
        )


def _format_search_rows(rows: list[sqlite3.Row], heading: str) -> str:
    if not rows:
        return "目前沒有找到明確結果。可以換一個更短、比較核心的關鍵字再試一次。"
    lines = [heading]
    for index, row in enumerate(rows, start=1):
        title = row["title"]
        detail = row["name"] if "name" in row.keys() else row["one_sentence_summary"]
        lines.append(f"{index}. {title}")
        if detail:
            lines.append(f"   {detail}")
        if row["episode_url"]:
            lines.append(f"   {row['episode_url']}")
    return _truncate("\n".join(lines))


def _answer_locally(question: str) -> str:
    episode_number = _episode_number_from_question(question)
    if episode_number is not None:
        return _format_episode_summary_answer(question, episode_number, _summary_by_episode_number(episode_number))

    search_query = _fallback_transcript_query(question)
    variants = _query_variants(question)
    summaries = _merge_rows_by_episode(_search_episode_summaries(variant, limit=4) for variant in variants)[:4]
    books = _merge_rows_by_episode(_search_mentions("book_mentions", variant, limit=3) for variant in variants)[:3]
    concepts = _merge_rows_by_episode(_search_mentions("concept_mentions", variant, limit=4) for variant in variants)[:4]
    transcripts = _merge_rows_by_episode(_search_transcripts(variant, limit=4) for variant in variants)[:4]

    if not any((summaries, books, concepts, transcripts)):
        return (
            f"你問：{question}\n\n"
            "目前沒有找到明確結果。建議改用 `/book`、`/topic` 或 `/mentioned` 搭配較短的關鍵字。"
        )

    lines = [f"你問：{question}", ""]
    if summaries:
        lines.append("可能相關的集數：")
        for row in summaries:
            lines.append(f"- {row['title']}：{row['one_sentence_summary']}")
    if books:
        lines.append("\n書籍索引：")
        for row in books:
            lines.append(f"- 《{row['name']}》— {row['title']}")
    if concepts:
        lines.append("\n概念索引：")
        for row in concepts:
            lines.append(f"- {row['name']} — {row['title']}")
    if transcripts:
        lines.append("\n逐字稿線索：")
        seen: set[str] = set()
        for row in transcripts:
            if row["guid"] in seen:
                continue
            seen.add(row["guid"])
            excerpt = _excerpt_around_query(row["chunk_text"], search_query, context=80)
            lines.append(f"- {row['title']}：{excerpt}…")
    lines.append("\n註：這是資料庫關鍵字檢索結果，不代表該集完整內容只限於上述主題。")
    return _truncate("\n".join(lines))


class ReferenceBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self._commands_synced = False

    async def setup_hook(self) -> None:
        self._register_commands()

    def _register_commands(self) -> None:
        @self.tree.command(name="ping", description="確認機器人是否在線")
        async def ping(interaction: discord.Interaction) -> None:
            latency_ms = round(self.latency * 1000)
            await interaction.response.send_message(f"Pong! 🏓 延遲約 {latency_ms} ms")

        @self.tree.command(name="episodes", description="列出最近的 Podcast 集數")
        @app_commands.describe(limit="顯示幾集（1 到 10）")
        async def episodes(interaction: discord.Interaction, limit: app_commands.Range[int, 1, 10] = 5) -> None:
            await interaction.response.defer(thinking=True)
            rows = await asyncio.to_thread(_recent_episodes, int(limit))
            if not rows:
                await interaction.followup.send("資料庫目前沒有集數。")
                return
            lines = ["最近的集數："]
            for index, row in enumerate(rows, start=1):
                lines.append(f"{index}. {row['title']}")
                if row["episode_url"]:
                    lines.append(f"   {row['episode_url']}")
            await interaction.followup.send(_truncate("\n".join(lines)))

        @self.tree.command(name="book", description="搜尋節目中提過的書")
        @app_commands.describe(query="書名或關鍵字")
        async def book(interaction: discord.Interaction, query: str) -> None:
            await interaction.response.defer(thinking=True)
            rows = await asyncio.to_thread(
                lambda: _merge_rows_by_episode(_search_mentions("book_mentions", variant, 8) for variant in _query_variants(query))[:8]
            )
            await interaction.followup.send(_format_search_rows(rows, f"書籍搜尋：{query}"))

        @self.tree.command(name="topic", description="搜尋節目主題與概念")
        @app_commands.describe(query="主題或關鍵字")
        async def topic(interaction: discord.Interaction, query: str) -> None:
            await interaction.response.defer(thinking=True)
            rows = await asyncio.to_thread(
                lambda: _merge_rows_by_episode(_search_mentions("concept_mentions", variant, 8) for variant in _query_variants(query))[:8]
            )
            await interaction.followup.send(_format_search_rows(rows, f"主題搜尋：{query}"))

        @self.tree.command(name="mentioned", description="搜尋逐字稿中出現的關鍵字")
        @app_commands.describe(query="要搜尋的關鍵字")
        async def mentioned(interaction: discord.Interaction, query: str) -> None:
            await interaction.response.defer(thinking=True)
            rows = await asyncio.to_thread(_search_transcripts, query, 6)
            if not rows:
                await interaction.followup.send("逐字稿裡目前沒有找到明確結果。")
                return
            lines = [f"逐字稿搜尋：{query}"]
            seen: set[str] = set()
            for row in rows:
                if row["guid"] in seen:
                    continue
                seen.add(row["guid"])
                excerpt = _excerpt_around_query(row["chunk_text"], query, context=130)
                lines.append(f"- {row['title']}\n  {excerpt}…")
            await interaction.followup.send(_truncate("\n".join(lines)))

        @self.tree.command(name="ask", description="用自然語言詢問節目內容")
        @app_commands.describe(question="例如：有沒有聊過職業倦怠？")
        async def ask(interaction: discord.Interaction, question: str) -> None:
            await interaction.response.defer(thinking=True)
            answer = await asyncio.to_thread(_answer_locally, question)
            await interaction.followup.send(answer)

    async def on_ready(self) -> None:
        if self._commands_synced:
            LOGGER.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "unknown")
            return

        # Global commands make the bot usable in every server where it is installed.
        global_commands = await self.tree.sync()
        LOGGER.info("Synced %d global slash commands", len(global_commands))

        # Optional guild sync provides immediate command visibility while testing.
        raw_guild_ids = ",".join(
            value for value in (os.getenv("DISCORD_GUILD_ID", ""), os.getenv("DISCORD_GUILD_IDS", "")) if value
        )
        guild_ids: set[int] = set()
        for value in raw_guild_ids.split(","):
            value = value.strip()
            if value.isdigit():
                guild_ids.add(int(value))
        for guild_id in sorted(guild_ids):
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            guild_commands = await self.tree.sync(guild=guild)
            LOGGER.info("Synced %d slash commands to guild %s", len(guild_commands), guild_id)

        self._commands_synced = True
        LOGGER.info("Bot is ready as %s (%s)", self.user, self.user.id if self.user else "unknown")

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or self.user is None:
            return
        if self.user in message.mentions:
            await message.channel.send("我在！請輸入 `/`，再選擇 `/ping`、`/ask` 或其他指令。")


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib API name
        if self.path in {"/", "/health", "/healthz"}:
            body = b"reference-discord-bot: ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        LOGGER.debug("health server: " + format, *args)


def _start_health_server() -> None:
    port = int(os.getenv("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, name="health-server", daemon=True)
    thread.start()
    LOGGER.info("Health server listening on port %d", port)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set")

    database_path = _env_database_path()
    if not Path(database_path).exists():
        raise RuntimeError(f"Database file not found: {database_path}")
    LOGGER.info("Using database: %s", database_path)

    _start_health_server()
    ReferenceBot().run(token, log_handler=None)


if __name__ == "__main__":
    main()
