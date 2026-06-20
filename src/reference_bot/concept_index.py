from __future__ import annotations

from pathlib import Path
import re

from reference_bot.episodes import BookMention, ConceptMention, EpisodeSummary
from reference_bot.normalization import normalize_mention_name
from reference_bot.storage import (
    list_episode_summaries,
    replace_book_mentions,
    replace_concept_mentions,
)


BOOK_LEVELS = {"main_focus", "discussed", "referenced", "passing_mention"}


def index_summary_mentions(database_path: str, limit: int = 100) -> tuple[int, int, int]:
    episodes_indexed = 0
    books_indexed = 0
    concepts_indexed = 0
    for summary in list_episode_summaries(database_path, limit=limit):
        books = extract_book_mentions(summary)
        concepts = extract_concept_mentions(summary)
        books_indexed += replace_book_mentions(database_path, summary.episode.guid, books)
        concepts_indexed += replace_concept_mentions(database_path, summary.episode.guid, concepts)
        episodes_indexed += 1
    return episodes_indexed, books_indexed, concepts_indexed


def extract_book_mentions(summary: EpisodeSummary) -> list[BookMention]:
    note_text = _summary_note_text(summary)
    section = _section_text(note_text, "主要書籍")
    mentions: list[BookMention] = []
    for line in _section_blocks(section):
        name = _book_name(line)
        if not name:
            continue
        mentions.append(
            BookMention(
                episode=summary.episode,
                name=name,
                mention_level=_mention_level(line),
                evidence=_clean_item_text(line),
            )
        )
    return _dedupe_books(mentions)


def extract_concept_mentions(summary: EpisodeSummary) -> list[ConceptMention]:
    note_text = _summary_note_text(summary)
    section = _section_text(note_text, "重要概念")
    mentions: list[ConceptMention] = []
    for line in _section_items(section):
        name = _concept_name(line)
        if not name:
            continue
        mentions.append(
            ConceptMention(
                episode=summary.episode,
                name=name,
                mention_level=_concept_level(summary, name),
                evidence=_clean_item_text(line),
            )
        )

    if not mentions:
        for topic in summary.topics:
            cleaned = topic.strip()
            if cleaned:
                mentions.append(
                    ConceptMention(
                        episode=summary.episode,
                        name=cleaned,
                        mention_level=_concept_level(summary, cleaned),
                        evidence=summary.one_sentence_summary,
                    )
                )
    return _dedupe_concepts(mentions)


def _summary_note_text(summary: EpisodeSummary) -> str:
    if not summary.summary_note_path:
        return ""
    path = Path(summary.summary_note_path).expanduser()
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _section_text(markdown: str, heading: str) -> str:
    if not markdown:
        return ""
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    match = re.search(pattern, markdown, flags=re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_heading = re.search(r"^##\s+", markdown[start:], flags=re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(markdown)
    return markdown[start:end].strip()


def _section_items(section: str) -> list[str]:
    items: list[str] = []
    for line in section.splitlines():
        if not line.startswith(("-", "*")):
            continue
        cleaned = line.strip()
        if cleaned:
            items.append(cleaned.lstrip("-*").strip())
    return items


def _section_blocks(section: str) -> list[str]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in section.splitlines():
        if line.startswith(("-", "*")):
            if current:
                blocks.append(current)
            current = [line.strip().lstrip("-*").strip()]
            continue
        if current and line.startswith((" ", "\t")) and line.strip().startswith(("-", "*")):
            current.append(line.strip().lstrip("-*").strip())
    if current:
        blocks.append(current)
    return ["；".join(part for part in block if part) for block in blocks]


def _book_name(line: str) -> str | None:
    match = re.search(r"《([^》]+)》", line)
    if match:
        return match.group(1).strip()
    name = re.split(r"[：:，,]", line, maxsplit=1)[0].strip()
    return name or None


def _concept_name(line: str) -> str | None:
    name = re.split(r"[：:，,]", line, maxsplit=1)[0].strip()
    name = normalize_mention_name(name)
    return name or None


def _mention_level(line: str) -> str:
    for level in BOOK_LEVELS:
        if level in line:
            return level
    return "referenced"


def _concept_level(summary: EpisodeSummary, name: str) -> str:
    if name in summary.episode.title:
        return "main_focus"
    if name in summary.one_sentence_summary:
        return "discussed"
    return "referenced"


def _clean_item_text(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _dedupe_books(mentions: list[BookMention]) -> list[BookMention]:
    seen: set[str] = set()
    deduped: list[BookMention] = []
    for mention in mentions:
        if mention.name in seen:
            continue
        seen.add(mention.name)
        deduped.append(mention)
    return deduped


def _dedupe_concepts(mentions: list[ConceptMention]) -> list[ConceptMention]:
    seen: set[str] = set()
    deduped: list[ConceptMention] = []
    for mention in mentions:
        if mention.name in seen:
            continue
        seen.add(mention.name)
        deduped.append(mention)
    return deduped
