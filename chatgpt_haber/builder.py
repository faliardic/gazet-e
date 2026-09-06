from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .sources import clean_editorial_pool, enrich_issue_images, fetch_rss_articles, page_articles, prioritize_articles
from .technology_page import build_technology_page, fetch_technology_articles, is_technology_article


def issue_from_rss(issue_date: str, paper_size: str, image_dir: Path | None = None) -> dict[str, Any] | None:
    general_articles = prioritize_articles(clean_editorial_pool(fetch_rss_articles()))
    if len(general_articles) < 3:
        return None

    front_articles, front_briefs = page_articles(general_articles, 0)
    inside_articles, inside_briefs = page_articles(general_articles, 32)
    technology_articles = fetch_technology_articles()
    if not technology_articles:
        technology_articles = [article for article in general_articles if is_technology_article(article)]

    issue_data = {
        "issue": {
            "issue_date": issue_date,
            "edition_name": "Anlık Baskı",
            "language": "tr-TR",
            "page_count": 3,
            "paper_size": paper_size,
            "title": "Gazet+E",
            "timezone": "Europe/Istanbul",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "edition_note": "Otomatik derlenmiş üç sayfalık baskı",
        },
        "pages": [
            {
                "page_no": 1,
                "template": "front_page",
                "name": "Manşet",
                "articles": front_articles,
                "briefs": front_briefs,
            },
            {
                "page_no": 2,
                "template": "news_page",
                "name": "Gündem ve Ekonomi",
                "articles": inside_articles,
                "briefs": inside_briefs,
            },
            build_technology_page(technology_articles),
        ],
    }
    if image_dir is not None:
        enrich_issue_images(issue_data, image_dir)
    return issue_data
