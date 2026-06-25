from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import re
import sqlite3

from reference_bot.config import load_rss_settings
from reference_bot.downloader import download_episode_audio
from reference_bot.macwhisper import default_macwhisper_bin, transcribe_episode_audio
from reference_bot.obsidian import DEFAULT_TRANSCRIPTS_DIR, export_transcript_note
from reference_bot.openai_summary import generate_openai_episode_summaries
from reference_bot.openai_transcription import (
    DEFAULT_OPENAI_TRANSCRIPTION_MODEL,
    DEFAULT_TRANSCRIPTION_PROMPT,
    transcribe_episode_audio_openai,
)
from reference_bot.rss_sync import sync_rss
from reference_bot.storage import (
    initialize_database,
    list_pending_downloads,
    list_pending_transcript_exports,
    list_pending_transcriptions,
    mark_audio_delete_failed,
    mark_audio_deleted,
    mark_audio_download_failed,
    mark_audio_downloaded,
    mark_transcript_imported,
    mark_transcript_note_export_failed,
    mark_transcript_note_exported,
    mark_transcription_failed,
)
from reference_bot.summary import DEFAULT_EPISODE_SUMMARIES_DIR, generate_episode_summaries
from reference_bot.transcript_index import index_transcripts


@dataclass(frozen=True)
class PipelineResult:
    rss_episodes_seen: int
    audio_downloaded: int
    audio_download_failed: int
    audio_deleted: int
    transcribed: int
    transcription_failed: int
    transcript_notes_exported: int
    transcript_note_export_failed: int
    transcripts_indexed: int
    summaries_generated: int


def run_pipeline(
    feed_url: str,
    database_path: str,
    audio_dir: str,
    transcripts_dir: str,
    obsidian_transcripts_dir: str,
    download_limit: int,
    transcribe_limit: int,
    export_limit: int,
    obsidian_episodes_dir: str = DEFAULT_EPISODE_SUMMARIES_DIR,
    mw_bin: str = "mw",
    model: str | None = None,
    persist: bool = False,
    timeout_seconds: int | None = None,
    transcription_provider: str = "macwhisper",
    openai_api_key: str | None = None,
    openai_transcription_model: str = DEFAULT_OPENAI_TRANSCRIPTION_MODEL,
    openai_transcription_prompt: str = DEFAULT_TRANSCRIPTION_PROMPT,
    openai_summary: bool = False,
    openai_summary_model: str = "gpt-4.1-mini",
    skip_promotional: bool = False,
    formal_episodes_only: bool = False,
    delete_audio_after_transcription: bool = False,
) -> PipelineResult:
    rss_episodes_seen = sync_rss(feed_url=feed_url, database_path=database_path)
    audio_downloaded, audio_download_failed = _download_pending_audio(
        database_path=database_path,
        audio_dir=audio_dir,
        limit=download_limit,
        skip_promotional=skip_promotional,
        formal_episodes_only=formal_episodes_only,
    )
    transcribed, transcription_failed, audio_deleted = _transcribe_pending_audio(
        database_path=database_path,
        transcripts_dir=transcripts_dir,
        limit=transcribe_limit,
        mw_bin=mw_bin,
        model=model,
        persist=persist,
        timeout_seconds=timeout_seconds,
        transcription_provider=transcription_provider,
        openai_api_key=openai_api_key,
        openai_transcription_model=openai_transcription_model,
        openai_transcription_prompt=openai_transcription_prompt,
        skip_promotional=skip_promotional,
        formal_episodes_only=formal_episodes_only,
        delete_audio_after_transcription=delete_audio_after_transcription,
    )
    transcript_notes_exported, transcript_note_export_failed = _export_pending_transcript_notes(
        database_path=database_path,
        transcripts_dir=obsidian_transcripts_dir,
        limit=export_limit,
    )
    transcripts_indexed = index_transcripts(database_path=database_path, limit=export_limit)
    if openai_summary:
        if not openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI summaries.")
        summaries_generated = generate_openai_episode_summaries(
            database_path=database_path,
            summaries_dir=obsidian_episodes_dir,
            limit=export_limit,
            api_key=openai_api_key,
            model=openai_summary_model,
        )
    else:
        summaries_generated = generate_episode_summaries(
            database_path=database_path,
            summaries_dir=obsidian_episodes_dir,
            limit=export_limit,
        )

    return PipelineResult(
        rss_episodes_seen=rss_episodes_seen,
        audio_downloaded=audio_downloaded,
        audio_download_failed=audio_download_failed,
        audio_deleted=audio_deleted,
        transcribed=transcribed,
        transcription_failed=transcription_failed,
        transcript_notes_exported=transcript_notes_exported,
        transcript_note_export_failed=transcript_note_export_failed,
        transcripts_indexed=transcripts_indexed,
        summaries_generated=summaries_generated,
    )


