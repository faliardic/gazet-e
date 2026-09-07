"""Cache-first Q08 generation, local validation, and semantic QA pipeline."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from threading import Lock
from typing import cast

from PIL import Image, UnidentifiedImageError

from services.edition_visual_brief import image_cache_key
from services.edition_visual_models import (
    VisualArtifact,
    VisualBrief,
    VisualReasonCode,
    VisualResult,
    VisualUsage,
)
from services.edition_visual_provider import (
    MAX_DECODED_BYTES,
    PROVIDER_ID,
    QA_MODEL,
    REQUESTED_IMAGE_MODEL,
    GeneratedImageResponse,
    ProviderCallError,
    VisualProvider,
)

IMAGE_ESTIMATED_COST_USD = 0.041
QA_INPUT_USD_PER_MILLION = 2.0
QA_OUTPUT_USD_PER_MILLION = 12.0
TRANSPARENCY_LABEL = "AI-generated editorial image"

_ALLOWED_REASONS = frozenset(
    (
        "budget_exceeded",
        "generation_blocked",
        "image_too_large",
        "invalid_dimensions",
        "invalid_media_type",
        "malformed_image",
        "prompt_too_long",
        "provider_access_unavailable",
        "provider_authentication_error",
        "provider_error",
        "provider_timeout",
        "qa_failed",
        "summary_identity_mismatch",
        "unsafe_brief",
        "documentary_risk",
        "unsupported_visual_detail",
        "identifiable_real_person",
        "embedded_text_or_logo",
        "sensitive_representation_violation",
        "style_mismatch",
    )
)


@dataclass(frozen=True)
class ExecutionBudget:
    max_calls: int = 2
    max_images: int = 1
    max_cost_usd: float = 0.08


@dataclass
class _UsageLedger:
    generation_calls: int = 0
    qa_calls: int = 0
    generation_input_tokens: int | None = None
    generation_output_tokens: int | None = None
    qa_input_tokens: int = 0
    qa_output_tokens: int = 0
    image_cost_usd: float = 0.0

    @property
    def calls(self) -> int:
        return self.generation_calls + self.qa_calls

    @property
    def estimated_cost_usd(self) -> float:
        return self.image_cost_usd + (
            self.qa_input_tokens * QA_INPUT_USD_PER_MILLION
            + self.qa_output_tokens * QA_OUTPUT_USD_PER_MILLION
        ) / 1_000_000


class VisualArtifactCache:
    def __init__(self) -> None:
        self._items: dict[str, VisualResult] = {}
        self._lock = Lock()

    def get(self, key: str) -> VisualResult | None:
        with self._lock:
            return self._items.get(key)

    def put(self, result: VisualResult) -> None:
        if result.artifact.status != "ready":
            raise ValueError("only ready visuals may be success-cached")
        with self._lock:
            self._items[result.artifact.image_cache_key] = result

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


class EditorialVisualPipeline:
    def __init__(
        self,
        provider: VisualProvider,
        *,
        cache: VisualArtifactCache | None = None,
        clock: Callable[[], datetime] | None = None,
        budget: ExecutionBudget = ExecutionBudget(),
    ) -> None:
        self._provider = provider
        self._cache = cache if cache is not None else VisualArtifactCache()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._budget = budget

    def create(self, brief: VisualBrief) -> VisualResult:
        cache_key = image_cache_key(
            brief, provider=PROVIDER_ID, model=REQUESTED_IMAGE_MODEL
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        ledger = _UsageLedger()
        response_model: str | None = None
        qa_response_model: str | None = None
        try:
            if self._budget.max_images < 1 or self._budget.max_calls < 1:
                raise _BudgetExceeded
            if IMAGE_ESTIMATED_COST_USD > self._budget.max_cost_usd:
                raise _BudgetExceeded
            ledger.generation_calls = 1
            generation = self._provider.generate(brief)
            ledger.image_cost_usd = IMAGE_ESTIMATED_COST_USD
            ledger.generation_input_tokens = generation.usage.input_tokens
            ledger.generation_output_tokens = generation.usage.output_tokens
            response_model = generation.response_model
            asset_id = _validate_image(generation)
            if ledger.calls >= self._budget.max_calls:
                raise _BudgetExceeded
            ledger.qa_calls = 1
            qa = self._provider.verify(brief, generation.image_bytes)
            ledger.qa_input_tokens = qa.input_tokens
            ledger.qa_output_tokens = qa.output_tokens
            qa_response_model = qa.response_model
            if ledger.estimated_cost_usd > self._budget.max_cost_usd:
                raise _BudgetExceeded
            if qa.verdict.status != "passed":
                return self._unavailable(
                    brief,
                    cache_key,
                    ledger,
                    (*qa.verdict.reason_codes, "qa_failed"),
                    response_model=response_model,
                    qa_response_model=qa_response_model,
                    qa_status="failed",
                )
            artifact = self._artifact(
                brief,
                cache_key,
                ledger,
                status="ready",
                reasons=(),
                response_model=response_model,
                qa_response_model=qa_response_model,
                qa_status="passed",
                asset_id=asset_id,
            )
            result = VisualResult(artifact=artifact, image_bytes=generation.image_bytes)
            self._cache.put(result)
            return result
        except _ImageValidationError as error:
            reason = error.reason_code
            qa_status = "not_run"
        except _BudgetExceeded:
            reason = "budget_exceeded"
            qa_status = "not_run" if ledger.qa_calls == 0 else "unavailable"
        except ProviderCallError as error:
            reason = error.reason_code
            qa_status = "not_run" if ledger.qa_calls == 0 else "unavailable"
        except Exception:
            reason = "provider_error"
            qa_status = "not_run" if ledger.qa_calls == 0 else "unavailable"
        return self._unavailable(
            brief,
            cache_key,
            ledger,
            (reason,),
            response_model=response_model,
            qa_response_model=qa_response_model,
            qa_status=qa_status,
        )

    def _unavailable(
        self,
        brief: VisualBrief,
        cache_key: str,
        ledger: _UsageLedger,
        reasons: tuple[str, ...],
        *,
        response_model: str | None,
        qa_response_model: str | None,
        qa_status: str,
    ) -> VisualResult:
        return VisualResult(
            artifact=self._artifact(
                brief,
                cache_key,
                ledger,
                status="unavailable",
                reasons=_bounded_reasons(reasons),
                response_model=response_model,
                qa_response_model=qa_response_model,
                qa_status=qa_status,
                asset_id=None,
            ),
            image_bytes=b"",
        )

    def _artifact(
        self,
        brief: VisualBrief,
        cache_key: str,
        ledger: _UsageLedger,
        *,
        status: str,
        reasons: tuple[VisualReasonCode, ...],
        response_model: str | None,
        qa_response_model: str | None,
        qa_status: str,
        asset_id: str | None,
    ) -> VisualArtifact:
        ready = status == "ready"
        return VisualArtifact.model_validate(
            {
                "cluster_id": brief.cluster_id,
                "lead_article_id": brief.lead_article_id,
                "evidence_article_ids": brief.evidence_article_ids,
                "fact_fingerprint": brief.fact_fingerprint,
                "locale": brief.locale,
                "asset_id": asset_id,
                "content_hash": asset_id,
                "width": brief.target_width if ready else None,
                "height": brief.target_height if ready else None,
                "media_type": "image/webp" if ready else None,
                "alt": brief.alt_text if ready else "",
                "transparency_label": TRANSPARENCY_LABEL,
                "generated_by_ai": True,
                "provider": PROVIDER_ID,
                "requested_model": REQUESTED_IMAGE_MODEL,
                "response_model": response_model,
                "generated_at": _as_utc(self._clock()),
                "brief_version": brief.brief_version,
                "prompt_version": brief.prompt_version,
                "style_version": brief.style_version,
                "safety_version": brief.safety_version,
                "representation_mode": brief.representation_mode,
                "safety_class": brief.safety_class,
                "safety_categories": brief.safety_categories,
                "visual_brief_key": brief.visual_brief_key,
                "image_cache_key": cache_key,
                "qa_model": QA_MODEL,
                "qa_response_model": qa_response_model,
                "qa_status": qa_status,
                "reason_codes": reasons,
                "status": status,
                "provider_call_count": ledger.calls,
                "usage": _usage(ledger),
            }
        )


class _BudgetExceeded(RuntimeError):
    pass


class _ImageValidationError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def _validate_image(generation: GeneratedImageResponse) -> str:
    image_bytes = generation.image_bytes
    if len(image_bytes) > MAX_DECODED_BYTES:
        raise _ImageValidationError("image_too_large")
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            if image.format != "WEBP":
                raise _ImageValidationError("invalid_media_type")
            if image.size != (1536, 1024):
                raise _ImageValidationError("invalid_dimensions")
            image.load()
    except _ImageValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise _ImageValidationError("malformed_image") from None
    return "sha256:" + hashlib.sha256(image_bytes).hexdigest()


def _bounded_reasons(reasons: tuple[str, ...]) -> tuple[VisualReasonCode, ...]:
    result: list[VisualReasonCode] = []
    for reason in reasons:
        normalized = reason if reason in _ALLOWED_REASONS else "provider_error"
        typed = cast(VisualReasonCode, normalized)
        if typed not in result:
            result.append(typed)
        if len(result) == 8:
            break
    return tuple(result or ["provider_error"])


def _usage(ledger: _UsageLedger) -> VisualUsage:
    return VisualUsage(
        generation_calls=ledger.generation_calls,
        qa_calls=ledger.qa_calls,
        generation_input_tokens=ledger.generation_input_tokens,
        generation_output_tokens=ledger.generation_output_tokens,
        qa_input_tokens=ledger.qa_input_tokens,
        qa_output_tokens=ledger.qa_output_tokens,
        estimated_cost_usd=round(ledger.estimated_cost_usd, 8),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
