from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_bot.concept_index import extract_book_mentions, extract_concept_mentions
from reference_bot.episodes import Episode, EpisodeSummary


SUMMARY_NOTE = """# EP Summary

## 一句話摘要
這集討論《納瓦爾寶典》中的財富與快樂。

## 主要書籍
- 《納瓦爾寶典》：main_focus，整集主軸。
- 《人生的五種財富》：referenced，用來補充財富觀。

## 重要概念
- 財富槓桿：討論如何不只用時間換錢。
- 快樂與慾望：討論快樂和多巴胺陷阱。
"""

NESTED_BOOK_NOTE = """## 主要書籍
- 《納瓦爾寶典》
  - mention_level: main_focus
  - 本集以此書為核心。
- 《窮查理的普通常識》
  - mention_level: referenced
  - 用來補充決策智慧。

## 重要概念
- 槓桿運用：討論人力、資金與科技槓桿。
"""


class ConceptIndexTests(unittest.TestCase):
    def test_extracts_books_and_concepts_from_summary_note(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            note_path = Path(temporary_directory) / "summary.md"
            note_path.write_text(SUMMARY_NOTE, encoding="utf-8")
            summary = EpisodeSummary(
                episode=Episode(
                    guid="episode-329",
                    title="EP.329《納瓦爾寶典》",
                    published_at=None,
                    episode_url=None,
                    audio_url=None,
                    description=None,
                ),
                one_sentence_summary="這集討論《納瓦爾寶典》中的財富與快樂。",
                key_points=[],
                topics=[],
                summary_note_path=str(note_path),
                generated_by="openai_structured_v1",
            )

            books = extract_book_mentions(summary)
            concepts = extract_concept_mentions(summary)

        self.assertEqual([book.name for book in books], ["納瓦爾寶典", "人生的五種財富"])
        self.assertEqual(books[0].mention_level, "main_focus")
        self.assertEqual([concept.name for concept in concepts], ["槓桿運用", "快樂與慾望"])

    def test_extract_books_handles_nested_bullets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            note_path = Path(temporary_directory) / "summary.md"
            note_path.write_text(NESTED_BOOK_NOTE, encoding="utf-8")
            summary = EpisodeSummary(
                episode=Episode(
                    guid="episode-329",
                    title="EP.329《納瓦爾寶典》",
                    published_at=None,
                    episode_url=None,
                    audio_url=None,
                    description=None,
                ),
                one_sentence_summary="這集討論《納瓦爾寶典》。",
                key_points=[],
                topics=[],
                summary_note_path=str(note_path),
                generated_by="openai_structured_v1",
            )

            books = extract_book_mentions(summary)

        self.assertEqual([book.name for book in books], ["納瓦爾寶典", "窮查理的普通常識"])
        self.assertEqual(books[0].mention_level, "main_focus")
        self.assertIn("本集以此書為核心", books[0].evidence)

    def test_extract_concepts_strips_markdown_emphasis_from_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            note_path = Path(temporary_directory) / "summary.md"
            note_path.write_text("## 重要概念\n- **ABZ計畫**：討論備案與職涯選擇。\n", encoding="utf-8")
            summary = EpisodeSummary(
                episode=Episode(
                    guid="episode-1",
                    title="EP.1《職涯選擇》",
                    published_at=None,
                    episode_url=None,
                    audio_url=None,
                    description=None,
                ),
                one_sentence_summary="這集討論職涯選擇。",
                key_points=[],
                topics=[],
                summary_note_path=str(note_path),
                generated_by="openai_structured_v1",
            )

            concepts = extract_concept_mentions(summary)

        self.assertEqual(concepts[0].name, "ABZ計畫")

    def test_extract_concepts_normalizes_known_alias_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            note_path = Path(temporary_directory) / "summary.md"
            note_path.write_text("## 重要概念\n- 心理邊界：討論如何維持關係中的距離。\n", encoding="utf-8")
            summary = EpisodeSummary(
                episode=Episode(
                    guid="episode-1",
                    title="EP.1《心理界限》",
                    published_at=None,
                    episode_url=None,
                    audio_url=None,
                    description=None,
                ),
                one_sentence_summary="這集討論心理界限。",
                key_points=[],
                topics=[],
                summary_note_path=str(note_path),
                generated_by="openai_structured_v1",
            )

            concepts = extract_concept_mentions(summary)

        self.assertEqual(concepts[0].name, "心理界限")

    def test_extract_concepts_falls_back_to_topics(self) -> None:
        summary = EpisodeSummary(
            episode=Episode(
                guid="episode-1",
                title="EP.1《職業倦怠》",
                published_at=None,
                episode_url=None,
                audio_url=None,
                description=None,
            ),
            one_sentence_summary="這集討論職業倦怠。",
            key_points=[],
            topics=["職業倦怠"],
            summary_note_path=None,
            generated_by="local_heuristic_v1",
        )

        concepts = extract_concept_mentions(summary)

        self.assertEqual(concepts[0].name, "職業倦怠")
        self.assertEqual(concepts[0].mention_level, "main_focus")


if __name__ == "__main__":
    unittest.main()
