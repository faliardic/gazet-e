from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from pydantic import ValidationError

from services.edition_news_fetch import (
    CONNECT_TIMEOUT_SECONDS,
    MAX_FETCH_ATTEMPTS,
    READ_TIMEOUT_SECONDS,
    EditionNewsCollector,
)
from services.edition_news_models import CollectionResult, SourceDefinition
from services.edition_news_normalize import (
    CandidateNormalizationError,
    article_identity,
    normalize_canonical_url,
    normalize_entry,
)
from services.edition_news_rank import (
    CLUSTER_POLICY_VERSION,
    RANKING_POLICY_VERSION,
    build_ranked_collection,
    collapse_exact_duplicates,
)
from services.edition_news_registry import RSS_REGISTRY

NOW = datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc)
SOURCE_A = RSS_REGISTRY[0]
SOURCE_B = RSS_REGISTRY[5]


class FakeResponse:
    def __init__(
        self,
        payload: bytes,
        *,
        status_code: int = 200,
        url: str = "https://feeds.example.test/news.xml",
        history: tuple[object, ...] = (),
    ) -> None:
        self.payload = payload
        self.status_code = status_code
        self.url = url
        self.history = history
        self.closed = False

    def iter_content(self, chunk_size: int):
        for offset in range(0, len(self.payload), chunk_size):
            yield self.payload[offset : offset + chunk_size]

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, actions: list[object]) -> None:
        self.actions = list(actions)
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        action = self.actions.pop(0)
        if isinstance(action, Exception):
            raise action
        action.url = url
        return action


