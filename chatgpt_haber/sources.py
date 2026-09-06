from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from html import unescape
import json
import mimetypes
import re
import unicodedata
from urllib.parse import urljoin, urlparse
from typing import Any

from .issue import slugify
from services.news_quality_filters import apply_hard_reject_filters, is_generic_earthquake_clickbait, sanitize_items_or_fail
from services.user_profile import load_profile


DEFAULT_FEEDS = {
    "NTV Türkiye": "https://www.ntv.com.tr/turkiye.rss",
    "NTV Dünya": "https://www.ntv.com.tr/dunya.rss",
    "NTV Ekonomi": "https://www.ntv.com.tr/ekonomi.rss",
    "NTV Teknoloji": "https://www.ntv.com.tr/teknoloji.rss",
    "NTV Spor": "https://www.ntv.com.tr/sporskor.rss",
    "Habertürk Gündem": "https://www.haberturk.com/rss/kategori/gundem.xml",
    "Habertürk Dünya": "https://www.haberturk.com/rss/kategori/dunya.xml",
    "Habertürk Ekonomi": "https://www.haberturk.com/rss/ekonomi.xml",
    "Habertürk Spor": "https://www.haberturk.com/rss/spor.xml",
    "Habertürk Teknoloji": "https://www.haberturk.com/rss/kategori/teknoloji.xml",
    "Sözcü Gündem": "https://www.sozcu.com.tr/feeds-rss-category-gundem",
    "Sözcü Dünya": "https://www.sozcu.com.tr/feeds-rss-category-dunya",
    "Sözcü Ekonomi": "https://www.sozcu.com.tr/feeds-rss-category-ekonomi",
    "Sözcü Spor": "https://www.sozcu.com.tr/feeds-rss-category-spor",
    "Sözcü Teknoloji": "https://www.sozcu.com.tr/feeds-rss-category-bilim-teknoloji",
    "Evrim Ağacı": "https://evrimagaci.org/rss.xml",
}
ANKA_HOMEPAGE_URL = "https://ankahaber.net/"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
REQUEST_HEADERS = {
    "User-Agent": "ChatGPT-Haber/0.2 (+https://example.com; print issue builder)",
}
DETAIL_SELECTORS = (
    "article p",
    "main article p",
    "[itemprop='articleBody'] p",
    "[itemprop='articleBody']",
    "[data-testid='article-body'] p",
    ".article-content p",
    ".article-body p",
    ".news-content p",
    ".story-content p",
    ".post-content p",
    ".content-detail p",
    ".news-detail p",
    ".haber-detay p",
    ".entry-content p",
    ".content p",
)
STOP_WORDS = {
    "aciklandi",
    "ardindan",
    "baskan",
    "baskani",
    "belli",
    "bir",
    "bugun",
    "cumhurbaskani",
    "dakika",
    "de",
    "da",
    "dedi",
    "den",
    "icin",
    "ile",
    "haber",
    "kisa",
    "ozet",
    "son",
    "sonra",
    "ve",
    "ya",
    "yeni",
}
SOURCE_SCORES = {
    "NTV Türkiye": 9,
    "NTV Dünya": 8,
    "NTV Ekonomi": 8,
    "NTV Teknoloji": 6,
    "NTV Spor": 6,
    "Habertürk Gündem": 8,
    "Habertürk Dünya": 7,
    "Habertürk Ekonomi": 7,
    "Habertürk Spor": 6,
    "Habertürk Teknoloji": 6,
    "Sözcü Gündem": 7,
    "Sözcü Dünya": 6,
    "Sözcü Ekonomi": 7,
    "Sözcü Spor": 5,
    "Sözcü Teknoloji": 5,
    "Evrim Ağacı": 4,
    "ANKA Haber Ajansı": 8,
    "Haberci06 Ankara": 7,
    "Başkent Gazete Ankara": 7,
    "Redaktör Haber Yerel": 6,
    "Ankara Haber Gündemi": 7,
}
SECTION_SCORES = {
    "gundem": 12,
    "ekonomi": 11,
    "dunya": 10,
    "ankara": 9,
    "teknoloji": 7,
    "spor": 6,
}
KEYWORD_SCORES = {
    "son dakika": 34,
    "afet": 22,
    "yangin": 18,
    "kaza": 15,
    "cumhurbaskani": 24,
    "bakan": 18,
    "meclis": 16,
    "yargitay": 18,
    "mahkeme": 16,
    "dava": 12,
    "tcmb": 22,
    "faiz": 20,
    "enflasyon": 20,
    "kredi": 14,
    "dolar": 14,
    "petrol": 13,
    "savas": 22,
    "iran": 12,
    "abd": 10,
    "rusya": 10,
    "israil": 14,
    "ankara": 10,
    "ulasim": 9,
    "toki": 9,
    "yapay zeka": 12,
    "google": 8,
    "avrupa": 8,
}
PROFILE_KEYWORDS = {
    "ankara": ("ankara", "cankaya", "mamak", "sincan", "ulasim", "metro"),
    "ekonomi": ("faiz", "kredi", "enflasyon", "tcmb", "dolar", "altin", "borsa"),
    "insaat": ("insaat", "santiye", "yapi", "ruhsat", "toki", "konut", "beton"),
    "deprem_yapi_guvenligi": ("deprem", "hasar", "guclendirme", "afet", "yapi guvenligi"),
    "yazilim_ai": ("yapay zeka", "ai", "python", "github", "chatgpt", "otomasyon"),
    "otomobil_ulasim": ("otomobil", "arac", "elektrikli", "trafik", "ulasim", "metro"),
    "saglik_enerji": ("saglik", "uyku", "beslenme", "enerji", "yorgunluk"),
    "kultur_kitap": ("kitap", "edebiyat", "sinema", "kultur", "sanat"),
}
CLICKBAIT_BLOCK_PATTERNS = (
    r"\bbunu\s+(?:duyan|goren|okuyan|izleyen)\b",
    r"\bkimse\s+(?:bunu\s+)?beklemiyordu\b",
    r"\bgorenler\s+(?:sasti|inanamadi|donup\s+bir\s+daha\s+bakti)\b",
    r"\bduyanlar\s+(?:sasti|inanamadi)\b",
    r"\bagizlari\s+acik\s+birakti\b",
    r"\bsoke\s+(?:eden|etti)\b",
    r"\bsir\s+gibi\s+saklanan\b",
    r"\byok\s+artik\b",
    r"\bpes\s+dedirten\b",
    r"\binanilmaz\s+(?:olay|goruntu|iddia|gelisme)\b",
    r"\bolay\s+(?:yaratti|oldu)\b",
    r"\b(?:bomba|flas)\s+(?:iddia|gelisme)\b",
    r"\bsakin\s+(?:bunu\s+)?(?:yapmayin|kacirmayin)\b",
    r"\bbunu\s+yapan\s+yandi\b",
)
CLICKBAIT_SOFT_PATTERNS = (
    r"\biste\s+(?:o|bu)\b",
    r"\bmerak\s+konusu\s+oldu\b",
    r"\bgundem\s+oldu\b",
    r"\bsosyal\s+medyayi\s+salladi\b",
    r"\bakillara\s+su\s+soruyu\s+getirdi\b",
    r"\bnedenini\s+duyan\b",
    r"\bilk\s+kez\s+(?:konustu|acikladi)\b",
)
QUESTION_NEWS_PATTERNS = (
    r"\b(?:mi|mu)\s+(?:oldu|edildi|geldi|basladi|bitecek|alindi|verildi|yapilacak|aciklandi)\b",
    r"\b(?:ne|neler|nerede|nereden|nereye|neden|nasil|hangi|kim|kime|kimin|kac|ne\s+kadar)\b",
    r"\b(?:nereden|nasil)\s+(?:alinir|alınır|yapilir|yapılır|basvurulur|başvurulur|ogrenilir|öğrenilir)\b",
    r"\b(?:son|anlik|yakindaki)\s+.+\s+(?:nerede|neler|ne\s+kadar|mi\s+oldu)\b",
)
ROUTINE_EARTHQUAKE_PATTERNS = (
    r"\bson\s+(?:depremler|deprem)\b",
    r"\banlik\s+deprem\b",
    r"\byakindaki\s+depremler\b",
    r"\baz\s+once\s+deprem\b",
    r"\bdeprem\s+(?:mi\s+oldu|nerede\s+oldu|buyuklugu\s+ne\s+kadar)\b",
    r"\b(?:afad|kandilli).{0,45}(?:son\s+depremler|deprem\s+listesi|deprem\s+verileri)\b",
    r"\bil\s+il\s+(?:afad|kandilli)?\s*son\s+depremler\b",
)
MAJOR_EARTHQUAKE_SIGNALS = (
    "can kaybi",
    "olu",
    "yarali",
    "enkaz",
    "yikim",
    "yikildi",
    "hasar",
    "agir hasar",
    "tahliye",
    "gocuk",
    "tsunami",
    "afet bolgesi",
    "acil durum",
    "kurtarma",
    "artci",
    "okul tatil",
    "ulasim",
    "altyapi",
    "resmi alarm",
)
NO_EARTHQUAKE_IMPACT_SIGNALS = (
    "hasar bildirilmedi",
    "can kaybi yok",
    "yarali yok",
    "olumsuzluk yok",
    "herhangi bir olumsuzluk",
)
OFFICIAL_EARTHQUAKE_SOURCES = (
    "afad",
    "kandilli",
    "koeri",
    "usgs",
    "emsc",
    "valilik",
    "bakanlik",
    "bakanligi",
)
TURKEY_EARTHQUAKE_LOCATIONS = (
    "turkiye",
    "marmara",
    "ege",
    "akdeniz",
    "balikesir",
    "istanbul",
    "izmir",
    "ankara",
    "malatya",
    "kahramanmaras",
    "hatay",
    "adiyaman",
    "elazig",
    "bingol",
    "van",
    "erzincan",
    "erzurum",
    "mugla",
    "canakkale",
)


