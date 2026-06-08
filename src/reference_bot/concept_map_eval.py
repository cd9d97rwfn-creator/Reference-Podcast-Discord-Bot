from __future__ import annotations

from dataclasses import dataclass

from reference_bot.concept_map import concept_map
from reference_bot.storage import search_book_mentions, search_episode_summaries


@dataclass(frozen=True)
class ConceptMapEvalCase:
    query: str
    expected_episode_keywords: tuple[str, ...]
    expected_concept_keywords: tuple[str, ...]


@dataclass(frozen=True)
class ConceptMapEvalResult:
    case: ConceptMapEvalCase
    status: str
    matched_episode_keywords: list[str]
    missing_episode_keywords: list[str]
    matched_concept_keywords: list[str]
    missing_concept_keywords: list[str]
    top_episodes: list[str]
    top_concepts: list[str]
    top_books: list[str]


DEFAULT_EVAL_CASES = (
    ConceptMapEvalCase(
        query="財富或資產累積相關的集數",
        expected_episode_keywords=("財富階梯", "納瓦爾寶典"),
        expected_concept_keywords=("財富", "財富階梯", "財富累積"),
    ),
    ConceptMapEvalCase(
        query="職業倦怠或身心耗竭",
        expected_episode_keywords=("終結職業倦怠",),
        expected_concept_keywords=("職業倦怠",),
    ),
    ConceptMapEvalCase(
        query="心理界限或邊界感",
        expected_episode_keywords=("心理界限",),
        expected_concept_keywords=("心理界限", "界限"),
    ),
    ConceptMapEvalCase(
        query="風險 黑天鵝 不確定性",
        expected_episode_keywords=("隨機騙局", "第一次工作就該懂"),
        expected_concept_keywords=("風險", "黑天鵝", "不確定性"),
    ),
    ConceptMapEvalCase(
        query="同理心與理性判斷",
        expected_episode_keywords=("失控的同理心",),
        expected_concept_keywords=("同理心", "理性"),
    ),
    ConceptMapEvalCase(
        query="專注力或分心",
        expected_episode_keywords=("專注力協定",),
        expected_concept_keywords=("專注力", "分心"),
    ),
    ConceptMapEvalCase(
        query="內耗或自我消耗",
        expected_episode_keywords=("心理界限", "正確犯錯"),
        expected_concept_keywords=("內耗",),
    ),
    ConceptMapEvalCase(
        query="一人公司 自媒體 創業",
        expected_episode_keywords=("一人公司",),
        expected_concept_keywords=("一人公司", "創業"),
    ),
    ConceptMapEvalCase(
        query="不反應 慈悲 好奇",
        expected_episode_keywords=("不反應的練習",),
        expected_concept_keywords=("不反應", "慈悲"),
    ),
    ConceptMapEvalCase(
        query="大腦韌性 思考力 情緒力",
        expected_episode_keywords=("給大腦的13堂全方位照護課",),
        expected_concept_keywords=("大腦", "韌性"),
    ),
    ConceptMapEvalCase(
        query="向上流動 階級 代價",
        expected_episode_keywords=("向上流動的代價",),
        expected_concept_keywords=("向上流動", "代價"),
    ),
    ConceptMapEvalCase(
        query="複雜之美 幾何 形狀",
        expected_episode_keywords=("複雜之美",),
        expected_concept_keywords=("幾何", "形狀"),
    ),
    ConceptMapEvalCase(
        query="戴明博士 品質管理 PDCA",
        expected_episode_keywords=("戴明博士四日談",),
        expected_concept_keywords=("PDCA", "品質"),
    ),
    ConceptMapEvalCase(
        query="新聞 媒體 焦慮",
        expected_episode_keywords=("新聞的騷動",),
        expected_concept_keywords=("新聞", "焦慮"),
    ),
    ConceptMapEvalCase(
        query="失智媽媽 照顧 長照",
        expected_episode_keywords=("失智媽媽",),
        expected_concept_keywords=("照顧", "長照"),
    ),
)


def evaluate_concept_map(
    database_path: str,
    cases: tuple[ConceptMapEvalCase, ...] = DEFAULT_EVAL_CASES,
    limit: int = 8,
) -> list[ConceptMapEvalResult]:
    return [_evaluate_case(database_path, case, limit=limit) for case in cases]


def format_eval_results(results: list[ConceptMapEvalResult]) -> str:
    passed = sum(1 for result in results if result.status == "PASS")
    lines = [f"Concept map eval: {passed}/{len(results)} PASS", ""]
    for index, result in enumerate(results, start=1):
        lines.append(f"{index}. [{result.status}] {result.case.query}")
        if result.missing_episode_keywords:
            lines.append("   missing episodes: " + ", ".join(result.missing_episode_keywords))
        if result.missing_concept_keywords:
            lines.append("   missing concepts: " + ", ".join(result.missing_concept_keywords))
        if result.top_episodes:
            lines.append("   top episodes: " + " | ".join(result.top_episodes[:5]))
        if result.top_concepts:
            lines.append("   top concepts: " + " | ".join(result.top_concepts[:6]))
        if result.top_books:
            lines.append("   top books: " + " | ".join(result.top_books[:4]))
        lines.append("")
    return "\n".join(lines).rstrip()


def _evaluate_case(database_path: str, case: ConceptMapEvalCase, *, limit: int) -> ConceptMapEvalResult:
    map_result = concept_map(database_path, case.query, limit=limit)
    summaries = search_episode_summaries(database_path, case.query, limit=limit)
    books = search_book_mentions(database_path, case.query, limit=limit)

    top_episodes = _dedupe(
        [
            *[cluster.episode.title for cluster in map_result.clusters],
            *[relationship.episode.title for relationship in map_result.relationships],
            *[summary.episode.title for summary in summaries],
            *[book.episode.title for book in books],
        ]
    )
    top_concepts = _dedupe(
        [
            *[
                _concept_label(cluster.cluster_name, cluster.mention_name)
                for cluster in map_result.clusters
            ],
            *[
                f"{relationship.source_name} {relationship.relation_type} {relationship.target_name}"
                for relationship in map_result.relationships
            ],
        ]
    )
    top_books = _dedupe([book.name for book in books])

    episode_haystack = "\n".join(top_episodes)
    concept_haystack = "\n".join([*top_concepts, *top_books])
    matched_episode_keywords, missing_episode_keywords = _match_keywords(
        episode_haystack,
        case.expected_episode_keywords,
    )
    matched_concept_keywords, missing_concept_keywords = _match_keywords(
        concept_haystack,
        case.expected_concept_keywords,
    )
    status = "PASS" if not missing_episode_keywords and not missing_concept_keywords else "REVIEW"

    return ConceptMapEvalResult(
        case=case,
        status=status,
        matched_episode_keywords=matched_episode_keywords,
        missing_episode_keywords=missing_episode_keywords,
        matched_concept_keywords=matched_concept_keywords,
        missing_concept_keywords=missing_concept_keywords,
        top_episodes=top_episodes,
        top_concepts=top_concepts,
        top_books=top_books,
    )


def _match_keywords(haystack: str, keywords: tuple[str, ...]) -> tuple[list[str], list[str]]:
    matched = [keyword for keyword in keywords if keyword in haystack]
    missing = [keyword for keyword in keywords if keyword not in haystack]
    return matched, missing


def _concept_label(cluster_name: str, mention_name: str) -> str:
    if cluster_name == mention_name:
        return cluster_name
    return f"{cluster_name} -> {mention_name}"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
