"""Immutable JSON-ready models for the Q06 live-news boundary."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceDefinition(FrozenModel):
    publisher_id: str
    source_id: str
    display_name: str
    family: str
    section: str
    feed_url: str


class SourceAttribution(FrozenModel):
    publisher_id: str
    source_id: str
    display_name: str
    section: str
    feed_url: str


class QualityDecision(FrozenModel):
    policy_version: str
    accepted: bool
    reason_codes: tuple[str, ...] = ()


class RankingBreakdown(FrozenModel):
    policy_version: str
    base: int
    recency: int
    publisher: int
    section: int
    headline_topic: int
    total: int


class ArticleCandidate(FrozenModel):
    article_id: str
    content_version: str
    canonical_url: str
    headline: str = Field(min_length=1, max_length=300)
    feed_excerpt: str = Field(max_length=1200)
    published_at: datetime | None = None
    collected_at: datetime
    attribution: SourceAttribution
    quality: QualityDecision
    ranking: RankingBreakdown | None = None


class FetchResult(FrozenModel):
    publisher_id: str
    source_id: str
    fetched_at: datetime
    success: bool
    status: str
    http_status: int | None = None
    item_count: int = 0
    rejected_item_count: int = 0
    diagnostic: str = Field(max_length=160)
    item_errors: tuple[str, ...] = ()
    candidates: tuple[ArticleCandidate, ...] = ()


class CollectionResult(FrozenModel):
    policy_version: str
    collected_at: datetime
    fetch_results: tuple[FetchResult, ...]
    candidates: tuple[ArticleCandidate, ...]


class ClusterBreakdown(FrozenModel):
    lead_score: int
    source_diversity: int
    total: int


class RankedCluster(FrozenModel):
    cluster_id: str
    cluster_policy_version: str
    member_article_ids: tuple[str, ...]
    lead_article_id: str
    publisher_ids: tuple[str, ...]
    score: int
    signals: ClusterBreakdown


class RankedCollection(FrozenModel):
    ranking_policy_version: str
    cluster_policy_version: str
    generated_at: datetime
    articles: tuple[ArticleCandidate, ...]
    rejected_articles: tuple[ArticleCandidate, ...]
    clusters: tuple[RankedCluster, ...]
    fetch_results: tuple[FetchResult, ...] = ()
