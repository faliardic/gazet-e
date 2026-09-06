from bs4 import BeautifulSoup
from copy import deepcopy
from pathlib import Path

from chatgpt_haber.issue import normalize_issue, read_json
from chatgpt_haber.render import image_src, render_html
from chatgpt_haber.builder import issue_from_rss
from chatgpt_haber.sources import (
    clickbait_score,
    dedupe_similar_articles,
    earthquake_event_gate,
    is_clickbait_article,
    page_articles,
    prioritize_articles,
    sanitize_issue_articles,
    score_article,
)


def test_single_html_document(tmp_path):
    html_path = tmp_path / "issue.html"
    render_html(normalize_issue(read_json(Path("examples/issue.sample.json"))), html_path)
    html = html_path.read_text(encoding="utf-8")
    assert html.lower().count("<!doctype html>") == 1
    assert html.lower().count("<html") == 1
    assert html.lower().count("<body") == 1


def test_three_pages_present(tmp_path):
    html_path = tmp_path / "issue.html"
    render_html(normalize_issue(read_json(Path("examples/issue.sample.json"))), html_path)
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "lxml")
    pages = soup.select(".page[data-page-no]")
    assert len(pages) == 3


def test_local_image_paths_render_as_file_uri(tmp_path):
    image_path = tmp_path / "photo.jpg"
    image_path.write_bytes(b"fake image")

    assert image_src(str(image_path)).startswith("file:///")


def test_article_headlines_link_to_local_detail_pages(tmp_path):
    html_path = tmp_path / "issue.html"
    render_html(normalize_issue(read_json(Path("examples/issue.sample.json"))), html_path)
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "lxml")

    headline_links = soup.select(".story__headline a[href]")
    assert headline_links
    assert all(link["href"].startswith("articles/") for link in headline_links)
    assert (tmp_path / headline_links[0]["href"]).exists()


def test_portable_pdf_mode_links_to_embedded_detail_pages(tmp_path):
    html_path = tmp_path / "issue.html"
    render_html(normalize_issue(read_json(Path("examples/issue.sample.json"))), html_path, portable_pdf_links=True)
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "lxml")

    headline_link = soup.select_one(".story__headline a[href]")
    assert headline_link
    assert headline_link["href"].startswith("#article-detail-")
    assert soup.select_one(headline_link["href"])


def test_portable_html_embeds_assets_without_file_links(tmp_path):
    html_path = tmp_path / "issue.html"
    render_html(
        normalize_issue(read_json(Path("examples/issue.sample.json"))),
        html_path,
        portable_pdf_links=True,
        portable_assets=True,
    )
    html = html_path.read_text(encoding="utf-8")

    assert "file:///" not in html
    assert "<style>" in html
    assert "data:image/png;base64," not in html
    assert "chatgpt-gazette-mark.png" not in html
    assert "chatgpt-haber-logo-cropped.png" not in html


def test_portable_html_embeds_article_images(tmp_path):
    image_path = tmp_path / "photo.jpg"
    image_path.write_bytes(b"fake image bytes")
    issue = normalize_issue(read_json(Path("examples/issue.sample.json")))
    issue["pages"][0]["articles"][0]["image"] = {
        "path": str(image_path),
        "alt": "Test",
        "caption": "Test",
        "credit": "Test",
        "crop": "landscape",
    }
    html_path = tmp_path / "issue.html"

    render_html(issue, html_path, portable_pdf_links=True, portable_assets=True)
    html = html_path.read_text(encoding="utf-8")

    assert "data:image/jpeg;base64," in html


def test_render_html_final_sanitizer_removes_generic_earthquake(tmp_path):
    issue = normalize_issue(read_json(Path("examples/issue.sample.json")))
    blocked = issue["pages"][0]["articles"][0].copy()
    blocked["id"] = "blocked-earthquake"
    blocked["headline"] = "Son dakika deprem mi oldu? Az önce deprem nerede oldu? İstanbul, Ankara, İzmir ve il il AFAD son depremler 01 Haziran 2026"
    blocked["dek"] = "Son depremler... Artçı deprem mi oldu? Son deprem büyüklüğü ne kadar?"
    issue["pages"][0]["articles"].insert(0, blocked)
    html_path = tmp_path / "issue.html"

    render_html(issue, html_path, portable_pdf_links=True)
    html = html_path.read_text(encoding="utf-8")

    assert "Son dakika deprem mi oldu" not in html