def _rss(
    title: str = "Merkez Bankası politika faizini sabit tuttu",
    link: str = "https://news.example.test/story?utm_source=x&amp;id=7",
    description: str = "Karar kurul toplantısının ardından açıklandı.",
) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><title>Test</title><item>
    <title>{title}</title><link>{link}</link><description>{description}</description>
    <pubDate>Mon, 07 Sep 2026 08:00:00 GMT</pubDate>
    </item></channel></rss>""".encode()


def _candidate(
    source: SourceDefinition = SOURCE_A,
    *,
    title: str = "Merkez Bankası politika faizini yüzde 45 seviyesinde tuttu",
    url: str = "https://example.test/story",
    published_at: datetime = NOW - timedelta(hours=1),
    excerpt: str = "Karar toplantının ardından duyuruldu.",
):
    return normalize_entry(
        {
            "title": title,
            "link": url,
            "summary": excerpt,
            "published": published_at.isoformat(),
        },
        source,
        NOW,
    )


def _collection(*candidates):
    return CollectionResult(
        policy_version="test-registry.v1",
        collected_at=NOW,
        fetch_results=(),
        candidates=tuple(candidates),
    )


def test_registry_ids_are_unique_stable_and_https() -> None:
    assert len(RSS_REGISTRY) == 16
    assert len({source.source_id for source in RSS_REGISTRY}) == 16
    assert {source.family for source in RSS_REGISTRY} == {
        "NTV",
        "Habertürk",
        "Sözcü",
        "Evrim Ağacı",
    }
    assert all(source.feed_url.startswith("https://") for source in RSS_REGISTRY)
    assert tuple((source.source_id, source.feed_url) for source in RSS_REGISTRY) == (
        ("ntv-turkiye", "https://www.ntv.com.tr/turkiye.rss"),
        ("ntv-dunya", "https://www.ntv.com.tr/dunya.rss"),
        ("ntv-ekonomi", "https://www.ntv.com.tr/ekonomi.rss"),
        ("ntv-teknoloji", "https://www.ntv.com.tr/teknoloji.rss"),
        ("ntv-spor", "https://www.ntv.com.tr/sporskor.rss"),
        ("haberturk-gundem", "https://www.haberturk.com/rss/kategori/gundem.xml"),
        ("haberturk-dunya", "https://www.haberturk.com/rss/kategori/dunya.xml"),
        ("haberturk-ekonomi", "https://www.haberturk.com/rss/ekonomi.xml"),
        ("haberturk-spor", "https://www.haberturk.com/rss/spor.xml"),
        (
            "haberturk-teknoloji",
            "https://www.haberturk.com/rss/kategori/teknoloji.xml",
        ),
        ("sozcu-gundem", "https://www.sozcu.com.tr/feeds-rss-category-gundem"),
        ("sozcu-dunya", "https://www.sozcu.com.tr/feeds-rss-category-dunya"),
        ("sozcu-ekonomi", "https://www.sozcu.com.tr/feeds-rss-category-ekonomi"),
        ("sozcu-spor", "https://www.sozcu.com.tr/feeds-rss-category-spor"),
        (
            "sozcu-teknoloji",
            "https://www.sozcu.com.tr/feeds-rss-category-bilim-teknoloji",
        ),
        ("evrim-agaci-bilim", "https://evrimagaci.org/rss.xml"),
    )


def test_bounded_fetch_uses_timeout_user_agent_and_retry() -> None:
    response = FakeResponse(_rss())
    session = FakeSession([requests.ConnectionError(), response])
    sleeps: list[float] = []
    result = EditionNewsCollector(
        registry=(SOURCE_A,),
        session=session,
        clock=lambda: NOW,
        sleeper=sleeps.append,
    ).collect()
    assert result.fetch_results[0].success is True
    assert len(session.calls) == MAX_FETCH_ATTEMPTS
    assert session.calls[0][1]["timeout"] == (
        CONNECT_TIMEOUT_SECONDS,
        READ_TIMEOUT_SECONDS,
    )
    assert session.calls[0][1]["stream"] is True
    assert session.calls[0][1]["headers"]["User-Agent"].startswith("Gazet+E/")
    assert sleeps == [0.2]
    assert response.closed is True


def test_feed_failure_is_structured_without_erasing_successful_feed() -> None:
    session = FakeSession(
        [
            requests.ConnectionError(),
            requests.ConnectionError(),
            FakeResponse(_rss()),
        ]
    )
    result = EditionNewsCollector(
        registry=(SOURCE_A, SOURCE_B),
        session=session,
        clock=lambda: NOW,
        sleeper=lambda _delay: None,
    ).collect()
    assert result.fetch_results[0].status == "network_error"
    assert result.fetch_results[0].success is False
    assert result.fetch_results[1].success is True
    assert len(result.candidates) == 1


def test_non_https_redirect_chain_fails_closed() -> None:
    redirect = type("Redirect", (), {"url": "http://unsafe.example.test/feed"})()
    session = FakeSession([FakeResponse(_rss(), history=(redirect,))])
    result = EditionNewsCollector(
        registry=(SOURCE_A,),
        session=session,
        clock=lambda: NOW,
    ).collect()
    assert result.fetch_results[0].success is False
    assert result.fetch_results[0].status == "unsafe_redirect"
    assert result.candidates == ()


def test_rss_entry_normalization_has_complete_source_attribution() -> None:
    candidate = _candidate()
    assert candidate.attribution.publisher_id == SOURCE_A.publisher_id
    assert candidate.attribution.source_id == SOURCE_A.source_id
    assert candidate.attribution.feed_url == SOURCE_A.feed_url
    assert candidate.attribution.section == SOURCE_A.section


@pytest.mark.parametrize(
    "url",
    [
        "http://example.test/story",
        "ftp://example.test/story",
        "https://user:password@example.test/story",
        "not-a-url",
    ],
)
def test_malformed_non_https_or_credential_url_fails_closed(url: str) -> None:
    with pytest.raises(CandidateNormalizationError):
        normalize_canonical_url(url)


def test_tracking_query_normalization_is_deterministic() -> None:
    first = normalize_canonical_url(
        "https://EXAMPLE.test:443/story?utm_source=x&id=7&fbclid=z&a=1#top"
    )
    second = normalize_canonical_url("https://example.test/story?a=1&id=7")
    assert first == second == "https://example.test/story?a=1&id=7"


def test_same_publisher_and_normalized_url_has_same_article_id() -> None:
    left = _candidate(url="https://example.test/story?utm_medium=rss&id=7")
    right = _candidate(url="https://EXAMPLE.test:443/story?id=7#fragment")
    assert left.article_id == right.article_id
    assert left.article_id == article_identity("ntv", left.canonical_url)


def test_changed_feed_facts_change_content_version_not_article_id() -> None:
    left = _candidate(excerpt="İlk kısa RSS açıklaması.")
    right = _candidate(excerpt="Güncellenmiş kısa RSS açıklaması.")
    assert left.article_id == right.article_id
    assert left.content_version != right.content_version


def test_exact_duplicates_collapse_to_deterministic_latest_version() -> None:
    older = _candidate(excerpt="Eski açıklama.", published_at=NOW - timedelta(hours=2))
    newer = _candidate(excerpt="Yeni açıklama.", published_at=NOW - timedelta(hours=1))
    forward = collapse_exact_duplicates((older, newer))
    reverse = collapse_exact_duplicates((newer, older))
    assert len(forward) == 1
    assert forward == reverse
    assert forward[0].content_version == newer.content_version


def test_different_publishers_remain_distinct_article_identities() -> None:
    left = _candidate(SOURCE_A)
    right = _candidate(SOURCE_B)
    assert left.canonical_url == right.canonical_url
    assert left.article_id != right.article_id


def test_cross_source_near_duplicate_story_clustering() -> None:
    left = _candidate(SOURCE_A)
    right = _candidate(
        SOURCE_B,
        title="TCMB politika faizini yüzde 45 seviyesinde sabit tuttu",
        url="https://other.example.test/economy/story",
    )
    ranked = build_ranked_collection(_collection(left, right), now=NOW)
    assert len(ranked.clusters) == 1
    assert set(ranked.clusters[0].member_article_ids) == {
        left.article_id,
        right.article_id,
    }


def test_generic_similar_unrelated_titles_do_not_overcluster() -> None:
    left = _candidate(
        SOURCE_A,
        title="Son dakika ekonomi piyasalarında yeni gelişme açıklandı",
    )
    right = _candidate(
        SOURCE_B,
        title="Son dakika belediye ulaşımında yeni gelişme açıklandı",
        url="https://other.example.test/city/story",
    )
    ranked = build_ranked_collection(_collection(left, right), now=NOW)
    assert len(ranked.clusters) == 2


def test_cluster_identity_member_and_lead_order_is_deterministic() -> None:
    left = _candidate(SOURCE_A)
    right = _candidate(
        SOURCE_B,
        title="TCMB politika faizini yüzde 45 seviyesinde sabit tuttu",
        url="https://other.example.test/economy/story",
    )
    forward = build_ranked_collection(_collection(left, right), now=NOW)
    reverse = build_ranked_collection(_collection(right, left), now=NOW)
    assert forward.clusters == reverse.clusters
    cluster = forward.clusters[0]
    assert cluster.cluster_policy_version == CLUSTER_POLICY_VERSION
    assert cluster.lead_article_id == forward.articles[0].article_id


def test_hard_rejected_content_cannot_enter_ranked_clusters() -> None:
    rejected = _candidate(
        title="Son dakika deprem mi oldu, AFAD son depremler",
        excerpt="Az önce deprem nerede oldu?",
    )
    ranked = build_ranked_collection(_collection(rejected), now=NOW)
    assert ranked.articles == ()
    assert ranked.clusters == ()
    assert ranked.rejected_articles == (ranked.rejected_articles[0],)


def test_quality_reject_reason_is_structured_and_versioned() -> None:
    candidate = _candidate(
        title="Son dakika deprem mi oldu, AFAD son depremler",
        excerpt="Az önce deprem nerede oldu?",
    )
    assert candidate.quality.accepted is False
    assert candidate.quality.policy_version == "gazet-e.quality.v1"
    assert candidate.quality.reason_codes == ("seo_generic_earthquake_clickbait",)


def test_ranking_signal_breakdown_is_deterministic_and_versioned() -> None:
    candidate = _candidate()
    first = build_ranked_collection(_collection(candidate), now=NOW)
    second = build_ranked_collection(_collection(candidate), now=NOW)
    assert first.articles[0].ranking == second.articles[0].ranking
    assert first.articles[0].ranking.policy_version == RANKING_POLICY_VERSION
    assert first.articles[0].ranking.total == sum(
        (
            first.articles[0].ranking.base,
            first.articles[0].ranking.recency,
            first.articles[0].ranking.publisher,
            first.articles[0].ranking.section,
            first.articles[0].ranking.headline_topic,
        )
    )


def test_recency_order_uses_injected_clock() -> None:
    recent = _candidate(url="https://example.test/recent", published_at=NOW - timedelta(hours=1))
    old = _candidate(url="https://example.test/old", published_at=NOW - timedelta(days=3))
    ranked = build_ranked_collection(_collection(old, recent), now=NOW)
    assert ranked.articles[0].article_id == recent.article_id
    assert ranked.articles[0].ranking.recency > ranked.articles[1].ranking.recency


def test_personalization_and_image_availability_are_not_model_or_rank_signals() -> None:
    candidate = _candidate()
    with pytest.raises(ValidationError):
        candidate.__class__(
            **candidate.model_dump(),
            image_url="https://example.test/image.jpg",
        )
    ranked = build_ranked_collection(_collection(candidate), now=NOW)
    signals = ranked.articles[0].ranking.model_dump()
    assert "profile" not in signals
    assert "personalization" not in signals
    assert "image" not in signals


def test_output_has_attribution_without_body_or_local_asset_path() -> None:
    ranked = build_ranked_collection(_collection(_candidate()), now=NOW)
    payload = ranked.model_dump(mode="json")
    article = payload["articles"][0]
    assert article["attribution"]["publisher_id"] == "ntv"
    assert article["attribution"]["feed_url"].startswith("https://")
    assert "body" not in article
    assert "image" not in article
    assert "asset_path" not in str(payload)


def test_q06_modules_have_no_ai_scraping_personalization_or_q05_mutation() -> None:
    root = Path(__file__).resolve().parents[1]
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((root / "services").glob("edition_news_*.py"))
    ).casefold()
    assert "feedparser.parse(source.feed_url" not in sources
    assert "beautifulsoup" not in sources
    assert "page_image" not in sources
    assert "article body" not in sources
    assert "openai" not in sources
    assert "anthropic" not in sources
    assert "user_profile" not in sources
    assert "edition_job_store" not in sources
    assert "edition_job_worker" not in sources
    assert "requests.get" not in sources
    assert "feedparser.parse(payload)" in inspect.getsource(EditionNewsCollector)
