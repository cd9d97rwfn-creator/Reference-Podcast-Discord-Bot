from __future__ import annotations

from pathlib import Path
import json
import mimetypes
import secrets
import ssl
import time
import urllib.error
import urllib.request


class OpenAIAPIError(RuntimeError):
    pass


def response_text(
    *,
    api_key: str,
    model: str,
    input_messages: list[dict[str, str]],
    temperature: float = 0,
    timeout_seconds: int = 360,
) -> str:
    payload = {
        "model": model,
        "temperature": temperature,
        "input": input_messages,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    parsed = _open_json(request, timeout_seconds)
    _raise_for_error(parsed)

    texts: list[str] = []
    for item in parsed.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                texts.append(content.get("text", ""))
    return "".join(texts).strip()


def chat_completion_text(
    *,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0,
    timeout_seconds: int = 180,
) -> str:
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": messages,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    parsed = _open_json(request, timeout_seconds)
    _raise_for_error(parsed)
    choices = parsed.get("choices", [])
    if not choices:
        return ""
    message = choices[0].get("message", {})
    return str(message.get("content", "")).strip()


def transcribe_audio_file(
    *,
    api_key: str,
    audio_path: Path,
    model: str,
    language: str,
    prompt: str | None = None,
    timeout_seconds: int = 180,
) -> str:
    fields = {
        "model": model,
        "language": language,
    }
    if prompt:
        fields["prompt"] = prompt

    body, boundary = _multipart_body(fields=fields, file_field="file", file_path=audio_path)
    request = urllib.request.Request(
        "https://api.openai.com/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    parsed = _open_json(request, timeout_seconds)
    _raise_for_error(parsed)
    return str(parsed.get("text", "")).strip()


def _open_json(request: urllib.request.Request, timeout_seconds: int) -> dict:
    raw = ""
    for attempt in range(1, 6):
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout_seconds,
                context=ssl.create_default_context(),
            ) as response:
                raw = response.read().decode("utf-8")
            break
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 5:
                try:
                    parsed_error = json.loads(raw)
                except json.JSONDecodeError:
                    raise
                _raise_for_error(parsed_error)
                raise OpenAIAPIError(f"OpenAI API request failed with HTTP {exc.code}.")
            time.sleep(_retry_delay_seconds(exc, attempt))
    else:
        raise OpenAIAPIError("OpenAI API request failed after retries.")

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OpenAIAPIError(f"OpenAI returned invalid JSON: {raw[:200]}") from exc


def _retry_delay_seconds(error: urllib.error.HTTPError, attempt: int) -> float:
    retry_after = error.headers.get("Retry-After")
    if retry_after:
        try:
            return min(float(retry_after), 90)
        except ValueError:
            pass
    return min(5 * (2 ** (attempt - 1)), 60)


def _raise_for_error(parsed: dict) -> None:
    error = parsed.get("error")
    if not error:
        return
    message = error.get("message") if isinstance(error, dict) else str(error)
    raise OpenAIAPIError(message or "OpenAI API request failed.")


def _multipart_body(
    *,
    fields: dict[str, str],
    file_field: str,
    file_path: Path,
) -> tuple[bytes, str]:
    boundary = "----reference-bot-" + secrets.token_hex(12)
    parts: list[bytes] = []
    for key, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
        parts.append(f"{value}\r\n".encode())

    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'.encode()
    )
    parts.append(f"Content-Type: {mime_type}\r\n\r\n".encode())
    parts.append(file_path.read_bytes())
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), boundary
