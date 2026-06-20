from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_bot.answer_synthesis import synthesize_answer
from reference_bot.episodes import (
    ConceptCluster,
    ConceptMention,
    ConceptRelationship,
    Episode,
    EpisodeSummary,
    TranscriptSearchResult,
)


class AnswerSynthesisTests(unittest.TestCase):
    def test_synthesize_answer_passes_retrieved_context_to_openai(self) -> None:
        episode = Episode(
            guid="episode-369",
            title="EP.369《終結職業倦怠》",
            published_at=None,
            episode_url=None,
            audio_url=None,
            description=None,
        )

        with patch("reference_bot.answer_synthesis.chat_completion_text", return_value="有，EP.369 很相關。") as call:
            answer = synthesize_answer(
                api_key="test-key",
                model="test-model",
                question="有沒有討論職業倦怠？",
                concept_mentions=[
                    ConceptMention(
                        episode=episode,
                        name="職業倦怠",
                        mention_level="main_focus",
                        evidence="整集主題。",
                    )
                ],
                concept_clusters=[
                    ConceptCluster(
                        episode=episode,
                        cluster_name="工作心理",
                        mention_name="職業倦怠",
                        mention_level="main_focus",
                        evidence="職業倦怠被歸在工作心理脈絡。",
                    )
                ],
                concept_relationships=[
                    ConceptRelationship(
                        episode=episode,
                        source_name="職業倦怠",
                        relation_type="similar_to",
                        target_name="工作耗損",
                        evidence="兩者在本集被放在相近脈絡討論。",
                    )
                ],
                summaries=[
                    EpisodeSummary(
                        episode=episode,
                        one_sentence_summary="本集探討職業倦怠。",
                        key_points=["好人容易心力交瘁。"],
                        topics=["職業倦怠"],
                        summary_note_path="Inbox/Podcast Import/episodes/ep369.md",
                        generated_by="openai_structured_v1",
                    )
                ],
                transcript_results=[
                    TranscriptSearchResult(
                        episode=episode,
                        chunk_index=1,
                        chunk_text="逐字稿提到 burnout 與職業倦怠。",
                        transcript_local_path="data/transcripts/ep369.txt",
                        obsidian_transcript_path="Inbox/Podcast Import/transcripts/ep369.md",
                    )
                ],
            )

        self.assertEqual(answer, "有，EP.369 很相關。")
        kwargs = call.call_args.kwargs
        self.assertEqual(kwargs["api_key"], "test-key")
        self.assertEqual(kwargs["model"], "test-model")
        user_message = kwargs["messages"][1]["content"]
        self.assertIn("有沒有討論職業倦怠", user_message)
        self.assertIn("EP.369《終結職業倦怠》", user_message)
        self.assertIn("概念索引", user_message)
        self.assertIn("職業倦怠｜main_focus", user_message)
        self.assertIn("概念地圖", user_message)
        self.assertIn("工作心理 -> 職業倦怠", user_message)
        self.assertIn("概念關係", user_message)
        self.assertIn("職業倦怠 similar_to 工作耗損", user_message)
        self.assertIn("好人容易心力交瘁", user_message)
        self.assertIn("逐字稿提到 burnout", user_message)


if __name__ == "__main__":
    unittest.main()
