from __future__ import annotations

from collections.abc import Iterable

from reference_bot.episodes import Episode


def parse_feed(feed_url: str) -> list[Episode]:
    import feedparser

    parsed_feed = feedparser.parse(feed_url)
    if parsed_feed.bozo:
        raise RuntimeError(f"Failed to parse RSS feed: {parsed_feed.bozo_exception}")

    episodes: list[Episode] = []
    for entry in parsed_feed.entries:
        episodes.append(
            Episode(
                guid=_entry_guid(entry),
                title=str(entry.get("title", "")).strip(),
                published_at=_published_at(entry),
                episode_url=_episode_url(entry),
                audio_url=_audio_url(entry.get("links", [])),
                description=_description(entry),
            )
        )

    return episodes


def _entry_guid(entry: object) -> str:
    for key in ("id", "guid", "link", "title"):
        value = entry.get(key)
        if value:
            return str(value).strip()

    raise RuntimeError("RSS entry is missing a stable id, link, and title.")


def _published_at(entry: object) -> str | None:
    value = entry.get("published") or entry.get("updated")
    if not value:
        return None
    return str(value).strip()


def _episode_url(entry: object) -> str | None:
    value = entry.get("link")
    if not value:
        return None
    return str(value).strip()


def _audio_url(links: Iterable[object]) -> str | None:
    for link in links:
        href = link.get("href")
        link_type = str(link.get("type", ""))
        rel = str(link.get("rel", ""))
        if href and (link_type.startswith("audio/") or rel == "enclosure"):
            return str(href).strip()

    return None


def _description(entry: object) -> str | None:
    value = entry.get("summary") or entry.get("description")
    if not value:
        return None
    return str(value).strip()
