from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    discord_token: str
    discord_guild_id: int | None = None
    database_path: str = "data/episodes.sqlite3"


@dataclass(frozen=True)
class RssSettings:
    podcast_rss_url: str
    database_path: str = "data/episodes.sqlite3"


def load_settings() -> Settings:
    from dotenv import load_dotenv

    load_dotenv()

    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("DISCORD_TOKEN is required. Add it to your .env file.")

    guild_id = _parse_optional_int(os.getenv("DISCORD_GUILD_ID"))
    database_path = os.getenv("DATABASE_PATH", "data/episodes.sqlite3").strip()
    if not database_path:
        raise RuntimeError("DATABASE_PATH cannot be empty.")

    return Settings(discord_token=token, discord_guild_id=guild_id, database_path=database_path)


def load_rss_settings() -> RssSettings:
    from dotenv import load_dotenv

    load_dotenv()

    rss_url = os.getenv("PODCAST_RSS_URL", "").strip()
    if not rss_url:
        raise RuntimeError("PODCAST_RSS_URL is required. Add it to your .env file.")

    database_path = os.getenv("DATABASE_PATH", "data/episodes.sqlite3").strip()
    if not database_path:
        raise RuntimeError("DATABASE_PATH cannot be empty.")

    return RssSettings(podcast_rss_url=rss_url, database_path=database_path)


def _parse_optional_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None

    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError("DISCORD_GUILD_ID must be a numeric Discord guild ID.") from exc
