from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_bot.ask import answer_question
from reference_bot.concept_map import index_concept_map
from reference_bot.episodes import ConceptCluster, ConceptMention, ConceptRelationship, Episode, EpisodeSummary
from reference_bot.storage import (
    replace_concept_clusters,
    replace_concept_mentions,
    replace_concept_relationships,
    replace_transcript_chunks,
    upsert_episode_summary,
    upsert_episodes,
)


class AskTests(unittest.TestCase):
    def test_answer_question_uses_llm_when_api_key_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            episode = Episode(
                guid="episode-369",
                title="EP.369《終結職業倦怠》",
                published_at="Fri, 17 Apr 2026 00:00:00 +0800",
                episode_url=None,
                audio_url=None,
                description=None,
            )
            upsert_episodes(database_path, [episode])
            upsert_episode_summary(
                database_path,
                EpisodeSummary(
                    episode=episode,
                    one_sentence_summary="本集探討職業倦怠。",
                    key_points=["職業倦怠是一種光譜。"],
                    topics=["職業倦怠"],
                    summary_note_path=None,
                    generated_by="openai_structured_v1",
                ),
            )
            replace_concept_mentions(
                database_path,
                episode.guid,
                [
                    ConceptMention(
                        episode=episode,
                        name="職業倦怠",
                        mention_level="main_focus",
                        evidence="整集主題。",
                    )
                ],
            )
            replace_concept_clusters(
                database_path,
                episode.guid,
                [
                    ConceptCluster(
                        episode=episode,
                        cluster_name="工作心理",
                        mention_name="職業倦怠",
                        mention_level="main_focus",
                        evidence="職業倦怠被歸在工作心理脈絡。",
                    )
                ],
            )
            replace_concept_relationships(
                database_path,
                episode.guid,
                [
                    ConceptRelationship(
                        episode=episode,
                        source_name="職業倦怠",
                        relation_type="similar_to",
                        target_name="工作耗損",
                        evidence="兩者在本集被放在相近脈絡討論。",
                    )
                ],
            )

            with patch("reference_bot.ask.synthesize_answer", return_value="有，EP.369 很相關。") as synthesize:
                result = answer_question(
                    database_path=database_path,
                    question="有沒有討論職業倦怠？",
                    api_key="test-key",
                    model="test-model",
                )

            self.assertTrue(result.used_llm)
            self.assertEqual(result.answer, "有，EP.369 很相關。")
            self.assertEqual(result.concept_mentions[0].name, "職業倦怠")
            self.assertEqual(result.concept_clusters[0].cluster_name, "工作心理")
            self.assertEqual(result.concept_relationships[0].target_name, "工作耗損")
            self.assertEqual(result.summaries[0].episode.title, "EP.369《終結職業倦怠》")
            self.assertEqual(synthesize.call_args.kwargs["concept_clusters"][0].cluster_name, "工作心理")
            self.assertEqual(synthesize.call_args.kwargs["concept_relationships"][0].target_name, "工作耗損")

    def test_answer_question_falls_back_without_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            episode = Episode(
                guid="episode-369",
                title="EP.369《終結職業倦怠》",
                published_at="Fri, 17 Apr 2026 00:00:00 +0800",
                episode_url=None,
                audio_url=None,
                description=None,
            )
            upsert_episodes(database_path, [episode])
            upsert_episode_summary(
                database_path,
                EpisodeSummary(
                    episode=episode,
                    one_sentence_summary="本集探討職業倦怠。",
                    key_points=["職業倦怠是一種光譜。"],
                    topics=["職業倦怠"],
                    summary_note_path=None,
                    generated_by="openai_structured_v1",
                ),
            )

            result = answer_question(
                database_path=database_path,
                question="有沒有討論職業倦怠？",
                api_key=None,
            )

            self.assertFalse(result.used_llm)
            self.assertIn("感謝您的詢問", result.answer)
            self.assertIn("EP.369", result.answer)

    def test_answer_question_falls_back_when_llm_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            episode = Episode(
                guid="episode-369",
                title="EP.369《終結職業倦怠》",
                published_at="Fri, 17 Apr 2026 00:00:00 +0800",
                episode_url=None,
                audio_url=None,
                description=None,
            )
            upsert_episodes(database_path, [episode])
            upsert_episode_summary(
                database_path,
                EpisodeSummary(
                    episode=episode,
                    one_sentence_summary="本集探討職業倦怠。",
                    key_points=["職業倦怠是一種光譜。"],
                    topics=["職業倦怠"],
                    summary_note_path=None,
                    generated_by="openai_structured_v1",
                ),
            )

            with patch("reference_bot.ask.synthesize_answer", side_effect=RuntimeError("quota")):
                result = answer_question(
                    database_path=database_path,
                    question="有沒有討論職業倦怠？",
                    api_key="test-key",
                )

            self.assertFalse(result.used_llm)
            self.assertIn("感謝您的詢問", result.answer)
            self.assertIn("EP.369", result.answer)

    def test_answer_question_uses_transcript_evidence_when_summary_does_not_match(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            episode = Episode(
                guid="episode-1",
                title="EP.1《其他主題》",
                published_at="Fri, 17 Apr 2026 00:00:00 +0800",
                episode_url=None,
                audio_url=None,
                description=None,
            )
            upsert_episodes(database_path, [episode])
            replace_transcript_chunks(
                database_path,
                transcript=type(
                    "Transcript",
                    (),
                    {
                        "episode": episode,
                        "transcript_local_path": "data/transcripts/ep1.txt",
                        "obsidian_transcript_path": "Inbox/Podcast Import/transcripts/ep1.md",
                    },
                )(),
                chunks=["這裡逐字稿提到職業倦怠與工作耗損。"],
            )

            result = answer_question(
                database_path=database_path,
                question="有沒有討論職業倦怠？",
                api_key=None,
            )

            self.assertFalse(result.used_llm)
            self.assertEqual(len(result.transcript_results), 1)
            self.assertIn("逐字稿也找到一些線索", result.answer)

    def test_answer_question_reports_mentions_even_without_summary_or_transcript_match(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            episode = Episode(
                guid="episode-329",
                title="EP.329《納瓦爾寶典》",
                published_at="Fri, 13 Jun 2025 00:00:00 +0800",
                episode_url=None,
                audio_url=None,
                description=None,
            )
            upsert_episodes(database_path, [episode])
            replace_concept_mentions(
                database_path,
                episode.guid,
                [
                    ConceptMention(
                        episode=episode,
                        name="槓桿運用",
                        mention_level="discussed",
                        evidence="討論如何不只用時間換錢。",
                    )
                ],
            )

            result = answer_question(
                database_path=database_path,
                question="有沒有聊過財富槓桿？",
                api_key=None,
            )

            self.assertFalse(result.used_llm)
            self.assertIn("概念/書籍索引先找到", result.answer)
            self.assertIn("槓桿運用", result.answer)
            self.assertNotIn("目前沒有在 summary index", result.answer)

    def test_answer_question_includes_concept_map_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            episode = Episode(
                guid="episode-372",
                title="EP.372《財富階梯》",
                published_at="Fri, 08 May 2026 00:00:00 +0800",
                episode_url=None,
                audio_url=None,
                description=None,
            )
            upsert_episodes(database_path, [episode])
            replace_concept_mentions(
                database_path,
                episode.guid,
                [
                    ConceptMention(
                        episode=episode,
                        name="財富階梯六級",
                        mention_level="referenced",
                        evidence="討論財富累積與不同財務階段。",
                    )
                ],
            )
            index_concept_map(database_path, limit=10)

            result = answer_question(
                database_path=database_path,
                question="有沒有聊過致富？",
                api_key=None,
            )

            self.assertFalse(result.used_llm)
            self.assertEqual(result.concept_clusters[0].cluster_name, "財富")
            self.assertIn("概念地圖：財富 -> 財富階梯六級", result.answer)
            self.assertIn("關係：財富 expands_on 財富階梯六級", result.answer)

    def test_answer_question_redirects_obvious_off_topic_questions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")

            result = answer_question(
                database_path=database_path,
                question="今天台北天氣怎麼樣？",
                api_key=None,
            )

            self.assertFalse(result.used_llm)
            self.assertIn("需要即時外部資料", result.answer)
            self.assertIn("引書店 Podcast", result.answer)
            self.assertIn("EP.375", result.answer)
            self.assertNotIn("summary index 或逐字稿 chunks", result.answer)

    def test_answer_question_keeps_keyword_hint_for_unmatched_podcast_queries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")

            result = answer_question(
                database_path=database_path,
                question="有沒有聊過火星移民？",
                api_key=None,
            )

            self.assertFalse(result.used_llm)
            self.assertIn("目前沒有在 summary index 或逐字稿 chunks", result.answer)
            self.assertIn("再試 `/ask`", result.answer)
            self.assertNotIn("不像在查節目", result.answer)


if __name__ == "__main__":
    unittest.main()
