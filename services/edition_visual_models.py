"""Immutable contracts for the Q08 editorial-visual boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RepresentationMode = Literal["editorial_illustrative", "editorial_conceptual"]
SafetyClass = Literal["ordinary", "sensitive_real_event", "named_real_person"]
SafetyCategory = Literal[
    "war_conflict",
    "disaster",
    "accident",
    "crime_violence",
    "political_event",
    "death_injury",
    "named_real_person",
]
QAReasonCode = Literal[
    "documentary_risk",
    "unsupported_visual_detail",
    "identifiable_real_person",
    "embedded_text_or_logo",
    "sensitive_representation_violation",
    "style_mismatch",
    "malformed_image",
]
VisualReasonCode = Literal[
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
]


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VisualBrief(FrozenModel):
    cluster_id: str = Field(min_length=1, max_length=128)
    lead_article_id: str = Field(min_length=1, max_length=128)
    evidence_article_ids: tuple[str, ...] = Field(min_length=1, max_length=4)
    fact_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    locale: str = Field(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
    representation_mode: RepresentationMode
    safety_class: SafetyClass
    safety_categories: tuple[SafetyCategory, ...] = Field(max_length=7)
    supported_subject_cues: tuple[str, ...] = Field(min_length=1, max_length=4)
    supported_context_cues: tuple[str, ...] = Field(max_length=4)
    forbidden_details: tuple[str, ...] = Field(min_length=1, max_length=16)
    composition_intent: str = Field(min_length=1, max_length=500)
    target_width: Literal[1536]
    target_height: Literal[1024]
    alt_text: str = Field(min_length=1, max_length=500)
    brief_version: str
    style_version: str
    safety_version: str
    prompt_version: str
    visual_brief_key: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @field_validator(
        "supported_subject_cues",
        "supported_context_cues",
        "forbidden_details",
    )
    @classmethod
    def strings_must_be_bounded_and_non_blank(
        cls, value: tuple[str, ...]
    ) -> tuple[str, ...]:
        cleaned = tuple(item.strip() for item in value)
        if any(not item or len(item) > 600 for item in cleaned):
            raise ValueError("visual brief strings must be non-blank and bounded")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("visual brief strings must be unique")
        return cleaned

    @model_validator(mode="after")
    def validate_safety_mode(self) -> VisualBrief:
        if len(self.evidence_article_ids) != len(set(self.evidence_article_ids)):
            raise ValueError("duplicate evidence article identity")
        if self.lead_article_id not in self.evidence_article_ids:
            raise ValueError("lead article must be present in evidence")
        if len(self.safety_categories) != len(set(self.safety_categories)):
            raise ValueError("duplicate safety category")
        sensitive = self.safety_class != "ordinary"
        if sensitive and self.representation_mode != "editorial_conceptual":
            raise ValueError("sensitive visual must be conceptual")
        if self.safety_class == "ordinary" and self.safety_categories:
            raise ValueError("ordinary brief cannot carry sensitive categories")
        return self


class VisualQAVerdict(FrozenModel):
    status: Literal["passed", "failed"]
    reason_codes: tuple[QAReasonCode, ...] = Field(max_length=7)

    @model_validator(mode="after")
    def validate_reason_contract(self) -> VisualQAVerdict:
        if self.status == "passed" and self.reason_codes:
            raise ValueError("passed QA cannot carry reasons")
        if self.status == "failed" and not self.reason_codes:
            raise ValueError("failed QA requires a reason")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("duplicate QA reason")
        return self


class VisualUsage(FrozenModel):
    generation_calls: int = Field(ge=0, le=1)
    qa_calls: int = Field(ge=0, le=1)
    generation_input_tokens: int | None = Field(default=None, ge=0)
    generation_output_tokens: int | None = Field(default=None, ge=0)
    qa_input_tokens: int = Field(ge=0)
    qa_output_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)


class VisualArtifact(FrozenModel):
    cluster_id: str
    lead_article_id: str
    evidence_article_ids: tuple[str, ...]
    fact_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    locale: str = Field(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
    asset_id: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    content_hash: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    media_type: Literal["image/webp"] | None = None
    alt: str = Field(max_length=500)
    transparency_label: Literal["AI-generated editorial image"]
    generated_by_ai: Literal[True]
    provider: Literal["openai"]
    requested_model: str
    response_model: str | None
    generated_at: datetime
    brief_version: str
    prompt_version: str
    style_version: str
    safety_version: str
    representation_mode: RepresentationMode
    safety_class: SafetyClass
    safety_categories: tuple[SafetyCategory, ...]
    visual_brief_key: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    image_cache_key: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    qa_model: str
    qa_response_model: str | None
    qa_status: Literal["passed", "failed", "unavailable", "not_run"]
    reason_codes: tuple[VisualReasonCode, ...] = Field(max_length=8)
    status: Literal["ready", "unavailable"]
    provider_call_count: int = Field(ge=0, le=2)
    usage: VisualUsage

    @field_validator("generated_at")
    @classmethod
    def generated_time_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must include timezone")
        return value

    @model_validator(mode="after")
    def validate_terminal_state(self) -> VisualArtifact:
        asset_fields = (
            self.asset_id,
            self.content_hash,
            self.width,
            self.height,
            self.media_type,
        )
        if self.status == "ready":
            if self.qa_status != "passed" or self.reason_codes:
                raise ValueError("ready visual requires passed QA")
            if any(value is None for value in asset_fields) or not self.alt:
                raise ValueError("ready visual requires complete asset metadata")
            if self.asset_id != self.content_hash:
                raise ValueError("asset identity must equal exact content hash")
        else:
            if not self.reason_codes or self.qa_status == "passed":
                raise ValueError("unavailable visual requires bounded failure")
        return self


@dataclass(frozen=True)
class VisualResult:
    artifact: VisualArtifact
    image_bytes: bytes

    def __post_init__(self) -> None:
        if self.artifact.status == "ready" and not self.image_bytes:
            raise ValueError("ready visual result requires image bytes")
        if self.artifact.status == "unavailable" and self.image_bytes:
            raise ValueError("unavailable visual result cannot expose image bytes")