def entry_image_url(entry: Any) -> str:
    for attr in ("media_content", "media_thumbnail"):
        values = getattr(entry, attr, None)
        if isinstance(values, list):
            for item in values:
                if isinstance(item, dict) and item.get("url"):
                    return str(item["url"])

    for link in getattr(entry, "links", []) or []:
        if not isinstance(link, dict):
            continue
        href = str(link.get("href") or "")
        mime_type = str(link.get("type") or "")
        rel = str(link.get("rel") or "")
        if href and (mime_type.startswith("image/") or rel in {"enclosure", "image"}):
            return href

    image = getattr(entry, "image", None)
    if isinstance(image, dict) and image.get("href"):
        return str(image["href"])
    if isinstance(image, dict) and image.get("url"):
        return str(image["url"])
    return ""


def page_image_url(page_url: str) -> str:
    if not page_url:
        return ""
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return ""

    try:
        response = requests.get(page_url, headers=REQUEST_HEADERS, timeout=8)
        response.raise_for_status()
    except Exception:
        return ""

    soup = BeautifulSoup(response.text, "html.parser")
    selectors = [
        ("meta", {"property": "og:image"}, "content"),
        ("meta", {"name": "twitter:image"}, "content"),
        ("meta", {"property": "twitter:image"}, "content"),
        ("link", {"rel": "image_src"}, "href"),
    ]
    for tag_name, attrs, value_attr in selectors:
        tag = soup.find(tag_name, attrs=attrs)
        value = tag.get(value_attr) if tag else ""
        if value:
            return urljoin(page_url, str(value))
    return ""


