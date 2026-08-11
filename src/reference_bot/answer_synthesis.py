from __future__ import annotations

from reference_bot.episodes import (
    BookMention,
    ConceptCluster,
    ConceptMention,
    ConceptRelationship,
    EpisodeSummary,
    TranscriptSearchResult,
)
from reference_bot.openai_api import chat_completion_text


DEFAULT_ASK_MODEL = "gpt-4.1-mini"


def synthesize_answer(
    *,
    api_key: str,
    model: str,
    question: str,
    summaries: list[EpisodeSummary],
    transcript_results: list[TranscriptSearchResult],
    book_mentions: list[BookMention] | None = None,
    concept_mentions: list[ConceptMention] | None = None,
    concept_clusters: list[ConceptCluster] | None = None,
    concept_relationships: list[ConceptRelationship] | None = None,
) -> str:
    context = _context_text(
        book_mentions=book_mentions or [],
        concept_mentions=concept_mentions or [],
        concept_clusters=concept_clusters or [],
        concept_relationships=concept_relationships or [],
        summaries=summaries,
        transcript_results=transcript_results,
    )
    if not context.strip():
        return ""

    return chat_completion_text(
        api_key=api_key,
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": f"使用者問題：{question}\n\n可用資料：\n{context}"},
        ],
        timeout_seconds=60,
    )


def _context_text(
    *,
    summaries: list[EpisodeSummary],
    transcript_results: list[TranscriptSearchResult],
    book_mentions: list[BookMention] | None = None,
    concept_mentions: list[ConceptMention] | None = None,
    concept_clusters: list[ConceptCluster] | None = None,
    concept_relationships: list[ConceptRelationship] | None = None,
) -> str:
    lines: list[str] = []
    if concept_mentions:
        lines.append("## 概念索引")
        for index, mention in enumerate(concept_mentions[:8], start=1):
            lines.append(f"[C{index}] {mention.name}｜{mention.mention_level}｜{mention.episode.title}")
            lines.append(f"依據：{mention.evidence}")
            lines.append("")

    if concept_clusters:
        lines.append("## 概念地圖")
        for index, cluster in enumerate(concept_clusters[:8], start=1):
            lines.append(
                f"[M{index}] {cluster.cluster_name} -> {cluster.mention_name}"
                f"｜{cluster.mention_level}｜{cluster.episode.title}"
            )
            lines.append(f"依據：{cluster.evidence}")
            lines.append("")

    if concept_relationships:
        lines.append("## 概念關係")
        for index, relationship in enumerate(concept_relationships[:8], start=1):
            lines.append(
                f"[R{index}] {relationship.source_name} "
                f"{relationship.relation_type} {relationship.target_name}"
                f"｜{relationship.episode.title}"
            )
            lines.append(f"依據：{relationship.evidence}")
            lines.append("")

    if book_mentions:
        lines.append("## 書籍索引")
        for index, mention in enumerate(book_mentions[:5], start=1):
            lines.append(f"[B{index}] 《{mention.name}》｜{mention.mention_level}｜{mention.episode.title}")
            lines.append(f"依據：{mention.evidence}")
            lines.append("")

    if summaries:
        lines.append("## 結構化摘要")
        for index, summary in enumerate(summaries[:5], start=1):
            lines.append(f"[S{index}] {summary.episode.title}")
            lines.append(f"一句話摘要：{summary.one_sentence_summary}")
            if summary.key_points:
                lines.append("重點：")
                lines.extend(f"- {point}" for point in summary.key_points[:5])
            if summary.topics:
                lines.append("主題：" + "、".join(summary.topics[:8]))
            lines.append("")

    if transcript_results:
        lines.append("## 逐字稿證據")
        for index, result in enumerate(transcript_results[:5], start=1):
            lines.append(f"[T{index}] {result.episode.title}")
            lines.append(f"chunk_index：{result.chunk_index}")
            lines.append(result.chunk_text.strip()[:1200])
            lines.append("")

    return "\n".join(lines).strip()


def _system_prompt() -> str:
    return """你是「引引」，引書店的一隻貓咪工讀生，也是「引書店 Podcast」的書庫管理員。
白天你整理書架、替客人找書；晚上你戴著耳機整理節目逐字稿、書籍、概念與它們之間的關係。Discord 是書店櫃台，資料庫是你看守的書庫。
你安靜、好奇、可靠，帶一點貓式的自信與幽默。偶爾可以使用書店或貓咪的比喻，但不要為了賣萌妨礙回答，也不要每句都加「喵」。查資料時，精準與可信度永遠優先於角色表演。

請只根據使用者提供的「結構化摘要」與「逐字稿證據」回答，不要使用外部知識，不要猜測。

回答規則：
- 使用繁體中文，語氣自然、清楚、保守。
- 開頭直接回答問題，不要說你是 AI。
- 可以自然地自稱「引引」，但不必在每次回答中重複自我介紹。
- 若找到相關內容，先說「有」，再列出最相關集數與原因。
- 若沒有明確直接命中，但有相近概念，請說「目前沒有看到足夠直接證據；但有相關線索」。
- 明確區分「直接命中」與「可能相關但不等同」；社會學、哲學、心理學概念不要混為同一個概念。
- 區分「整集主題 / 詳細討論 / 逐字稿短暫提到」。
- 優先使用概念索引與書籍索引判斷相關性，再用結構化摘要與逐字稿補充。
- 書名、概念名、主題很像時，要說明它們的關係只是資料中的線索，不代表等同。
- 優先引用結構化摘要；逐字稿只作為證據或補充。
- 不要顯示檔案路徑、summary note、chunk_index 等內部資訊。
- 不要顯示 [C1]、[M1]、[R1]、[B1]、[S1]、[T1] 這類內部資料標籤；證據請用集數和自然語句描述。
- 若資料不足，要明確說目前資料只能支持到哪裡；可以說「引引翻過目前的書架，但沒有找到足以確認的紀錄」。
- 回答格式請使用：直接回答、最相關集數、可能相關但不等同、證據。若某段沒有內容可省略。
- 最後加一小段「證據」列出 1 到 3 個短片段或摘要依據。
- Discord 回覆請控制在 1500 字以內。"""
