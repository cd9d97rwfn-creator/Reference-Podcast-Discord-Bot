from __future__ import annotations

from dataclasses import dataclass
import re

from reference_bot.episodes import ConceptCluster, ConceptMention, ConceptRelationship
from reference_bot.normalization import cluster_names_for_text, normalize_mention_name
from reference_bot.storage import (
    list_concept_mentions,
    replace_concept_clusters,
    replace_concept_relationships,
    search_book_mentions,
    search_concept_clusters,
    search_concept_relationships,
)


@dataclass(frozen=True)
class ConceptMapResult:
    query: str
    clusters: list[ConceptCluster]
    relationships: list[ConceptRelationship]


def index_concept_map(database_path: str, limit: int = 100) -> tuple[int, int, int]:
    mentions_by_episode: dict[str, list[ConceptMention]] = {}
    for mention in list_concept_mentions(database_path, limit=limit * 20):
        mentions_by_episode.setdefault(mention.episode.guid, []).append(mention)
        if len(mentions_by_episode) >= limit:
            break
    return index_concept_map_from_mentions(database_path, mentions_by_episode)


def index_concept_map_from_mentions(
    database_path: str,
    mentions_by_episode: dict[str, list[ConceptMention]],
) -> tuple[int, int, int]:
    episodes_indexed = 0
    clusters_indexed = 0
    relationships_indexed = 0
    for episode_guid, mentions in mentions_by_episode.items():
        clusters = _clusters_from_mentions(mentions)
        relationships = _relationships_from_clusters(clusters)
        clusters_indexed += replace_concept_clusters(database_path, episode_guid, clusters)
        relationships_indexed += replace_concept_relationships(database_path, episode_guid, relationships)
        episodes_indexed += 1
    return episodes_indexed, clusters_indexed, relationships_indexed


def concept_map(database_path: str, query: str, limit: int = 12) -> ConceptMapResult:
    return ConceptMapResult(
        query=query,
        clusters=search_concept_clusters(database_path, query=query, limit=limit),
        relationships=search_concept_relationships(database_path, query=query, limit=limit),
    )


def format_concept_map(database_path: str, result: ConceptMapResult) -> str:
    if not result.clusters and not result.relationships:
        return f"沒有找到「{result.query}」的概念地圖資料。"

    lines = [f"概念地圖：{result.query}", ""]
    if result.clusters:
        lines.append("相關集數與子概念：")
        for cluster in result.clusters[:8]:
            label = cluster.mention_name
            if cluster.mention_name != cluster.cluster_name:
                label = f"{cluster.cluster_name} -> {cluster.mention_name}"
            lines.append(f"- {label}｜{cluster.mention_level}｜{cluster.episode.title}")
            if cluster.evidence:
                lines.append(f"  線索：{_short_line(cluster.evidence)}")

    book_mentions = search_book_mentions(database_path, result.query, limit=5)
    if book_mentions:
        lines.extend(["", "相關書籍："])
        for mention in book_mentions:
            lines.append(f"- 《{mention.name}》｜{mention.mention_level}｜{mention.episode.title}")

    if result.relationships:
        lines.extend(["", "概念關係："])
        for relationship in result.relationships[:8]:
            lines.append(
                f"- {relationship.source_name} {relationship.relation_type} "
                f"{relationship.target_name}｜{relationship.episode.title}"
            )
            if relationship.evidence:
                lines.append(f"  線索：{_short_line(relationship.evidence)}")

    return "\n".join(lines)


def _clusters_from_mentions(mentions: list[ConceptMention]) -> list[ConceptCluster]:
    clusters: list[ConceptCluster] = []
    for mention in mentions:
        mention_name = normalize_mention_name(mention.name)
        cluster_names = cluster_names_for_text(f"{mention_name} {mention.evidence}") or [mention_name]
        for cluster_name in cluster_names:
            clusters.append(
                ConceptCluster(
                    episode=mention.episode,
                    cluster_name=cluster_name,
                    mention_name=mention_name,
                    mention_level=mention.mention_level,
                    evidence=mention.evidence,
                )
            )
    return _dedupe_clusters(clusters)


def _relationships_from_clusters(clusters: list[ConceptCluster]) -> list[ConceptRelationship]:
    relationships: list[ConceptRelationship] = []
    for cluster in clusters:
        if cluster.cluster_name == cluster.mention_name:
            continue
        relationships.append(
            ConceptRelationship(
                episode=cluster.episode,
                source_name=cluster.cluster_name,
                relation_type="expands_on",
                target_name=cluster.mention_name,
                evidence=cluster.evidence,
            )
        )
    return _dedupe_relationships(relationships)


def _dedupe_clusters(clusters: list[ConceptCluster]) -> list[ConceptCluster]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[ConceptCluster] = []
    for cluster in clusters:
        key = (cluster.episode.guid, cluster.cluster_name, cluster.mention_name)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cluster)
    return deduped


def _dedupe_relationships(relationships: list[ConceptRelationship]) -> list[ConceptRelationship]:
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[ConceptRelationship] = []
    for relationship in relationships:
        key = (
            relationship.episode.guid,
            relationship.source_name,
            relationship.relation_type,
            relationship.target_name,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(relationship)
    return deduped


def _short_line(text: str, limit: int = 160) -> str:
    cleaned = " ".join(text.split())
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"__([^_]+)__", r"\1", cleaned)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."
