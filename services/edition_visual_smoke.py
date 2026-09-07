"""Memory-only two-scenario live provider gate for Q08."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

from services.edition_summary_models import EvidenceFact, SummaryFactPacket
from services.edition_visual_brief import build_visual_brief
from services.edition_visual_pipeline import EditorialVisualPipeline
from services.edition_visual_provider import OpenAIVisualProvider

LIVE_MAX_CALLS = 4
LIVE_MAX_IMAGES = 2
LIVE_MAX_COST_USD = 0.15


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print(
            json.dumps(
                {"passed": False, "reason": "missing_openai_api_key", "status": "pending"},
                sort_keys=True,
            )
        )
        return 2
    provider = OpenAIVisualProvider()
    evidence: list[dict[str, object]] = []
    total_calls = 0
    total_images = 0
    total_cost = 0.0
    for scenario, packet, expected_mode in _scenarios():
        brief = build_visual_brief(packet)
        result = EditorialVisualPipeline(provider).create(brief)
        artifact = result.artifact
        total_calls += artifact.provider_call_count
        total_images += int(artifact.usage.generation_calls > 0)
        total_cost += artifact.usage.estimated_cost_usd
        evidence.append(
            {
                "asset_id": artifact.asset_id,
                "byte_count": len(result.image_bytes),
                "dimensions": (
                    [artifact.width, artifact.height]
                    if artifact.width is not None and artifact.height is not None
                    else None
                ),
                "estimated_cost_usd": artifact.usage.estimated_cost_usd,
                "generation_input_tokens": artifact.usage.generation_input_tokens,
                "generation_output_tokens": artifact.usage.generation_output_tokens,
                "provider_call_count": artifact.provider_call_count,
                "qa_input_tokens": artifact.usage.qa_input_tokens,
                "qa_model": artifact.qa_model,
                "qa_output_tokens": artifact.usage.qa_output_tokens,
                "reason_codes": list(artifact.reason_codes),
                "representation_mode": artifact.representation_mode,
                "requested_generation_model": artifact.requested_model,
                "safety_class": artifact.safety_class,
                "scenario": scenario,
                "status": artifact.status,
            }
        )
        if artifact.status != "ready" or artifact.representation_mode != expected_mode:
            break
    passed = (
        len(evidence) == 2
        and all(item["status"] == "ready" for item in evidence)
        and total_calls <= LIVE_MAX_CALLS
        and total_images <= LIVE_MAX_IMAGES
        and total_cost <= LIVE_MAX_COST_USD
    )
    print(
        json.dumps(
            {
                "estimated_cost_usd": round(total_cost, 8),
                "passed": passed,
                "provider_call_count": total_calls,
                "scenarios": evidence,
                "status": "ready" if passed else "unavailable",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if passed else 1


def _scenarios() -> tuple[tuple[str, SummaryFactPacket, str], ...]:
    return (
        (
            "non_sensitive",
            _packet(
                "culture",
                "Kent kütüphanesi hafta sonu okuma programını duyurdu",
                "Sentetik duyuru, çocuklar için okuma etkinliği planlandığını bildiriyor.",
            ),
            "editorial_illustrative",
        ),
        (
            "sensitive_real_event",
            _packet(
                "disaster",
                "Sentetik kıyı kentinde deprem tatbikatı sonrası afet planı görüşüldü",
                "Tamamen sentetik olay kaydı, deprem riskine ilişkin planlama toplantısını bildiriyor.",
            ),
            "editorial_conceptual",
        ),
    )


def _packet(suffix: str, headline: str, excerpt: str) -> SummaryFactPacket:
    fingerprint = "sha256:" + hashlib.sha256(
        f"gazet-e.q08.synthetic.{suffix}.v1".encode("utf-8")
    ).hexdigest()
    article_id = f"synthetic-article-{suffix}"
    return SummaryFactPacket(
        cluster_id=f"synthetic-cluster-{suffix}",
        lead_article_id=article_id,
        locale="tr-TR",
        fact_fingerprint=fingerprint,
        evidence=(
            EvidenceFact(
                article_id=article_id,
                content_version=f"synthetic-content-{suffix}-v1",
                source_id=f"synthetic-source-{suffix}",
                publisher_id=f"synthetic-publisher-{suffix}",
                source_name="Sentetik Q08 Kaynağı",
                canonical_url=f"https://example.org/synthetic-q08-{suffix}",
                headline=headline,
                feed_excerpt=excerpt,
                published_at=datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc),
            ),
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
