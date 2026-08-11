from __future__ import annotations

import asyncio
import logging
import os
import random
import re

import discord

from reference_bot.answer_synthesis import DEFAULT_ASK_MODEL
from reference_bot.ask import answer_question, format_podcast_no_match_answer
from reference_bot.config import Settings, load_settings
from reference_bot.episodes import (
    BookMention,
    ConceptCluster,
    ConceptMention,
    ConceptRelationship,
    Episode,
    EpisodeSummary,
    TranscriptSearchResult,
)


LOGGER = logging.getLogger(__name__)
BOT_DISPLAY_NAME = "引引"


PING_RESPONSES = (
    "喵，店門有開，引引也醒著。今天可以幫你查引書店的集數、書和概念。",
    "在喔。貓咪工讀生引引已經坐回櫃檯，資料庫也乖乖待命中。",
    "喵嗚，連線正常。你可以開始丟問題，引引來幫你翻摘要書架和逐字稿抽屜。",
    "收到。引書店的貓咪工讀生引引在線，尾巴晃一下表示系統正常。",
)


class ReferenceBot(discord.Client):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.settings = settings
        self.tree = discord.app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        if self.settings.discord_guild_ids:
            for guild_id in self.settings.discord_guild_ids:
                guild = discord.Object(id=guild_id)
                self.tree.clear_commands(guild=guild)
                await self.tree.sync(guild=guild)
                LOGGER.info("Removed slash commands from guild %s", guild_id)

        self.tree.clear_commands(guild=None)
        await self.tree.sync()
        LOGGER.info("Removed global slash commands")

    async def on_ready(self) -> None:
        for guild in self.guilds:
            member = guild.me
            if member is None or member.nick == BOT_DISPLAY_NAME:
                continue
            try:
                await member.edit(nick=BOT_DISPLAY_NAME, reason="Set the bot persona display name")
                LOGGER.info("Set bot nickname to %s in guild %s", BOT_DISPLAY_NAME, guild.id)
            except discord.Forbidden:
                LOGGER.warning(
                    "Could not set bot nickname in guild %s; grant the bot Change Nickname permission",
                    guild.id,
                )
            except discord.HTTPException as exc:
                LOGGER.warning("Could not set bot nickname in guild %s: %s", guild.id, exc)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or self.user is None:
            return

        is_direct_message = message.guild is None
        mentions_bot = self.user in message.mentions
        if not is_direct_message and not mentions_bot:
            return

        question = _strip_bot_mention(message.content, self.user.id)
        if not question:
            await message.reply("直接問我引書店節目、書籍或概念就可以了，喵。", mention_author=False)
            return

        if question.casefold() in {"ping", "在嗎", "在嗎？"}:
            await message.reply(_format_ping_response(), mention_author=False)
            return

        async with message.channel.typing():
            result = await asyncio.to_thread(
                answer_question,
                database_path=self.settings.database_path,
                question=question,
                api_key=os.getenv("OPENAI_API_KEY", "").strip() or None,
                model=os.getenv("OPENAI_ASK_MODEL", DEFAULT_ASK_MODEL).strip() or DEFAULT_ASK_MODEL,
            )
        await message.reply(_truncate_discord_message(result.answer), mention_author=False)


def _format_ping_response() -> str:
    return random.choice(PING_RESPONSES)


def _strip_bot_mention(content: str, bot_user_id: int) -> str:
    without_mention = re.sub(rf"<@!?{bot_user_id}>", " ", content)
    return re.sub(r"\s+", " ", without_mention).strip()


def _format_episodes_response(indexed_episodes: list[Episode]) -> str:
    if not indexed_episodes:
        return "No indexed episodes found yet."

    lines = ["Recently indexed episodes:"]
    for index, episode in enumerate(indexed_episodes, start=1):
        published_at = episode.published_at or "unknown date"
        lines.append(f"{index}. {episode.title}")
        lines.append(f"   Published: {published_at}")
    return _truncate_discord_message("\n".join(lines))


def _format_mentioned_response(query: str, results: list[TranscriptSearchResult]) -> str:
    if not results:
        return f"沒有找到逐字稿關鍵字命中：{query}"

    deduped_results = _first_result_per_episode(results)
    lines = [
        f"逐字稿關鍵字命中：{query}",
        "注意：這不是摘要或主題判斷，只代表逐字稿片段出現這個詞。",
        "目前 MacWhisper CLI 逐字稿不含時間戳。",
    ]
    for index, result in enumerate(deduped_results, start=1):
        lines.append(f"{index}. {result.episode.title}")
        lines.append(f"   證據片段: {_excerpt(result.chunk_text, query)}")
    return _truncate_discord_message("\n".join(lines))


