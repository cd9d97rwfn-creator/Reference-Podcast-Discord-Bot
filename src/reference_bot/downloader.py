from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import shutil
from urllib.parse import unquote, urlparse
from urllib.request import Request
from urllib.request import urlopen

from reference_bot.episodes import Episode


@dataclass(frozen=True)
class DownloadResult:
    episode: Episode
    local_path: Path | None
    error: str | None

    @property
    def succeeded(self) -> bool:
        return self.error is None and self.local_path is not None


def download_episode_audio(episode: Episode, audio_dir: str) -> DownloadResult:
    if not episode.audio_url:
        return DownloadResult(episode=episode, local_path=None, error="Episode has no audio URL.")

    target_directory = Path(audio_dir)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / audio_filename(episode)

    if target_path.exists():
        return DownloadResult(episode=episode, local_path=target_path, error=None)

    temporary_path = target_path.with_suffix(f"{target_path.suffix}.part")

    try:
        request = Request(
            episode.audio_url,
            headers={
                "User-Agent": "ReferencePodcastBot/0.1 (+https://www.referencebookstore.com)",
            },
        )
        with urlopen(request, timeout=60) as response:
            with temporary_path.open("wb") as output_file:
                shutil.copyfileobj(response, output_file)
        temporary_path.replace(target_path)
    except Exception as exc:
        if temporary_path.exists():
            temporary_path.unlink()
        return DownloadResult(episode=episode, local_path=None, error=str(exc))

    return DownloadResult(episode=episode, local_path=target_path, error=None)


def audio_filename(episode: Episode) -> str:
    date_prefix = _date_prefix(episode.published_at)
    guid_hash = hashlib.sha256(episode.guid.encode("utf-8")).hexdigest()[:12]
    title_slug = _slugify(episode.title)[:80] or "episode"
    extension = _audio_extension(episode.audio_url) if episode.audio_url else ".mp3"
    return f"{date_prefix}-{guid_hash}-{title_slug}{extension}"


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


def _audio_extension(audio_url: str | None) -> str:
    if not audio_url:
        return ".mp3"

    path = unquote(urlparse(audio_url).path)
    extension = Path(path).suffix.lower()
    if extension in {".mp3", ".m4a", ".mp4", ".wav", ".aac", ".ogg"}:
        return extension
    return ".mp3"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", value, flags=re.UNICODE)
    slug = re.sub(r"-+", "-", slug).strip("-_")
    return slug.lower()