def main() -> None:
    settings = load_rss_settings()

    parser = argparse.ArgumentParser(description="Run the podcast import pipeline.")
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
    parser.add_argument("--mw-bin", default=os.getenv("MACWHISPER_BIN", default_macwhisper_bin()))
    parser.add_argument("--model", default=os.getenv("MACWHISPER_MODEL"))
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=None)
    parser.add_argument(
        "--transcription-provider",
        choices=["macwhisper", "openai"],
        default=os.getenv("TRANSCRIPTION_PROVIDER", "macwhisper"),
    )
    parser.add_argument(
        "--openai-transcription-model",
        default=os.getenv("OPENAI_TRANSCRIBE_MODEL", DEFAULT_OPENAI_TRANSCRIPTION_MODEL),
    )
    parser.add_argument(
        "--openai-transcription-prompt",
        default=os.getenv("OPENAI_TRANSCRIBE_PROMPT", DEFAULT_TRANSCRIPTION_PROMPT),
    )
    parser.add_argument("--openai-summary", action="store_true")
    parser.add_argument("--openai-summary-model", default=os.getenv("OPENAI_SUMMARY_MODEL", "gpt-4.1-mini"))
    parser.add_argument("--skip-promotional", action="store_true")
    parser.add_argument("--formal-episodes-only", action="store_true")
    parser.add_argument("--delete-audio-after-transcription", action="store_true")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--download-limit", type=int, default=None)
    parser.add_argument("--transcribe-limit", type=int, default=None)
    parser.add_argument("--export-limit", type=int, default=None)
    args = parser.parse_args()

    result = run_pipeline(
        feed_url=args.feed_url,
        database_path=args.database_path,
        audio_dir=args.audio_dir,
        transcripts_dir=args.transcripts_dir,
        obsidian_transcripts_dir=args.obsidian_transcripts_dir,
        download_limit=_resolved_limit(args.download_limit, args.limit),
        transcribe_limit=_resolved_limit(args.transcribe_limit, args.limit),
        export_limit=_resolved_limit(args.export_limit, args.limit),
        obsidian_episodes_dir=args.obsidian_episodes_dir,
        mw_bin=args.mw_bin,
        model=args.model,
        persist=args.persist,
        timeout_seconds=args.timeout_seconds,
        transcription_provider=args.transcription_provider,
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip() or None,
        openai_transcription_model=args.openai_transcription_model,
        openai_transcription_prompt=args.openai_transcription_prompt,
        openai_summary=args.openai_summary,
        openai_summary_model=args.openai_summary_model,
        skip_promotional=args.skip_promotional,
        formal_episodes_only=args.formal_episodes_only,
        delete_audio_after_transcription=args.delete_audio_after_transcription,
    )

    print("Pipeline complete.")
    print(f"RSS episodes seen: {result.rss_episodes_seen}")
    print(f"Audio downloaded: {result.audio_downloaded}")
    print(f"Audio download failed: {result.audio_download_failed}")
    print(f"Audio deleted: {result.audio_deleted}")
    print(f"Transcribed: {result.transcribed}")
    print(f"Transcription failed: {result.transcription_failed}")
    print(f"Transcript notes exported: {result.transcript_notes_exported}")
    print(f"Transcript note export failed: {result.transcript_note_export_failed}")
    print(f"Transcripts indexed: {result.transcripts_indexed}")
    print(f"Summaries generated: {result.summaries_generated}")


def _resolved_limit(specific_limit: int | None, default_limit: int) -> int:
    if specific_limit is None:
        return default_limit
    return specific_limit


def _download_pending_audio(
    database_path: str,
    audio_dir: str,
    limit: int,
    skip_promotional: bool,
    formal_episodes_only: bool,
) -> tuple[int, int]:
    if limit < 1:
        return 0, 0

    downloaded = 0
    failed = 0
    for episode in list_pending_downloads(
        database_path,
        limit=_candidate_limit(limit, skip_promotional, formal_episodes_only),
    ):
        if _should_skip_episode(
            episode.title,
            skip_promotional=skip_promotional,
            formal_episodes_only=formal_episodes_only,
        ):
            continue
        if downloaded + failed >= limit:
            break
        result = download_episode_audio(episode, audio_dir)
        if result.succeeded and result.local_path is not None:
            mark_audio_downloaded(database_path, episode.guid, str(result.local_path))
            downloaded += 1
            continue

        mark_audio_download_failed(
            database_path,
            episode.guid,
            result.error or "Unknown download error.",
        )
        failed += 1

    return downloaded, failed