def _format_book_response(query: str, results: list[BookMention]) -> str:
    if not results:
        return f"沒有找到書籍索引命中：{query}"

    lines = [
        f"書籍索引命中：{query}",
        "注意：mention level 代表節目中的討論程度，不等於完整書摘。",
    ]
    for index, mention in enumerate(results, start=1):
        lines.append(f"{index}. 《{mention.name}》")
        lines.append(f"   集數：{mention.episode.title}")
        lines.append(f"   程度：{mention.mention_level}")
        if mention.evidence:
            lines.append(f"   線索：{_short_line(mention.evidence)}")
    return _truncate_discord_message("\n".join(lines))


def _format_topic_response(
    query: str,
    results: list[ConceptMention],
    clusters: list[ConceptCluster] | None = None,
    relationships: list[ConceptRelationship] | None = None,
) -> str:
    clusters = clusters or []
    relationships = relationships or []
    if not results and not clusters and not relationships:
        return f"沒有找到主題/概念索引命中：{query}"

    lines = [
        f"主題/概念索引命中：{query}",
        "注意：這是 summary index 的保守索引；需要時可換關鍵字再問我查逐字稿證據。",
    ]
    if clusters:
        lines.extend(["", "概念地圖："])
        for cluster in clusters[:4]:
            label = cluster.mention_name
            if cluster.mention_name != cluster.cluster_name:
                label = f"{cluster.cluster_name} -> {cluster.mention_name}"
            lines.append(f"- {label}｜{cluster.episode.title}")
    if relationships:
        lines.extend(["", "概念關係："])
        for relationship in relationships[:3]:
            lines.append(
                f"- {relationship.source_name} {relationship.relation_type} "
                f"{relationship.target_name}｜{relationship.episode.title}"
            )
    if not results:
        return _truncate_discord_message("\n".join(lines))

    lines.extend(["", "索引命中："])
    for index, mention in enumerate(results, start=1):
        lines.append(f"{index}. {mention.name}")
        lines.append(f"   集數：{mention.episode.title}")
        lines.append(f"   程度：{mention.mention_level}")
        if mention.evidence:
            lines.append(f"   線索：{_short_line(mention.evidence)}")
    return _truncate_discord_message("\n".join(lines))


def _format_episode_summary_answer(
    question: str,
    episode_number: int,
    summary: EpisodeSummary | None,
) -> str:
    if summary is None:
        return (
            f"我有看懂你在問 EP.{episode_number}，但目前還沒有這集的 summary index。"
            "可以先跑 `reference-generate-summaries` 產生摘要。"
        )

    lines = [
        f"你問：{question}",
        f"EP.{episode_number}: {summary.episode.title}",
        "",
        summary.one_sentence_summary,
        "",
        "重點：",
    ]
    lines.extend([f"- {point}" for point in summary.key_points[:4]])
    if summary.topics:
        lines.extend(["", "主題：", ", ".join(summary.topics[:6])])
    if summary.generated_by.startswith("openai_"):
        lines.extend(["", "注意：這是 OpenAI 結構化摘要；若 Obsidian note 有人工修正，應以修正版為準。"])
    else:
        lines.extend(["", "注意：這是本地規則產生的保守摘要，之後可升級成 LLM 結構化摘要。"])
    return _truncate_discord_message("\n".join(lines))


def _format_natural_language_answer(
    question: str,
    summaries: list[EpisodeSummary],
    transcript_results: list[TranscriptSearchResult],
) -> str:
    if not summaries and not transcript_results:
        return format_podcast_no_match_answer(question)

    lines = [f"你問：{question}", ""]
    if summaries:
        lines.append("感謝您的詢問，目前引書店Podcast的摘要有這些可能集數：")
        for index, summary in enumerate(summaries, start=1):
            lines.append(f"{index}. {summary.episode.title}")
            lines.append(f"   {summary.one_sentence_summary}")
            matching_points = _matching_lines(question, summary.key_points + summary.topics)
            if matching_points:
                lines.append(f"   相關線索：{matching_points[0]}")

    transcript_only = _first_result_per_episode(transcript_results)
    if transcript_only:
        lines.extend(["", "逐字稿也找到一些線索："])
        for index, result in enumerate(transcript_only[:3], start=1):
            lines.append(f"{index}. {result.episode.title}")
            lines.append("   片段：")
            lines.append(_indent_block(_readable_excerpt(result.chunk_text, _fallback_transcript_query(question))))
        lines.append("注意：逐字稿線索只代表片段命中，不一定代表該集主題。")

    return _truncate_discord_message("\n".join(lines))


