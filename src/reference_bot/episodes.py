from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Episode:
    guid: str
    title: str
    published_at: str | None
    episode_url: str | None
    audio_url: str | None
    description: str | None


@dataclass(frozen=True)
class TranscribedEpisode:
    episode: Episode
    transcript_local_path: str


@dataclass(frozen=True)
class IndexedTranscript:
    episode: Episode
    transcript_local_path: str
    obsidian_transcript_path: str | None


@dataclass(frozen=True)
class TranscriptSearchResult:
    episode: Episode
    chunk_index: int
    chunk_text: str
    transcript_local_path: str
    obsidian_transcript_path: str | None


@dataclass(frozen=True)
class EpisodeSummary:
    episode: Episode
    one_sentence_summary: str
    key_points: list[str]
    topics: list[str]
    summary_note_path: str | None
    generated_by: str


@dataclass(frozen=True)
class BookMention:
    episode: Episode
    name: str
    mention_level: str
    evidence: str


@dataclass(frozen=True)
class ConceptMention:
    episode: Episode
    name: str
    mention_level: str
    evidence: str


@dataclass(frozen=True)
class ConceptCluster:
    episode: Episode
    cluster_name: str
    mention_name: str
    mention_level: str
    evidence: str


@dataclass(frozen=True)
class ConceptRelationship:
    episode: Episode
    source_name: str
    relation_type: str
    target_name: str
    evidence: str
