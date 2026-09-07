"""Bounded live OpenAI smoke for the Q07 provider gate."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

from services.edition_summary_models import EvidenceFact, SummaryFactPacket
from services.edition_summary_pipeline import (
    INPUT_USD_PER_MILLION,
    OUTPUT_USD_PER_MILLION,
    EditorialSummaryPipeline,
    ExecutionBudget,
)
from services.edition_summary_provider import OpenAIResponsesProvider

LIVE_SMOKE_BUDGET = ExecutionBudget(
    max_calls=2,
    max_input_tokens=4_000,
    max_output_tokens=900,
    max_cost_usd=0.03,
)


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print(
            json.dumps(
                {
                    "passed": False,
                    "status": "pending",
                    "reason": "missing_openai_api_key",
                },
                sort_keys=True,
            )
        )
        return 2

    pipeline = EditorialSummaryPipeline(
        OpenAIResponsesProvider(),
        budget=LIVE_SMOKE_BUDGET,
        max_repairs=0,
    )
    artifact = pipeline.summarize(_synthetic_packet())
    cost = (
        artifact.usage.input_tokens * INPUT_USD_PER_MILLION
        + artifact.usage.output_tokens * OUTPUT_USD_PER_MILLION
    ) / 1_000_000
    passed = artifact.status == "ready" and artifact.verification_status == "passed"
    print(
        json.dumps(
            {
                "estimated_cost_usd": round(cost, 8),
                "input_tokens": artifact.usage.input_tokens,
                "output_tokens": artifact.usage.output_tokens,
                "passed": passed,
                "provider": artifact.provider,
                "provider_call_count": artifact.provider_call_count,
                "requested_model": artifact.requested_model,
                "response_model": artifact.response_model,
                "status": artifact.status,
                "verification_status": artifact.verification_status,
                "verifier_response_model": artifact.verifier_response_model,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if passed else 1


def _synthetic_packet() -> SummaryFactPacket:
    fingerprint = "sha256:" + hashlib.sha256(
        b"gazet-e.q07.synthetic-smoke.v1"
    ).hexdigest()
    return SummaryFactPacket(
        cluster_id="synthetic-cluster-q07",
        lead_article_id="synthetic-article-q07",
        locale="tr-TR",
        fact_fingerprint=fingerprint,
        evidence=(
            EvidenceFact(
                article_id="synthetic-article-q07",
                content_version="synthetic-content-v1",
                source_id="synthetic-source-q07",
                publisher_id="synthetic-publisher-q07",
                source_name="Sentetik Q07 Kaynağı",
                canonical_url="https://example.org/synthetic-q07",
                headline="Kent kütüphanesi hafta sonu programını duyurdu",
                feed_excerpt=(
                    "Sentetik belediye bülteni, kütüphanenin hafta sonu açık "
                    "olacağını ve çocuklar için okuma etkinliği düzenleneceğini bildirdi."
                ),
                published_at=datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc),
            ),
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
