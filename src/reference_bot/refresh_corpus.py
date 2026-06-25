from __future__ import annotations

import argparse
from dataclasses import dataclass
import os

from reference_bot.config import load_rss_settings
from reference_bot.concept_index import index_summary_mentions
from reference_bot.concept_map import index_concept_map
from reference_bot.healthcheck import format_health_report, run_healthcheck
from reference_bot.macwhisper import default_macwhisper_bin
from reference_bot.obsidian import DEFAULT_TRANSCRIPTS_DIR
from reference_bot.openai_summary import DEFAULT_OPENAI_SUMMARY_MODEL
from reference_bot.openai_transcription import (
    DEFAULT_OPENAI_TRANSCRIPTION_MODEL,
    DEFAULT_TRANSCRIPTION_PROMPT,
)
from reference_bot.pipeline import run_pipeline
from reference_bot.summary import DEFAULT_EPISODE_SUMMARIES_DIR


@dataclass(frozen=True)
class RefreshCorpusResult:
    pipeline_audio_downloaded: int
    pipeline_transcribed: int
    pipeline_transcript_notes_exported: int
    pipeline_transcripts_indexed: int
    pipeline_summaries_generated: int
    summary_episodes_indexed: int
    book_mentions_indexed: int
    concept_mentions_indexed: int
    concept_map_episodes_indexed: int
    concept_clusters_indexed: int
    concept_relationships_indexed: int


def refresh_corpus(
    *,
    feed_url: str,
    database_path: str,
    audio_dir: str,
    transcripts_dir: str,
    obsidian_transcripts_dir: str,
    obsidian_episodes_dir: str,
    limit: int,
    openai_api_key: str,
    openai_transcription_model: str = DEFAULT_OPENAI_TRANSCRIPTION_MODEL,
    openai_transcription_prompt: str = DEFAULT_TRANSCRIPTION_PROMPT,
    openai_summary_model: str = DEFAULT_OPENAI_SUMMARY_MODEL,
    mention_limit: int = 500,
    concept_map_limit: int = 500,
    run_eval: bool = False,
) -> RefreshCorpusResult:
    pipeline_result = run_pipeline(
        feed_url=feed_url,
        database_path=database_path,
        audio_dir=audio_dir,
        transcripts_dir=transcripts_dir,
        obsidian_transcripts_dir=obsidian_transcripts_dir,
        download_limit=limit,
        transcribe_limit=limit,
        export_limit=limit,
        obsidian_episodes_dir=obsidian_episodes_dir,
        mw_bin=default_macwhisper_bin(),
        transcription_provider="openai",
        openai_api_key=openai_api_key,
        openai_transcription_model=openai_transcription_model,
        openai_transcription_prompt=openai_transcription_prompt,
        openai_summary=True,
        openai_summary_model=openai_summary_model,
        skip_promotional=True,
        formal_episodes_only=True,
        delete_audio_after_transcription=True,
    )
    summary_episodes, book_mentions, concept_mentions = index_summary_mentions(
        database_path,
        limit=mention_limit,
    )
    map_episodes, concept_clusters, concept_relationships = index_concept_map(
        database_path,
        limit=concept_map_limit,
    )
    health_report = run_healthcheck(
        database_path=database_path,
        run_eval=run_eval,
        include_environment=False,
    )
    print(format_health_report(health_report))
    if not health_report.ok:
        raise RuntimeError("Corpus refresh failed the data healthcheck.")

    return RefreshCorpusResult(
        pipeline_audio_downloaded=pipeline_result.audio_downloaded,
        pipeline_transcribed=pipeline_result.transcribed,
        pipeline_transcript_notes_exported=pipeline_result.transcript_notes_exported,
        pipeline_transcripts_indexed=pipeline_result.transcripts_indexed,
        pipeline_summaries_generated=pipeline_result.summaries_generated,
        summary_episodes_indexed=summary_episodes,
        book_mentions_indexed=book_mentions,
        concept_mentions_indexed=concept_mentions,
        concept_map_episodes_indexed=map_episodes,
        concept_clusters_indexed=concept_clusters,
        concept_relationships_indexed=concept_relationships,
    )


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    settings = load_rss_settings()

    parser = argparse.ArgumentParser(description="Refresh podcast corpus data for scheduled deployment.")
    parser.add_argument("--feed-url", default=settings.podcast_rss_url)
    parser.add_argument("--database-path", default=settings.database_path)
    parser.add_argument("--audio-dir", default=os.getenv("AUDIO_DIR", "data/audio"))
    parser.add_argument("--transcripts-dir", default=os.getenv("TRANSCRIPTS_DIR", "data/transcripts"))
    parser.add_argument(
        "--obsidian-transcripts-dir",
        default=os.getenv("OBSIDIAN_TRANSCRIPTS_DIR", DEFAULT_TRANSCRIPTS_DIR),
    )
    parser.add_argument(
        "--obsidian-episodes-dir",
        default=os.getenv("OBSIDIAN_EPISODES_DIR", DEFAULT_EPISODE_SUMMARIES_DIR),
    )
    parser.add_argument("--limit", type=int, default=int(os.getenv("REFERENCE_REFRESH_LIMIT", "3")))
    parser.add_argument("--mention-limit", type=int, default=500)
    parser.add_argument("--concept-map-limit", type=int, default=500)
    parser.add_argument(
        "--openai-transcription-model",
        default=os.getenv("OPENAI_TRANSCRIBE_MODEL", DEFAULT_OPENAI_TRANSCRIPTION_MODEL),
    )
    parser.add_argument(
        "--openai-transcription-prompt",
        default=os.getenv("OPENAI_TRANSCRIBE_PROMPT", DEFAULT_TRANSCRIPTION_PROMPT),
    )
    parser.add_argument("--openai-summary-model", default=os.getenv("OPENAI_SUMMARY_MODEL", DEFAULT_OPENAI_SUMMARY_MODEL))
    parser.add_argument("--run-eval", action="store_true")
    args = parser.parse_args()

    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for scheduled corpus refresh.")

    result = refresh_corpus(
        feed_url=args.feed_url,
        database_path=args.database_path,
        audio_dir=args.audio_dir,
        transcripts_dir=args.transcripts_dir,
        obsidian_transcripts_dir=args.obsidian_transcripts_dir,
        obsidian_episodes_dir=args.obsidian_episodes_dir,
        limit=args.limit,
        openai_api_key=openai_api_key,
        openai_transcription_model=args.openai_transcription_model,
        openai_transcription_prompt=args.openai_transcription_prompt,
        openai_summary_model=args.openai_summary_model,
        mention_limit=args.mention_limit,
        concept_map_limit=args.concept_map_limit,
        run_eval=args.run_eval,
    )

    print("Corpus refresh complete.")
    print(f"Audio downloaded: {result.pipeline_audio_downloaded}")
    print(f"Transcribed: {result.pipeline_transcribed}")
    print(f"Transcript notes exported: {result.pipeline_transcript_notes_exported}")
    print(f"Transcripts indexed: {result.pipeline_transcripts_indexed}")
    print(f"Summaries generated: {result.pipeline_summaries_generated}")
    print(f"Summary episodes indexed: {result.summary_episodes_indexed}")
    print(f"Book mentions indexed: {result.book_mentions_indexed}")
    print(f"Concept mentions indexed: {result.concept_mentions_indexed}")
    print(f"Concept map episodes indexed: {result.concept_map_episodes_indexed}")
    print(f"Concept clusters indexed: {result.concept_clusters_indexed}")
    print(f"Concept relationships indexed: {result.concept_relationships_indexed}")


if __name__ == "__main__":
    main()
