"""Canonical URL, identity and feed-entry normalization for Q06."""

from __future__ import annotations

import calendar
import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from services.edition_news_models import (
    ArticleCandidate,
    QualityDecision,
    SourceAttribution,
    SourceDefinition,
)
from services.news_quality_filters import apply_hard_reject_filters

IDENTITY_VERSION = "article-id.v1"
CONTENT_VERSION = "article-content.v1"
QUALITY_POLICY_VERSION = "gazet-e.quality.v1"
MAX_HEADLINE_LENGTH = 300
MAX_EXCERPT_LENGTH = 1200

_TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "dclid",
    "msclkid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "vero_conv",
    "vero_id",
}


class CandidateNormalizationError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def normalize_canonical_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except (ValueError, AttributeError) as error:
        raise CandidateNormalizationError("invalid_article_url") from error
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise CandidateNormalizationError("invalid_article_url")
    if parsed.username is not None or parsed.password is not None:
        raise CandidateNormalizationError("credential_bearing_article_url")

    host = parsed.hostname.lower()
    if port is not None and port != 443:
        host = f"{host}:{port}"
    path = parsed.path or "/"
    query = sorted(
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not _is_tracking_parameter(key)
    )
    return urlunsplit(("https", host, path, urlencode(query, doseq=True), ""))


def article_identity(publisher_id: str, canonical_url: str) -> str:
    payload = f"{IDENTITY_VERSION}{publisher_id}{canonical_url}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def content_identity(
    article_id: str,
    headline: str,
    excerpt: str,
    published_at: datetime | None,
) -> str:
    published = published_at.isoformat() if published_at else ""
    facts = "\x1f".join(
        (
            CONTENT_VERSION,
            article_id,
            normalize_text(headline),
            normalize_text(excerpt),
            published,
        )
    )
    return hashlib.sha256(facts.encode("utf-8")).hexdigest()


def normalize_entry(
    entry: Any,
    source: SourceDefinition,
    collected_at: datetime,
) -> ArticleCandidate:
    headline = clean_feed_text(_entry_value(entry, "title"))[:MAX_HEADLINE_LENGTH]
    if not headline:
        raise CandidateNormalizationError("missing_headline")
    raw_url = _entry_value(entry, "link") or _entry_value(entry, "id")
    canonical_url = normalize_canonical_url(raw_url)
    excerpt = clean_feed_text(
        _entry_value(entry, "summary") or _entry_value(entry, "description")
    )[:MAX_EXCERPT_LENGTH]
    published_at = entry_publication_time(entry)
    article_id = article_identity(source.publisher_id, canonical_url)
    quality = quality_decision(headline, excerpt, canonical_url)
    return ArticleCandidate(
        article_id=article_id,
        content_version=content_identity(
            article_id,
            headline,
            excerpt,
            published_at,
        ),
        canonical_url=canonical_url,
        headline=headline,
        feed_excerpt=excerpt,
        published_at=published_at,
        collected_at=collected_at,
        attribution=SourceAttribution(
            publisher_id=source.publisher_id,
            source_id=source.source_id,
            display_name=source.display_name,
            section=source.section,
            feed_url=source.feed_url,
        ),
        quality=quality,
    )


def quality_decision(
    headline: str,
    excerpt: str,
    canonical_url: str,
) -> QualityDecision:
    legacy_view = {
        "headline": headline,
        "summary": excerpt,
        "canonical_url": canonical_url,
    }
    apply_hard_reject_filters(legacy_view)
    if legacy_view.get("rejected"):
        reason = str(legacy_view.get("reject_reason") or "hard_reject")
        return QualityDecision(
            policy_version=QUALITY_POLICY_VERSION,
            accepted=False,
            reason_codes=(reason,),
        )
    return QualityDecision(
        policy_version=QUALITY_POLICY_VERSION,
        accepted=True,
    )


def clean_feed_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", unescape(without_tags)).strip()


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = text.replace("ı", "i")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def entry_publication_time(entry: Any) -> datetime | None:
    structured = _entry_raw(entry, "published_parsed") or _entry_raw(
        entry,
        "updated_parsed",
    )
    if structured:
        try:
            return datetime.fromtimestamp(calendar.timegm(structured), timezone.utc)
        except (OverflowError, TypeError, ValueError):
            pass
    raw = _entry_value(entry, "published") or _entry_value(entry, "updated")
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_tracking_parameter(key: str) -> bool:
    normalized = key.casefold()
    return normalized.startswith("utm_") or normalized in _TRACKING_PARAMETERS


def _entry_value(entry: Any, key: str) -> str:
    value = _entry_raw(entry, key)
    return str(value or "")


def _entry_raw(entry: Any, key: str) -> Any:
    if isinstance(entry, dict):
        return entry.get(key)
    return getattr(entry, key, None)
