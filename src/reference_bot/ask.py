from __future__ import annotations

from dataclasses import dataclass
import re

from reference_bot.answer_synthesis import DEFAULT_ASK_MODEL, synthesize_answer
from reference_bot.episodes import (
    BookMention,
    ConceptCluster,
    ConceptMention,
    ConceptRelationship,
    EpisodeSummary,
    TranscriptSearchResult,
)
from reference_bot.storage import (
    get_episode_summary_by_number,
    search_book_mentions,
    search_concept_clusters,
    search_concept_mentions,
    search_concept_relationships,
    search_episode_summaries,
    search_transcript_chunks,
)


@dataclass(frozen=True)
class AskResult:
    answer: str
    book_mentions: list[BookMention]
    concept_mentions: list[ConceptMention]
    concept_clusters: list[ConceptCluster]
    concept_relationships: list[ConceptRelationship]
    summaries: list[EpisodeSummary]
    transcript_results: list[TranscriptSearchResult]
    used_llm: bool


def answer_question(
    *,
    database_path: str,
    question: str,
    api_key: str | None = None,
    model: str = DEFAULT_ASK_MODEL,
) -> AskResult:
    from reference_bot.bot import (
        _episode_number_from_question,
        _fallback_transcript_query,
        _first_result_per_episode,
        _format_episode_summary_answer,
    )

    episode_number = _episode_number_from_question(question)
    if episode_number is not None:
        summary = get_episode_summary_by_number(database_path, episode_number)
        return AskResult(
            answer=_format_episode_summary_answer(question, episode_number, summary),
            book_mentions=[],
            concept_mentions=[],
            concept_clusters=[],
            concept_relationships=[],
            summaries=[summary] if summary else [],
            transcript_results=[],
            used_llm=False,
        )

    book_mentions = search_book_mentions(database_path, query=question, limit=5)
    concept_mentions = search_concept_mentions(database_path, query=question, limit=8)
    concept_clusters = search_concept_clusters(database_path, query=question, limit=8)
    concept_relationships = search_concept_relationships(database_path, query=question, limit=8)
    summaries = search_episode_summaries(database_path, query=question, limit=5)
    transcript_results = search_transcript_chunks(
        database_path,
        query=_fallback_transcript_query(question),
        limit=8,
    )
    transcript_results = _first_result_per_episode(transcript_results)

    if api_key and (book_mentions or concept_mentions or summaries or transcript_results):
        try:
            answer = synthesize_answer(
                api_key=api_key,
                model=model,
                question=question,
                summaries=summaries,
                transcript_results=transcript_results[:3],
                book_mentions=book_mentions,
                concept_mentions=concept_mentions,
                concept_clusters=concept_clusters,
                concept_relationships=concept_relationships,
            )
        except Exception:
            answer = ""
        if answer.strip():
            return AskResult(
                answer=answer.strip(),
                book_mentions=book_mentions,
                concept_mentions=concept_mentions,
                concept_clusters=concept_clusters,
                concept_relationships=concept_relationships,
                summaries=summaries,
                transcript_results=transcript_results,
                used_llm=True,
            )

    fallback_answer = _format_structured_fallback_answer(
        question,
        summaries=summaries,
        transcript_results=transcript_results,
        book_mentions=book_mentions,
        concept_mentions=concept_mentions,
        concept_clusters=concept_clusters,
        concept_relationships=concept_relationships,
        transcript_query=_fallback_transcript_query(question),
    )

    return AskResult(
        answer=fallback_answer,
        book_mentions=book_mentions,
        concept_mentions=concept_mentions,
        concept_clusters=concept_clusters,
        concept_relationships=concept_relationships,
        summaries=summaries,
        transcript_results=transcript_results,
        used_llm=False,
    )


