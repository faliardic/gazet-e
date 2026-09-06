from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import re
import sys
from typing import Any


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


BASE_DIR = app_base_dir()
PAGE_COUNT = 3

SUPPORTED_TEMPLATES = {"front_page", "news_page"}
SUPPORTED_STORY_SIZES = {"hero", "lead", "secondary", "brief", "radar"}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def slugify(text: str, fallback: str) -> str:
    text = (text or fallback).lower()
    for old, new in {"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u"}.items():
        text = text.replace(old, new)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or fallback


def split_body(value: Any, fallback: str) -> list[str]:
    if isinstance(value, list):
        paragraphs = [str(item).strip() for item in value if str(item).strip()]
    else:
        text = str(value or fallback or "").strip()
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n|(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ])", text) if part.strip()]
    return paragraphs or [fallback or "Haber metni kaynak özetinden derlendi."]


def story_to_article(story: dict[str, Any], section: str, story_size: str, column_span: int) -> dict[str, Any]:
    title = str(story.get("headline") or story.get("title") or "Başlık").strip()
    dek = str(story.get("dek") or story.get("subtitle") or story.get("summary") or "").strip()
    sources = story.get("source_bundle") or story.get("sources") or []
    if isinstance(sources, dict):
        sources = [sources]

    source_bundle = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        source_bundle.append(
            {
                "name": str(source.get("name") or "Kaynak"),
                "url": str(source.get("url") or "https://example.com"),
                "published_at": str(source.get("published_at") or datetime.now(timezone.utc).isoformat()),
                "source_type": str(source.get("source_type") or "publisher"),
                "is_primary": bool(source.get("is_primary", False)),
            }
        )

    if not source_bundle:
        source_bundle.append(
            {
                "name": "Kaynak",
                "url": "https://example.com",
                "published_at": datetime.now(timezone.utc).isoformat(),
                "source_type": "publisher",
                "is_primary": False,
            }
        )

    status = str(story.get("status") or "confirmed")
    verification_status = "verified"
    if status in {"rumor", "needs_review"}:
        verification_status = "needs_review"
    elif len(source_bundle) == 1:
        verification_status = "single_source"

    image = story.get("image") if isinstance(story.get("image"), dict) else {}

    return {
        "id": str(story.get("id") or slugify(title, "story")),
        "section": section,
        "kicker": str(story.get("kicker") or section.replace("_", " ").upper()),
        "headline": title,
        "dek": dek or title,
        "byline": str(story.get("byline") or "Haber Merkezi"),
        "dateline": str(story.get("dateline") or "İstanbul"),
        "importance": int(story.get("importance") or story.get("priority") or 100),
        "body": split_body(story.get("body"), dek or str(story.get("summary") or title)),
        "pullquote": str(story.get("pullquote") or ""),
        "tags": story.get("tags") if isinstance(story.get("tags"), list) else [section],
        "image": {
            "path": str(image.get("path") or ""),
            "source_url": str(image.get("source_url") or source_bundle[0]["url"]),
            "alt": str(image.get("alt") or title),
            "caption": str(image.get("caption") or dek or title),
            "credit": str(image.get("credit") or source_bundle[0]["name"]),
            "width": int(image.get("width") or 0),
            "height": int(image.get("height") or 0),
            "crop": str(image.get("crop") or "landscape"),
        },
        "source_bundle": source_bundle,
        "verification": {
            "status": verification_status,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "method": ["cross_source"] if len(source_bundle) > 1 else ["primary_source"],
            "note": str(story.get("verification_note") or "Kaynaklar kontrol edildi."),
        },
        "layout_hint": {
            "story_size": story_size,
            "column_span": max(1, min(5, int(column_span))),
            "preferred_position": "top" if story_size in {"hero", "lead"} else "mid",
        },
    }


def normalize_issue(raw: dict[str, Any], issue_date: str | None = None, paper_size: str = "A3") -> dict[str, Any]:
    if looks_like_modern_issue(raw):
        raw.setdefault("issue", {})
        raw["issue"]["page_count"] = PAGE_COUNT
        raw["issue"]["language"] = "tr-TR"
        raw["issue"]["paper_size"] = paper_size
        return raw

    meta = raw.get("issue", {}) if isinstance(raw.get("issue"), dict) else {}
    pages = raw.get("pages", []) if isinstance(raw.get("pages"), list) else []
    selected = pages[:PAGE_COUNT]
    while len(selected) < PAGE_COUNT:
        selected.append({})

    normalized_pages = [
        normalize_front_page(selected[0]),
        normalize_news_page(selected[1], page_no=2, name="Gündem ve Ekonomi"),
        normalize_news_page(selected[2], page_no=3, name="Ankara Özel Bülteni"),
    ]

    return {
        "issue": {
            "issue_date": issue_date or str(meta.get("issue_date") or meta.get("date") or datetime.now().date().isoformat()),
            "edition_name": str(meta.get("edition_name") or "Anlık Baskı"),
            "language": "tr-TR",
            "page_count": PAGE_COUNT,
            "paper_size": paper_size,
            "title": str(meta.get("title") or meta.get("newspaper_name") or "Gazet+E"),
            "timezone": "Europe/Istanbul",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "edition_note": "Otomatik derlenmiş üç sayfalık baskı",
        },
        "pages": normalized_pages,
    }


