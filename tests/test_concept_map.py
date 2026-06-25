from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_bot.concept_map import concept_map, format_concept_map, index_concept_map
from reference_bot.episodes import ConceptMention, Episode
from reference_bot.storage import (
    replace_concept_mentions,
    search_concept_clusters,
    search_concept_relationships,
    upsert_episodes,
)


class ConceptMapTests(unittest.TestCase):
    def test_index_concept_map_clusters_known_concepts(self) -> None:
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
                        evidence="討論財富累積與階段差異。",
                    ),
                    ConceptMention(
                        episode=episode,
                        name="財富守護",
                        mention_level="referenced",
                        evidence="討論如何守住資產。",
                    ),
                ],
            )

            episodes, clusters, relationships = index_concept_map(database_path, limit=10)
            cluster_results = search_concept_clusters(database_path, "致富", limit=10)
            relationship_results = search_concept_relationships(database_path, "財富", limit=10)

        self.assertEqual(episodes, 1)
        self.assertEqual(clusters, 2)
        self.assertEqual(relationships, 2)
        self.assertEqual({cluster.cluster_name for cluster in cluster_results}, {"財富"})
        self.assertIn("財富階梯六級", {cluster.mention_name for cluster in cluster_results})
        self.assertIn(
            ("財富", "expands_on", "財富階梯六級"),
            {
                (relationship.source_name, relationship.relation_type, relationship.target_name)
                for relationship in relationship_results
            },
        )

    def test_format_concept_map_includes_clusters_books_and_relationships(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            episode = Episode(
                guid="episode-339",
                title="EP.339《心理界限》",
                published_at="Fri, 22 Aug 2025 00:00:00 +0800",
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
                        name="家庭心理界限模糊",
                        mention_level="referenced",
                        evidence="討論家庭關係中的心理界限。",
                    )
                ],
            )
            index_concept_map(database_path, limit=10)

            output = format_concept_map(database_path, concept_map(database_path, "邊界感", limit=10))

        self.assertIn("概念地圖：邊界感", output)
        self.assertIn("心理界限 -> 家庭心理界限模糊", output)
        self.assertIn("心理界限 expands_on 家庭心理界限模糊", output)

    def test_index_concept_map_does_not_cluster_generic_boundaries_as_psychological(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = str(Path(temporary_directory) / "episodes.sqlite3")
            episode = Episode(
                guid="episode-346",
                title="EP.346《植物靈藥》",
                published_at="Fri, 26 Sep 2025 00:00:00 +0800",
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
                        name="合法與非法的模糊邊界",
                        mention_level="referenced",
                        evidence="討論法律規定與執法實務矛盾。",
                    )
                ],
            )

            index_concept_map(database_path, limit=10)
            relationship_results = search_concept_relationships(database_path, "心理界限", limit=10)

        self.assertNotIn(
            ("心理界限", "合法與非法的模糊邊界"),
            {
                (relationship.source_name, relationship.target_name)
                for relationship in relationship_results
            },
        )


if __name__ == "__main__":
    unittest.main()
