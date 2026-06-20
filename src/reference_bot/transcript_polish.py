from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import time

from reference_bot.openai_api import chat_completion_text


DEFAULT_POLISH_MODEL = "gpt-4.1-mini"
DEFAULT_POLISH_CHARS = 700
DEFAULT_POLISH_RETRIES = 3
DEFAULT_POLISH_TIMEOUT_SECONDS = 180


@dataclass(frozen=True)
class PolishResult:
    source_path: Path
    cleaned_path: Path
    chunks_polished: int


def polish_transcript_file(
    *,
    source_path: Path,
    api_key: str,
    model: str = DEFAULT_POLISH_MODEL,
    chunk_chars: int = DEFAULT_POLISH_CHARS,
    retries: int = DEFAULT_POLISH_RETRIES,
    overwrite: bool = False,
) -> PolishResult:
    if chunk_chars < 500:
        raise ValueError("chunk_chars must be at least 500.")

    cleaned_path = cleaned_transcript_path(source_path)
    if cleaned_path.exists() and cleaned_path.stat().st_size and not overwrite:
        return PolishResult(source_path=source_path, cleaned_path=cleaned_path, chunks_polished=0)

    text = source_path.read_text(encoding="utf-8").strip()
    chunks = _chunks(text, chunk_chars)
    parts_dir = source_path.with_name(f"{source_path.stem}-cleaned-parts-{chunk_chars}")
    parts_dir.mkdir(parents=True, exist_ok=True)
    cleaned_parts: list[str] = []
    chunks_polished = 0
    for index, chunk in enumerate(chunks, start=1):
        part_path = parts_dir / f"part-{index:03d}.txt"
        if part_path.exists() and part_path.stat().st_size and not overwrite:
            cleaned_parts.append(part_path.read_text(encoding="utf-8").strip())
            continue

        print(f"  polishing chunk {index}/{len(chunks)}", flush=True)
        cleaned_text = _polish_chunk(
            api_key=api_key,
            model=model,
            chunk=chunk,
            retries=retries,
        )
        part_path.write_text(cleaned_text.strip() + "\n", encoding="utf-8")
        print(f"  polished chunk {index}/{len(chunks)}", flush=True)
        cleaned_parts.append(cleaned_text)
        chunks_polished += 1

    cleaned_path.write_text("\n\n".join(part.strip() for part in cleaned_parts).strip() + "\n", encoding="utf-8")
    return PolishResult(source_path=source_path, cleaned_path=cleaned_path, chunks_polished=chunks_polished)


def _polish_chunk(*, api_key: str, model: str, chunk: str, retries: int) -> str:
    attempts = max(1, retries)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return chat_completion_text(
                api_key=api_key,
                model=model,
                temperature=0,
                messages=[
                    {"role": "system", "content": _polish_system_prompt()},
                    {"role": "user", "content": f"請校對以下逐字稿片段，只輸出校對後文本：\n\n{chunk}"},
                ],
                timeout_seconds=DEFAULT_POLISH_TIMEOUT_SECONDS,
            )
        except Exception as error:
            last_error = error
            if attempt == attempts:
                break
            time.sleep(min(2**attempt, 10))
    if last_error is None:
        raise RuntimeError("Failed to polish transcript chunk.")
    raise last_error


def cleaned_transcript_path(source_path: Path) -> Path:
    if source_path.stem.endswith("-cleaned"):
        return source_path
    return source_path.with_name(f"{source_path.stem}-cleaned{source_path.suffix}")


def _chunks(text: str, chunk_chars: int) -> list[str]:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n{2,}", text) if paragraph.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for paragraph in paragraphs:
        paragraph_length = len(paragraph)
        if current and current_length + paragraph_length + 2 > chunk_chars:
            chunks.append("\n\n".join(current))
            current = []
            current_length = 0
        if paragraph_length > chunk_chars:
            chunks.extend(_split_long_text(paragraph, chunk_chars))
            continue
        current.append(paragraph)
        current_length += paragraph_length + 2
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _split_long_text(text: str, chunk_chars: int) -> list[str]:
    return [text[index : index + chunk_chars] for index in range(0, len(text), chunk_chars)]


def _polish_system_prompt() -> str:
    return """你是繁體中文 podcast 逐字稿校對器。只做校對，不做摘要。
規則：
- 補上標點符號與自然段落，讓文字適合閱讀與搜尋。
- 修正常見語音辨識錯字、同音錯字、人名/書名錯字。
- 使用繁體中文。
- 保留口語語氣，不要刪除主持人的口頭禪或贅字，除非只是重複辨識錯誤。
- 不新增原文沒有的資訊，不把內容摘要化。
- 不確定的專有名詞可以保守保留。"""
