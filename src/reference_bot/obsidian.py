from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from reference_bot.episodes import Episode, TranscribedEpisode


PODCAST_NAME = "引書店"
DEFAULT_TRANSCRIPTS_DIR = "Inbox/Podcast Import/transcripts"
TRANSCRIPT_NOTE_STATUS_INDEXED = "indexed"


def export_transcript_note(
    transcribed_episode: TranscribedEpisode,
    transcripts_dir: str,
) -> Path:
    transcript_path = Path(transcribed_episode.transcript_local_path).expanduser()
    if not transcript_path.is_file():
        raise FileNotFoundError(f"Transcript file does not exist: {transcript_path}")

    output_directory = Path(transcripts_dir).expanduser()
    output_directory.mkdir(parents=True, exist_ok=True)

    target_path = _unique_markdown_path(
        output_directory / f"{_note_filename_stem(transcribed_episode.episode)}.md"
    )
    transcript_text = transcript_path.read_text(encoding="utf-8").strip()
    target_path.write_text(
        _transcript_note_content(
            episode=transcribed_episode.episode,
            transcript_source_path=str(transcript_path),
            transcript_text=transcript_text,
        ),
        encoding="utf-8",
    )
    return target_path


def _transcript_note_content(
    episode: Episode,
    transcript_source_path: str,
    transcript_text: str,
) -> str:
    note_stem = _note_filename_stem(episode)
    exported_at = datetime.now(timezone.utc).isoformat()
    frontmatter = {
        "type": "podcast_transcript",
        "status": TRANSCRIPT_NOTE_STATUS_INDEXED,
        "podcast": PODCAST_NAME,
        "title": episode.title,
        "guid": episode.guid,
        "published_at": episode.published_at,
        "episode_url": episode.episode_url,
        "audio_url": episode.audio_url,
        "transcript_source": transcript_source_path,
        "transcript_has_timestamps": "false",
        "exported_at": exported_at,
    }
    lines = ["---"]
    for key, value in frontmatter.items():
        lines.append(f"{key}: {_yaml_value(value)}")
    lines.extend(
        [
            "---",
            "",
            f"# {episode.title}",
            "",
            f"Episode note: [[{note_stem}|Episode note]]",
            "",
            "## Transcript",
            "",
            transcript_text,
            "",
        ]
    )
    return "\n".join(lines)


def _yaml_value(value: str | None) -> str:
    if value is None or value == "":
        return "null"
    return json.dumps(value, ensure_ascii=False)


def _unique_markdown_path(target_path: Path) -> Path:
    if not target_path.exists():
        return target_path

    counter = 2
    while True:
        candidate = target_path.with_name(f"{target_path.stem}-{counter}{target_path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _note_filename_stem(episode: Episode) -> str:
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
