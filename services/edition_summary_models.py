"""Immutable contracts for the Q07 editorial-summary boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SummaryReasonCode = Literal[
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
]


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceFact(FrozenModel):
    article_id: str = Field(min_length=1, max_length=128)
    content_version: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    publisher_id: str = Field(min_length=1, max_length=128)
    source_name: str = Field(min_length=1, max_length=160)
    canonical_url: str = Field(min_length=1, max_length=2048)
    headline: str = Field(min_length=1, max_length=300)
    feed_excerpt: str = Field(max_length=600)
    published_at: datetime | None = None

    @field_validator("canonical_url")
    @classmethod
    def canonical_url_must_be_safe_https(cls, value: str) -> str:
        return _safe_https_url(value)

    @field_validator("published_at")
    @classmethod
    def publication_time_must_be_aware(cls, value: datetime | None) -> datetime | None:
        return _aware_datetime(value, "published_at")


class SummaryFactPacket(FrozenModel):
    cluster_id: str = Field(min_length=1, max_length=128)
    lead_article_id: str = Field(min_length=1, max_length=128)
    locale: str = Field(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
    fact_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    evidence: tuple[EvidenceFact, ...] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def validate_evidence_identity(self) -> SummaryFactPacket:
        article_ids = [fact.article_id for fact in self.evidence]
        if len(article_ids) != len(set(article_ids)):
            raise ValueError("duplicate evidence article_id")
        if self.lead_article_id not in article_ids:
            raise ValueError("lead article must be present in evidence")
        return self


class ReadingParagraph(FrozenModel):
    type: Literal["paragraph"]
    text: str = Field(min_length=1, max_length=600)

    @field_validator("text")
    @classmethod
    def paragraph_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("paragraph cannot be blank")
        return value.strip()


class SummaryDraft(FrozenModel):
    dek: str = Field(min_length=1, max_length=180)
    summary: str = Field(min_length=1, max_length=500)
    reading_body: tuple[ReadingParagraph, ...] = Field(min_length=1, max_length=4)
    evidence_article_ids: tuple[str, ...] = Field(min_length=1, max_length=4)
    evidence_source_ids: tuple[str, ...] = Field(min_length=1, max_length=4)

    @field_validator("dek", "summary")
    @classmethod
    def editorial_text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("editorial text cannot be blank")
        return value.strip()

    @model_validator(mode="after")
    def validate_unique_references(self) -> SummaryDraft:
        if len(self.evidence_article_ids) != len(set(self.evidence_article_ids)):
            raise ValueError("duplicate evidence article reference")
        if len(self.evidence_source_ids) != len(set(self.evidence_source_ids)):
            raise ValueError("duplicate evidence source reference")
        return self


class VerificationVerdict(FrozenModel):
    status: Literal["passed", "failed"]
    reason_codes: tuple[SummaryReasonCode, ...] = Field(max_length=6)

    @model_validator(mode="after")
    def validate_reason_contract(self) -> VerificationVerdict:
        if self.status == "passed" and self.reason_codes:
            raise ValueError("passed verification cannot carry reasons")
        if self.status == "failed" and not self.reason_codes:
            raise ValueError("failed verification requires a reason")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("duplicate verification reason")
        return self


class ProviderUsage(FrozenModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class ArtifactEvidence(FrozenModel):
    article_id: str
    content_version: str
    source_id: str
    publisher_id: str
    source_name: str
    canonical_url: str
    published_at: datetime | None = None

    @field_validator("canonical_url")
    @classmethod
    def canonical_url_must_be_safe_https(cls, value: str) -> str:
        return _safe_https_url(value)

    @field_validator("published_at")
    @classmethod
    def publication_time_must_be_aware(cls, value: datetime | None) -> datetime | None:
        return _aware_datetime(value, "published_at")


class SummaryArtifact(FrozenModel):
    cluster_id: str
    lead_article_id: str
    evidence_article_ids: tuple[str, ...]
    evidence_source_ids: tuple[str, ...]
    evidence: tuple[ArtifactEvidence, ...] = Field(min_length=1, max_length=4)
    locale: str = Field(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
    dek: str = Field(max_length=180)
    summary: str = Field(max_length=500)
    reading_body: tuple[ReadingParagraph, ...] = Field(max_length=4)
    prompt_version: str
    verifier_prompt_version: str
    editorial_policy_version: str
    provider: str
    requested_model: str
    response_model: str | None
    verifier_response_model: str | None
    generated_at: datetime
    summary_cache_key: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    verification_status: Literal["passed", "failed", "unavailable"]
    reason_codes: tuple[SummaryReasonCode, ...] = Field(max_length=6)
    status: Literal["ready", "unavailable"]
    provider_call_count: int = Field(ge=0, le=4)
    usage: ProviderUsage

    @field_validator("generated_at")
    @classmethod
    def generated_time_must_be_aware(cls, value: datetime) -> datetime:
        checked = _aware_datetime(value, "generated_at")
        assert checked is not None
        return checked

    @model_validator(mode="after")
    def validate_terminal_state(self) -> SummaryArtifact:
        evidence_article_ids = {item.article_id for item in self.evidence}
        evidence_source_ids = {item.source_id for item in self.evidence}
        if set(self.evidence_article_ids) != evidence_article_ids:
            raise ValueError("artifact evidence article metadata mismatch")
        if set(self.evidence_source_ids) != evidence_source_ids:
            raise ValueError("artifact evidence source metadata mismatch")
        if self.lead_article_id not in evidence_article_ids:
            raise ValueError("artifact evidence must include the lead article")
        if self.status == "ready":
            if self.verification_status != "passed" or self.reason_codes:
                raise ValueError("ready artifact must have passed verification")
            if not self.dek or not self.summary or not self.reading_body:
                raise ValueError("ready artifact requires editorial content")
        else:
            if self.verification_status == "passed":
                raise ValueError("unavailable artifact cannot be verified")
            if self.dek or self.summary or self.reading_body:
                raise ValueError("unavailable artifact cannot publish fallback content")
            if not self.reason_codes:
                raise ValueError("unavailable artifact requires a bounded reason")
        return self


def _safe_https_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        parsed.port
    except ValueError as error:
        raise ValueError("canonical_url must be a valid HTTPS URL") from error
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("canonical_url must be a safe HTTPS URL")
    return value


def _aware_datetime(value: datetime | None, field_name: str) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{field_name} must include timezone")
    return value