def _episode_number_from_question(question: str) -> int | None:
    patterns = [
        r"\bEP\.?\s*(\d{1,4})\b",
        r"\bep\.?\s*(\d{1,4})\b",
        r"第\s*(\d{1,4})\s*集",
        r"\b(\d{1,4})\s*集",
    ]
    for pattern in patterns:
        match = re.search(pattern, question)
        if match:
            return int(match.group(1))
    return None


def _fallback_transcript_query(question: str) -> str:
    stopwords = {
        "有沒有",
        "是否",
        "請問",
        "聊過",
        "討論過",
        "討論",
        "提到",
        "提過",
        "講過",
        "講到",
        "相關",
        "有關",
        "關於",
        "哪幾集",
        "哪一集",
        "哪些",
        "什麼",
        "嗎",
        "的",
        "跟",
        "和",
    }
    cleaned_question = question
    for stopword in sorted(stopwords, key=len, reverse=True):
        cleaned_question = cleaned_question.replace(stopword, " ")
    terms = [
        term.strip()
        for term in re.split(r"[\s，,。？?：:！!、/「」『』《》（）()]+", cleaned_question)
        if term.strip()
    ]
    useful_terms = [term for term in terms if term not in stopwords]
    if not useful_terms:
        return question.strip()
    return max(useful_terms, key=len)


def _matching_lines(question: str, lines: list[str]) -> list[str]:
    terms = [
        term.strip()
        for term in re.split(r"[\s，,。？?：:！!、/「」『』《》（）()]+", question)
        if len(term.strip()) >= 2
    ]
    matches: list[str] = []
    for line in lines:
        if any(term in line for term in terms):
            matches.append(line)
    return matches


def _first_result_per_episode(
    results: list[TranscriptSearchResult],
) -> list[TranscriptSearchResult]:
    seen_episode_guids: set[str] = set()
    deduped_results: list[TranscriptSearchResult] = []

    for result in results:
        if result.episode.guid in seen_episode_guids:
            continue

        seen_episode_guids.add(result.episode.guid)
        deduped_results.append(result)

    return deduped_results


def _excerpt(text: str, query: str, radius: int = 90) -> str:
    match_index = text.lower().find(query.lower())
    if match_index < 0:
        return text[: radius * 2].strip()

    start = max(0, match_index - radius)
    end = min(len(text), match_index + len(query) + radius)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"


def _readable_excerpt(text: str, query: str, radius: int = 140) -> str:
    excerpt = _excerpt(text, query, radius=radius)
    excerpt = re.sub(r"^##\s*chunk\s+\d+\s+approx\s+\d{2}:\d{2}", "", excerpt).strip()
    excerpt = re.sub(r"\n{3,}", "\n\n", excerpt)
    excerpt = re.sub(r"[ \t]+", " ", excerpt)
    excerpt = _break_long_unpunctuated_lines(excerpt)
    return excerpt.strip()


def _break_long_unpunctuated_lines(text: str, line_length: int = 44) -> str:
    punctuations = "。！？!?；;，,"
    output_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if len(stripped) <= line_length or any(mark in stripped for mark in punctuations):
            output_lines.append(stripped)
            continue

        chunks = [stripped[index : index + line_length] for index in range(0, len(stripped), line_length)]
        output_lines.extend(chunks)
    return "\n".join(output_lines)


def _indent_block(text: str, prefix: str = "   ") -> str:
    return "\n".join(f"{prefix}{line}" if line else "" for line in text.splitlines())


def _short_line(text: str, limit: int = 160) -> str:
    cleaned_text = re.sub(r"\s+", " ", text).strip()
    if len(cleaned_text) <= limit:
        return cleaned_text
    return cleaned_text[: limit - 3].rstrip() + "..."


def _truncate_discord_message(value: str, limit: int = 1900) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    bot = ReferenceBot(settings)
    bot.run(settings.discord_token)


if __name__ == "__main__":
    main()