def _transcribe_pending_audio(
    database_path: str,
    transcripts_dir: str,
    limit: int,
    mw_bin: str,
    model: str | None,
    persist: bool,
    timeout_seconds: int | None,
    transcription_provider: str,
    openai_api_key: str | None,
    openai_transcription_model: str,
    openai_transcription_prompt: str,
    skip_promotional: bool,
    formal_episodes_only: bool,
    delete_audio_after_transcription: bool,
) -> tuple[int, int, int]:
    if limit < 1:
        return 0, 0, 0

    transcribed = 0
    failed = 0
    audio_deleted = 0
    audio_paths = _audio_local_paths(database_path)

    for episode in list_pending_transcriptions(
        database_path,
        limit=_candidate_limit(limit, skip_promotional, formal_episodes_only),
    ):
        if _should_skip_episode(
            episode.title,
            skip_promotional=skip_promotional,
            formal_episodes_only=formal_episodes_only,
        ):
            continue
        if transcribed + failed >= limit:
            break
        audio_local_path = audio_paths.get(episode.guid)
        if not audio_local_path:
            mark_transcription_failed(database_path, episode.guid, "Episode has no audio_local_path.")
            failed += 1
            continue

        print(f"Transcribing: {episode.title}", flush=True)
        if transcription_provider == "openai":
            if not openai_api_key:
                mark_transcription_failed(database_path, episode.guid, "OPENAI_API_KEY is required.")
                failed += 1
                continue
            result = transcribe_episode_audio_openai(
                episode=episode,
                audio_local_path=audio_local_path,
                transcripts_dir=transcripts_dir,
                api_key=openai_api_key,
                model=openai_transcription_model,
                prompt=openai_transcription_prompt,
                timeout_seconds=timeout_seconds or 180,
            )
        else:
            result = transcribe_episode_audio(
                episode=episode,
                audio_local_path=audio_local_path,
                transcripts_dir=transcripts_dir,
                mw_bin=mw_bin,
                model=model,
                persist=persist,
                timeout_seconds=timeout_seconds,
            )
        if result.succeeded and result.transcript_path is not None:
            mark_transcript_imported(database_path, episode.guid, str(result.transcript_path))
            transcribed += 1
            print(f"Transcribed: {episode.title}", flush=True)
            if delete_audio_after_transcription:
                audio_deleted += _delete_audio_file(database_path, episode.guid, audio_local_path)
            continue

        mark_transcription_failed(
            database_path,
            episode.guid,
            result.error or "Unknown transcription error.",
        )
        failed += 1
        print(f"Transcription failed: {episode.title}", flush=True)
        if result.error and _is_fatal_openai_quota_error(result.error):
            break

    return transcribed, failed, audio_deleted


def _export_pending_transcript_notes(
    database_path: str,
    transcripts_dir: str,
    limit: int,
) -> tuple[int, int]:
    exported = 0
    failed = 0

    for candidate in list_pending_transcript_exports(database_path, limit=limit):
        try:
            note_path = export_transcript_note(candidate, transcripts_dir)
        except Exception as exc:
            mark_transcript_note_export_failed(database_path, candidate.episode.guid, str(exc))
            failed += 1
            continue

        mark_transcript_note_exported(database_path, candidate.episode.guid, str(note_path))
        exported += 1

    return exported, failed


def _audio_local_paths(database_path: str) -> dict[str, str]:
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT guid, audio_local_path
            FROM episodes
            WHERE audio_local_path IS NOT NULL
                AND TRIM(audio_local_path) != ''
            """
        ).fetchall()

    return {row[0]: row[1] for row in rows}


def _delete_audio_file(database_path: str, episode_guid: str, audio_local_path: str) -> int:
    audio_path = Path(audio_local_path)
    try:
        if audio_path.exists():
            audio_path.unlink()
        mark_audio_deleted(database_path, episode_guid)
        return 1
    except OSError as exc:
        mark_audio_delete_failed(database_path, episode_guid, str(exc))
        return 0


def _candidate_limit(limit: int, skip_promotional: bool, formal_episodes_only: bool = False) -> int:
    if not skip_promotional and not formal_episodes_only:
        return limit
    return max(limit * 3, limit)


def _should_skip_episode(title: str, *, skip_promotional: bool, formal_episodes_only: bool) -> bool:
    if formal_episodes_only and not _is_formal_episode_title(title):
        return True
    if skip_promotional and _is_promotional_title(title):
        return True
    return False


def _is_formal_episode_title(title: str) -> bool:
    return re.search(r"\bEP\.?\s*\d+", title, flags=re.IGNORECASE) is not None


def _is_promotional_title(title: str) -> bool:
    return any(
        marker in title
        for marker in ["團購", "報名", "活動", "超限時", "優惠", "折扣", "作品推薦", "幕後特輯"]
    )


def _is_fatal_openai_quota_error(error: str) -> bool:
    lowered = error.lower()
    return "exceeded your current quota" in lowered or "billing details" in lowered


if __name__ == "__main__":
    main()
