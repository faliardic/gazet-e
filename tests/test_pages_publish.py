from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from bs4 import BeautifulSoup

from chatgpt_haber import pages_publish
from chatgpt_haber.issue import write_json


def article(article_id: str, headline: str, url: str, *, section: str = "gundem") -> dict:
    return {
        "id": article_id,
        "section": section,
        "kicker": section.upper(),
        "headline": headline,
        "importance": 10,
        "dek": f"{headline} özeti",
        "body": [f"{headline} metni."],
        "source_bundle": [
            {
                "name": "Kaynak",
                "url": url,
                "published_at": "2026-07-12T09:00:00+03:00",
                "source_type": "rss",
                "is_primary": False,
            }
        ],
        "verification": {
            "status": "single_source",
            "checked_at": "2026-07-12T09:05:00+03:00",
            "method": ["primary_source"],
            "note": "Test verisi.",
        },
        "layout_hint": {"story_size": "secondary", "column_span": 1, "preferred_position": "mid"},
        "image": {},
    }


def sample_issue() -> dict:
    main = article("main-1", "Ana haber", "https://example.com/main")
    brief = article("brief-1", "Kısa haber", "https://example.com/brief")
    tech = article("tech-1", "Teknoloji haberi", "https://example.com/tech", section="teknoloji")
    return {
        "issue": {
            "issue_date": "2026-07-12",
            "page_count": 3,
            "paper_size": "A3",
            "title": "Gazet+E",
            "generated_at": "2026-07-12T09:10:00+03:00",
        },
        "pages": [
            {"page_no": 1, "template": "front_page", "name": "Manşet", "articles": [deepcopy(main)], "briefs": [deepcopy(brief)]},
            {"page_no": 2, "template": "news_page", "name": "Gündem ve Ekonomi", "articles": [deepcopy(main)], "briefs": []},
            {"page_no": 3, "template": "news_page", "name": "Teknoloji", "articles": [deepcopy(tech)], "briefs": []},
        ],
    }


def install_fake_build(monkeypatch, issue_data: dict) -> None:
    def fake_run_build(**kwargs):
        assert kwargs["mode"] == "full"
        staging_dir = Path(kwargs["out"]).parent
        staging_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = staging_dir / "gazete.pdf"
        json_path = staging_dir / "issue.json"
        pdf_path.write_bytes(b"%PDF-1.4\n")
        write_json(json_path, issue_data)
        return {"pdf": pdf_path, "issue_json": json_path}

    monkeypatch.setattr(pages_publish, "run_build", fake_run_build)


def test_publish_pages_site_creates_portable_site_and_archive(monkeypatch, tmp_path):
    install_fake_build(monkeypatch, sample_issue())
    docs_dir = tmp_path / "docs"
    old_issue_dir = docs_dir / "archive" / "2026-06-06"
    old_issue_dir.mkdir(parents=True)
    (old_issue_dir / "index.html").write_text("<html>old</html>", encoding="utf-8")
    (old_issue_dir / "gazete.pdf").write_bytes(b"%PDF-1.4\n")
    (old_issue_dir / "issue.json").write_text("{}", encoding="utf-8")

    first = pages_publish.publish_pages_site(
        docs_dir=docs_dir,
        staging_dir=tmp_path / "staging",
        issue_date="2026-07-12",
        live=False,
        input_json=Path("examples/issue.sample.json"),
    )
    second = pages_publish.publish_pages_site(
        docs_dir=docs_dir,
        staging_dir=tmp_path / "staging",
        issue_date="2026-07-12",
        live=False,
        input_json=Path("examples/issue.sample.json"),
    )

    assert first["index_html"].exists()
    assert first["pdf"].exists()
    assert first["issue_json"].exists()
    assert first["nojekyll"].exists()
    assert first["archive_index"].exists()
    assert first["archive_issue_html"].exists()
    assert first["archive_issue_pdf"].exists()
    assert first["archive_issue_json"].exists()
    assert second["archive_issue_dir"] == first["archive_issue_dir"]
    assert old_issue_dir.exists()

    html = first["index_html"].read_text(encoding="utf-8")
    archive_html = first["archive_index"].read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")

    toolbar = soup.select_one(".web-toolbar")
    assert toolbar is not None
    assert toolbar.select_one("a[href='gazete.pdf']").get_text(strip=True) == "PDF İNDİR"
    assert toolbar.select_one("a[href='archive/']").get_text(strip=True) == "ARŞİV"
    assert toolbar.select_one("a[href='https://github.com/faliardic/chatgpt-haber']").get_text(strip=True) == "GITHUB"
    assert "SON GÜNCELLEME" in toolbar.get_text(" ", strip=True)
    assert "file:///" not in html
    assert "V:\\" not in html
    assert ":\\\\" not in html
    assert "Teknoloji" in html

    main_link = soup.select_one(".story__headline a[href]")
    brief_link = soup.select_one(".front-rail__item a[href]")
    assert main_link["href"].startswith("#article-detail-")
    assert brief_link["href"].startswith("#article-detail-")
    assert brief_link["href"] != "https://example.com/brief"
    assert len(soup.select(".detail-page__back")) >= 2
    assert all(link["href"] == "#top" for link in soup.select(".detail-page__back"))
    assert soup.select_one(".detail-page__open-source[href='https://example.com/main']")
    assert not soup.select(".detail-page__source")
    assert not soup.select(".story__source")
    assert "Gazet+E" in html
    assert "ChatGPT Gazette" not in html
    assert "CHATGPT HABER" not in html

    assert "Gazet+E Arşiv" in archive_html
    assert "ChatGPT Gazette" not in archive_html
    assert archive_html.count("2026-07-12/") == 2
    assert archive_html.count("2026-06-06/") == 2
    assert "12 Temmuz 2026" in archive_html
    assert "Gazeteyi Aç" in archive_html
    assert "PDF İndir" in archive_html