def clean_html_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip(" \t\r\n")


def useful_detail_paragraph(text: str, headline: str) -> bool:
    normalized = normalize_for_match(text)
    if len(text) < 45:
        return False
    normalized_headline = normalize_for_match(headline)
    if normalized == normalized_headline:
        return False
    if normalized_headline and len(normalized) < len(normalized_headline) + 24 and normalized in normalized_headline:
        return False
    blocked_fragments = (
        "abone ol",
        "bildirimlere izin ver",
        "cerez",
        "cookie",
        "facebook",
        "instagram",
        "ilgili haber",
        "paylas",
        "reklam",
        "son dakika haberleri",
        "sosyal medya",
        "whatsapp",
    )
    return not any(fragment in normalized for fragment in blocked_fragments)


def split_detail_paragraphs(value: str) -> list[str]:
    text = clean_html_text(value)
    if not text:
        return []
    raw_parts = re.split(r"(?:\r?\n){2,}|(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ0-9])", text)
    parts = [part.strip() for part in raw_parts if part.strip()]
    if len(parts) <= 1 and len(text) > 900:
        parts = [part.strip() for part in re.split(r"\s{2,}", text) if part.strip()]
    return parts or [text]


def meaningful_detail(paragraphs: list[str]) -> bool:
    total_chars = sum(len(paragraph) for paragraph in paragraphs)
    return len(paragraphs) >= 3 or total_chars >= 500


def unique_useful_paragraphs(paragraphs: list[str], headline: str, max_paragraphs: int | None) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()
    for paragraph in paragraphs:
        text = clean_html_text(paragraph)
        key = normalize_for_match(text)
        if not key or key in seen or not useful_detail_paragraph(text, headline):
            continue
        selected.append(text)
        seen.add(key)
        if max_paragraphs is not None and len(selected) >= max_paragraphs:
            break
    return selected


