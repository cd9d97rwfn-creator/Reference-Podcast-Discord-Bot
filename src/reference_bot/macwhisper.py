from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import shutil
import subprocess

from reference_bot.episodes import Episode


APP_BUNDLE_MW_PATH = "/Applications/MacWhisper.app/Contents/MacOS/mw"


@dataclass(frozen=True)
class MacWhisperTranscriptionResult:
    episode: Episode
    transcript_path: Path | None
    error: str | None

    @property
    def succeeded(self) -> bool:
        return self.error is None and self.transcript_path is not None


def transcribe_episode_audio(
    episode: Episode,
    audio_local_path: str,
    transcripts_dir: str,
    mw_bin: str = "mw",
    model: str | None = None,
    persist: bool = False,
    timeout_seconds: int | None = None,
) -> MacWhisperTranscriptionResult:
    audio_path = Path(audio_local_path).expanduser()
    if not audio_path.is_file():
        return MacWhisperTranscriptionResult(
            episode=episode,
            transcript_path=None,
            error=f"Audio file does not exist: {audio_path}",
        )

    output_directory = Path(transcripts_dir).expanduser()
    output_directory.mkdir(parents=True, exist_ok=True)
    transcript_path = _unique_text_path(output_directory / f"{_transcript_filename_stem(episode)}.txt")

    command = [mw_bin, "transcribe"]
    if model:
        command.extend(["--model", model])
    if persist:
        command.append("--persist")
    command.append(str(audio_path))

    try:
        completed_process = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        return MacWhisperTranscriptionResult(
            episode=episode,
            transcript_path=None,
            error=f"MacWhisper CLI not found: {mw_bin}",
        )
    except subprocess.TimeoutExpired as exc:
        return MacWhisperTranscriptionResult(
            episode=episode,
            transcript_path=None,
            error=f"MacWhisper transcription timed out after {exc.timeout} seconds.",
        )

    if completed_process.returncode != 0:
        error = completed_process.stderr.strip() or completed_process.stdout.strip()
        return MacWhisperTranscriptionResult(
            episode=episode,
            transcript_path=None,
            error=error or f"MacWhisper exited with status {completed_process.returncode}.",
        )

    transcript_text = completed_process.stdout.strip()
    if not transcript_text:
        return MacWhisperTranscriptionResult(
            episode=episode,
            transcript_path=None,
            error="MacWhisper returned an empty transcript.",
        )

    transcript_path.write_text(transcript_text + "\n", encoding="utf-8")
    return MacWhisperTranscriptionResult(
        episode=episode,
        transcript_path=transcript_path,
        error=None,
    )


def default_macwhisper_bin() -> str:
    path_mw = shutil.which("mw")
    if path_mw:
        return path_mw

    app_bundle_mw = Path(APP_BUNDLE_MW_PATH)
    if app_bundle_mw.is_file():
        return str(app_bundle_mw)

    return "mw"


def _unique_text_path(target_path: Path) -> Path:
    if not target_path.exists():
        return target_path

    counter = 2
    while True:
        candidate = target_path.with_name(f"{target_path.stem}-{counter}{target_path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _transcript_filename_stem(episode: Episode) -> str:
    date_prefix = _date_prefix(episode.published_at)
    guid_hash = hashlib.sha256(episode.guid.encode("utf-8")).hexdigest()[:12]
    title_slug = _slugify(episode.title)[:80] or "episode"
    return f"{date_prefix}-{guid_hash}-{title_slug}"


def _date_prefix(published_at: str | None) -> str:
    if not published_at:
        return "unknown-date"

    match = re.search(r"\b(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\b", published_at)
    if not match:
        return "unknown-date"

    day, month_name, year = match.groups()
    months = {
        "Jan": "01",
        "Feb": "02",
        "Mar": "03",
        "Apr": "04",
        "May": "05",
        "Jun": "06",
        "Jul": "07",
        "Aug": "08",
        "Sep": "09",
        "Oct": "10",
        "Nov": "11",
        "Dec": "12",
    }
    month = months.get(month_name, "00")
    return f"{year}-{month}-{int(day):02d}"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", value, flags=re.UNICODE)
    slug = re.sub(r"-+", "-", slug).strip("-_")
    return slug.lower()