def _format_structured_fallback_answer(
    question: str,
    *,
    summaries: list[EpisodeSummary],
    transcript_results: list[TranscriptSearchResult],
    book_mentions: list[BookMention],
    concept_mentions: list[ConceptMention],
    concept_clusters: list[ConceptCluster],
    concept_relationships: list[ConceptRelationship],
    transcript_query: str,
) -> str:
    has_index_hits = bool(book_mentions or concept_mentions or concept_clusters or concept_relationships)
    if not summaries and not transcript_results and not has_index_hits:
        return _format_no_match_answer(question)

    lines = [f"你問：{question}", "", "簡短回答："]
    if summaries:
        lines.append("感謝您的詢問，有找到摘要索引中可能相關的集數；下面依集數、橫向概念與證據整理。")
    elif transcript_results and has_index_hits:
        lines.append("有找到索引與逐字稿片段，但目前缺少直接命中的摘要；先把可查到的線索保守列出。")
    elif transcript_results:
        lines.append("摘要索引還沒有直接命中，不過逐字稿也找到一些線索；這只代表片段相關。")
    else:
        lines.append("概念/書籍索引先找到這些可能相關項目，但還需要摘要或逐字稿片段作為更強證據。")

    episodes = _rank_related_episodes(
        summaries=summaries,
        transcript_results=transcript_results,
        book_mentions=book_mentions,
        concept_mentions=concept_mentions,
        concept_clusters=concept_clusters,
        concept_relationships=concept_relationships,
    )
    if episodes:
        lines.extend(["", "相關集數："])
        for index, episode in enumerate(episodes[:4], start=1):
            lines.append(f"{index}. {episode.title}")
            summary = _summary_for_episode(summaries, episode.guid)
            if summary:
                lines.append(f"   主軸：{_short_line(summary.one_sentence_summary)}")
            signals = _episode_signals(
                episode.guid,
                book_mentions=book_mentions,
                concept_mentions=concept_mentions,
                concept_clusters=concept_clusters,
                concept_relationships=concept_relationships,
            )
            if signals:
                lines.append(f"   索引：{', '.join(signals[:4])}")

    map_lines = _concept_map_lines(concept_clusters, concept_relationships)
    if map_lines:
        lines.extend(["", "橫向概念：", *map_lines[:5]])

    if concept_mentions or book_mentions:
        lines.extend(["", "概念/書籍索引先找到："])
        for mention in concept_mentions[:5]:
            lines.append(f"- 概念：{mention.name}（{mention.mention_level}，{mention.episode.title}）")
        for mention in book_mentions[:3]:
            lines.append(f"- 書籍：《{mention.name}》（{mention.mention_level}，{mention.episode.title}）")

    transcript_only = _first_result_per_episode_local(transcript_results)
    if transcript_only:
        lines.extend(["", "逐字稿也找到一些線索："])
        for index, result in enumerate(transcript_only[:3], start=1):
            lines.append(f"{index}. {result.episode.title}")
            lines.append(f"   片段：{_readable_excerpt(result.chunk_text, transcript_query)}")

    lines.extend(
        [
            "",
            "注意：這代表目前索引找到相關討論，不等於該集完整摘要了某本書；逐字稿命中也可能只是片段提及。",
        ]
    )
    return _truncate_discord_message("\n".join(lines))


def _format_no_match_answer(question: str) -> str:
    if _looks_off_topic(question):
        return _format_off_topic_answer(question)

    return format_podcast_no_match_answer(question)


def format_podcast_no_match_answer(question: str) -> str:
    return (
        f"你問：{question}\n\n"
        "喵，我剛剛幫你翻了一下引書店的摘要書架和逐字稿抽屜，"
        "目前還沒有找到很明確相關的內容。\n\n"
        "你可以丟給我更接近節目用語的關鍵字，或換個問法再試一次 `/ask`。"
    )


def _format_off_topic_answer(question: str) -> str:
    response = _off_topic_response(question)
    return (
        f"你問：{question}\n\n"
        f"{response}\n\n"
        "我主要負責查「引書店 Podcast」的集數、書籍、概念與逐字稿證據。"
        "你可以改問：`有沒有聊過職業倦怠？`、`哪幾集提到納瓦爾？`、`EP.375 在講什麼？`"
    )


def _off_topic_response(question: str) -> str:
    normalized_question = question.lower()
    if any(term in normalized_question for term in ("你是誰", "你會什麼", "help", "使用說明")):
        return "我是引書店資料查詢 bot，不是通用聊天 bot；我會盡量把問題拉回節目資料。"
    if any(term in question for term in ("天氣", "幾點", "現在時間", "匯率", "股價", "新聞", "路況")):
        return "這題需要即時外部資料，我這裡沒有連外查詢能力，所以先不亂答。"
    if any(term in question for term in ("股票", "投資建議", "醫生", "診斷", "法律", "律師", "報稅")):
        return "這題可能牽涉專業判斷，我只能查節目中是否提過相關內容，不能當成建議。"
    if any(term in question for term in ("講笑話", "唱歌", "寫程式", "作業", "算命", "星座")):
        return "這題有點超出節目查詢範圍，我先把自己收斂一點。"
    return "這題看起來不像在查節目、書籍或概念，我先不硬答。"