def test_detail_page_keeps_top_source_link_without_footer(tmp_path):
    html_path = tmp_path / "issue.html"
    render_html(normalize_issue(read_json(Path("examples/issue.sample.json"))), html_path)
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "lxml")

    detail_path = tmp_path / soup.select_one(".story__headline a[href]")["href"]
    detail_soup = BeautifulSoup(detail_path.read_text(encoding="utf-8"), "lxml")

    source_link = detail_soup.select_one(".detail-nav a[href^='https://']")
    assert source_link
    assert source_link.get_text(strip=True) == "KAYNAĞI AÇ"
    assert source_link["href"].startswith("https://")
    assert detail_soup.select_one(".detail-brand").get_text(strip=True) == "GAZET+E"
    assert not detail_soup.select(".detail-brand img")
    assert "ChatGPT Gazette" not in detail_soup.get_text(" ", strip=True)
    assert not detail_soup.select(".detail-source")


def test_front_page_rail_lists_twenty_text_only_items(tmp_path):
    issue = normalize_issue(read_json(Path("examples/issue.sample.json")))
    front = issue["pages"][0]
    source_article = deepcopy(front["articles"][0])
    front["briefs"] = []
    for index in range(20):
        article = deepcopy(source_article)
        article["id"] = f"rail-{index}"
        article["headline"] = f"Kısa haber {index + 1}"
        article["image"] = {"path": "should-not-render.jpg"}
        article["layout_hint"] = {"story_size": "brief", "column_span": 1, "preferred_position": "rail"}
        front["briefs"].append(article)

    html_path = tmp_path / "issue.html"
    render_html(issue, html_path)
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "lxml")

    rail_items = soup.select(".page[data-page-no='1'] .front-rail__item")
    assert len(rail_items) == 20
    assert [item.select_one(".front-rail__number").get_text(strip=True) for item in rail_items[:3]] == ["01", "02", "03"]
    assert not soup.select(".page[data-page-no='1'] .front-rail img")


def test_rail_numbering_continues_across_pages(tmp_path):
    issue = normalize_issue(read_json(Path("examples/issue.sample.json")))
    source_article = deepcopy(issue["pages"][0]["articles"][0])
    for page in issue["pages"]:
        page["briefs"] = []
        for index in range(20):
            article = deepcopy(source_article)
            article["id"] = f"page-{page['page_no']}-rail-{index}"
            article["headline"] = f"Kısa haber {index + 1}"
            article["layout_hint"] = {"story_size": "brief", "column_span": 1, "preferred_position": "rail"}
            page["briefs"].append(article)

    html_path = tmp_path / "issue.html"
    render_html(issue, html_path)
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "lxml")

    assert soup.select_one(".page[data-page-no='1'] .front-rail__number").get_text(strip=True) == "01"
    assert soup.select_one(".page[data-page-no='2'] .front-rail__number").get_text(strip=True) == "21"
    assert soup.select_one(".page[data-page-no='3'] .front-rail__number").get_text(strip=True) == "41"


def test_live_issue_has_three_pages_with_technology_third_page(monkeypatch):
    articles = []
    for index in range(96):
        articles.append(
            {
                "id": f"story-{index}",
                "section": "gundem",
                "headline": f"Haber ozelkonu{index + 1}",
                "importance": index + 1,
                "dek": f"Kısa özet ozelkonu{index + 1}",
                "body": [f"Kısa haber metni ozelkonu{index + 1}."],
                "source_bundle": [
                    {
                        "name": "Kaynak",
                        "url": "https://example.com",
                        "published_at": "2026-05-26",
                        "source_type": "rss",
                        "is_primary": False,
                    }
                ],
                "verification": {
                    "status": "single_source",
                    "checked_at": "2026-05-26",
                    "method": ["primary_source"],
                    "note": "Test",
                },
                "layout_hint": {"story_size": "secondary", "column_span": 1, "preferred_position": "mid"},
                "image": {},
            }
        )
    technology_articles = []
    for index in range(40):
        article = deepcopy(articles[index])
        article["id"] = f"tech-story-{index}"
        article["section"] = "teknoloji"
        article["headline"] = f"Teknoloji haberi {index + 1}"
        article["kicker"] = "TEKNOLOJİ"
        technology_articles.append(article)

    monkeypatch.setattr("chatgpt_haber.builder.fetch_rss_articles", lambda: articles)
    monkeypatch.setattr("chatgpt_haber.builder.fetch_technology_articles", lambda: technology_articles)

    issue = issue_from_rss("2026-05-26", "A3")

    assert issue["issue"]["page_count"] == 3
    assert issue["pages"][2]["name"] == "Teknoloji"
    for page in issue["pages"]:
        assert len(page["articles"]) == 12
        assert len(page["briefs"]) == 20
        assert all(article["layout_hint"]["story_size"] == "brief" for article in page["briefs"])
    assert all(article["section"] == "teknoloji" for article in issue["pages"][2]["articles"])
    assert all(article["section"] == "teknoloji" for article in issue["pages"][2]["briefs"])


