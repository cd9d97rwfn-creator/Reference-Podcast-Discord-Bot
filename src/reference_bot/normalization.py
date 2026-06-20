from __future__ import annotations

import re


STOPWORDS = {
    "有沒有",
    "是否",
    "請問",
    "可以",
    "幫我",
    "有哪些",
    "有",
    "沒有",
    "聊過",
    "討論過",
    "討論",
    "介紹",
    "推薦",
    "提到",
    "提過",
    "講過",
    "講到",
    "相關",
    "有關",
    "關於",
    "觀念",
    "概念",
    "集數",
    "集",
    "書籍",
    "書",
    "主題",
    "哪幾集",
    "哪一集",
    "哪些",
    "什麼",
    "嗎",
    "的",
    "跟",
    "和",
    "或",
    "是",
    "在",
    "講",
    "問",
}


ALIAS_GROUPS = (
    ("職業倦怠", ("工作倦怠", "身心耗竭", "工作耗損", "burnout", "倦怠")),
    ("心理界限", ("心理邊界", "人際界線", "人際界限", "界線", "邊界", "界限")),
    ("同理心", ("共感", "移情", "同情", "empathy")),
    ("焦慮", ("焦慮感", "不安", "擔心")),
    ("壓力", ("微壓力", "壓力源", "stress")),
    ("財富", ("財務", "金錢", "資產", "致富", "wealth")),
    ("槓桿運用", ("槓桿", "財富槓桿")),
    ("風險", ("不確定性", "隨機", "黑天鵝", "機率")),
    ("理性判斷", ("理性", "理性計算", "理性分析", "理性行動")),
    ("內耗", ("精神內耗", "自我消耗", "心理消耗")),
    ("專注力", ("專注", "注意力", "分心")),
    ("慣習", ("習慣", "habitus")),
)


CLUSTER_ALIAS_GROUPS = (
    ("職業倦怠", ("工作倦怠", "身心耗竭", "工作耗損", "burnout", "倦怠")),
    ("心理界限", ("心理邊界", "心理界線", "人際界線", "人際界限", "家庭心理界限", "同理心的邊界")),
    ("同理心", ("共感", "移情", "同情", "empathy")),
    ("焦慮", ("焦慮感", "不安", "擔心")),
    ("壓力", ("微壓力", "壓力源", "stress")),
    ("財富", ("財務", "金錢", "資產", "致富", "wealth")),
    ("槓桿運用", ("槓桿", "財富槓桿")),
    ("風險", ("不確定性", "隨機", "黑天鵝", "機率")),
    ("理性判斷", ("理性", "理性計算", "理性分析", "理性行動")),
    ("內耗", ("精神內耗", "自我消耗", "心理消耗")),
    ("專注力", ("專注", "注意力", "分心")),
    ("慣習", ("習慣", "habitus")),
)


def query_terms(query: str) -> list[str]:
    cleaned_query = query
    for stopword in sorted(STOPWORDS, key=len, reverse=True):
        cleaned_query = cleaned_query.replace(stopword, " ")
    terms = [
        normalize_search_text(term)
        for term in re.split(r"[\s，,。？?：:！!、/「」『』《》（）()【】\[\]]+", cleaned_query)
        if normalize_search_text(term)
    ]
    return _dedupe_terms([term for term in terms if term not in STOPWORDS])


def expanded_query_terms(query: str) -> list[str]:
    expanded: list[str] = []
    for term in query_terms(query):
        expanded.append(term)
        alias_terms = _alias_terms(term)
        expanded.extend(alias_terms)
        if not alias_terms and len(term) >= 4 and looks_like_cjk(term):
            expanded.append(term[-2:])
            expanded.append(term[:2])
    return _dedupe_terms([term for term in expanded if len(term) >= 2])


def normalize_mention_name(value: str) -> str:
    cleaned = normalize_search_text(value)
    cleaned = re.sub(r"^\d+\.\s*", "", cleaned).strip()
    cleaned = _strip_markdown_emphasis(cleaned)
    cleaned = re.sub(r"\s*\((?:aka|又稱|亦稱|英文|英語)[^)]+\)\s*", "", cleaned, flags=re.IGNORECASE)
    canonical = CANONICAL_NAMES.get(_normalize_for_exact_match(cleaned))
    if canonical:
        return canonical
    return cleaned


def cluster_names_for_text(value: str) -> list[str]:
    normalized_value = _normalize_for_exact_match(value)
    matches: list[str] = []
    for canonical, aliases in CLUSTER_ALIAS_GROUPS:
        for term in (canonical, *aliases):
            normalized_term = _normalize_for_exact_match(term)
            if normalized_term and normalized_term in normalized_value:
                matches.append(canonical)
                break
    return _dedupe_terms(matches)


def normalize_search_text(value: str) -> str:
    cleaned = value.strip()
    cleaned = _strip_markdown_emphasis(cleaned)
    cleaned = cleaned.replace("：", ":")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def looks_like_cjk(value: str) -> bool:
    return any("\u4e00" <= character <= "\u9fff" for character in value)


def _alias_terms(term: str) -> list[str]:
    normalized_term = _normalize_for_exact_match(term)
    matches: list[str] = []
    for alias, group in ALIASES.items():
        normalized_alias = _normalize_for_exact_match(alias)
        if normalized_term == normalized_alias or normalized_term in normalized_alias or normalized_alias in normalized_term:
            matches.extend(group)
    return matches


def _normalize_for_exact_match(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _strip_markdown_emphasis(value: str) -> str:
    cleaned = value.strip()
    while len(cleaned) >= 2 and (
        (cleaned.startswith("**") and cleaned.endswith("**"))
        or (cleaned.startswith("__") and cleaned.endswith("__"))
    ):
        cleaned = cleaned[2:-2].strip()
    while len(cleaned) >= 2 and (
        (cleaned.startswith("*") and cleaned.endswith("*"))
        or (cleaned.startswith("_") and cleaned.endswith("_"))
    ):
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _dedupe_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for term in terms:
        if term in seen:
            continue
        seen.add(term)
        deduped.append(term)
    return deduped


ALIASES: dict[str, tuple[str, ...]] = {}
CANONICAL_NAMES: dict[str, str] = {}
for canonical, aliases in ALIAS_GROUPS:
    group = (canonical, *aliases)
    for value in group:
        ALIASES[value] = group
        CANONICAL_NAMES[_normalize_for_exact_match(value)] = canonical
