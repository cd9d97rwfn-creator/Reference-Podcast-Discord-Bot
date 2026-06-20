from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from reference_bot.episodes import Episode, EpisodeSummary, IndexedTranscript
from reference_bot.storage import (
    list_indexed_episodes_without_summary,
    upsert_episode_summary,
)


DEFAULT_EPISODE_SUMMARIES_DIR = "Inbox/Podcast Import/episodes"
GENERATED_BY = "local_heuristic_v1"


def generate_episode_summaries(
    database_path: str,
    summaries_dir: str = DEFAULT_EPISODE_SUMMARIES_DIR,
    limit: int = 10,
) -> int:
    generated_count = 0
    for transcript in list_indexed_episodes_without_summary(database_path, limit=limit):
        summary = build_episode_summary(transcript)
        note_path = export_episode_summary_note(summary, summaries_dir)
        summary_with_note = EpisodeSummary(
            episode=summary.episode,
            one_sentence_summary=summary.one_sentence_summary,
            key_points=summary.key_points,
            topics=summary.topics,
            summary_note_path=str(note_path),
            generated_by=summary.generated_by,
        )
        upsert_episode_summary(database_path, summary_with_note)
        generated_count += 1

    return generated_count


def build_episode_summary(transcript: IndexedTranscript) -> EpisodeSummary:
    episode = transcript.episode
    title_topic = _title_topic(episode.title)
    transcript_text = _read_transcript_excerpt(transcript.transcript_local_path)
    description = _plain_text(episode.description or "")
    topics = _topics_from_title(episode.title)
    key_points = _key_points(episode, title_topic, description, transcript_text)

    if title_topic:
        one_sentence_summary = f"這集主要圍繞「{title_topic}」展開。"
    else:
        one_sentence_summary = f"這集主題可先從標題「{episode.title}」理解；目前摘要由本地規則保守生成。"

    return EpisodeSummary(
        episode=episode,
        one_sentence_summary=one_sentence_summary,
        key_points=key_points,
        topics=topics,
        summary_note_path=None,
        generated_by=GENERATED_BY,
    )


def export_episode_summary_note(summary: EpisodeSummary, summaries_dir: str) -> Path:
    output_directory = Path(summaries_dir).expanduser()
    output_directory.mkdir(parents=True, exist_ok=True)
    target_path = _unique_markdown_path(output_directory / f"{_note_filename_stem(summary.episode)}.md")
    target_path.write_text(_summary_note_content(summary), encoding="utf-8")
    return target_path


def _summary_note_content(summary: EpisodeSummary) -> str:
    frontmatter = {
        "type": "podcast_episode_summary",
        "status": "indexed",
        "summary_kind": summary.generated_by,
        "podcast": "引書店",
        "title": summary.episode.title,
        "guid": summary.episode.guid,
        "published_at": summary.episode.published_at,
        "episode_url": summary.episode.episode_url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    lines = ["---"]
    for key, value in frontmatter.items():
        lines.append(f"{key}: {_yaml_value(value)}")
    lines.extend(["---", "", f"# {summary.episode.title}", ""])
    lines.extend(["## One-Sentence Summary", "", summary.one_sentence_summary, ""])
    lines.extend(["## Key Points", ""])
    lines.extend([f"- {point}" for point in summary.key_points])
    lines.extend(["", "## Topics", ""])
    lines.extend([f"- {topic}" for topic in summary.topics])
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This summary was generated locally from metadata and transcript text; it is conservative and may be upgraded with an LLM summary later.",
            "- Current MacWhisper CLI transcripts do not include timestamps.",
            "",
        ]
    )
    return "\n".join(lines)


def _key_points(
    episode: Episode,
    title_topic: str | None,
    description: str,
    transcript_text: str,
) -> list[str]:
    points: list[str] = []
    if title_topic:
        points.append(f"標題主題：{title_topic}")
    if _guest_label(episode.title):
        points.append(f"來賓/系列資訊：{_guest_label(episode.title)}")
    if description:
        points.append(f"RSS 描述節錄：{description[:160]}")
    if transcript_text:
        points.append(f"逐字稿開頭節錄：{transcript_text[:180]}")
    if not points:
        points.append("目前只有 episode metadata 可用，尚未產生深入摘要。")
    return points[:4]


def _topics_from_title(title: str) -> list[str]:
    topics: list[str] = []
    title_topic = _title_topic(title)
    if title_topic:
        topics.append(title_topic)

    quoted = re.findall(r"『([^』]+)』", title)
    topics.extend(quoted)

    if "feat." in title:
        topics.append("訪談")
    if "廣告" in title or "團購" in title or "報名" in title:
        topics.append("活動/廣告")
    return _dedupe([topic.strip(" 。.") for topic in topics if topic.strip()])


def _title_topic(title: str) -> str | None:
    match = re.search(r"《([^》]+)》", title)
    if match:
        return match.group(1).strip()
    return None


def _guest_label(title: str) -> str | None:
    match = re.search(r"(feat\.\s*[^＿]+)", title)
    if match:
        return match.group(1).strip()
    return None


def _read_transcript_excerpt(transcript_path: str, limit: int = 600) -> str:
    path = Path(transcript_path).expanduser()
    if not path.is_file():
        return ""
    return _plain_text(path.read_text(encoding="utf-8")[:limit])


def _plain_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


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


def _note_filename_stem(episode: Episode) -> str:
    guid_hash = hashlib.sha256(episode.guid.encode("utf-8")).hexdigest()[:12]
    title_slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", episode.title, flags=re.UNICODE)
    title_slug = re.sub(r"-+", "-", title_slug).strip("-_").lower()[:80] or "episode"
    return f"{guid_hash}-{title_slug}"
