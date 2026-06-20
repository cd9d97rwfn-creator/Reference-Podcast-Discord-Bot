from __future__ import annotations

import argparse
import os

from reference_bot.config import load_rss_settings
from reference_bot.openai_summary import (
    DEFAULT_OPENAI_SUMMARY_MODEL,
    generate_openai_episode_summaries,
)
from reference_bot.summary import DEFAULT_EPISODE_SUMMARIES_DIR


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    settings = load_rss_settings()

    parser = argparse.ArgumentParser(description="Generate OpenAI episode summary notes.")
    parser.add_argument("--database-path", default=settings.database_path)
    parser.add_argument("--summaries-dir", default=os.getenv("OBSIDIAN_EPISODES_DIR", DEFAULT_EPISODE_SUMMARIES_DIR))
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--model", default=os.getenv("OPENAI_SUMMARY_MODEL", DEFAULT_OPENAI_SUMMARY_MODEL))
    parser.add_argument("--replace-existing", action="store_true")
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required. Add it to your .env file.")

    generated_count = generate_openai_episode_summaries(
        database_path=args.database_path,
        summaries_dir=args.summaries_dir,
        limit=args.limit,
        api_key=api_key,
        model=args.model,
        replace_existing=args.replace_existing,
    )
    print(f"OpenAI summaries generated: {generated_count}")


if __name__ == "__main__":
    main()
