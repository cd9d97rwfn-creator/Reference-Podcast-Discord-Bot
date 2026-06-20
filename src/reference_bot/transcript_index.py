from __future__ import annotations

from pathlib import Path
import re

from reference_bot.episodes import IndexedTranscript
from reference_bot.storage import list_indexed_transcripts, replace_transcript_chunks


DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 150


def index_transcripts(
    database_path: str,
    limit: int = 10,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> int:
    indexed_count = 0
    for transcript in list_indexed_transcripts(database_path, limit=limit):
        chunks = transcript_chunks(
            transcript,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        replace_transcript_chunks(database_path, transcript, chunks)
        indexed_count += 1

    return indexed_count


def transcript_chunks(
    transcript: IndexedTranscript,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be greater than 0.")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap cannot be negative.")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size.")

    transcript_path = Path(transcript.transcript_local_path).expanduser()
    text = _normalize_text(transcript_path.read_text(encoding="utf-8"))
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end].strip())
        if end == len(text):
            break
        start = end - chunk_overlap

    return [chunk for chunk in chunks if chunk]


def _normalize_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()
