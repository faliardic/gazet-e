"""Deterministic Q06-to-Q07 source-fact packet and cache identities."""

from __future__ import annotations

import hashlib
import json

from services.edition_news_models import ArticleCandidate, RankedCollection
from services.edition_summary_models import EvidenceFact, SummaryFactPacket

MAX_EVIDENCE_ARTICLES = 4
MAX_EVIDENCE_EXCERPT_CHARS = 600


class FactPacketError(ValueError):
    """Safe, bounded fact-packet construction failure."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def build_fact_packet(
    collection: RankedCollection,
    cluster_id: str,
    *,
    locale: str = "tr-TR",
) -> SummaryFactPacket:
    matching_clusters = tuple(
        item for item in collection.clusters if item.cluster_id == cluster_id
    )
    if not matching_clusters:
        raise FactPacketError("unknown_cluster_reference")
    if len(matching_clusters) != 1:
        raise FactPacketError("duplicate_cluster_reference")
    cluster = matching_clusters[0]
    if len(collection.articles) != len(
        {article.article_id for article in collection.articles}
    ):
        raise FactPacketError("duplicate_article_reference")
    if len(cluster.member_article_ids) != len(set(cluster.member_article_ids)):
        raise FactPacketError("duplicate_cluster_member")
    articles_by_id = {article.article_id: article for article in collection.articles}
    try:
        members = tuple(articles_by_id[item] for item in cluster.member_article_ids)
    except KeyError as error:
        raise FactPacketError("unknown_article_reference") from error
    if cluster.lead_article_id not in cluster.member_article_ids:
        raise FactPacketError("unknown_lead_reference")

    fingerprint = _cluster_fingerprint(cluster.cluster_id, members)
    evidence_order = (
        articles_by_id[cluster.lead_article_id],
        *sorted(
            (
                article
                for article in members
                if article.article_id != cluster.lead_article_id
            ),
            key=lambda article: article.article_id,
        ),
    )[:MAX_EVIDENCE_ARTICLES]
    evidence = tuple(_evidence_fact(article) for article in evidence_order)
    return SummaryFactPacket(
        cluster_id=cluster.cluster_id,
        lead_article_id=cluster.lead_article_id,
        locale=locale,
        fact_fingerprint=fingerprint,
        evidence=evidence,
    )


def summary_cache_key(
    packet: SummaryFactPacket,
    *,
    prompt_version: str,
    verifier_prompt_version: str,
    editorial_policy_version: str,
    provider: str,
    model: str,
) -> str:
    payload = {
        "cluster_id": packet.cluster_id,
        "editorial_policy_version": editorial_policy_version,
        "fact_fingerprint": packet.fact_fingerprint,
        "locale": packet.locale,
        "model": model,
        "prompt_version": prompt_version,
        "provider": provider,
        "verifier_prompt_version": verifier_prompt_version,
    }
    return _sha256_json(payload)


def _evidence_fact(article: ArticleCandidate) -> EvidenceFact:
    return EvidenceFact(
        article_id=article.article_id,
        content_version=article.content_version,
        source_id=article.attribution.source_id,
        publisher_id=article.attribution.publisher_id,
        source_name=article.attribution.display_name,
        canonical_url=article.canonical_url,
        headline=article.headline,
        feed_excerpt=article.feed_excerpt[:MAX_EVIDENCE_EXCERPT_CHARS],
        published_at=article.published_at,
    )


def _cluster_fingerprint(
    cluster_id: str,
    members: tuple[ArticleCandidate, ...],
) -> str:
    payload = {
        "cluster_id": cluster_id,
        "members": sorted(
            (
                {
                    "article_id": article.article_id,
                    "content_version": article.content_version,
                }
                for article in members
            ),
            key=lambda item: (item["article_id"], item["content_version"]),
        ),
    }
    return _sha256_json(payload)


def _sha256_json(payload: object) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
