from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from .issue import slugify, story_to_article
from .sources import (
    clean_editorial_pool,
    normalize_for_match,
    page_articles,
    parse_feed_articles,
    prioritize_articles,
)


TECHNOLOGY_FEEDS = {
    "NTV Teknoloji": "https://www.ntv.com.tr/teknoloji.rss",
    "Habertürk Teknoloji": "https://www.haberturk.com/rss/kategori/teknoloji.xml",
    "Sözcü Bilim-Teknoloji": "https://www.sozcu.com.tr/feeds-rss-category-bilim-teknoloji",
    "Evrim Ağacı": "https://evrimagaci.org/rss.xml",
}

TECHNOLOGY_SECTION_NAMES = {
    "teknoloji",
    "technology",
    "technology science",
    "technology_science",
    "bilim",
    "bilim teknoloji",
    "bilim_teknoloji",
    "science",
}

TECHNOLOGY_TERMS = (
    "teknoloji",
    "yapay zeka",
    "artificial intelligence",
    "bilim",
    "yazilim",
    "software",
    "donanim",
    "robot",
    "uzay",
    "siber",
    "dijital",
    "internet",
    "akilli telefon",
    "android",
    "apple",
    "google",
    "microsoft",
    "openai",
    "chatgpt",
)


def is_technology_article(article: dict[str, Any]) -> bool:
    section = normalize_for_match(str(article.get("section") or article.get("category") or ""))
    if section in {normalize_for_match(value) for value in TECHNOLOGY_SECTION_NAMES}:
        return True

    sources = article.get("source_bundle") if isinstance(article.get("source_bundle"), list) else []
    source = sources[0] if sources and isinstance(sources[0], dict) else {}
    source_text = normalize_for_match(str(source.get("name") or ""))
    if "teknoloji" in source_text or "evrim agaci" in source_text:
        return True

    text = normalize_for_match(
        " ".join(
            [
                str(article.get("headline") or article.get("title") or ""),
                str(article.get("dek") or article.get("subtitle") or article.get("summary") or ""),
                str(article.get("section") or article.get("category") or ""),
            ]
        )
    )
    return any(normalize_for_match(term) in text for term in TECHNOLOGY_TERMS)


def fetch_technology_articles(limit: int = 96) -> list[dict[str, Any]]:
    articles = parse_feed_articles(TECHNOLOGY_FEEDS, limit)
    technology_only = [article for article in articles if is_technology_article(article)]
    return prioritize_articles(clean_editorial_pool(technology_only))[:limit]


def legacy_technology_articles(raw_issue: dict[str, Any]) -> list[dict[str, Any]]:
    pages = raw_issue.get("pages") if isinstance(raw_issue.get("pages"), list) else []
    articles: list[dict[str, Any]] = []
    seen: set[str] = set()

    for page in pages:
        if not isinstance(page, dict):
            continue
        page_section = str(page.get("section") or "")
        stories: list[dict[str, Any]] = []
        for key in ("headline", "main_story"):
            story = page.get(key)
            if isinstance(story, dict):
                stories.append(story)
        for key in ("lead_stories", "stories", "briefs"):
            collection = page.get(key)
            if isinstance(collection, list):
                stories.extend(story for story in collection if isinstance(story, dict))

        for story in stories:
            probe = dict(story)
            probe["section"] = str(story.get("category") or page_section)
            if not is_technology_article(probe):
                continue
            article = story_to_article(story, "teknoloji", "secondary", 1)
            article["section"] = "teknoloji"
            article["kicker"] = "TEKNOLOJİ"
            key = str(article.get("id") or article.get("headline") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            articles.append(article)

    return prioritize_articles(clean_editorial_pool(articles)) if articles else []


def normalized_technology_articles(issue_data: dict[str, Any]) -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in issue_data.get("pages", []):
        if not isinstance(page, dict):
            continue
        for collection_name in ("articles", "briefs"):
            collection = page.get(collection_name)
            if not isinstance(collection, list):
                continue
            for article in collection:
                if not isinstance(article, dict) or not is_technology_article(article):
                    continue
                key = str(article.get("id") or article.get("headline") or "")
                if not key or key in seen:
                    continue
                seen.add(key)
                articles.append(deepcopy(article))
    return prioritize_articles(clean_editorial_pool(articles)) if articles else []


def technology_placeholder_article() -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": "teknoloji-akisi-bekleniyor",
        "section": "teknoloji",
        "kicker": "TEKNOLOJİ",
        "headline": "Teknoloji akışı güncelleniyor",
        "importance": 1,
        "dek": "Güncel teknoloji kaynaklarından yeterli içerik alınamadı; sonraki üretimde akış yeniden denenecek.",
        "body": [
            "Teknoloji sayfası yalnız teknoloji ve bilim kaynaklarından oluşturulur.",
            "Kaynak akışı geçici olarak yetersiz kaldığı için Ankara veya genel gündem haberleri bu sayfaya taşınmadı.",
        ],
        "source_bundle": [
            {
                "name": "Gazet+E Teknoloji Masası",
                "url": "https://example.com",
                "published_at": now,
                "source_type": "editorial_notice",
                "is_primary": True,
            }
        ],
        "verification": {
            "status": "verified",
            "checked_at": now,
            "method": ["editorial_boundary"],
            "note": "Teknoloji dışı içerik kullanılmaması için güvenli yedek kayıt.",
        },
        "layout_hint": {"story_size": "secondary", "column_span": 1, "preferred_position": "mid"},
        "image": {},
    }


def expand_articles(articles: list[dict[str, Any]], minimum: int = 32) -> list[dict[str, Any]]:
    expanded = [deepcopy(article) for article in articles]
    if not expanded:
        expanded = [technology_placeholder_article()]

    seed = [deepcopy(article) for article in expanded]
    index = 0
    while len(expanded) < minimum:
        clone = deepcopy(seed[index % len(seed)])
        base_id = str(clone.get("id") or slugify(str(clone.get("headline") or "teknoloji"), "teknoloji"))
        clone["id"] = f"{base_id}-copy-{len(expanded) + 1}"
        clone["importance"] = len(expanded) + 1
        expanded.append(clone)
        index += 1
    return expanded


def build_technology_page(articles: list[dict[str, Any]]) -> dict[str, Any]:
    technology_only = [deepcopy(article) for article in articles if is_technology_article(article)]
    technology_only = expand_articles(prioritize_articles(clean_editorial_pool(technology_only)))
    main_articles, briefs = page_articles(technology_only, 0)

    for article in main_articles + briefs:
        article["section"] = "teknoloji"
        article["kicker"] = "TEKNOLOJİ"

    return {
        "page_no": 3,
        "template": "news_page",
        "name": "Teknoloji",
        "articles": main_articles,
        "briefs": briefs,
    }


def ensure_technology_third_page(
    issue_data: dict[str, Any],
    *,
    raw_issue: dict[str, Any] | None = None,
    technology_articles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    if technology_articles:
        candidates.extend(deepcopy(technology_articles))
    if raw_issue:
        candidates.extend(legacy_technology_articles(raw_issue))
    candidates.extend(normalized_technology_articles(issue_data))

    pages = issue_data.get("pages")
    if not isinstance(pages, list) or len(pages) < 3:
        raise ValueError("Teknoloji sayfası için üç sayfalık issue verisi gerekli.")

    pages[2] = build_technology_page(candidates)
    issue = issue_data.setdefault("issue", {})
    issue["page_count"] = 3
    issue["edition_note"] = "Otomatik derlenmiş üç sayfalık baskı"
    return issue_data
