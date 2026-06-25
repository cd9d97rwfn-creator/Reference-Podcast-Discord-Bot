from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_bot.episodes import Episode
from reference_bot.openai_summary import generate_openai_episode_summaries
from reference_bot.storage import (
    get_episode_summary_by_number,
    mark_transcript_imported,
    mark_transcript_note_exported,
    upsert_episodes,
)


OPENAI_SUMMARY = """# EP.329《納瓦爾寶典》Summary

## 一句話摘要
這集討論《納瓦爾寶典》中的財富、快樂與實踐。

## 這集在講什麼
- 討論財富不是單純用時間換錢。
- 討論快樂、家庭責任與多巴胺陷阱。

## 主要書籍
- 《納瓦爾寶典》：main_focus，整集主軸。

## 重要概念
- 價值、信任與資源：賺錢的核心。
- 消費升級：阻礙財富累積。

## 主持人/來賓個人故事
- 主持人談到育兒與責任。

## 可能可問的問題
- EP.329 在講什麼？

## 不確定處
- 無。
"""


class OpenAISummaryTests(unittest.TestCase):
    def test_generate_openai_episode_summaries_stores_structured_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database_path = str(root / "episodes.sqlite3")
            transcript_path = root / "ep329.txt"
            summaries_dir = root / "Inbox" / "Podcast Import" / "episodes"
            transcript_path.write_text("逐字稿內容", encoding="utf-8")
            upsert_episodes(
                database_path,
                [
                    Episode(
                        guid="episode-329",
                        title="EP.329《納瓦爾寶典》",
                        published_at=None,
                        episode_url=None,
                        audio_url=None,
                        description=None,
                    )
                ],
            )
            mark_transcript_imported(database_path, "episode-329", str(transcript_path))
            mark_transcript_note_exported(
                database_path,
                "episode-329",
                "Inbox/Podcast Import/transcripts/ep329.md",
            )

            with patch("reference_bot.openai_summary.response_text", return_value=OPENAI_SUMMARY):
                generated_count = generate_openai_episode_summaries(
                    database_path=database_path,
                    summaries_dir=str(summaries_dir),
                    api_key="test-key",
                    limit=1,
                )

            summary = get_episode_summary_by_number(database_path, 329)
            self.assertEqual(generated_count, 1)
            self.assertIsNotNone(summary)
            assert summary is not None
            self.assertEqual(summary.generated_by, "openai_structured_v1")
            self.assertIn("財富、快樂與實踐", summary.one_sentence_summary)
            self.assertIn("財富不是單純用時間換錢", summary.key_points[0])
            note_path = Path(summary.summary_note_path or "")
            self.assertTrue(note_path.is_file())
            note_text = note_path.read_text(encoding="utf-8")
            self.assertIn("## Corrections", note_text)
            self.assertIn("## Feedback Log", note_text)


if __name__ == "__main__":
    unittest.main()