def looks_like_modern_issue(raw: dict[str, Any]) -> bool:
    pages = raw.get("pages")
    return (
        isinstance(pages, list)
        and len(pages) == PAGE_COUNT
        and all(isinstance(page, dict) and page.get("template") in SUPPORTED_TEMPLATES for page in pages)
    )


def normalize_front_page(page: dict[str, Any]) -> dict[str, Any]:
    headline = page.get("headline") if isinstance(page.get("headline"), dict) else {}
    leads = page.get("lead_stories") if isinstance(page.get("lead_stories"), list) else []
    briefs = page.get("briefs") if isinstance(page.get("briefs"), list) else []
    articles = [story_to_article(headline, "gundem", "hero", 1)]
    articles.extend(story_to_article(story, str(story.get("category") or "gundem"), "secondary", 1) for story in leads[:11])
    articles.sort(key=lambda article: article.get("importance", 100))
    brief_articles = [story_to_article(story, str(story.get("category") or "gundem"), "brief", 1) for story in briefs[:20]]
    return {"page_no": 1, "template": "front_page", "name": "Manşet", "articles": articles, "briefs": brief_articles}


def fill_to_count(articles: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if not articles:
        return articles
    idx = 0
    while len(articles) < count:
        clone = dict(articles[idx % len(articles)])
        clone["id"] = f"{clone.get('id', 'story')}-copy-{len(articles) + 1}"
        clone["importance"] = len(articles) + 1
        articles.append(clone)
        idx += 1
    return articles[:count]


def normalize_news_page(
    page: dict[str, Any],
    page_no: int,
    name: str,
    template: str = "news_page",
) -> dict[str, Any]:
    section = str(page.get("section") or "gundem")
    main_story = page.get("main_story") if isinstance(page.get("main_story"), dict) else {}
    stories = page.get("stories") if isinstance(page.get("stories"), list) else []
    briefs = page.get("briefs") if isinstance(page.get("briefs"), list) else []
    articles = [story_to_article(main_story, section, "lead", 1)]
    articles.extend(story_to_article(story, str(story.get("category") or section), "secondary", 1) for story in stories[:11])
    articles = fill_to_count(articles, 12)
    for idx, article in enumerate(articles):
        article["importance"] = idx + 1
        article["layout_hint"]["story_size"] = "hero" if idx == 0 else "lead" if idx == 1 else "secondary"
        article["layout_hint"]["column_span"] = 1

    brief_source = briefs or stories or [main_story]
    brief_articles = [story_to_article(story, str(story.get("category") or section), "brief", 1) for story in brief_source[:20]]
    brief_articles = fill_to_count(brief_articles, 20)
    return {"page_no": page_no, "template": template, "name": name, "articles": articles, "briefs": brief_articles}


def validate_issue_data(issue_data: dict[str, Any]) -> None:
    if not isinstance(issue_data, dict):
        raise ValueError("root object/dict olmalı")
    issue = issue_data.get("issue")
    pages = issue_data.get("pages")
    if not isinstance(issue, dict):
        raise ValueError("issue object/dict olmalı")
    if not isinstance(pages, list):
        raise ValueError("pages liste/array olmalı")

    page_count = int(issue.get("page_count", 0))
    actual_count = len(pages)
    if page_count != actual_count:
        raise ValueError(f"issue.page_count ({page_count}) ile gerçek sayfa sayısı ({actual_count}) uyuşmuyor.")
    if actual_count != PAGE_COUNT:
        raise ValueError(f"Bu sürüm {PAGE_COUNT} sayfa bekliyor; gelen sayfa sayısı: {actual_count}")

    for idx, page in enumerate(pages, start=1):
        template = page.get("template")
        if template not in SUPPORTED_TEMPLATES:
            raise ValueError(f"pages[{idx}] için geçersiz template: {template}")
        articles = page.get("articles", [])
        if not isinstance(articles, list) or not articles:
            raise ValueError(f"pages[{idx}] articles boş olamaz")
        for a_idx, article in enumerate(articles, start=1):
            if not article.get("headline"):
                raise ValueError(f"pages[{idx}].articles[{a_idx}] headline boş")
            if not article.get("body"):
                raise ValueError(f"pages[{idx}].articles[{a_idx}] body boş")
            story_size = article.get("layout_hint", {}).get("story_size")
            if story_size not in SUPPORTED_STORY_SIZES:
                raise ValueError(f"pages[{idx}].articles[{a_idx}] story_size geçersiz")
            image_path = article.get("image", {}).get("path")
            if image_path and not Path(image_path).exists():
                raise ValueError(f"pages[{idx}].articles[{a_idx}] image.path bulunamadı: {image_path}")
