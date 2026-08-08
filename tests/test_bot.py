from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_bot.bot import (
    PING_RESPONSES,
    _episode_number_from_question,
    _fallback_transcript_query,
    _format_book_response,
    _format_episode_summary_answer,
    _format_episodes_response,
    _format_mentioned_response,
    _format_natural_language_answer,
    _format_topic_response,
    _readable_excerpt,
    _strip_bot_mention,
)
from reference_bot.episodes import (
    BookMention,
    ConceptCluster,
    ConceptMention,
    ConceptRelationship,
    Episode,
    EpisodeSummary,
    TranscriptSearchResult,
)


class BotResponseTests(unittest.TestCase):
    def test_strip_bot_mention_accepts_both_discord_mention_forms(self) -> None:
        self.assertEqual(_strip_bot_mention("<@123> 有聊過倦怠嗎？", 123), "有聊過倦怠嗎？")
        self.assertEqual(_strip_bot_mention("嗨 <@!123>   EP.375 呢", 123), "嗨 EP.375 呢")

    def test_ping_responses_are_warm_cat_clerk_messages(self) -> None:
        self.assertGreaterEqual(len(PING_RESPONSES), 3)
        for response in PING_RESPONSES:
            with self.subTest(response=response):
                self.assertNotEqual(response, "Pong!")
                self.assertTrue(response.strip())
                self.assertTrue(any(term in response for term in ("喵", "貓咪店員", "小店員")))
                self.assertTrue(any(term in response for term in ("正常", "在線", "醒著", "待命")))

    def test_format_episodes_response_lists_indexed_episodes(self) -> None:
        response = _format_episodes_response(
            [
                Episode(
                    guid="episode-1",
                    title="第一集",
                    published_at="Mon, 01 Jun 2026 00:00:00 +0800",
                    episode_url=None,
                    audio_url=None,
                    description=None,
                )
            ]
        )

        self.assertIn("Recently indexed episodes", response)
        self.assertIn("第一集", response)

    def test_format_mentioned_response_warns_result_is_keyword_search(self) -> None:
        response = _format_mentioned_response(
            "品質",
            [
                TranscriptSearchResult(
                    episode=Episode(
                        guid="episode-1",
                        title="品質管理這一集",
                        published_at=None,
                        episode_url=None,
                        audio_url=None,
                        description=None,
                    ),
                    chunk_index=3,
                    chunk_text="這段提到品質管理與系統穩定。",
                    transcript_local_path="data/transcripts/episode.txt",
                    obsidian_transcript_path="Inbox/Podcast Import/transcripts/episode.md",
                )
            ],
        )

        self.assertIn("逐字稿關鍵字命中：品質", response)
        self.assertIn("這不是摘要或主題判斷", response)
        self.assertIn("不含時間戳", response)
        self.assertIn("品質管理這一集", response)
        self.assertIn("證據片段", response)

    def test_format_mentioned_response_handles_no_matches(self) -> None:
        self.assertIn("沒有找到逐字稿關鍵字命中", _format_mentioned_response("不存在", []))

    def test_format_book_response_lists_mention_level_and_evidence(self) -> None:
        response = _format_book_response(
            "納瓦爾",
            [
                BookMention(
                    episode=Episode(
                        guid="episode-329",
                        title="EP.329《納瓦爾寶典》",
                        published_at=None,
                        episode_url=None,
                        audio_url=None,
                        description=None,
                    ),
                    name="納瓦爾寶典",
                    mention_level="main_focus",
                    evidence="整集主軸，討論財富與快樂。",
                )
            ],
        )

        self.assertIn("書籍索引命中：納瓦爾", response)
        self.assertIn("《納瓦爾寶典》", response)
        self.assertIn("EP.329", response)
        self.assertIn("main_focus", response)
        self.assertIn("不等於完整書摘", response)

    def test_format_book_response_handles_no_matches(self) -> None:
        self.assertIn("沒有找到書籍索引命中", _format_book_response("不存在", []))

    def test_format_topic_response_lists_mention_level_and_evidence(self) -> None:
        episode = Episode(
            guid="episode-369",
            title="EP.369《終結職業倦怠》",
            published_at=None,
            episode_url=None,
            audio_url=None,
            description=None,
        )
        response = _format_topic_response(
            "職業倦怠",
            [
                ConceptMention(
                    episode=episode,
                    name="職業倦怠",
                    mention_level="main_focus",
                    evidence="本集探討職業倦怠的多面向成因。",
                )
            ],
            [
                ConceptCluster(
                    episode=episode,
                    cluster_name="職業倦怠",
                    mention_name="理想性工作反而更容易導致職業倦怠",
                    mention_level="referenced",
                    evidence="理想工作也可能耗竭。",
                )
            ],
            [
                ConceptRelationship(
                    episode=episode,
                    source_name="職業倦怠",
                    relation_type="expands_on",
                    target_name="理想性工作反而更容易導致職業倦怠",
                    evidence="理想工作也可能耗竭。",
                )
            ],
        )

        self.assertIn("主題/概念索引命中：職業倦怠", response)
        self.assertIn("概念地圖", response)
        self.assertIn("職業倦怠 -> 理想性工作", response)
        self.assertIn("expands_on", response)
        self.assertIn("EP.369", response)
        self.assertIn("main_focus", response)
        self.assertIn("summary index", response)
        self.assertIn("再問我", response)

    def test_format_topic_response_handles_no_matches(self) -> None:
        self.assertIn("沒有找到主題/概念索引命中", _format_topic_response("不存在", []))

    def test_format_mentioned_response_shows_each_episode_once(self) -> None:
        episode = Episode(
            guid="episode-1",
            title="品質管理這一集",
            published_at=None,
            episode_url=None,
            audio_url=None,
            description=None,
        )
        response = _format_mentioned_response(
            "品質",
            [
                TranscriptSearchResult(
                    episode=episode,
                    chunk_index=1,
                    chunk_text="第一段提到品質。",
                    transcript_local_path="data/transcripts/episode.txt",
                    obsidian_transcript_path=None,
                ),
                TranscriptSearchResult(
                    episode=episode,
                    chunk_index=2,
                    chunk_text="第二段也提到品質。",
                    transcript_local_path="data/transcripts/episode.txt",
                    obsidian_transcript_path=None,
                ),
            ],
        )

        self.assertEqual(response.count("品質管理這一集"), 1)

    def test_episode_number_from_question_parses_common_forms(self) -> None:
        cases = {
            "EP.375 在講什麼": 375,
            "ep 375 有提到什麼": 375,
            "第375集在講什麼": 375,
            "375集在講什麼": 375,
        }

        for question, expected in cases.items():
            with self.subTest(question=question):
                self.assertEqual(_episode_number_from_question(question), expected)

    def test_format_episode_summary_answer(self) -> None:
        summary = EpisodeSummary(
            episode=Episode(
                guid="episode-375",
                title="EP.375《三種真實》",
                published_at=None,
                episode_url=None,
                audio_url=None,
                description=None,
            ),
            one_sentence_summary="這集主要圍繞「三種真實」展開。",
            key_points=["標題主題：三種真實"],
            topics=["三種真實"],
            summary_note_path="Inbox/Podcast Import/episodes/ep375.md",
            generated_by="local_heuristic_v1",
        )

        response = _format_episode_summary_answer("375集在講什麼", 375, summary)

        self.assertIn("EP.375", response)
        self.assertIn("三種真實", response)
        self.assertIn("重點", response)
        self.assertIn("保守摘要", response)

    def test_format_natural_language_answer_uses_summary_results(self) -> None:
        response = _format_natural_language_answer(
            "有沒有聊過職業倦怠？",
            [
                EpisodeSummary(
                    episode=Episode(
                        guid="episode-369",
                        title="EP.369《終結職業倦怠》",
                        published_at=None,
                        episode_url=None,
                        audio_url=None,
                        description=None,
                    ),
                    one_sentence_summary="本集探討職業倦怠的多面向成因與類型。",
                    key_points=["探討理想與現實的矛盾如何加劇職業倦怠。"],
                    topics=["職業倦怠是光譜狀態。"],
                    summary_note_path="Inbox/Podcast Import/episodes/ep369.md",
                    generated_by="openai_structured_v1",
                )
            ],
            [],
        )

        self.assertIn("感謝您的詢問，目前引書店Podcast的摘要有這些可能集數", response)
        self.assertIn("EP.369", response)
        self.assertIn("職業倦怠", response)
        self.assertNotIn("Summary note", response)

    def test_fallback_transcript_query_extracts_core_topic_from_common_questions(self) -> None:
        cases = [
            "有沒有聊過職業倦怠？",
            "有沒有跟職業倦怠相關",
            "有沒有討論職業倦怠",
        ]

        for question in cases:
            with self.subTest(question=question):
                self.assertEqual(_fallback_transcript_query(question), "職業倦怠")

    def test_readable_excerpt_breaks_long_unpunctuated_text(self) -> None:
        text = (
            "這是一段沒有標點符號而且很長很長的逐字稿內容使用者如果直接讀會非常辛苦所以需要先斷行"
            "讓證據片段至少可以分成幾行閱讀起來比較不會像一整塊牆"
        )

        excerpt = _readable_excerpt(text, "逐字稿", radius=80)

        self.assertIn("\n", excerpt)


if __name__ == "__main__":
    unittest.main()
