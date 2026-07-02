from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    discord_token: str
    discord_guild_ids: tuple[int, ...] = ()
    database_path: str = "data/episodes.sqlite3"

    @property
    def discord_guild_id(self) -> int | None:
        return self.discord_guild_ids[0] if self.discord_guild_ids else None


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

    guild_ids = _parse_optional_ints(os.getenv("DISCORD_GUILD_IDS"))
    if not guild_ids:
        guild_ids = _parse_optional_ints(os.getenv("DISCORD_GUILD_ID"), variable_name="DISCORD_GUILD_ID")
    database_path = os.getenv("DATABASE_PATH", "data/episodes.sqlite3").strip()
    if not database_path:
        raise RuntimeError("DATABASE_PATH cannot be empty.")

    return Settings(discord_token=token, discord_guild_ids=guild_ids, database_path=database_path)


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


def _parse_optional_ints(value: str | None, *, variable_name: str = "DISCORD_GUILD_IDS") -> tuple[int, ...]:
    if value is None or not value.strip():
        return ()

    guild_ids: list[int] = []
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        try:
            guild_id = int(item)
        except ValueError as exc:
            raise RuntimeError(f"{variable_name} must contain numeric Discord guild IDs.") from exc
        if guild_id not in guild_ids:
            guild_ids.append(guild_id)
    return tuple(guild_ids)
