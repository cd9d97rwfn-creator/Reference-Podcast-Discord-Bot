from __future__ import annotations

import argparse
import os

from reference_bot.config import load_rss_settings
from reference_bot.downloader import download_episode_audio
from reference_bot.storage import (
    list_pending_downloads,
    mark_audio_download_failed,
    mark_audio_downloaded,
)


def main() -> None:
    settings = load_rss_settings()

    parser = argparse.ArgumentParser(description="Download pending podcast audio files.")
    parser.add_argument("--database-path", default=settings.database_path)
    parser.add_argument("--audio-dir", default=os.getenv("AUDIO_DIR", "data/audio"))
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()

    episodes = list_pending_downloads(args.database_path, limit=args.limit)
    print(f"Pending downloads selected: {len(episodes)}")

    for episode in episodes:
        print(f"Downloading: {episode.title}")
        result = download_episode_audio(episode, args.audio_dir)

        if result.succeeded and result.local_path is not None:
            mark_audio_downloaded(args.database_path, episode.guid, str(result.local_path))
            print(f"  saved: {result.local_path}")
            continue

        error = result.error or "Unknown download error."
        mark_audio_download_failed(args.database_path, episode.guid, error)
        print(f"  failed: {error}")


if __name__ == "__main__":
    main()
