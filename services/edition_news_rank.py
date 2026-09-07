"""Versioned deterministic Q06 dedupe, clustering and ranking policy."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from services.edition_news_models import (
    ArticleCandidate,
    ClusterBreakdown,
    CollectionResult,
    RankedCluster,
    RankedCollection,
    RankingBreakdown,
)
from services.edition_news_normalize import normalize_text

RANKING_POLICY_VERSION = "gazet-e.news-ranking.v1"
CLUSTER_POLICY_VERSION = "gazet-e.story-cluster.v1"

PUBLISHER_SCORES = {"ntv": 9, "haberturk": 8, "sozcu": 7, "evrim-agaci": 4}
SECTION_SCORES = {"gundem": 12, "ekonomi": 11, "dunya": 10, "teknoloji": 7, "spor": 6}
TOPIC_SCORES = {
    "afet": 12,
    "yangin": 10,
    "meclis": 9,
    "mahkeme": 8,
    "tcmb": 12,
    "faiz": 10,
    "enflasyon": 10,
    "savas": 12,
    "yapay zeka": 8,
}
_STOP_WORDS = {
    "aciklandi",
    "ardindan",
    "bir",
    "bugun",
    "daha",
    "icin",
    "ile",
    "son",
    "sonra",
    "ve",
    "yeni",
}


def build_ranked_collection(
    collection: CollectionResult,
    *,
    now: datetime | None = None,
) -> RankedCollection:
    clock = _as_utc(now or datetime.now(timezone.utc))
    deduped = collapse_exact_duplicates(collection.candidates)
    scored = tuple(rank_article(article, clock) for article in deduped)
    accepted = tuple(
        sorted(
            (article for article in scored if article.quality.accepted),
            key=_article_order,
        )
    )
    rejected = tuple(
        sorted(
            (article for article in scored if not article.quality.accepted),
            key=lambda article: article.article_id,
        )
    )
    clusters = cluster_articles(accepted)
    return RankedCollection(
        ranking_policy_version=RANKING_POLICY_VERSION,
        cluster_policy_version=CLUSTER_POLICY_VERSION,
        generated_at=clock,
        articles=accepted,
        rejected_articles=rejected,
        clusters=clusters,
        fetch_results=collection.fetch_results,
    )


def collapse_exact_duplicates(
    candidates: tuple[ArticleCandidate, ...] | list[ArticleCandidate],
) -> tuple[ArticleCandidate, ...]:
    selected: dict[str, ArticleCandidate] = {}
    for candidate in candidates:
        current = selected.get(candidate.article_id)
        if current is None or _content_choice(candidate) > _content_choice(current):
            selected[candidate.article_id] = candidate
    return tuple(selected[key] for key in sorted(selected))


def rank_article(article: ArticleCandidate, now: datetime) -> ArticleCandidate:
    publisher = PUBLISHER_SCORES.get(article.attribution.publisher_id, 0)
    section = SECTION_SCORES.get(article.attribution.section, 0)
    recency = _recency_score(article.published_at, now)
    topic = _topic_score(article.headline)
    base = 20
    total = base + recency + publisher + section + topic
    if not article.quality.accepted:
        total = 0
    return article.model_copy(
        update={
            "ranking": RankingBreakdown(
                policy_version=RANKING_POLICY_VERSION,
                base=base,
                recency=recency,
                publisher=publisher,
                section=section,
                headline_topic=topic,
                total=total,
            )
        }
    )


def cluster_articles(
    articles: tuple[ArticleCandidate, ...] | list[ArticleCandidate],
) -> tuple[RankedCluster, ...]:
    ordered = tuple(sorted(articles, key=lambda article: article.article_id))
    groups: list[list[ArticleCandidate]] = []
    for article in ordered:
        matching_group = next(
            (
                group
                for group in groups
                if all(_same_story_signal(article, member) for member in group)
            ),
            None,
        )
        if matching_group is None:
            groups.append([article])
        else:
            matching_group.append(article)

    clusters = tuple(_make_cluster(group) for group in groups)
    return tuple(sorted(clusters, key=lambda cluster: (-cluster.score, cluster.cluster_id)))


def _make_cluster(members: list[ArticleCandidate]) -> RankedCluster:
    ranked_members = tuple(sorted(members, key=_article_order))
    lead = ranked_members[0]
    stable_ids = tuple(sorted(article.article_id for article in members))
    publisher_ids = tuple(sorted({article.attribution.publisher_id for article in members}))
    diversity = min(max(len(publisher_ids) - 1, 0) * 3, 9)
    lead_score = lead.ranking.total if lead.ranking else 0
    score = lead_score + diversity
    identity = hashlib.sha256(
        (CLUSTER_POLICY_VERSION + "".join(stable_ids)).encode("utf-8")
    ).hexdigest()
    return RankedCluster(
        cluster_id=identity,
        cluster_policy_version=CLUSTER_POLICY_VERSION,
        member_article_ids=tuple(article.article_id for article in ranked_members),
        lead_article_id=lead.article_id,
        publisher_ids=publisher_ids,
        score=score,
        signals=ClusterBreakdown(
            lead_score=lead_score,
            source_diversity=diversity,
            total=score,
        ),
    )


def _same_story_signal(left: ArticleCandidate, right: ArticleCandidate) -> bool:
    if left.attribution.publisher_id == right.attribution.publisher_id:
        return False
    if left.attribution.section != right.attribution.section:
        return False
    if left.published_at and right.published_at:
        distance = abs((_as_utc(left.published_at) - _as_utc(right.published_at)).total_seconds())
        if distance > 36 * 3600:
            return False
    left_tokens = _headline_tokens(left.headline)
    right_tokens = _headline_tokens(right.headline)
    if len(left_tokens) < 4 or len(right_tokens) < 4:
        return False
    shared = left_tokens & right_tokens
    if len(shared) < 3:
        return False
    containment = len(shared) / min(len(left_tokens), len(right_tokens))
    jaccard = len(shared) / len(left_tokens | right_tokens)
    return containment >= 0.6 and jaccard >= 0.4


def _headline_tokens(headline: str) -> set[str]:
    return {
        token
        for token in normalize_text(headline).split()
        if len(token) > 2 and token not in _STOP_WORDS
    }


def _article_order(article: ArticleCandidate) -> tuple[int, float, str]:
    total = article.ranking.total if article.ranking else 0
    published = _timestamp(article.published_at)
    return (-total, -published, article.article_id)


def _content_choice(article: ArticleCandidate) -> tuple[float, str]:
    return (_timestamp(article.published_at), article.content_version)


def _timestamp(value: datetime | None) -> float:
    return _as_utc(value).timestamp() if value else 0.0


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _recency_score(published_at: datetime | None, now: datetime) -> int:
    if published_at is None:
        return 0
    hours = max(0.0, (_as_utc(now) - _as_utc(published_at)).total_seconds() / 3600)
    if hours <= 2:
        return 18
    if hours <= 6:
        return 14
    if hours <= 12:
        return 10
    if hours <= 24:
        return 6
    if hours <= 48:
        return 2
    return 0


def _topic_score(headline: str) -> int:
    normalized = normalize_text(headline)
    return min(
        sum(points for topic, points in TOPIC_SCORES.items() if topic in normalized),
        30,
    )