def test_similar_articles_from_different_sources_are_deduped():
    articles = [
        {
            "section": "dunya",
            "headline": "Cumhurbaşkanı Erdoğan Pezeşkiyan ile görüştü",
            "dek": "Cumhurbaşkanı Erdoğan, İran Cumhurbaşkanı Pezeşkiyan ile telefonda görüştü.",
            "image_url": "https://example.com/erdogan-pezeskiyan.jpg",
        },
        {
            "section": "dunya",
            "headline": "Cumhurbaşkanı Erdoğan, İranlı mevkidaşı Pezeşkiyan'la görüştü",
            "dek": "Cumhurbaşkanı Erdoğan, İranlı mevkidaşı Mesud Pezeşkiyan ile telefonda görüştü.",
            "image_url": "https://cdn.example.com/erdogan-pezeskiyan.jpg",
        },
        {
            "section": "ekonomi",
            "headline": "Petrol fiyatları haftaya yükselişle başladı",
            "dek": "Küresel piyasalarda petrol fiyatları yeni haftaya yükselişle girdi.",
            "image_url": "",
        },
    ]

    deduped = dedupe_similar_articles(articles)

    assert [article["headline"] for article in deduped] == [
        "Cumhurbaşkanı Erdoğan Pezeşkiyan ile görüştü",
        "Petrol fiyatları haftaya yükselişle başladı",
    ]


def test_articles_are_prioritized_by_editorial_importance():
    articles = [
        {
            "section": "spor",
            "headline": "Takım yeni sezon hazırlıklarına başladı",
            "dek": "Kulüp antrenman programını açıkladı.",
            "image_url": "",
            "importance": 1,
            "source_bundle": [{"name": "Sözcü Spor", "published_at": "2026-05-26T07:00:00+00:00"}],
        },
        {
            "section": "ekonomi",
            "headline": "TCMB faiz kararı açıklandı",
            "dek": "Merkez Bankası faiz kararını ve enflasyon görünümünü duyurdu.",
            "image_url": "",
            "importance": 2,
            "source_bundle": [{"name": "NTV Ekonomi", "published_at": "2026-05-26T09:00:00+00:00"}],
        },
        {
            "section": "gundem",
            "headline": "Deprem sonrası ağır hasar açıklaması",
            "dek": "AFAD bölgede deprem sonrası ağır hasar ve kurtarma çalışmalarının sürdüğünü açıkladı.",
            "image_url": "",
            "importance": 3,
            "source_bundle": [{"name": "Habertürk Gündem", "published_at": "2026-05-26T08:00:00+00:00"}],
        },
    ]

    prioritized = prioritize_articles(articles)

    assert prioritized[0]["headline"] == "Deprem sonrası ağır hasar açıklaması"
    assert prioritized[1]["headline"] == "TCMB faiz kararı açıklandı"
    assert prioritized[0]["importance_score"] > prioritized[-1]["importance_score"]


