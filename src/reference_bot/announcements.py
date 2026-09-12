from __future__ import annotations

import json
import re
from urllib import request

from reference_bot.episodes import EpisodeSummary
from reference_bot.storage import (
    list_pending_episode_announcements,
    mark_episode_announcement_failed,
    mark_episode_announcement_sent,
)


DEFAULT_SPOTIFY_URL = "https://open.spotify.com/show/7eG1p84LghCfWPqzv2Dwts"
DEFAULT_APPLE_PODCASTS_URL = "https://podcasts.apple.com/podcast/1517351878"
DEFAULT_ANNOUNCEMENT_CHANNEL_ID = 1511396029369548804
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
    sent = 0
    failed = 0
    for candidate in list_pending_episode_announcements(database_path, limit=limit):
        summary = candidate.summary
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
            failed += 1
            continue

        mark_episode_announcement_sent(database_path, summary.episode.guid)
        sent += 1
    return sent, failed


def format_episode_announcement(
    summary: EpisodeSummary,
    *,
    spotify_url: str = DEFAULT_SPOTIFY_URL,
    apple_podcasts_url: str = DEFAULT_APPLE_PODCASTS_URL,
) -> str:
    episode_label = _episode_label(summary.episode.title)
    topic = _clean_text(summary.topics[0] if summary.topics else summary.one_sentence_summary)
    core_argument = _clean_text(
        _title_core_argument(summary.episode.title)
        or (summary.key_points[0] if summary.key_points else summary.one_sentence_summary),
        limit=50,
    )
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
