"""Direct-psycopg durable store for Q05 edition jobs."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from services.edition_job_models import (
    ACTIVE_STATES,
    MAX_ATTEMPTS,
    CancellationStatus,
    EditionRequest,
    FailureStatus,
    JobState,
    JobStatus,
    idempotency_identity,
    normalize_idempotency_key,
    validate_transition,
)
from services.edition_job_validation import (
    CanonicalEditionValidator,
    ValidatedEdition,
)


class JobNotFound(LookupError):
    pass


class IdempotencyConflict(ValueError):
    pass


class LeaseConflict(RuntimeError):
    pass


class EditionImmutableConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    state: JobState
    stage: JobState
    attempt: int
    created_at: datetime
    updated_at: datetime
    checkpoint_at: datetime | None
    lease_owner: str | None
    lease_expires_at: datetime | None
    heartbeat_at: datetime | None
    cancellation_requested_at: datetime | None
    cancellation_effective_at: datetime | None
    failure_code: str | None
    failure_retryable: bool | None
    failure_attempt: int | None
    failure_diagnostic: str | None
    edition_id: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> JobRecord:
        return cls(
            job_id=row["job_id"],
            state=JobState(row["state"]),
            stage=JobState(row["stage"]),
            attempt=row["attempt"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            checkpoint_at=row["checkpoint_at"],
            lease_owner=row["lease_owner"],
            lease_expires_at=row["lease_expires_at"],
            heartbeat_at=row["heartbeat_at"],
            cancellation_requested_at=row["cancellation_requested_at"],
            cancellation_effective_at=row["cancellation_effective_at"],
            failure_code=row["failure_code"],
            failure_retryable=row["failure_retryable"],
            failure_attempt=row["failure_attempt"],
            failure_diagnostic=row["failure_diagnostic"],
            edition_id=row["edition_id"],
        )

    def to_status(self) -> JobStatus:
        cancellation = None
        if self.cancellation_requested_at is not None:
            cancellation = CancellationStatus(
                requested_at=self.cancellation_requested_at,
                effective_at=self.cancellation_effective_at,
            )
        failure = None
        if self.state is JobState.FAILED:
            failure = FailureStatus(
                code=self.failure_code or "internal_stage_error",
                retryable=bool(self.failure_retryable),
                attempt=self.failure_attempt or self.attempt,
                diagnostic=self.failure_diagnostic or "Stage failed safely.",
            )
        return JobStatus(
            job_id=self.job_id,
            state=self.state,
            stage=self.stage,
            attempt=self.attempt,
            created_at=self.created_at,
            updated_at=self.updated_at,
            checkpoint_at=self.checkpoint_at,
            cancellation=cancellation,
            failure=failure,
            edition_id=self.edition_id if self.state is JobState.READY else None,
        )


class EditionJobStore:
    def __init__(self, dsn: str) -> None:
        if not dsn:
            raise ValueError("A PostgreSQL DSN is required.")
        self._dsn = dsn

    def _connect(self) -> psycopg.Connection[dict[str, Any]]:
        return psycopg.connect(self._dsn, row_factory=dict_row)

    def initialize_schema(self) -> None:
        states = ", ".join(f"'{state.value}'" for state in JobState)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS editions (
                    edition_id TEXT PRIMARY KEY,
                    contract_version TEXT NOT NULL,
                    document JSONB NOT NULL,
                    document_hash CHAR(64) NOT NULL,
                    published_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
                )
                """
            )
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS edition_jobs (
                    job_id TEXT PRIMARY KEY,
                    idempotency_hash CHAR(64) NOT NULL UNIQUE,
                    request_fingerprint CHAR(64) NOT NULL,
                    request_body JSONB NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ({states})),
                    stage TEXT NOT NULL CHECK (stage IN ({states})),
                    attempt INTEGER NOT NULL DEFAULT 0 CHECK (attempt >= 0),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                    checkpoint_at TIMESTAMPTZ,
                    lease_owner TEXT,
                    lease_expires_at TIMESTAMPTZ,
                    heartbeat_at TIMESTAMPTZ,
                    cancellation_requested_at TIMESTAMPTZ,
                    cancellation_effective_at TIMESTAMPTZ,
                    cancellation_actor TEXT,
                    cancellation_reason TEXT,
                    failure_code TEXT,
                    failure_retryable BOOLEAN,
                    failure_attempt INTEGER,
                    failure_diagnostic TEXT,
                    edition_id TEXT REFERENCES editions(edition_id)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS edition_jobs_runnable_idx
                ON edition_jobs (created_at, job_id)
                WHERE state IN (
                    'requested', 'collecting', 'selecting', 'summarizing',
                    'illustrating', 'laying_out'
                )
                """
            )

    def create_job(self, idempotency_key: str | None, request: EditionRequest) -> JobRecord:
        normalized_key = normalize_idempotency_key(idempotency_key)
        key_hash = idempotency_identity(normalized_key)
        request_fingerprint = request.fingerprint()
        job_id = str(uuid.uuid4())
        with self._connect() as connection:
            row = connection.execute(
                """
                INSERT INTO edition_jobs (
                    job_id, idempotency_hash, request_fingerprint,
                    request_body, state, stage
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (idempotency_hash) DO NOTHING
                RETURNING *
                """,
                (
                    job_id,
                    key_hash,
                    request_fingerprint,
                    Jsonb(request.model_dump(mode="json")),
                    JobState.REQUESTED.value,
                    JobState.REQUESTED.value,
                ),
            ).fetchone()
            if row is None:
                row = connection.execute(
                    "SELECT * FROM edition_jobs WHERE idempotency_hash = %s",
                    (key_hash,),
                ).fetchone()
                if row is None:
                    raise RuntimeError("Idempotent job lookup failed safely.")
                if row["request_fingerprint"] != request_fingerprint:
                    raise IdempotencyConflict(
                        "Idempotency-Key is already bound to another request."
                    )
            return JobRecord.from_row(row)

    def get_job(self, job_id: str) -> JobRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM edition_jobs WHERE job_id = %s",
                (job_id,),
            ).fetchone()
        if row is None:
            raise JobNotFound(job_id)
        return JobRecord.from_row(row)

    def get_edition(self, edition_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT document FROM editions WHERE edition_id = %s",
                (edition_id,),
            ).fetchone()
        if row is None:
            raise JobNotFound(edition_id)
        return row["document"]

    def request_cancellation(
        self,
        job_id: str,
        *,
        actor: str = "api",
        reason: str = "user_requested",
    ) -> JobRecord:
        actor = _safe_text(actor, fallback="api", maximum=64)
        reason = _safe_text(reason, fallback="user_requested", maximum=120)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM edition_jobs WHERE job_id = %s FOR UPDATE",
                (job_id,),
            ).fetchone()
            if row is None:
                raise JobNotFound(job_id)
            current = JobState(row["state"])
            if current in (JobState.READY, JobState.FAILED, JobState.CANCELLED):
                return JobRecord.from_row(row)
            if current is JobState.REQUESTED:
                validate_transition(current, JobState.CANCELLED)
                row = connection.execute(
                    """
                    UPDATE edition_jobs
                    SET state = 'cancelled',
                        cancellation_requested_at = COALESCE(
                            cancellation_requested_at, clock_timestamp()
                        ),
                        cancellation_effective_at = COALESCE(
                            cancellation_effective_at, clock_timestamp()
                        ),
                        cancellation_actor = COALESCE(cancellation_actor, %s),
                        cancellation_reason = COALESCE(cancellation_reason, %s),
                        checkpoint_at = clock_timestamp(),
                        updated_at = clock_timestamp()
                    WHERE job_id = %s
                    RETURNING *
                    """,
                    (actor, reason, job_id),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    UPDATE edition_jobs
                    SET cancellation_requested_at = COALESCE(
                            cancellation_requested_at, clock_timestamp()
                        ),
                        cancellation_actor = COALESCE(cancellation_actor, %s),
                        cancellation_reason = COALESCE(cancellation_reason, %s),
                        updated_at = clock_timestamp()
                    WHERE job_id = %s
                    RETURNING *
                    """,
                    (actor, reason, job_id),
                ).fetchone()
            return JobRecord.from_row(row)

    def claim_job(
        self,
        worker_id: str,
        *,
        lease_seconds: float = 30.0,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> JobRecord | None:
        worker_id = _safe_worker_id(worker_id)
        lease = _lease_duration(lease_seconds)
        active_values = [state.value for state in ACTIVE_STATES]
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM edition_jobs
                WHERE state = 'requested'
                   OR (
                        state = ANY(%s)
                        AND (
                            lease_owner IS NULL
                            OR lease_expires_at <= clock_timestamp()
                        )
                   )
                ORDER BY created_at, job_id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                (active_values,),
            ).fetchone()
            if row is None:
                return None

            current = JobState(row["state"])
            if row["cancellation_requested_at"] is not None:
                validate_transition(current, JobState.CANCELLED)
                row = connection.execute(
                    """
                    UPDATE edition_jobs
                    SET state = 'cancelled',
                        cancellation_effective_at = COALESCE(
                            cancellation_effective_at, clock_timestamp()
                        ),
                        checkpoint_at = clock_timestamp(),
                        updated_at = clock_timestamp(),
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        heartbeat_at = NULL
                    WHERE job_id = %s
                    RETURNING *
                    """,
                    (row["job_id"],),
                ).fetchone()
                return JobRecord.from_row(row)

            attempt = row["attempt"] + 1
            if attempt > max_attempts:
                validate_transition(current, JobState.FAILED)
                row = connection.execute(
                    """
                    UPDATE edition_jobs
                    SET state = 'failed',
                        failure_code = 'max_attempts_exhausted',
                        failure_retryable = FALSE,
                        failure_attempt = attempt - 1,
                        failure_diagnostic = 'Maximum worker attempts exhausted.',
                        checkpoint_at = clock_timestamp(),
                        updated_at = clock_timestamp(),
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        heartbeat_at = NULL
                    WHERE job_id = %s
                    RETURNING *
                    """,
                    (row["job_id"],),
                ).fetchone()
                return JobRecord.from_row(row)

            target = (
                JobState.COLLECTING if current is JobState.REQUESTED else current
            )
            if current is JobState.REQUESTED:
                validate_transition(current, target)
            row = connection.execute(
                """
                UPDATE edition_jobs
                SET state = %s,
                    stage = %s,
                    attempt = %s,
                    lease_owner = %s,
                    lease_expires_at = clock_timestamp() + %s,
                    heartbeat_at = clock_timestamp(),
                    checkpoint_at = clock_timestamp(),
                    updated_at = clock_timestamp()
                WHERE job_id = %s
                RETURNING *
                """,
                (
                    target.value,
                    target.value,
                    attempt,
                    worker_id,
                    lease,
                    row["job_id"],
                ),
            ).fetchone()
            return JobRecord.from_row(row)

    def heartbeat(
        self,
        job_id: str,
        worker_id: str,
        *,
        lease_seconds: float = 30.0,
    ) -> JobRecord:
        worker_id = _safe_worker_id(worker_id)
        lease = _lease_duration(lease_seconds)
        with self._connect() as connection:
            row = connection.execute(
                """
                UPDATE edition_jobs
                SET heartbeat_at = clock_timestamp(),
                    lease_expires_at = clock_timestamp() + %s,
                    updated_at = clock_timestamp()
                WHERE job_id = %s
                  AND lease_owner = %s
                  AND state = ANY(%s)
                  AND lease_expires_at > clock_timestamp()
                RETURNING *
                """,
                (lease, job_id, worker_id, [state.value for state in ACTIVE_STATES]),
            ).fetchone()
        if row is None:
            raise LeaseConflict("Worker does not own a live lease.")
        return JobRecord.from_row(row)

    def checkpoint_and_advance(
        self,
        job_id: str,
        worker_id: str,
        target: JobState,
        *,
        lease_seconds: float = 30.0,
    ) -> JobRecord:
        worker_id = _safe_worker_id(worker_id)
        lease = _lease_duration(lease_seconds)
        with self._connect() as connection:
            row = self._locked_live_job(connection, job_id, worker_id)
            current = JobState(row["state"])
            if row["cancellation_requested_at"] is not None:
                return self._cancel_at_checkpoint(connection, row)
            validate_transition(current, target)
            if target not in ACTIVE_STATES:
                raise ValueError("Ready publication and terminal failure use dedicated paths.")
            row = connection.execute(
                """
                UPDATE edition_jobs
                SET state = %s,
                    stage = %s,
                    checkpoint_at = clock_timestamp(),
                    heartbeat_at = clock_timestamp(),
                    lease_expires_at = clock_timestamp() + %s,
                    updated_at = clock_timestamp()
                WHERE job_id = %s
                RETURNING *
                """,
                (target.value, target.value, lease, job_id),
            ).fetchone()
            return JobRecord.from_row(row)

    def fail_job(
        self,
        job_id: str,
        worker_id: str,
        *,
        code: str,
        retryable: bool,
        diagnostic: str,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> JobRecord:
        code = _safe_code(code)
        diagnostic = _safe_text(
            diagnostic,
            fallback="Stage failed safely.",
            maximum=160,
        )
        with self._connect() as connection:
            row = self._locked_live_job(connection, job_id, _safe_worker_id(worker_id))
            current = JobState(row["state"])
            if row["cancellation_requested_at"] is not None:
                return self._cancel_at_checkpoint(connection, row)
            validate_transition(current, JobState.FAILED)
            bounded_retryable = bool(retryable and row["attempt"] < max_attempts)
            row = connection.execute(
                """
                UPDATE edition_jobs
                SET state = 'failed',
                    failure_code = %s,
                    failure_retryable = %s,
                    failure_attempt = attempt,
                    failure_diagnostic = %s,
                    checkpoint_at = clock_timestamp(),
                    updated_at = clock_timestamp(),
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    heartbeat_at = NULL
                WHERE job_id = %s
                RETURNING *
                """,
                (code, bounded_retryable, diagnostic, job_id),
            ).fetchone()
            return JobRecord.from_row(row)

    def requeue_retryable(
        self,
        job_id: str,
        *,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM edition_jobs WHERE job_id = %s FOR UPDATE",
                (job_id,),
            ).fetchone()
            if row is None:
                raise JobNotFound(job_id)
            if (
                JobState(row["state"]) is not JobState.FAILED
                or not row["failure_retryable"]
                or row["attempt"] >= max_attempts
            ):
                return False
            validate_transition(
                JobState.FAILED,
                JobState.REQUESTED,
                system_retry=True,
            )
            connection.execute(
                """
                UPDATE edition_jobs
                SET state = 'requested',
                    stage = 'requested',
                    failure_code = NULL,
                    failure_retryable = NULL,
                    failure_attempt = NULL,
                    failure_diagnostic = NULL,
                    checkpoint_at = clock_timestamp(),
                    updated_at = clock_timestamp()
                WHERE job_id = %s
                """,
                (job_id,),
            )
            return True

    def publish_ready_edition(
        self,
        job_id: str,
        worker_id: str,
        document: dict[str, Any],
        validator: CanonicalEditionValidator,
    ) -> JobRecord:
        validated = validator.validate(document)
        with self._connect() as connection:
            row = self._locked_live_job(connection, job_id, _safe_worker_id(worker_id))
            current = JobState(row["state"])
            if row["cancellation_requested_at"] is not None:
                return self._cancel_at_checkpoint(connection, row)
            validate_transition(current, JobState.READY)
            if current is not JobState.LAYING_OUT:
                raise ValueError("Only laying_out may publish a ready edition.")
            self._insert_immutable_edition(connection, validated)
            row = connection.execute(
                """
                UPDATE edition_jobs
                SET state = 'ready',
                    stage = 'ready',
                    edition_id = %s,
                    checkpoint_at = clock_timestamp(),
                    updated_at = clock_timestamp(),
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    heartbeat_at = NULL
                WHERE job_id = %s
                RETURNING *
                """,
                (validated.edition_id, job_id),
            ).fetchone()
            return JobRecord.from_row(row)

    def _locked_live_job(
        self,
        connection: psycopg.Connection[dict[str, Any]],
        job_id: str,
        worker_id: str,
    ) -> dict[str, Any]:
        row = connection.execute(
            """
            SELECT *, lease_expires_at > clock_timestamp() AS lease_is_live
            FROM edition_jobs
            WHERE job_id = %s
            FOR UPDATE
            """,
            (job_id,),
        ).fetchone()
        if row is None:
            raise JobNotFound(job_id)
        if row["lease_owner"] != worker_id or not row["lease_is_live"]:
            raise LeaseConflict("Worker does not own a live lease.")
        if JobState(row["state"]) not in ACTIVE_STATES:
            raise LeaseConflict("Job is not in an active leased state.")
        return row

    def _cancel_at_checkpoint(
        self,
        connection: psycopg.Connection[dict[str, Any]],
        row: dict[str, Any],
    ) -> JobRecord:
        current = JobState(row["state"])
        validate_transition(current, JobState.CANCELLED)
        updated = connection.execute(
            """
            UPDATE edition_jobs
            SET state = 'cancelled',
                cancellation_effective_at = COALESCE(
                    cancellation_effective_at, clock_timestamp()
                ),
                checkpoint_at = clock_timestamp(),
                updated_at = clock_timestamp(),
                lease_owner = NULL,
                lease_expires_at = NULL,
                heartbeat_at = NULL
            WHERE job_id = %s
            RETURNING *
            """,
            (row["job_id"],),
        ).fetchone()
        return JobRecord.from_row(updated)

    def _insert_immutable_edition(
        self,
        connection: psycopg.Connection[dict[str, Any]],
        edition: ValidatedEdition,
    ) -> None:
        existing = connection.execute(
            """
            SELECT document_hash
            FROM editions
            WHERE edition_id = %s
            FOR UPDATE
            """,
            (edition.edition_id,),
        ).fetchone()
        if existing is not None:
            if existing["document_hash"].strip() != edition.document_hash:
                raise EditionImmutableConflict(
                    "Published edition content is immutable by edition_id."
                )
            return
        connection.execute(
            """
            INSERT INTO editions (
                edition_id, contract_version, document, document_hash
            )
            VALUES (%s, %s, %s, %s)
            """,
            (
                edition.edition_id,
                edition.contract_version,
                Jsonb(edition.document),
                edition.document_hash,
            ),
        )


def _lease_duration(seconds: float) -> timedelta:
    if seconds <= 0 or seconds > 300:
        raise ValueError("Lease duration must be within (0, 300] seconds.")
    return timedelta(seconds=seconds)


def _safe_worker_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", value):
        raise ValueError("worker_id contains unsupported characters.")
    return value


def _safe_code(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9_]{1,64}", value):
        return "internal_stage_error"
    return value


def _safe_text(value: str, *, fallback: str, maximum: int) -> str:
    compact = " ".join(str(value).split())[:maximum]
    lowered = compact.lower()
    forbidden = (
        "secret",
        "api_key",
        "token",
        "password",
        "prompt",
        "postgresql://",
    )
    if not compact or any(marker in lowered for marker in forbidden):
        return fallback
    return compact
