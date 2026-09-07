"""Source-grounded Q07 editorial-summary orchestration and cache."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Literal, TypeVar, cast

from services.edition_summary_facts import summary_cache_key
from services.edition_summary_models import (
    ArtifactEvidence,
    ProviderUsage,
    SummaryArtifact,
    SummaryDraft,
    SummaryFactPacket,
    SummaryReasonCode,
    VerificationVerdict,
)
from services.edition_summary_provider import (
    EDITORIAL_POLICY_VERSION,
    GENERATOR_PROMPT_VERSION,
    PROVIDER_ID,
    REQUESTED_MODEL,
    VERIFIER_PROMPT_VERSION,
    ProviderCallError,
    ProviderResponse,
    SummaryProvider,
)

INPUT_USD_PER_MILLION = 2.0
OUTPUT_USD_PER_MILLION = 12.0
_ALLOWED_REASONS = frozenset(
    (
        "budget_exceeded",
        "invented_date",
        "invented_entity",
        "invented_name",
        "invented_number",
        "invented_quote",
        "malformed_output",
        "oversized_output",
        "provider_error",
        "provider_timeout",
        "provider_truncated",
        "repair_failed",
        "unknown_source_reference",
        "unsupported_claim",
        "verification_failed",
    )
)


@dataclass(frozen=True)
class ExecutionBudget:
    max_calls: int = 4
    max_input_tokens: int = 8_000
    max_output_tokens: int = 1_800
    max_cost_usd: float = 0.04


@dataclass
class _UsageLedger:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def estimated_cost_usd(self) -> float:
        return (
            self.input_tokens * INPUT_USD_PER_MILLION
            + self.output_tokens * OUTPUT_USD_PER_MILLION
        ) / 1_000_000


class _BudgetExceeded(RuntimeError):
    pass


class SummaryArtifactCache:
    """Small exact-key cache boundary; only verified artifacts may enter."""

    def __init__(self) -> None:
        self._items: dict[str, SummaryArtifact] = {}
        self._lock = Lock()

    def get(self, key: str) -> SummaryArtifact | None:
        with self._lock:
            return self._items.get(key)

    def put(self, artifact: SummaryArtifact) -> None:
        if artifact.status != "ready" or artifact.verification_status != "passed":
            raise ValueError("only verified ready artifacts may be cached")
        with self._lock:
            self._items[artifact.summary_cache_key] = artifact

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


ResponseT = TypeVar("ResponseT", SummaryDraft, VerificationVerdict)


class EditorialSummaryPipeline:
    def __init__(
        self,
        provider: SummaryProvider,
        *,
        cache: SummaryArtifactCache | None = None,
        clock: Callable[[], datetime] | None = None,
        budget: ExecutionBudget = ExecutionBudget(),
        max_repairs: int = 1,
    ) -> None:
        if max_repairs not in {0, 1}:
            raise ValueError("max_repairs must be zero or one")
        self._provider = provider
        self._cache = cache if cache is not None else SummaryArtifactCache()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._budget = budget
        self._max_repairs = max_repairs

    def summarize(self, packet: SummaryFactPacket) -> SummaryArtifact:
        cache_key = summary_cache_key(
            packet,
            prompt_version=GENERATOR_PROMPT_VERSION,
            verifier_prompt_version=VERIFIER_PROMPT_VERSION,
            editorial_policy_version=EDITORIAL_POLICY_VERSION,
            provider=PROVIDER_ID,
            model=REQUESTED_MODEL,
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        ledger = _UsageLedger()
        response_model: str | None = None
        verifier_response_model: str | None = None
        try:
            generation = self._invoke(
                ledger,
                lambda: self._provider.generate(packet),
            )
            response_model = generation.response_model
            draft = generation.payload
            local_reason = _validate_draft_references(packet, draft)
            if local_reason is not None:
                return self._unavailable(
                    packet,
                    cache_key,
                    ledger,
                    (local_reason,),
                    response_model=response_model,
                    verifier_response_model=None,
                    verification_status="failed",
                )

            verification = self._invoke(
                ledger,
                lambda: self._provider.verify(packet, draft),
            )
            verifier_response_model = verification.response_model
            if verification.payload.status == "passed":
                artifact = self._ready(
                    packet,
                    draft,
                    cache_key,
                    ledger,
                    response_model,
                    verifier_response_model,
                )
                self._cache.put(artifact)
                return artifact

            if self._max_repairs == 0:
                return self._unavailable(
                    packet,
                    cache_key,
                    ledger,
                    (*verification.payload.reason_codes, "verification_failed"),
                    response_model=response_model,
                    verifier_response_model=verifier_response_model,
                    verification_status="failed",
                )

            repair = self._invoke(
                ledger,
                lambda: self._provider.generate(
                    packet,
                    prior_draft=draft,
                    reason_codes=verification.payload.reason_codes,
                ),
            )
            response_model = repair.response_model
            repaired_draft = repair.payload
            local_reason = _validate_draft_references(packet, repaired_draft)
            if local_reason is not None:
                return self._unavailable(
                    packet,
                    cache_key,
                    ledger,
                    (local_reason, "repair_failed"),
                    response_model=response_model,
                    verifier_response_model=verifier_response_model,
                    verification_status="failed",
                )

            final_verification = self._invoke(
                ledger,
                lambda: self._provider.verify(packet, repaired_draft),
            )
            verifier_response_model = final_verification.response_model
            if final_verification.payload.status == "passed":
                artifact = self._ready(
                    packet,
                    repaired_draft,
                    cache_key,
                    ledger,
                    response_model,
                    verifier_response_model,
                )
                self._cache.put(artifact)
                return artifact
            return self._unavailable(
                packet,
                cache_key,
                ledger,
                (*final_verification.payload.reason_codes, "repair_failed"),
                response_model=response_model,
                verifier_response_model=verifier_response_model,
                verification_status="failed",
            )
        except _BudgetExceeded:
            reason = "budget_exceeded"
        except ProviderCallError as error:
            reason = error.reason_code
        except Exception:
            reason = "provider_error"
        return self._unavailable(
            packet,
            cache_key,
            ledger,
            (reason,),
            response_model=response_model,
            verifier_response_model=verifier_response_model,
            verification_status="unavailable",
        )

    def _invoke(
        self,
        ledger: _UsageLedger,
        call: Callable[[], ProviderResponse[ResponseT]],
    ) -> ProviderResponse[ResponseT]:
        if ledger.calls >= self._budget.max_calls:
            raise _BudgetExceeded
        ledger.calls += 1
        response = call()
        ledger.input_tokens += response.usage.input_tokens
        ledger.output_tokens += response.usage.output_tokens
        if (
            ledger.input_tokens > self._budget.max_input_tokens
            or ledger.output_tokens > self._budget.max_output_tokens
            or ledger.estimated_cost_usd > self._budget.max_cost_usd
        ):
            raise _BudgetExceeded
        return response

    def _ready(
        self,
        packet: SummaryFactPacket,
        draft: SummaryDraft,
        cache_key: str,
        ledger: _UsageLedger,
        response_model: str,
        verifier_response_model: str,
    ) -> SummaryArtifact:
        return SummaryArtifact(
            cluster_id=packet.cluster_id,
            lead_article_id=packet.lead_article_id,
            evidence_article_ids=draft.evidence_article_ids,
            evidence_source_ids=draft.evidence_source_ids,
            evidence=_artifact_evidence(
                packet,
                article_ids=set(draft.evidence_article_ids),
                source_ids=set(draft.evidence_source_ids),
            ),
            locale=packet.locale,
            dek=draft.dek,
            summary=draft.summary,
            reading_body=draft.reading_body,
            prompt_version=GENERATOR_PROMPT_VERSION,
            verifier_prompt_version=VERIFIER_PROMPT_VERSION,
            editorial_policy_version=EDITORIAL_POLICY_VERSION,
            provider=PROVIDER_ID,
            requested_model=REQUESTED_MODEL,
            response_model=response_model,
            verifier_response_model=verifier_response_model,
            generated_at=_as_utc(self._clock()),
            summary_cache_key=cache_key,
            verification_status="passed",
            reason_codes=(),
            status="ready",
            provider_call_count=ledger.calls,
            usage=_usage(ledger),
        )

    def _unavailable(
        self,
        packet: SummaryFactPacket,
        cache_key: str,
        ledger: _UsageLedger,
        reason_codes: tuple[str, ...],
        *,
        response_model: str | None,
        verifier_response_model: str | None,
        verification_status: Literal["failed", "unavailable"],
    ) -> SummaryArtifact:
        return SummaryArtifact(
            cluster_id=packet.cluster_id,
            lead_article_id=packet.lead_article_id,
            evidence_article_ids=tuple(
                fact.article_id for fact in packet.evidence
            ),
            evidence_source_ids=tuple(
                sorted({fact.source_id for fact in packet.evidence})
            ),
            evidence=_artifact_evidence(packet),
            locale=packet.locale,
            dek="",
            summary="",
            reading_body=(),
            prompt_version=GENERATOR_PROMPT_VERSION,
            verifier_prompt_version=VERIFIER_PROMPT_VERSION,
            editorial_policy_version=EDITORIAL_POLICY_VERSION,
            provider=PROVIDER_ID,
            requested_model=REQUESTED_MODEL,
            response_model=response_model,
            verifier_response_model=verifier_response_model,
            generated_at=_as_utc(self._clock()),
            summary_cache_key=cache_key,
            verification_status=verification_status,
            reason_codes=_bounded_reasons(reason_codes),
            status="unavailable",
            provider_call_count=ledger.calls,
            usage=_usage(ledger),
        )


def _validate_draft_references(
    packet: SummaryFactPacket,
    draft: SummaryDraft,
) -> SummaryReasonCode | None:
    article_ids = {fact.article_id for fact in packet.evidence}
    source_ids = {fact.source_id for fact in packet.evidence}
    referenced_articles = set(draft.evidence_article_ids)
    referenced_sources = set(draft.evidence_source_ids)
    sources_for_referenced_articles = {
        fact.source_id
        for fact in packet.evidence
        if fact.article_id in referenced_articles
    }
    if (
        packet.lead_article_id not in draft.evidence_article_ids
        or not referenced_articles.issubset(article_ids)
        or not referenced_sources.issubset(source_ids)
        or referenced_sources != sources_for_referenced_articles
    ):
        return "unknown_source_reference"
    return None


def _bounded_reasons(reason_codes: tuple[str, ...]) -> tuple[SummaryReasonCode, ...]:
    bounded: list[SummaryReasonCode] = []
    for reason in reason_codes:
        normalized = reason if reason in _ALLOWED_REASONS else "provider_error"
        typed = cast(SummaryReasonCode, normalized)
        if typed not in bounded:
            bounded.append(typed)
        if len(bounded) == 6:
            break
    return tuple(bounded or ["provider_error"])


def _usage(ledger: _UsageLedger) -> ProviderUsage:
    return ProviderUsage(
        input_tokens=ledger.input_tokens,
        output_tokens=ledger.output_tokens,
    )


def _artifact_evidence(
    packet: SummaryFactPacket,
    *,
    article_ids: set[str] | None = None,
    source_ids: set[str] | None = None,
) -> tuple[ArtifactEvidence, ...]:
    return tuple(
        ArtifactEvidence(
            article_id=fact.article_id,
            content_version=fact.content_version,
            source_id=fact.source_id,
            publisher_id=fact.publisher_id,
            source_name=fact.source_name,
            canonical_url=fact.canonical_url,
            published_at=fact.published_at,
        )
        for fact in packet.evidence
        if (article_ids is None or fact.article_id in article_ids)
        and (source_ids is None or fact.source_id in source_ids)
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
