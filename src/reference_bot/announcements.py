from __future__ import annotations

import json
import re
from urllib import request

from reference_bot.episodes import EpisodeSummary
from reference_bot.storage import (
    list_pending_episode_announcements,
    mark_episode_announcement_failed,
    mark_episode_announcement_sent,
    mark_episode_announcements_superseded,
)


DEFAULT_SPOTIFY_URL = "https://open.spotify.com/show/7eG1p84LghCfWPqzv2Dwts"
DEFAULT_APPLE_PODCASTS_URL = "https://podcasts.apple.com/podcast/1517351878"
DEFAULT_ANNOUNCEMENT_CHANNEL_ID = 1316432650071969823
DISCORD_API_BASE_URL = "https://discord.com/api/v10"


def publish_pending_episode_announcements(
    *,
    database_path: str,
    discord_token: str,
    channel_id: int,
    spotify_url: str = DEFAULT_SPOTIFY_URL,
    apple_podcasts_url: str = DEFAULT_APPLE_PODCASTS_URL,
    limit: int = 10,
) -> tuple[int, int]:
    if limit < 1:
        raise ValueError("limit must be greater than 0.")

    candidates = list_pending_episode_announcements(database_path, limit=None)
    if not candidates:
        return 0, 0

    latest = candidates[0]
    mark_episode_announcements_superseded(
        database_path,
        [candidate.summary.episode.guid for candidate in candidates[1:]],
    )
    summary = latest.summary
    content = format_episode_announcement(
        summary,
        spotify_url=spotify_url,
        apple_podcasts_url=apple_podcasts_url,
    )
    try:
        _send_discord_message(
            discord_token=discord_token,
            channel_id=channel_id,
            content=content,
        )
    except Exception as exc:
        mark_episode_announcement_failed(database_path, summary.episode.guid, str(exc))
        return 0, 1

    mark_episode_announcement_sent(database_path, summary.episode.guid)
    return 1, 0


def format_episode_announcement(
    summary: EpisodeSummary,
    *,
    spotify_url: str = DEFAULT_SPOTIFY_URL,
    apple_podcasts_url: str = DEFAULT_APPLE_PODCASTS_URL,
) -> str:
    episode_label = _episode_label(summary.episode.title)
    topic = _clean_text(summary.topics[0] if summary.topics else summary.one_sentence_summary)
    core_argument = _announcement_summary(summary)
    return (
        f"喵～～～新一集的{episode_label}上架囉 "
        f"（[Spotify]({spotify_url})、[Apple Podcast]({apple_podcasts_url})）\n"
        f"這集的主題是{topic}，引引最喜歡的地方是{core_argument}，一起來聽聽看喵～"
    )


def _episode_label(title: str) -> str:
    match = re.search(r"\bEP\.?\s*(\d{1,4})\b", title, flags=re.IGNORECASE)
    if match:
        return f"EP.{match.group(1)}"
    return title.strip()


def _title_core_argument(title: str) -> str | None:
    match = re.search(r"『([^』]+)』", title)
    if match:
        return match.group(1).strip()
    return None


def _announcement_summary(summary: EpisodeSummary) -> str:
    candidates = [summary.one_sentence_summary]
    title_argument = _title_core_argument(summary.episode.title)
    if title_argument:
        candidates.append(title_argument)
    candidates.extend(
        point
        for point in summary.key_points
        if not point.startswith(
            ("標題主題：", "來賓/系列資訊：", "RSS 描述節錄：", "逐字稿開頭節錄：")
        )
    )

    parts: list[str] = []
    for candidate in candidates:
        cleaned = _clean_text(candidate)
        if not cleaned or cleaned in parts:
            continue
        parts.append(cleaned)
        combined = "；".join(parts)
        if len(combined) >= 50:
            return _clean_text(combined, limit=100)

    topic = _clean_text(summary.topics[0] if summary.topics else summary.episode.title)
    guest = _guest_label(summary.episode.title)
    metadata_summary = f"本集以「{topic}」為主題"
    if title_argument:
        metadata_summary += f"，從「{_clean_text(title_argument)}」延伸討論"
    if guest:
        metadata_summary += f"，並邀請{guest}分享相關經驗與觀點"
    else:
        metadata_summary += "，分享其中值得思考的觀點、經驗與實際啟發"
    return _clean_text(metadata_summary, limit=100)


def _guest_label(title: str) -> str | None:
    match = re.search(r"feat\.\s*([^＿]+)", title, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _clean_text(value: str, *, limit: int | None = None) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip().strip("。！？!?，,；;：:")
    if limit is not None and len(cleaned) > limit:
        cleaned = cleaned[: limit - 1].rstrip() + "…"
    return cleaned


def _send_discord_message(*, discord_token: str, channel_id: int, content: str) -> None:
    payload = json.dumps(
        {
            "content": content,
            "allowed_mentions": {"parse": []},
        }
    ).encode("utf-8")
    message_request = request.Request(
        f"{DISCORD_API_BASE_URL}/channels/{channel_id}/messages",
        data=payload,
        headers={
            "Authorization": f"Bot {discord_token}",
            "Content-Type": "application/json",
            "User-Agent": "reference-podcast-discord-bot/1.0",
        },
        method="POST",
    )
    with request.urlopen(message_request, timeout=30) as response:
        if response.status not in (200, 201):
            raise RuntimeError(f"Discord returned HTTP {response.status}.")
