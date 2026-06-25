from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_bot.concept_map import index_concept_map
from reference_bot.concept_map_eval import (
    ConceptMapEvalCase,
    evaluate_concept_map,
    format_eval_results,
)
from reference_bot.config import RssSettings
from reference_bot.episodes import BookMention, ConceptMention, Episode, EpisodeSummary
from reference_bot.eval_concept_map import main
from reference_bot.storage import (
    replace_book_mentions,
    replace_concept_mentions,
    upsert_episode_summary,
    upsert_episodes,
)


class ConceptMapEvalTests(unittest.TestCase):
    def test_evaluate_concept_map_reports_pass_and_review_cases(self) -> None:
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
            upsert_episode_summary(
                database_path,
                EpisodeSummary(
                    episode=episode,
                    one_sentence_summary="本集討論財富階梯與財富累積。",
                    key_points=["財富階梯六級。"],
                    topics=["財富"],
                    summary_note_path=None,
                    generated_by="openai_structured_v1",
                ),
            )
            replace_book_mentions(
                database_path,
                episode.guid,
                [
                    BookMention(
                        episode=episode,
                        name="財富階梯",
                        mention_level="main_focus",
                        evidence="整集主題。",
                    )
                ],
            )
            replace_concept_mentions(
                database_path,
                episode.guid,
                [
                    ConceptMention(
                        episode=episode,
                        name="財富階梯六級",
                        mention_level="referenced",
                        evidence="討論財富累積。",
                    )
                ],
            )
            index_concept_map(database_path, limit=10)

            results = evaluate_concept_map(
                database_path,
                cases=(
                    ConceptMapEvalCase(
                        query="致富",
                        expected_episode_keywords=("財富階梯",),
                        expected_concept_keywords=("財富",),
                    ),
                    ConceptMapEvalCase(
                        query="心理界限",
                        expected_episode_keywords=("心理界限",),
                        expected_concept_keywords=("心理界限",),
                    ),
                ),
            )
            output = format_eval_results(results)

        self.assertEqual([result.status for result in results], ["PASS", "REVIEW"])
        self.assertIn("Concept map eval: 1/2 PASS", output)
        self.assertIn("[REVIEW] 心理界限", output)

    def test_eval_concept_map_cli_prints_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            output = StringIO()
            with patch(
                "reference_bot.eval_concept_map.load_rss_settings",
                return_value=RssSettings(
                    podcast_rss_url="https://example.com/feed.xml",
                    database_path=database_path,
                ),
            ):
                with patch("sys.argv", ["reference-eval-concept-map", "--skip-reindex"]):
                    with redirect_stdout(output):
                        main()

        self.assertIn("Concept map eval:", output.getvalue())
        self.assertIn("[REVIEW]", output.getvalue())


if __name__ == "__main__":
    unittest.main()
