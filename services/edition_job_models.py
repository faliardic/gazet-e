"""Public-safe request/status models and Q05 lifecycle rules."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

REQUEST_VERSION = "gazet-e.edition-request.v2"
LEGACY_REQUEST_VERSION = "gazet-e.edition-request.v1"
MAX_IDEMPOTENCY_KEY_LENGTH = 128
MAX_ATTEMPTS = 3


class JobState(StrEnum):
    REQUESTED = "requested"
    COLLECTING = "collecting"
    SELECTING = "selecting"
    SUMMARIZING = "summarizing"
    ILLUSTRATING = "illustrating"
    LAYING_OUT = "laying_out"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_STATES = (
    JobState.COLLECTING,
    JobState.SELECTING,
    JobState.ILLUSTRATING,
    JobState.LAYING_OUT,
)
TERMINAL_STATES = (JobState.READY, JobState.FAILED, JobState.CANCELLED)

NEXT_STATE = {
    JobState.REQUESTED: JobState.COLLECTING,
    JobState.COLLECTING: JobState.SELECTING,
    JobState.SELECTING: JobState.ILLUSTRATING,
    JobState.ILLUSTRATING: JobState.LAYING_OUT,
    JobState.LAYING_OUT: JobState.READY,
}


class InvalidTransition(ValueError):
    """Raised when a caller attempts to skip or reverse lifecycle truth."""


def validate_transition(
    current: JobState,
    target: JobState,
    *,
    system_retry: bool = False,
) -> None:
    if system_retry and current is JobState.FAILED and target is JobState.REQUESTED:
        return
    if current in TERMINAL_STATES:
        raise InvalidTransition(f"Terminal state {current.value} cannot transition.")
    if target in (JobState.FAILED, JobState.CANCELLED):
        return
    if NEXT_STATE.get(current) is not target:
        raise InvalidTransition(
            f"Invalid lifecycle transition {current.value} -> {target.value}."
        )


class EditionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_version: str = Field(pattern=r"^gazet-e\.edition-request\.v[12]$")
    locale: str = Field(min_length=2, max_length=32)
    timezone: str = Field(min_length=1, max_length=64)

    @field_validator("request_version")
    @classmethod
    def require_supported_version(cls, value: str) -> str:
        if value not in {LEGACY_REQUEST_VERSION, REQUEST_VERSION}:
            raise ValueError(f"unsupported request_version: {value}")
        return value

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z]{2}(?:-[A-Z]{2})?", value):
            raise ValueError("locale must use a language or language-REGION tag")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("timezone must be a known IANA timezone") from error
        return value

    def normalized_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def fingerprint(self) -> str:
        return hashlib.sha256(self.normalized_json().encode("utf-8")).hexdigest()


def normalize_idempotency_key(value: str | None) -> str:
    if value is None:
        raise ValueError("Idempotency-Key is required.")
    normalized = value.strip()
    if not normalized:
        raise ValueError("Idempotency-Key must not be empty.")
    if len(normalized) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise ValueError(
            f"Idempotency-Key must be at most {MAX_IDEMPOTENCY_KEY_LENGTH} characters."
        )
    if any(ord(character) < 33 or ord(character) > 126 for character in normalized):
        raise ValueError("Idempotency-Key must contain visible ASCII characters only.")
    return normalized


def idempotency_identity(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class CancellationStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    requested_at: datetime
    effective_at: datetime | None = None


class FailureStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    retryable: bool
    attempt: int
    diagnostic: str


class JobStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str
    state: JobState
    stage: JobState
    attempt: int
    created_at: datetime
    updated_at: datetime
    checkpoint_at: datetime | None = None
    cancellation: CancellationStatus | None = None
    failure: FailureStatus | None = None
    edition_id: str | None = None