def test_clickbait_articles_are_filtered_from_priority_pool():
    articles = [
        {
            "section": "gundem",
            "headline": "Bunu duyanlar inanamadı!",
            "dek": "Sosyal medyada gündem olan iddia olay yarattı.",
            "image_url": "",
            "importance": 1,
            "source_bundle": [{"name": "Habertürk Gündem", "published_at": "2026-05-26T09:00:00+00:00"}],
        },
        {
            "section": "ekonomi",
            "headline": "TCMB faiz kararını açıkladı",
            "dek": "Merkez Bankası politika faizine ilişkin kararını duyurdu.",
            "image_url": "",
            "importance": 2,
            "source_bundle": [{"name": "NTV Ekonomi", "published_at": "2026-05-26T09:00:00+00:00"}],
        },
    ]

    prioritized = prioritize_articles(articles)

    assert [article["headline"] for article in prioritized] == ["TCMB faiz kararını açıkladı"]


def test_editorial_headlines_are_not_marked_as_clickbait():
    article = {
        "headline": "Deprem sonrası son dakika açıklaması",
        "dek": "AFAD bölgede çalışmaların sürdüğünü duyurdu.",
    }

    assert not is_clickbait_article(article)
    assert clickbait_score(article) == 0


def test_question_style_news_is_blocked():
    articles = [
        {
            "headline": "Son dakika deprem mi oldu? Az önce deprem nerede oldu?",
            "dek": "İstanbul, Ankara, İzmir ve il il AFAD son depremler 01 Haziran 2026",
        },
        {
            "headline": "Yeni destek başvurusu nereden alınır",
            "dek": "Başvuru nasıl yapılacak ve şartları neler?",
        },
        {
            "headline": "Konut satışlarında mayıs verileri açıklandı",
            "dek": "TÜİK konut satışlarına ilişkin mayıs ayı verilerini yayımladı.",
        },
    ]

    assert is_clickbait_article(articles[0])
    assert is_clickbait_article(articles[1])
    assert not is_clickbait_article(articles[2])


def test_routine_earthquake_updates_are_blocked_but_major_damage_news_remains():
    routine_update = {
        "headline": "AFAD son depremler listesini yayımladı",
        "dek": "Anlık deprem verileri ve il il son depremler güncellendi.",
    }
    major_news = {
        "headline": "Depremde ağır hasar oluştu",
        "dek": "Bölgede enkaz kaldırma ve kurtarma çalışmaları sürüyor.",
    }

    assert is_clickbait_article(routine_update)
    assert not is_clickbait_article(major_news)


def test_question_earthquake_update_is_removed_at_page_and_issue_level():
    blocked = {
        "id": "blocked",
        "section": "gundem",
        "headline": "Son dakika deprem mi oldu? Az önce deprem nerede oldu?",
        "dek": "İstanbul, Ankara, İzmir ve il il AFAD son depremler 01 Haziran 2026",
        "body": ["Son depremler listesi"],
        "source_bundle": [{"name": "Kaynak", "url": "https://example.com/blocked"}],
        "verification": {"status": "single_source"},
        "layout_hint": {"story_size": "secondary"},
        "image": {},
    }
    allowed = {
        "id": "allowed",
        "section": "gundem",
        "headline": "Bölgede deprem sonrası ağır hasar tespit edildi",
        "dek": "Kurtarma ekipleri enkaz alanında çalışmalarını sürdürüyor.",
        "body": ["Hasar tespit çalışmaları sürüyor."],
        "source_bundle": [{"name": "Kaynak", "url": "https://example.com/allowed"}],
        "verification": {"status": "single_source"},
        "layout_hint": {"story_size": "secondary"},
        "image": {},
    }

    main_articles, _ = page_articles([blocked, allowed], 0)
    issue = {"pages": [{"articles": [blocked, allowed], "briefs": [blocked]}]}
    sanitize_issue_articles(issue)

    assert all(article["id"] != "blocked" for article in main_articles)
    assert [article["id"] for article in issue["pages"][0]["articles"]] == ["allowed"]
    assert issue["pages"][0]["briefs"] == []


def test_earthquake_event_gate_classifies_seo_generic_clickbait():
    article = {
        "headline": "Son dakika deprem mi oldu? Az önce deprem nerede oldu? İstanbul, Ankara, İzmir ve il il AFAD son depremler 01 Haziran 2026",
        "dek": "Son depremler listesi güncellendi.",
    }

    result = earthquake_event_gate(article)

    assert result["earthquake_classification"] == "seo_generic_earthquake"
    assert result["accepted"] is False
    assert result["reject_reason"] == "seo_generic_earthquake_clickbait"


