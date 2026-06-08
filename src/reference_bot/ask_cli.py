from __future__ import annotations

import argparse
import os

from reference_bot.answer_synthesis import DEFAULT_ASK_MODEL
from reference_bot.ask import answer_question
from reference_bot.config import load_rss_settings


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    settings = load_rss_settings()

    parser = argparse.ArgumentParser(description="Ask the Reference Bookstore podcast index locally.")
    parser.add_argument("question")
    parser.add_argument("--database-path", default=settings.database_path)
    parser.add_argument("--model", default=os.getenv("OPENAI_ASK_MODEL", DEFAULT_ASK_MODEL))
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--show-sources", action="store_true")
    args = parser.parse_args()

    api_key = None if args.no_llm else os.getenv("OPENAI_API_KEY", "").strip() or None
    result = answer_question(
        database_path=args.database_path,
        question=args.question,
        api_key=api_key,
        model=args.model,
    )
    print(result.answer)
    if args.show_sources:
        print()
        print(f"used_llm: {result.used_llm}")
        print("concept_matches:")
        for mention in result.concept_mentions:
            print(f"- {mention.name} ({mention.mention_level}) {mention.episode.title}")
        print("book_matches:")
        for mention in result.book_mentions:
            print(f"- {mention.name} ({mention.mention_level}) {mention.episode.title}")
        print("summary_matches:")
        for summary in result.summaries:
            print(f"- {summary.episode.title}")
        print("transcript_matches:")
        for transcript in result.transcript_results[:5]:
            print(f"- {transcript.episode.title} chunk {transcript.chunk_index}")


if __name__ == "__main__":
    main()
