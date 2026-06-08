from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from reference_bot.episodes import EpisodeSummary, IndexedTranscript
from reference_bot.openai_api import response_text
from reference_bot.storage import list_indexed_transcripts_for_summary, upsert_episode_summary
from reference_bot.summary import DEFAULT_EPISODE_SUMMARIES_DIR


DEFAULT_OPENAI_SUMMARY_MODEL = "gpt-4.1-mini"
GENERATED_BY = "openai_structured_v1"


@dataclass(frozen=True)
class OpenAISummaryResult:
    summary: EpisodeSummary
    note_body: str


def generate_openai_episode_summaries(
    *,
    database_path: str,
    api_key: str,
    summaries_dir: str = DEFAULT_EPISODE_SUMMARIES_DIR,
    limit: int = 10,
    model: str = DEFAULT_OPENAI_SUMMARY_MODEL,
    replace_existing: bool = False,
) -> int:
    generated_count = 0
    transcripts = list_indexed_transcripts_for_summary(
        database_path,
        limit=limit,
        replace_existing=replace_existing,
    )
    for transcript in transcripts:
        result = build_openai_episode_summary(transcript=transcript, api_key=api_key, model=model)
        note_path = export_openai_episode_summary_note(result, summaries_dir)
        summary_with_note = EpisodeSummary(
            episode=result.summary.episode,
            one_sentence_summary=result.summary.one_sentence_summary,
            key_points=result.summary.key_points,
            topics=result.summary.topics,
            summary_note_path=str(note_path),
            generated_by=result.summary.generated_by,
        )
        upsert_episode_summary(database_path, summary_with_note)
        generated_count += 1

    return generated_count


def build_openai_episode_summary(
    *,
    transcript: IndexedTranscript,
    api_key: str,
    model: str = DEFAULT_OPENAI_SUMMARY_MODEL,
) -> OpenAISummaryResult:
    transcript_text = Path(transcript.transcript_local_path).read_text(encoding="utf-8")
    note_body = response_text(
        api_key=api_key,
        model=model,
        temperature=0,
        input_messages=[
            {"role": "system", "content": _summary_system_prompt()},
            {
                "role": "user",
                "content": (
                    f"Episode title: {transcript.episode.title}\n"
                    f"Published at: {transcript.episode.published_at or 'unknown'}\n\n"
                    f"Transcript:\n{transcript_text}"
                ),
            },
        ],
    )
    one_sentence_summary = _section_first_paragraph(note_body, "一句話摘要")
    key_points = _section_bullets(note_body, "這集在講什麼")
    topics = _section_bullets(note_body, "重要概念")

    if not one_sentence_summary:
        one_sentence_summary = f"這集討論「{_title_topic(transcript.episode.title) or transcript.episode.title}」。"
    if not key_points:
        key_points = [line for line in note_body.splitlines() if line.strip()][:4]
    if not topics:
        topics = _topics_from_title(transcript.episode.title)

    summary = EpisodeSummary(
        episode=transcript.episode,
        one_sentence_summary=one_sentence_summary,
        key_points=key_points[:8],
        topics=topics[:12],
        summary_note_path=None,
        generated_by=GENERATED_BY,
    )
    return OpenAISummaryResult(summary=summary, note_body=note_body)


def export_openai_episode_summary_note(result: OpenAISummaryResult, summaries_dir: str) -> Path:
    output_directory = Path(summaries_dir).expanduser()
    output_directory.mkdir(parents=True, exist_ok=True)
    target_path = _unique_markdown_path(
        output_directory / f"{_note_filename_stem(result.summary.episode)}.md"
    )
    target_path.write_text(_summary_note_content(result), encoding="utf-8")
    return target_path


def _summary_note_content(result: OpenAISummaryResult) -> str:
    episode = result.summary.episode
    frontmatter = {
        "type": "podcast_episode_summary",
        "status": "indexed",
        "summary_kind": result.summary.generated_by,
        "podcast": "引書店",
        "title": episode.title,
        "guid": episode.guid,
        "published_at": episode.published_at,
        "episode_url": episode.episode_url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    lines = ["---"]
    for key, value in frontmatter.items():
        lines.append(f"{key}: {_yaml_value(value)}")
    lines.extend(["---", "", result.note_body.strip(), ""])
    lines.extend(
        [
            "## Corrections",
            "",
            "- Add human corrections here. Bot answers should prefer corrected facts over raw AI output.",
            "",
            "## Feedback Log",
            "",
            "- Pending Discord/user feedback can be appended here before becoming verified corrections.",
            "",
        ]
    )
    return "\n".join(lines)


def _summary_system_prompt() -> str:
    return """你是 podcast 知識整理助理。請根據逐字稿產生可供 Obsidian/Discord 查詢使用的繁體中文 episode summary。
請務必保守：只根據逐字稿，不要補充外部知識。若逐字稿品質疑似有錯字或不確定，請在「不確定處」列出。
格式固定如下：
# EP Summary

## 一句話摘要

## 這集在講什麼
用 5-8 個 bullet，具體寫出主持人/來賓討論的脈絡，不要空泛。

## 主要書籍
每本書列出：書名、mention_level（main_focus/discussed/referenced/passing_mention）、這集怎麼談它。

## 重要概念
列出 8-12 個概念，每個概念用一句話說明本集怎麼談。

## 主持人/來賓個人故事
列出逐字稿中可被日後查詢的人生經驗、工作經驗、家庭經驗或明確立場。沒有就寫「未明確提到」。

## 可能可問的問題
列出 8 個 Discord 使用者可能會問的自然語言問題。

## 不確定處
列出逐字稿可能導致摘要不確定的詞、人名、片段。"""


def _section_first_paragraph(markdown: str, heading: str) -> str:
    section = _section_text(markdown, heading)
    for line in section.splitlines():
        cleaned = line.strip().lstrip("-").strip()
        if cleaned:
            return cleaned
    return ""


def _section_bullets(markdown: str, heading: str) -> list[str]:
    section = _section_text(markdown, heading)
    bullets: list[str] = []
    for line in section.splitlines():
        cleaned = line.strip()
        if cleaned.startswith(("-", "*")):
            bullets.append(cleaned.lstrip("-*").strip())
    return bullets


def _section_text(markdown: str, heading: str) -> str:
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    match = re.search(pattern, markdown, flags=re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_heading = re.search(r"^##\s+", markdown[start:], flags=re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(markdown)
    return markdown[start:end].strip()


def _topics_from_title(title: str) -> list[str]:
    topic = _title_topic(title)
    return [topic] if topic else []


def _title_topic(title: str) -> str | None:
    match = re.search(r"《([^》]+)》", title)
    if match:
        return match.group(1).strip()
    return None


def _yaml_value(value: str | None) -> str:
    if value is None or value == "":
        return "null"
    return json.dumps(value, ensure_ascii=False)


def _unique_markdown_path(target_path: Path) -> Path:
    if not target_path.exists():
        return target_path

    counter = 2
    while True:
        candidate = target_path.with_name(f"{target_path.stem}-{counter}{target_path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _note_filename_stem(episode) -> str:
    guid_hash = hashlib.sha256(episode.guid.encode("utf-8")).hexdigest()[:12]
    title_slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", episode.title, flags=re.UNICODE)
    title_slug = re.sub(r"-+", "-", title_slug).strip("-_").lower()[:80] or "episode"
    return f"{guid_hash}-{title_slug}"
