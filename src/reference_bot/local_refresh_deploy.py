from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
from urllib import request

from reference_bot.config import load_rss_settings
from reference_bot.obsidian import DEFAULT_TRANSCRIPTS_DIR
from reference_bot.openai_summary import DEFAULT_OPENAI_SUMMARY_MODEL
from reference_bot.openai_transcription import (
    DEFAULT_OPENAI_TRANSCRIPTION_MODEL,
    DEFAULT_TRANSCRIPTION_PROMPT,
)
from reference_bot.refresh_corpus import refresh_corpus
from reference_bot.summary import DEFAULT_EPISODE_SUMMARIES_DIR


@dataclass(frozen=True)
class LocalRefreshDeployResult:
    changed: bool
    committed: bool
    pushed: bool
    deploy_hook_called: bool
    commit_message: str | None


def local_refresh_deploy(
    *,
    repo_dir: str,
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
    branch: str | None = None,
    remote: str = "origin",
    push: bool = True,
    pull_first: bool = True,
    deploy_hook_url: str | None = None,
) -> LocalRefreshDeployResult:
    repo_path = Path(repo_dir).expanduser().resolve()
    _ensure_git_repo(repo_path)
    database_path = _repo_path(repo_path, database_path)
    audio_dir = _repo_path(repo_path, audio_dir)
    transcripts_dir = _repo_path(repo_path, transcripts_dir)
    obsidian_transcripts_dir = _repo_path(repo_path, obsidian_transcripts_dir)
    obsidian_episodes_dir = _repo_path(repo_path, obsidian_episodes_dir)
    if pull_first:
        _run_git(repo_path, "pull", "--ff-only")

    refresh_corpus(
        feed_url=feed_url,
        database_path=database_path,
        audio_dir=audio_dir,
        transcripts_dir=transcripts_dir,
        obsidian_transcripts_dir=obsidian_transcripts_dir,
        obsidian_episodes_dir=obsidian_episodes_dir,
        limit=limit,
        openai_api_key=openai_api_key,
        openai_transcription_model=openai_transcription_model,
        openai_transcription_prompt=openai_transcription_prompt,
        openai_summary_model=openai_summary_model,
        mention_limit=mention_limit,
        concept_map_limit=concept_map_limit,
        run_eval=run_eval,
    )

    tracked_paths = ["data/episodes.sqlite3"]
    _run_git(repo_path, "add", *tracked_paths)
    changed = _has_staged_changes(repo_path)
    if not changed:
        print("No deployable corpus changes.")
        return LocalRefreshDeployResult(
            changed=False,
            committed=False,
            pushed=False,
            deploy_hook_called=False,
            commit_message=None,
        )

    commit_message = "Refresh podcast corpus"
    _run_git(repo_path, "commit", "-m", commit_message)
    pushed = False
    if push:
        target_branch = branch or _current_branch(repo_path)
        _run_git(repo_path, "push", remote, f"HEAD:{target_branch}")
        pushed = True

    hook_called = False
    if deploy_hook_url:
        _call_deploy_hook(deploy_hook_url)
        hook_called = True

    return LocalRefreshDeployResult(
        changed=True,
        committed=True,
        pushed=pushed,
        deploy_hook_called=hook_called,
        commit_message=commit_message,
    )


def _ensure_git_repo(repo_path: Path) -> None:
    if not (repo_path / ".git").exists():
        raise RuntimeError(
            f"{repo_path} is not a Git checkout. Local refresh deploy needs a repo that can push to GitHub."
        )


def _repo_path(repo_path: Path, value: str) -> str:
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path)
    return str(repo_path / path)


def _run_git(repo_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    command = ["git", *args]
    print(f"+ {' '.join(command)}")
    return subprocess.run(
        command,
        cwd=repo_path,
        check=True,
        text=True,
    )


def _has_staged_changes(repo_path: Path) -> bool:
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=repo_path,
        check=False,
    )
    if result.returncode == 0:
        return False
    if result.returncode == 1:
        return True
    raise RuntimeError("Could not check staged git changes.")


def _current_branch(repo_path: Path) -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo_path,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    branch = result.stdout.strip()
    if not branch:
        raise RuntimeError("Cannot push from detached HEAD unless --branch is provided.")
    return branch


def _call_deploy_hook(deploy_hook_url: str) -> None:
    print("Calling deploy hook.")
    request.urlopen(request.Request(deploy_hook_url, method="POST"), timeout=30).close()


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    settings = load_rss_settings()

    parser = argparse.ArgumentParser(
        description="Refresh the corpus locally, commit data/episodes.sqlite3, push it to GitHub, and optionally call a deploy hook."
    )
    parser.add_argument("--repo-dir", default=os.getenv("REFERENCE_REPO_DIR", "."))
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
    parser.add_argument("--branch", default=os.getenv("REFERENCE_DEPLOY_BRANCH") or None)
    parser.add_argument("--remote", default=os.getenv("REFERENCE_DEPLOY_REMOTE", "origin"))
    parser.add_argument("--no-pull", action="store_true")
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--deploy-hook-url", default=os.getenv("RENDER_DEPLOY_HOOK_URL") or None)
    args = parser.parse_args()

    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for local refresh deploy.")

    result = local_refresh_deploy(
        repo_dir=args.repo_dir,
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
        branch=args.branch,
        remote=args.remote,
        push=not args.no_push,
        pull_first=not args.no_pull,
        deploy_hook_url=args.deploy_hook_url,
    )
    print("Local refresh deploy complete.")
    print(f"Changed: {result.changed}")
    print(f"Committed: {result.committed}")
    print(f"Pushed: {result.pushed}")
    print(f"Deploy hook called: {result.deploy_hook_called}")


if __name__ == "__main__":
    main()