def test_earthquake_event_gate_classifies_minor_ticker_and_caps_importance():
    article = {
        "headline": "AFAD duyurdu: Ege Denizi'nde 3.2 büyüklüğünde deprem",
        "dek": "Hasar bildirilmedi.",
        "source_bundle": [{"name": "AFAD"}],
    }

    result = earthquake_event_gate(article)
    prioritized = prioritize_articles([article, {"headline": "TCMB faiz kararını açıkladı", "dek": "Karar duyuruldu."}])

    assert result["earthquake_classification"] == "minor_earthquake_ticker"
    assert result["accepted"] is True
    assert prioritized[-1]["earthquake_classification"] == "minor_earthquake_ticker"
    assert prioritized[-1]["importance_cap_applied"] is True


def test_earthquake_event_gate_accepts_5_1_without_auto_top():
    article = {
        "headline": "AFAD duyurdu: Balıkesir'de 5.1 büyüklüğünde deprem",
        "dek": "Hasar bildirilmedi.",
        "source_bundle": [{"name": "AFAD"}],
    }

    result = earthquake_event_gate(article)

    assert result["earthquake_classification"] == "serious_earthquake_event"
    assert result["accepted"] is True
    assert score_article(article) < 120


def test_earthquake_event_gate_raises_damage_event():
    article = {
        "headline": "AFAD: Marmara'da 4.8 büyüklüğünde deprem, bazı binalarda hasar bildirildi",
        "dek": "Bölgede hasar tespit çalışması başlatıldı.",
        "source_bundle": [{"name": "AFAD"}],
    }

    result = earthquake_event_gate(article)

    assert result["earthquake_classification"] == "serious_earthquake_event"
    assert result["accepted"] is True
    assert result["impact_detected"] is True


def test_earthquake_event_gate_allows_major_tsunami_alert():
    article = {
        "headline": "7.0 büyüklüğünde deprem sonrası tsunami uyarısı",
        "dek": "USGS verilerine göre bölgede resmi alarm verildi.",
        "source_bundle": [{"name": "USGS"}],
    }

    result = earthquake_event_gate(article)

    assert result["earthquake_classification"] == "serious_earthquake_event"
    assert result["accepted"] is True


def test_anka_articles_are_added_to_live_pool(monkeypatch):
    monkeypatch.setattr("chatgpt_haber.sources.parse_feed_articles", lambda feeds, limit: [])
    monkeypatch.setattr(
        "chatgpt_haber.sources.extract_anka_articles",
        lambda limit: [
            {
                "id": "anka-1",
                "section": "gundem",
                "headline": "ANKA gündem haberini geçti",
                "dek": "ANKA Haber Ajansı kaynaklı güncel haber.",
                "image_url": "",
                "importance": 1,
                "source_bundle": [{"name": "ANKA Haber Ajansı", "published_at": "2026-06-01T09:00:00+00:00"}],
            }
        ],
    )

    from chatgpt_haber.sources import fetch_rss_articles

    articles = fetch_rss_articles()

    assert articles[0]["source_bundle"][0]["name"] == "ANKA Haber Ajansı"


def test_all_pages_use_shared_grid_layout(tmp_path):
    html_path = tmp_path / "issue.html"
    render_html(normalize_issue(read_json(Path("examples/issue.sample.json"))), html_path)
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "lxml")

    assert len(soup.select(".page .front-layout")) == 3