def iter_json_ld_nodes(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        nodes = [value]
        graph = value.get("@graph")
        if isinstance(graph, list):
            nodes.extend(node for node in graph if isinstance(node, dict))
        return nodes
    if isinstance(value, list):
        nodes: list[dict[str, Any]] = []
        for item in value:
            nodes.extend(iter_json_ld_nodes(item))
        return nodes
    return []


def json_ld_article_body(soup: Any) -> str:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text(" ", strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for node in iter_json_ld_nodes(data):
            node_type = node.get("@type")
            types = node_type if isinstance(node_type, list) else [node_type]
            normalized_types = {str(item).lower() for item in types if item}
            if not normalized_types.intersection({"newsarticle", "article"}):
                continue
            body = node.get("articleBody")
            if body:
                return str(body)
    return ""


def remove_unwanted_detail_nodes(soup: Any) -> None:
    selectors = (
        "script",
        "style",
        "noscript",
        "iframe",
        "nav",
        "footer",
        "aside",
        "form",
        ".advertisement",
        ".ads",
        ".cookie",
        ".related",
        ".share",
        ".social",
        ".subscribe",
        "[class*='reklam']",
        "[id*='reklam']",
        "[class*='abon']",
        "[id*='abon']",
        "[class*='cookie']",
        "[id*='cookie']",
        "[class*='related']",
        "[id*='related']",
        "[class*='share']",
        "[id*='share']",
    )
    for unwanted in soup.select(", ".join(selectors)):
        unwanted.decompose()


def extract_article_detail_with_status(
    page_url: str,
    headline: str = "",
    max_paragraphs: int | None = 12,
) -> tuple[list[str], str]:
    if not page_url:
        return [], "source_unavailable"
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return [], "source_unavailable"

    try:
        response = requests.get(page_url, headers=REQUEST_HEADERS, timeout=9)
        response.raise_for_status()
    except Exception:
        return [], "source_unavailable"

    soup = BeautifulSoup(response.text, "html.parser")
    json_ld_body = json_ld_article_body(soup)
    json_ld_paragraphs = unique_useful_paragraphs(split_detail_paragraphs(json_ld_body), headline, max_paragraphs)
    if meaningful_detail(json_ld_paragraphs):
        return json_ld_paragraphs, "json_ld_extracted"

    remove_unwanted_detail_nodes(soup)
    candidates: list[str] = []
    for selector in DETAIL_SELECTORS:
        selector_candidates: list[str] = []
        for paragraph in soup.select(selector):
            selector_candidates.append(paragraph.get_text(" ", strip=True))
        candidates.extend(selector_candidates)
        selected = unique_useful_paragraphs(candidates, headline, max_paragraphs)
        if meaningful_detail(selected):
            break

    selected = unique_useful_paragraphs(candidates, headline, max_paragraphs)
    if meaningful_detail(selected):
        return selected, "source_extracted"

    description = soup.find("meta", attrs={"property": "og:description"}) or soup.find("meta", attrs={"name": "description"})
    content = clean_html_text(str(description.get("content") or "")) if description else ""
    if useful_detail_paragraph(content, headline):
        return [content], "summary_fallback"
    return [], "source_unavailable"


def extract_article_detail(page_url: str, headline: str = "", max_paragraphs: int | None = 12) -> list[str]:
    paragraphs, _status = extract_article_detail_with_status(page_url, headline, max_paragraphs)
    return paragraphs


def fallback_article_body(article: dict[str, Any]) -> list[str]:
    body = article.get("body") if isinstance(article.get("body"), list) else []
    paragraphs = [clean_html_text(str(paragraph)) for paragraph in body if clean_html_text(str(paragraph))]
    if paragraphs:
        return paragraphs
    for key in ("dek", "summary", "description"):
        text = clean_html_text(str(article.get(key) or ""))
        if text:
            return [text]
    return [clean_html_text(str(article.get("headline") or "Haber detayı hazırlanıyor."))]


def enrich_article_details(issue_data: dict[str, Any]) -> dict[str, Any]:
    cache: dict[str, tuple[list[str], str]] = {}
    for page in issue_data.get("pages", []):
        if not isinstance(page, dict):
            continue
        for collection_name in ("articles", "briefs"):
            collection = page.get(collection_name, [])
            if not isinstance(collection, list):
                continue
            for article in collection:
                if not isinstance(article, dict):
                    continue
                sources = article.get("source_bundle") if isinstance(article.get("source_bundle"), list) else []
                source = sources[0] if sources and isinstance(sources[0], dict) else {}
                source_url = str(source.get("url") or "")
                if not source_url or source_url == "https://example.com":
                    paragraphs = fallback_article_body(article)
                    article["body"] = paragraphs
                    article["detail_status"] = "summary_fallback"
                    article["detail_paragraph_count"] = len(paragraphs)
                    article["detail_character_count"] = sum(len(paragraph) for paragraph in paragraphs)
                    continue
                if source_url not in cache:
                    cache[source_url] = extract_article_detail_with_status(source_url, str(article.get("headline") or ""))
                paragraphs, status = cache[source_url]
                if paragraphs:
                    article["body"] = paragraphs
                    article["detail_status"] = status
                else:
                    paragraphs = fallback_article_body(article)
                    article["body"] = paragraphs
                    article["detail_status"] = "summary_fallback" if paragraphs else "source_unavailable"
                article["detail_paragraph_count"] = len(article.get("body", []))
                article["detail_character_count"] = sum(len(str(paragraph)) for paragraph in article.get("body", []))
    return issue_data


def extension_from_response(url: str, content_type: str) -> str:
    parsed_ext = Path(urlparse(url).path).suffix.lower()
    if parsed_ext in IMAGE_EXTENSIONS:
        return ".jpg" if parsed_ext == ".jpeg" else parsed_ext

    mime = content_type.split(";", 1)[0].strip().lower()
    guessed = mimetypes.guess_extension(mime) or ".jpg"
    if guessed == ".jpe":
        return ".jpg"
    return guessed if guessed in IMAGE_EXTENSIONS else ".jpg"


def image_dimensions(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image
    except ImportError:
        return 0, 0

    try:
        with Image.open(path) as image:
            return image.size
    except Exception:
        return 0, 0


def fallback_font(size: int, bold: bool = False):
    from PIL import ImageFont

    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/seguisb.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default(size=size)


def wrapped_lines(draw: Any, text: str, font: Any, max_width: int, max_lines: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if current and bbox[2] - bbox[0] > max_width:
            lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break
        else:
            current = candidate
    if current and len(lines) < max_lines:
        lines.append(current)
    return lines


def fallback_image(article: dict[str, Any], image_dir: Path) -> dict[str, Any] | None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    headline = str(article.get("headline") or "Haber")
    section = str(article.get("section") or "gundem").upper()
    article_id = str(article.get("id") or headline)
    image_dir.mkdir(parents=True, exist_ok=True)
    path = image_dir / f"{slugify(article_id, 'story')}-fallback.jpg"

    palette = {
        "ANKARA": ("#f2efe8", "#243447", "#b14a32"),
        "EKONOMI": ("#edf3f8", "#243b53", "#2f6f9f"),
        "GUNDEM": ("#f0f4f8", "#2f3a3f", "#8a4f2a"),
        "SPOR": ("#eaf6ef", "#174a3c", "#2f855a"),
        "TEKNOLOJI": ("#eef2ff", "#243447", "#4c51bf"),
        "DUNYA": ("#f4f1ea", "#2f3a3f", "#8c6d31"),
    }
    bg, fg, accent = palette.get(slugify(section, "gundem").upper(), ("#f4f4f2", "#252525", "#777777"))
    image = Image.new("RGB", (1200, 720), bg)
    draw = ImageDraw.Draw(image)
    font_large = fallback_font(58, bold=True)
    font_small = fallback_font(28, bold=True)
    font_caption = fallback_font(24)

    draw.rectangle((0, 0, 1200, 720), fill=bg)
    draw.rectangle((0, 0, 1200, 74), fill=fg)
    draw.rectangle((0, 646, 1200, 720), fill=fg)
    draw.rectangle((48, 112, 1152, 608), outline=accent, width=8)
    draw.rectangle((80, 144, 240, 154), fill=accent)
    draw.text((80, 34), section, fill="#ffffff", font=font_small)

    lines = wrapped_lines(draw, headline, font_large, 980, 4)
    y = 250
    for line in lines:
        draw.text((92, y), line, fill=fg, font=font_large)
        y += 70
    draw.text((92, 650), "Gazet+E | TEMSİLİ GÖRSEL", fill="#ffffff", font=font_caption)
    image.save(path, quality=88)
    return {"path": str(path), "source_url": "", "width": 1200, "height": 720}


def download_image(image_url: str, image_dir: Path, article_id: str) -> dict[str, Any] | None:
    if not image_url:
        return None
    try:
        import requests
    except ImportError:
        return None

    try:
        response = requests.get(image_url, headers=REQUEST_HEADERS, timeout=12)
        response.raise_for_status()
    except Exception:
        return None

    content_type = response.headers.get("content-type", "")
    if content_type and not content_type.lower().startswith("image/"):
        return None

    image_dir.mkdir(parents=True, exist_ok=True)
    safe_id = slugify(article_id, "story")
    ext = extension_from_response(image_url, content_type)
    path = image_dir / f"{safe_id}{ext}"
    path.write_bytes(response.content)
    width, height = image_dimensions(path)
    if width <= 0 or height <= 0:
        path.unlink(missing_ok=True)
        return None
    return {"path": str(path), "source_url": image_url, "width": width, "height": height}


def ensure_article_image(article: dict[str, Any], image_dir: Path) -> None:
    image = article.get("image")
    if isinstance(image, dict) and image.get("path"):
        return

    source_bundle = article.get("source_bundle") if isinstance(article.get("source_bundle"), list) else []
    source = source_bundle[0] if source_bundle and isinstance(source_bundle[0], dict) else {}
    source_url = str(source.get("url") or "")
    image_url = str(article.get("image_url") or "")
    if not image_url:
        image_url = page_image_url(source_url)

    downloaded = download_image(image_url, image_dir, str(article.get("id") or article.get("headline") or "story"))
    if not downloaded:
        downloaded = fallback_image(article, image_dir)
    if not downloaded:
        return

    article["image"] = {
        "path": downloaded["path"],
        "source_url": downloaded["source_url"] or source_url,
        "alt": str(article.get("headline") or "Haber fotoğrafı"),
        "caption": str(article.get("dek") or article.get("headline") or "Haber fotoğrafı"),
        "credit": str(source.get("name") or "Kaynak"),
        "width": downloaded["width"],
        "height": downloaded["height"],
        "crop": "landscape",
    }


def enrich_issue_images(issue_data: dict[str, Any], image_dir: Path) -> dict[str, Any]:
    seen: set[int] = set()
    for page in issue_data.get("pages", []):
        if not isinstance(page, dict):
            continue
        for collection_name in ("articles", "briefs"):
            collection = page.get(collection_name, [])
            if not isinstance(collection, list):
                continue
            for article in collection:
                if not isinstance(article, dict):
                    continue
                if article.get("layout_hint", {}).get("story_size") == "brief":
                    continue
                object_id = id(article)
                if object_id in seen:
                    continue
                seen.add(object_id)
                ensure_article_image(article, image_dir)
    return issue_data


def section_for_source(source_name: str) -> str:
    source_key = source_name.lower()
    if "ankara" in source_key or "yerel" in source_key:
        return "ankara"
    if any(value in source_key for value in ("ekonomi", "tcmb")):
        return "ekonomi"
    if "spor" in source_key:
        return "spor"
    if any(value in source_key for value in ("teknoloji", "evrim")):
        return "teknoloji"
    if "dünya" in source_key or "dunya" in source_key:
        return "dunya"
    return "gundem"


def normalize_for_match(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    for old, new in {"ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c"}.items():
        text = text.replace(old, new)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def normalize_with_decimal(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    for old, new in {"ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c"}.items():
        text = text.replace(old, new)
    return re.sub(r"[^a-z0-9.,]+", " ", text).strip()


def match_tokens(article: dict[str, Any]) -> set[str]:
    text = normalize_for_match(f"{article.get('headline', '')} {article.get('dek', '')}")
    return {token for token in text.split() if len(token) > 2 and token not in STOP_WORDS}


def clickbait_score(article: dict[str, Any]) -> int:
    headline = str(article.get("headline") or "")
    dek = str(article.get("dek") or "")
    text = normalize_for_match(f"{headline} {dek}")
    score = 0

    for pattern in CLICKBAIT_BLOCK_PATTERNS:
        if re.search(pattern, text):
            score += 45
    for pattern in CLICKBAIT_SOFT_PATTERNS:
        if re.search(pattern, text):
            score += 15

    stripped = headline.strip()
    if stripped.endswith(("...", "..", "…")):
        score += 35
    if "!" in headline:
        score += min(headline.count("!") * 12, 30)
    if "?" in headline and not any(token in text for token in ("mi ", "mu ", "ne ", "neden ", "nasil ", "kac ")):
        score += min(headline.count("?") * 10, 20)
    if len(stripped) <= 28 and any(word in text.split() for word in ("iste", "sok", "olay", "bomba")):
        score += 12
    return score


def is_question_news(article: dict[str, Any]) -> bool:
    headline = str(article.get("headline") or "")
    text = normalize_for_match(f"{headline} {article.get('dek', '')}")
    if "?" in headline:
        return True
    return any(re.search(pattern, text) for pattern in QUESTION_NEWS_PATTERNS)


def earthquake_text(article: dict[str, Any]) -> str:
    return normalize_for_match(raw_article_text(article))


def raw_article_text(article: dict[str, Any]) -> str:
    body = article.get("body", [])
    body_text = " ".join(str(item) for item in body) if isinstance(body, list) else str(body or "")
    return " ".join(
        [
            str(article.get("headline") or ""),
            str(article.get("dek") or ""),
            body_text,
            source_name(article),
        ]
    )


def extract_earthquake_magnitude(text: str) -> float | None:
    patterns = (
        r"\b(\d{1,2}(?:[.,]\d)?)\s*buyuklugunde\b",
        r"\b(\d{1,2}(?:[.,]\d)?)\s*buyuklugundeki\b",
        r"\b(\d{1,2}(?:[.,]\d)?)\s*buyuklukte\b",
        r"\b(?:mw|ml|m)\s*(\d{1,2}(?:[.,]\d)?)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return float(match.group(1).replace(",", "."))
            except ValueError:
                return None
    return None


def extract_earthquake_location(text: str) -> str:
    for location in TURKEY_EARTHQUAKE_LOCATIONS:
        if location in text:
            return location
    return ""


def earthquake_event_gate(article: dict[str, Any]) -> dict[str, Any]:
    apply_hard_reject_filters(article)
    if article.get("reject_reason") == "seo_generic_earthquake_clickbait":
        return {
            "accepted": False,
            "earthquake_classification": "seo_generic_earthquake",
            "magnitude": None,
            "location": "",
            "official_source_detected": False,
            "impact_detected": False,
            "reject_reason": "seo_generic_earthquake_clickbait",
            "importance_cap_applied": False,
        }
    raw_text = normalize_with_decimal(raw_article_text(article))
    text = earthquake_text(article)
    if "deprem" not in text:
        return {"accepted": True, "earthquake_classification": "not_earthquake"}

    magnitude = extract_earthquake_magnitude(raw_text)
    location = extract_earthquake_location(text)
    official_source_detected = any(source in text for source in OFFICIAL_EARTHQUAKE_SOURCES)
    no_impact_detected = any(signal in text for signal in NO_EARTHQUAKE_IMPACT_SIGNALS)
    impact_detected = any(signal in text for signal in MAJOR_EARTHQUAKE_SIGNALS) and not no_impact_detected
    generic_clickbait = any(re.search(pattern, text) for pattern in ROUTINE_EARTHQUAKE_PATTERNS)
    turkey_event = not location or location in TURKEY_EARTHQUAKE_LOCATIONS
    serious_by_magnitude = magnitude is not None and magnitude >= (5.0 if turkey_event else 6.0)

    result: dict[str, Any] = {
        "accepted": True,
        "earthquake_classification": "minor_earthquake_ticker",
        "magnitude": magnitude,
        "location": location,
        "official_source_detected": official_source_detected,
        "impact_detected": impact_detected,
        "reject_reason": "",
        "importance_cap_applied": False,
    }

    if (generic_clickbait or is_generic_earthquake_clickbait(article)) and not (serious_by_magnitude or impact_detected):
        result.update(
            {
                "accepted": False,
                "earthquake_classification": "seo_generic_earthquake",
                "reject_reason": "seo_generic_earthquake_clickbait",
            }
        )
    elif serious_by_magnitude or impact_detected:
        result["earthquake_classification"] = "serious_earthquake_event"
    else:
        result["importance_cap_applied"] = True

    return result


def apply_earthquake_gate(article: dict[str, Any]) -> bool:
    result = earthquake_event_gate(article)
    if result["earthquake_classification"] == "not_earthquake":
        return True
    for key in (
        "earthquake_classification",
        "magnitude",
        "location",
        "official_source_detected",
        "impact_detected",
        "reject_reason",
        "importance_cap_applied",
    ):
        value = result.get(key)
        if value is not None:
            article[key] = value
    return bool(result["accepted"])


def is_routine_earthquake_update(article: dict[str, Any]) -> bool:
    return not earthquake_event_gate(article)["accepted"]


def is_clickbait_article(article: dict[str, Any]) -> bool:
    if not apply_earthquake_gate(article):
        return True
    return is_question_news(article) or clickbait_score(article) >= 45


def filter_clickbait_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for article in articles:
        if not is_clickbait_article(article):
            filtered.append(article)
    return filtered


def clean_editorial_pool(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sanitize_items_or_fail(filter_clickbait_articles(articles), "editorial_pool")


def sanitize_issue_articles(issue_data: dict[str, Any]) -> dict[str, Any]:
    for page in issue_data.get("pages", []):
        if not isinstance(page, dict):
            continue
        for collection_name in ("articles", "briefs"):
            collection = page.get(collection_name, [])
            if isinstance(collection, list):
                page[collection_name] = sanitize_items_or_fail(
                    clean_editorial_pool([article for article in collection if isinstance(article, dict)]),
                    f"{collection_name}_final_sanitizer_page_{page.get('page_no', '?')}",
                )
    return issue_data


def image_match_key(value: str) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    return normalize_for_match(Path(parsed.path).stem)


def article_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_tokens = match_tokens(left)
    right_tokens = match_tokens(right)
    if not left_tokens or not right_tokens:
        return 0
    overlap = len(left_tokens & right_tokens)
    return overlap / max(1, min(len(left_tokens), len(right_tokens)))


def is_duplicate_article(candidate: dict[str, Any], selected: list[dict[str, Any]]) -> bool:
    for article in selected:
        if duplicate_match(candidate, article):
            return True
    return False


def duplicate_match(candidate: dict[str, Any], article: dict[str, Any]) -> bool:
    candidate_image = image_match_key(str(candidate.get("image_url") or ""))
    if candidate_image and candidate_image == image_match_key(str(article.get("image_url") or "")):
        return True
    same_section = candidate.get("section") == article.get("section")
    threshold = 0.58 if same_section else 0.68
    return article_similarity(candidate, article) >= threshold


def source_name(article: dict[str, Any]) -> str:
    sources = article.get("source_bundle") if isinstance(article.get("source_bundle"), list) else []
    source = sources[0] if sources and isinstance(sources[0], dict) else {}
    return str(source.get("name") or "")


def published_datetime(article: dict[str, Any]) -> datetime | None:
    sources = article.get("source_bundle") if isinstance(article.get("source_bundle"), list) else []
    source = sources[0] if sources and isinstance(sources[0], dict) else {}
    value = str(source.get("published_at") or "")
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def recency_score(article: dict[str, Any]) -> int:
    dt = published_datetime(article)
    if not dt:
        return 0
    hours = max(0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600)
    if hours <= 2:
        return 18
    if hours <= 6:
        return 14
    if hours <= 12:
        return 10
    if hours <= 24:
        return 6
    return 0


def keyword_importance(article: dict[str, Any]) -> int:
    text = normalize_for_match(f"{article.get('headline', '')} {article.get('dek', '')}")
    score = 0
    for keyword, points in KEYWORD_SCORES.items():
        if normalize_for_match(keyword) in text:
            score += points
    return min(score, 75)


def earthquake_severity_score(article: dict[str, Any]) -> int:
    classification = str(article.get("earthquake_classification") or earthquake_event_gate(article).get("earthquake_classification") or "")
    magnitude = article.get("magnitude")
    official = bool(article.get("official_source_detected"))
    impact = bool(article.get("impact_detected"))
    score = 0
    if classification == "serious_earthquake_event":
        score += 22
    if isinstance(magnitude, (int, float)):
        if magnitude >= 7:
            score += 35
        elif magnitude >= 6:
            score += 24
        elif magnitude >= 5:
            score += 14
    if impact:
        score += 48
    if official:
        score += 8
    if classification == "minor_earthquake_ticker":
        score -= 18
    return score


def profile_score(article: dict[str, Any]) -> int:
    profile = load_profile()
    text = normalize_for_match(f"{article.get('headline', '')} {article.get('dek', '')} {article.get('section', '')}")
    score = 0
    for key, keywords in PROFILE_KEYWORDS.items():
        try:
            weight = int(profile.get(key, 0))
        except (TypeError, ValueError):
            weight = 0
        if weight <= 0:
            continue
        if any(keyword in text for keyword in keywords):
            score += weight * 3
    return min(score, 24)


def score_article(article: dict[str, Any]) -> int:
    source = source_name(article)
    section = str(article.get("section") or "")
    duplicate_bonus = min(int(article.get("duplicate_count") or 1) - 1, 4) * 12
    score = 20
    score += SOURCE_SCORES.get(source, 4)
    score += SECTION_SCORES.get(section, 4)
    score += keyword_importance(article)
    score += earthquake_severity_score(article)
    score += profile_score(article)
    score += recency_score(article)
    score += duplicate_bonus
    if article.get("image_url"):
        score += 4
    score -= min(clickbait_score(article), 60)
    return max(score, 0)


def sort_by_importance(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scored = sorted(
        articles,
        key=lambda article: (
            score_article(article),
            -int(article.get("importance") or 9999),
            source_name(article),
        ),
        reverse=True,
    )
    for idx, article in enumerate(scored, start=1):
        article["importance"] = idx
        article["importance_score"] = score_article(article)
        if article.get("earthquake_classification") == "minor_earthquake_ticker":
            article["importance_cap_applied"] = True
            article["importance"] = max(article["importance"], 3)
    return scored


def dedupe_similar_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    articles = sanitize_items_or_fail(articles, "dedupe_before")
    selected: list[dict[str, Any]] = []
    for article in articles:
        for existing in selected:
            if duplicate_match(article, existing):
                existing["duplicate_count"] = int(existing.get("duplicate_count") or 1) + 1
                break
        else:
            article["duplicate_count"] = 1
            selected.append(article)
    return sort_by_importance(selected)


def prioritize_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sanitize_items_or_fail(
        sort_by_importance(dedupe_similar_articles(filter_clickbait_articles(articles))),
        "ranked_articles",
    )


def parse_feed_articles(feeds: dict[str, str], limit: int) -> list[dict[str, Any]]:
    try:
        import feedparser
    except ImportError:
        return []

    by_source: list[list[dict[str, Any]]] = []
    seen_links: set[str] = set()
    per_feed_limit = max(5, limit // max(1, len(feeds)))
    for source_name, url in feeds.items():
        parsed = feedparser.parse(url)
        source_articles: list[dict[str, Any]] = []
        for entry in parsed.entries[:per_feed_limit]:
            published = (
                getattr(entry, "published", None)
                or getattr(entry, "updated", None)
                or datetime.now(timezone.utc).isoformat()
            )
            title = str(getattr(entry, "title", "Başlık"))
            summary = clean_html_text(str(getattr(entry, "summary", title)))
            link = str(getattr(entry, "link", url))
            if link in seen_links:
                continue
            image_url = entry_image_url(entry)
            section = section_for_source(source_name)
            article = {
                "id": f"{source_name.lower().replace(' ', '-')}-{len(source_articles) + 1}",
                "section": section,
                "headline": title,
                "importance": len(source_articles) + 1,
                "dek": summary,
                "body": [summary],
                "source_bundle": [
                    {
                        "name": source_name,
                        "url": link,
                        "published_at": published,
                        "source_type": "institution" if source_name == "TCMB" else "rss",
                        "is_primary": source_name == "TCMB",
                    }
                ],
                "verification": {
                    "status": "single_source",
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "method": ["primary_source"],
                    "note": f"{source_name} RSS akışından alındı.",
                },
                "layout_hint": {"story_size": "secondary", "column_span": 2, "preferred_position": "mid"},
                "image": {},
                "image_url": image_url,
            }
            if is_clickbait_article(article):
                continue
            seen_links.add(link)
            source_articles.append(article)
        if source_articles:
            by_source.append(source_articles)

    articles: list[dict[str, Any]] = []
    max_source_len = max((len(items) for items in by_source), default=0)
    for idx in range(max_source_len):
        for source_articles in by_source:
            if idx < len(source_articles):
                source_articles[idx]["importance"] = len(articles) + 1
                articles.append(source_articles[idx])
    return dedupe_similar_articles(articles)[:limit]


def extract_anka_articles(limit: int = 40) -> list[dict[str, Any]]:
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    try:
        response = requests.get(ANKA_HOMEPAGE_URL, headers=REQUEST_HEADERS, timeout=10)
        response.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    articles: list[dict[str, Any]] = []
    seen_links: set[str] = set()
    for link_tag in soup.select("a[href^='/haber/']"):
        href = str(link_tag.get("href") or "")
        link = urljoin(ANKA_HOMEPAGE_URL, href)
        title = clean_html_text(link_tag.get_text(" ", strip=True))
        if not title:
            title = clean_html_text(str(link_tag.get("aria-label") or link_tag.get("title") or ""))
        if not title or len(title) < 18 or link in seen_links:
            continue

        image_url = ""
        image_tag = link_tag.find("img")
        if image_tag:
            image_url = str(image_tag.get("src") or image_tag.get("data-src") or "")
            if image_url:
                image_url = urljoin(ANKA_HOMEPAGE_URL, image_url)

        article = {
            "id": f"anka-haber-ajansi-{len(articles) + 1}",
            "section": "gundem",
            "headline": title,
            "importance": len(articles) + 1,
            "dek": title,
            "body": [title],
            "source_bundle": [
                {
                    "name": "ANKA Haber Ajansı",
                    "url": link,
                    "published_at": datetime.now(timezone.utc).isoformat(),
                    "source_type": "agency",
                    "is_primary": False,
                }
            ],
            "verification": {
                "status": "single_source",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "method": ["primary_source"],
                "note": "ANKA Haber Ajansı ana sayfa akışından alındı.",
            },
            "layout_hint": {"story_size": "secondary", "column_span": 2, "preferred_position": "mid"},
            "image": {},
            "image_url": image_url,
        }
        if is_clickbait_article(article):
            continue
        seen_links.add(link)
        articles.append(article)
        if len(articles) >= limit:
            break

    return dedupe_similar_articles(articles)


def fetch_rss_articles(limit: int = 120) -> list[dict[str, Any]]:
    articles = parse_feed_articles(DEFAULT_FEEDS, limit)
    articles.extend(extract_anka_articles(max(15, limit // 4)))
    return prioritize_articles(articles)[:limit]




def page_articles(source_articles: list[dict[str, Any]], start: int = 0) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source_articles = clean_editorial_pool(source_articles)
    layouts = [
        {"story_size": "hero", "column_span": 1, "preferred_position": "top"},
        {"story_size": "lead", "column_span": 1, "preferred_position": "top"},
    ] + [{"story_size": "secondary", "column_span": 1, "preferred_position": "mid"} for _ in range(10)]

    main_articles = deepcopy(source_articles[start : start + 12])
    if len(main_articles) < 12:
        main_articles.extend(deepcopy(source_articles[: 12 - len(main_articles)]))
    for offset, (article, layout_hint) in enumerate(zip(main_articles, layouts)):
        article["importance"] = offset + 1
        article["layout_hint"] = layout_hint

    rail_articles = deepcopy(source_articles[start + 12 : start + 32])
    if len(rail_articles) < 20:
        rail_articles.extend(deepcopy(source_articles[: 20 - len(rail_articles)]))
    for offset, article in enumerate(rail_articles[:20]):
        article["importance"] = offset + 1
        article["layout_hint"] = {"story_size": "brief", "column_span": 1, "preferred_position": "rail"}
        article["image"] = {}
    return (
        sanitize_items_or_fail(main_articles[:12], "front_page_before_render"),
        sanitize_items_or_fail(rail_articles[:20], "latest_before_render"),
    )
