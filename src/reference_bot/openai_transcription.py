from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import shutil
import subprocess
from pathlib import Path
import re
import time

from reference_bot.episodes import Episode
from reference_bot.openai_api import transcribe_audio_file


DEFAULT_OPENAI_TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe"
DEFAULT_TRANSCRIPTION_PROMPT = (
    "這是繁體中文 podcast《引書店》。請保留繁體中文、書名、人名與口語脈絡。"
    "常見詞包含：引書店、納瓦爾寶典、泛思醫學。"
)


@dataclass(frozen=True)
class OpenAITranscriptionResult:
    episode: Episode
    transcript_path: Path | None
    error: str | None

    @property
    def succeeded(self) -> bool:
        return self.error is None and self.transcript_path is not None


def transcribe_episode_audio_openai(
    *,
    episode: Episode,
    audio_local_path: str,
    transcripts_dir: str,
    api_key: str,
    model: str = DEFAULT_OPENAI_TRANSCRIPTION_MODEL,
    language: str = "zh",
    prompt: str = DEFAULT_TRANSCRIPTION_PROMPT,
    chunk_seconds: int = 240,
    bitrate: str = "24k",
    timeout_seconds: int = 180,
    chunks_dir: str = ".openai-audio-chunks",
) -> OpenAITranscriptionResult:
    audio_path = Path(audio_local_path).expanduser()
    if not audio_path.is_file():
        return OpenAITranscriptionResult(
            episode=episode,
            transcript_path=None,
            error=f"Audio file does not exist: {audio_path}",
        )

    output_directory = Path(transcripts_dir).expanduser()
    output_directory.mkdir(parents=True, exist_ok=True)
    transcript_path = _unique_text_path(
        output_directory / f"{_transcript_filename_stem(episode)}-openai-direct.txt"
    )

    try:
        chunk_paths = split_audio_for_openai(
            audio_path=audio_path,
            chunks_dir=Path(chunks_dir).expanduser() / _chunk_directory_name(episode),
            chunk_seconds=chunk_seconds,
            bitrate=bitrate,
        )
        transcript_text = _transcribe_chunks(
            chunk_paths=chunk_paths,
            api_key=api_key,
            model=model,
            language=language,
            prompt=prompt,
            timeout_seconds=timeout_seconds,
            episode_title=episode.title,
        )
    except Exception as exc:
        return OpenAITranscriptionResult(episode=episode, transcript_path=None, error=str(exc))

    if not transcript_text.strip():
        return OpenAITranscriptionResult(
            episode=episode,
            transcript_path=None,
            error="OpenAI returned an empty transcript.",
        )

    transcript_path.write_text(transcript_text.strip() + "\n", encoding="utf-8")
    return OpenAITranscriptionResult(episode=episode, transcript_path=transcript_path, error=None)


def split_audio_for_openai(
    *,
    audio_path: Path,
    chunks_dir: Path,
    chunk_seconds: int,
    bitrate: str,
) -> list[Path]:
    if chunk_seconds < 30:
        raise ValueError("chunk_seconds must be at least 30.")

    ffmpeg_path = _ffmpeg_path()
    if chunks_dir.exists():
        shutil.rmtree(chunks_dir)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    output_pattern = chunks_dir / "chunk-%03d.m4a"
    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(audio_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        bitrate,
        "-f",
        "segment",
        "-segment_time",
        str(chunk_seconds),
        "-reset_timestamps",
        "1",
        str(output_pattern),
    ]
    completed_process = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed_process.returncode != 0:
        error = completed_process.stderr.strip() or completed_process.stdout.strip()
        raise RuntimeError(error or f"ffmpeg exited with status {completed_process.returncode}.")

    chunk_paths = sorted(chunks_dir.glob("chunk-*.m4a"))
    if not chunk_paths:
        raise RuntimeError("ffmpeg did not produce audio chunks.")
    return chunk_paths


def _transcribe_chunks(
    *,
    chunk_paths: list[Path],
    api_key: str,
    model: str,
    language: str,
    prompt: str,
    timeout_seconds: int,
    episode_title: str,
) -> str:
    parts: list[str] = []
    for index, chunk_path in enumerate(chunk_paths):
        print(
            f"OpenAI transcription chunk {index + 1}/{len(chunk_paths)}: {episode_title}",
            flush=True,
        )
        text = transcribe_audio_file(
            api_key=api_key,
            audio_path=chunk_path,
            model=model,
            language=language,
            prompt=prompt,
            timeout_seconds=timeout_seconds,
        )
        start_minute = index * 4
        parts.append(f"## chunk {index:03d} approx {start_minute:02d}:00\n\n{text}")
        time.sleep(1)
    return "\n\n".join(parts)


def _ffmpeg_path() -> str:
    configured_path = os.getenv("FFMPEG_BIN", "").strip()
    if configured_path:
        return configured_path

    path_ffmpeg = shutil.which("ffmpeg")
    if path_ffmpeg:
        return path_ffmpeg

    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError(
            "ffmpeg is required for OpenAI transcription chunks. Install ffmpeg, "
            "set FFMPEG_BIN, or install imageio-ffmpeg."
        ) from exc
    return str(imageio_ffmpeg.get_ffmpeg_exe())


def _chunk_directory_name(episode: Episode) -> str:
    return hashlib.sha256(episode.guid.encode("utf-8")).hexdigest()[:12]


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
    title_slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", episode.title, flags=re.UNICODE)
    title_slug = re.sub(r"-+", "-", title_slug).strip("-_").lower()[:80] or "episode"
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
    return f"{year}-{months.get(month_name, '00')}-{int(day):02d}"