def _looks_off_topic(question: str) -> bool:
    if not question.strip():
        return True

    if _has_podcast_query_intent(question):
        return False

    off_topic_terms = {
        "你是誰",
        "你會什麼",
        "help",
        "使用說明",
        "天氣",
        "幾點",
        "現在時間",
        "匯率",
        "股價",
        "新聞",
        "路況",
        "股票",
        "投資建議",
        "醫生",
        "診斷",
        "法律",
        "律師",
        "報稅",
        "講笑話",
        "唱歌",
        "寫程式",
        "作業",
        "算命",
        "星座",
    }
    normalized_question = question.lower()
    return any(term in normalized_question for term in off_topic_terms)


def _has_podcast_query_intent(question: str) -> bool:
    intent_patterns = [
        r"\bep\.?\s*\d{1,4}\b",
        r"第\s*\d{1,4}\s*集",
        r"\b\d{1,4}\s*集",
    ]
    if any(re.search(pattern, question, flags=re.IGNORECASE) for pattern in intent_patterns):
        return True

    intent_terms = {
        "引書店",
        "節目",
        "集數",
        "哪一集",
        "哪幾集",
        "哪集",
        "有沒有聊過",
        "有沒有討論",
        "有沒有提到",
        "聊過",
        "討論過",
        "提到",
        "提過",
        "講過",
        "書",
        "書籍",
        "概念",
        "主題",
        "逐字稿",
        "摘要",
    }
    return any(term in question for term in intent_terms)


def _format_mentions_only_answer(
    question: str,
    *,
    book_mentions: list[BookMention],
    concept_mentions: list[ConceptMention],
    concept_clusters: list[ConceptCluster],
    concept_relationships: list[ConceptRelationship],
) -> str:
    lines = [
        f"你問：{question}",
        "",
        "目前概念/書籍索引先找到這些可能相關項目，但 summary 或逐字稿還沒有直接命中同一個問法：",
    ]
    _append_concept_map_lines(lines, concept_clusters, concept_relationships)
    for mention in concept_mentions[:5]:
        lines.append(f"- 概念：{mention.name}（{mention.mention_level}，{mention.episode.title}）")
    for mention in book_mentions[:3]:
        lines.append(f"- 書籍：《{mention.name}》（{mention.mention_level}，{mention.episode.title}）")
    lines.append("")
    lines.append("注意：這代表索引判斷相關，仍需要摘要或逐字稿片段作為更強證據。")
    return "\n".join(lines)


def _prepend_mentions(
    answer: str,
    *,
    book_mentions: list[BookMention],
    concept_mentions: list[ConceptMention],
    concept_clusters: list[ConceptCluster],
    concept_relationships: list[ConceptRelationship],
) -> str:
    if not book_mentions and not concept_mentions and not concept_clusters and not concept_relationships:
        return answer

    lines = ["索引先找到這些可能相關項目："]
    _append_concept_map_lines(lines, concept_clusters, concept_relationships)
    for mention in concept_mentions[:5]:
        lines.append(f"- 概念：{mention.name}（{mention.mention_level}，{mention.episode.title}）")
    for mention in book_mentions[:3]:
        lines.append(f"- 書籍：《{mention.name}》（{mention.mention_level}，{mention.episode.title}）")
    lines.extend(["", answer])
    return "\n".join(lines)


def _append_concept_map_lines(
    lines: list[str],
    concept_clusters: list[ConceptCluster],
    concept_relationships: list[ConceptRelationship],
) -> None:
    for cluster in concept_clusters[:3]:
        label = cluster.mention_name
        if cluster.mention_name != cluster.cluster_name:
            label = f"{cluster.cluster_name} -> {cluster.mention_name}"
        lines.append(f"- 概念地圖：{label}（{cluster.episode.title}）")
    for relationship in concept_relationships[:2]:
        lines.append(
            f"- 關係：{relationship.source_name} {relationship.relation_type} "
            f"{relationship.target_name}（{relationship.episode.title}）"
        )