def test_fast_pdf_html_embeds_main_and_brief_article_details(tmp_path):
    issue = normalize_issue(read_json(Path("examples/issue.sample.json")))
    seed = deepcopy(issue["pages"][0]["articles"][0])
    for page in issue["pages"]:
        article = deepcopy(seed)
        article["id"] = f"main-{page['page_no']}"
        article["headline"] = f"Ana haber {page['page_no']}"
        article["source_bundle"][0]["url"] = f"https://example.com/main-{page['page_no']}"
        brief = deepcopy(seed)
        brief["id"] = f"brief-{page['page_no']}"
        brief["headline"] = f"Kısa haber {page['page_no']}"
        brief["source_bundle"][0]["url"] = f"https://example.com/brief-{page['page_no']}"
        brief["layout_hint"] = {"story_size": "brief", "column_span": 1, "preferred_position": "rail"}
        brief["image"] = {}
        page["articles"] = [article]
        page["briefs"] = [brief]

    html_path = tmp_path / "issue.html"
    render_html(issue, html_path, portable_pdf_links=True)
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "lxml")

    main_link = soup.select_one(".story__headline a[href]")
    brief_link = soup.select_one(".front-rail__item a[href]")
    detail_pages = soup.select(".detail-page")

    assert main_link["href"].startswith("#article-detail-")
    assert brief_link["href"].startswith("#article-detail-")
    assert brief_link["href"] != "https://example.com/brief-1"
    assert len(detail_pages) == 6
    assert any("Kısa haber" in page.get_text(" ", strip=True) for page in detail_pages)
    assert len(detail_pages[0].select(".detail-page__back")) == 2
    assert all(button["href"] == "#top" for button in detail_pages[0].select(".detail-page__back"))


def test_masthead_uses_gazet_e_brand_without_old_decorations(tmp_path):
    html_path = tmp_path / "issue.html"
    render_html(normalize_issue(read_json(Path("examples/issue.sample.json"))), html_path)
    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")

    assert "Gazet+E" in html
    assert "ChatGPT Gazette" not in html
    assert soup.select_one(".masthead__gazette").get_text(strip=True) == "GAZET+E"
    assert soup.select_one(".masthead__mark") is None
    assert "chatgpt-gazette-mark.png" not in html
    assert "chatgpt-haber-logo-cropped.png" not in html
    assert "GÜVENİLİR" not in html
    assert "TARAFSIZ" not in html
    assert "masthead__slogan" not in html
    assert "masthead__chevrons" not in html
    assert "masthead__globe" not in html


def test_story_images_link_to_same_target_as_headlines(tmp_path):
    issue = normalize_issue(read_json(Path("examples/issue.sample.json")))
    issue["pages"][0]["articles"][0]["image"] = {
        "path": "https://example.com/photo.jpg",
        "alt": "Test görsel",
        "caption": "Test görsel başlığı",
        "credit": "Test",
        "crop": "landscape",
    }
    html_path = tmp_path / "issue.html"

    render_html(issue, html_path, portable_pdf_links=True)
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "lxml")

    story = soup.select_one(".story")
    headline_link = story.select_one(".story__headline a[href]")
    image_link = story.select_one(".figure__link[href]")
    image = image_link.select_one("img")
    assert image_link["href"] == headline_link["href"]
    assert image_link["href"].startswith("#article-detail-")
    assert image["alt"] == "Test görsel"


def test_source_footers_are_not_rendered_on_cards_or_detail_pages(tmp_path):
    html_path = tmp_path / "issue.html"
    render_html(normalize_issue(read_json(Path("examples/issue.sample.json"))), html_path, portable_pdf_links=True)
    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")

    assert not soup.select(".story__source")
    assert not soup.select(".detail-source")
    assert not soup.select(".detail-page__source")
    assert "single_source" not in " ".join(story.get_text(" ", strip=True) for story in soup.select(".story"))
    assert soup.select_one(".detail-page__open-source")


def test_duplicate_main_and_brief_share_one_detail_page(tmp_path):
    issue = normalize_issue(read_json(Path("examples/issue.sample.json")))
    seed = deepcopy(issue["pages"][0]["articles"][0])
    seed["source_bundle"][0]["url"] = "https://example.com/shared-detail"
    main = deepcopy(seed)
    main["id"] = "main-shared"
    brief = deepcopy(seed)
    brief["id"] = "brief-shared"
    brief["headline"] = "Paylaşılan kısa haber"
    brief["layout_hint"] = {"story_size": "brief", "column_span": 1, "preferred_position": "rail"}
    issue["pages"] = [issue["pages"][0]]
    issue["pages"][0]["articles"] = [main]
    issue["pages"][0]["briefs"] = [brief]
    html_path = tmp_path / "issue.html"

    render_html(issue, html_path, portable_pdf_links=True)
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "lxml")

    headline_link = soup.select_one(".story__headline a[href]")["href"]
    brief_link = soup.select_one(".front-rail__item a[href]")["href"]
    assert brief_link == headline_link
    assert len(soup.select(".detail-page")) == 1