def _concept_map_lines(
    concept_clusters: list[ConceptCluster],
    concept_relationships: list[ConceptRelationship],
) -> list[str]:
    lines: list[str] = []
    for cluster in concept_clusters[:3]:
        label = cluster.mention_name
        if cluster.mention_name != cluster.cluster_name:
            label = f"{cluster.cluster_name} -> {cluster.mention_name}"
        lines.append(f"- 概念地圖：{label}（{cluster.episode.title}）")
    for relationship in concept_relationships[:2]:
        lines.append(
            f"- 關係：{relationship.source_name} {relationship.relation_type} "
            f"{relationship.target_name}（{relationship.episode.title}）"
        )
    return lines


def _rank_related_episodes(
    *,
    summaries: list[EpisodeSummary],
    transcript_results: list[TranscriptSearchResult],
    book_mentions: list[BookMention],
    concept_mentions: list[ConceptMention],
    concept_clusters: list[ConceptCluster],
    concept_relationships: list[ConceptRelationship],
):
    scores: dict[str, int] = {}
    episodes_by_guid = {}

    def add(guid: str, episode, score: int) -> None:
        episodes_by_guid.setdefault(guid, episode)
        scores[guid] = scores.get(guid, 0) + score

    for summary in summaries:
        add(summary.episode.guid, summary.episode, 5)
    for cluster in concept_clusters:
        add(cluster.episode.guid, cluster.episode, 3)
    for relationship in concept_relationships:
        add(relationship.episode.guid, relationship.episode, 3)
    for mention in concept_mentions:
        add(mention.episode.guid, mention.episode, 2)
    for mention in book_mentions:
        add(mention.episode.guid, mention.episode, 2)
    for result in transcript_results:
        add(result.episode.guid, result.episode, 1)

    return [
        episodes_by_guid[guid]
        for guid, _score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
    ]


def _summary_for_episode(summaries: list[EpisodeSummary], episode_guid: str) -> EpisodeSummary | None:
    for summary in summaries:
        if summary.episode.guid == episode_guid:
            return summary
    return None


def _episode_signals(
    episode_guid: str,
    *,
    book_mentions: list[BookMention],
    concept_mentions: list[ConceptMention],
    concept_clusters: list[ConceptCluster],
    concept_relationships: list[ConceptRelationship],
) -> list[str]:
    signals: list[str] = []
    signals.extend(
        cluster.cluster_name if cluster.cluster_name == cluster.mention_name else f"{cluster.cluster_name}->{cluster.mention_name}"
        for cluster in concept_clusters
        if cluster.episode.guid == episode_guid
    )
    signals.extend(
        f"{relationship.source_name}->{relationship.target_name}"
        for relationship in concept_relationships
        if relationship.episode.guid == episode_guid
    )
    signals.extend(
        mention.name for mention in concept_mentions if mention.episode.guid == episode_guid
    )
    signals.extend(
        f"《{mention.name}》" for mention in book_mentions if mention.episode.guid == episode_guid
    )
    return _dedupe(signals)


def _first_result_per_episode_local(
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


def _readable_excerpt(text: str, query: str, radius: int = 120) -> str:
    import re

    match_index = text.lower().find(query.lower())
    if match_index < 0:
        excerpt = text[: radius * 2].strip()
    else:
        start = max(0, match_index - radius)
        end = min(len(text), match_index + len(query) + radius)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(text) else ""
        excerpt = f"{prefix}{text[start:end].strip()}{suffix}"
    excerpt = re.sub(r"^##\s*chunk\s+\d+\s+approx\s+\d{2}:\d{2}", "", excerpt).strip()
    excerpt = re.sub(r"\s+", " ", excerpt)
    return _short_line(excerpt, limit=260)


def _short_line(text: str, limit: int = 160) -> str:
    import re

    cleaned_text = re.sub(r"\s+", " ", text).strip()
    if len(cleaned_text) <= limit:
        return cleaned_text
    return cleaned_text[: limit - 3].rstrip() + "..."


def _truncate_discord_message(value: str, limit: int = 1900) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
