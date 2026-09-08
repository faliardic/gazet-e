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
    REQUEST_VERSION,
    idempotency_identity,
    normalize_idempotency_key,
    validate_transition,
)
from services.edition_job_validation import (
    CanonicalEditionValidator,
    ValidatedEdition,
)
from services.edition_integration_models import canonical_safe_payload


class JobNotFound(LookupError):
    pass


class IdempotencyConflict(ValueError):
    pass


class LeaseConflict(RuntimeError):
    pass


class EditionImmutableConflict(RuntimeError):
    pass


class IntegrationConflict(RuntimeError):
    pass


class PaidDispatchBlocked(RuntimeError):
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
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS edition_jobs_runnable_v2_idx
                ON edition_jobs (created_at, job_id)
                WHERE state IN (
                    'requested', 'collecting', 'selecting',
                    'illustrating', 'laying_out'
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS edition_integration_runs (
                    job_id TEXT PRIMARY KEY REFERENCES edition_jobs(job_id)
                        ON DELETE CASCADE,
                    policy_version TEXT NOT NULL,
                    policy_fingerprint CHAR(71) NOT NULL,
                    policy JSONB NOT NULL,
                    assembly_fingerprint CHAR(71),
                    edition_id TEXT,
                    generated_at TIMESTAMPTZ,
                    logical_provider_calls INTEGER NOT NULL DEFAULT 0,
                    transport_attempts INTEGER NOT NULL DEFAULT 0,
                    generated_images INTEGER NOT NULL DEFAULT 0,
                    estimated_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS edition_stage_manifests (
                    job_id TEXT NOT NULL REFERENCES edition_jobs(job_id)
                        ON DELETE CASCADE,
                    stage TEXT NOT NULL,
                    manifest_version TEXT NOT NULL,
                    manifest JSONB NOT NULL,
                    manifest_hash CHAR(64) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                    PRIMARY KEY (job_id, stage)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS edition_artifact_cache (
                    artifact_kind TEXT NOT NULL,
                    cache_key CHAR(71) NOT NULL,
                    artifact JSONB NOT NULL,
                    artifact_hash CHAR(64) NOT NULL,
                    source_job_id TEXT NOT NULL REFERENCES edition_jobs(job_id),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                    PRIMARY KEY (artifact_kind, cache_key)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS edition_paid_operations (
                    job_id TEXT NOT NULL REFERENCES edition_jobs(job_id)
                        ON DELETE CASCADE,
                    operation_id TEXT NOT NULL,
                    artifact_kind TEXT NOT NULL,
                    cache_key CHAR(71) NOT NULL,
                    attempt INTEGER NOT NULL,
                    state TEXT NOT NULL CHECK (
                        state IN ('reserved', 'completed', 'uncertain')
                    ),
                    logical_calls INTEGER NOT NULL CHECK (logical_calls >= 0),
                    transport_attempts INTEGER NOT NULL CHECK (transport_attempts >= 0),
                    generated_images INTEGER NOT NULL CHECK (generated_images >= 0),
                    estimated_cost_usd DOUBLE PRECISION NOT NULL
                        CHECK (estimated_cost_usd >= 0),
                    result JSONB,
                    reserved_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                    completed_at TIMESTAMPTZ,
                    PRIMARY KEY (job_id, operation_id)
                )
                """
            )
            connection.execute(
                """
                ALTER TABLE edition_paid_operations
                ADD COLUMN IF NOT EXISTS attempt INTEGER NOT NULL DEFAULT 0
                """
            )

    def create_job(self, idempotency_key: str | None, request: EditionRequest) -> JobRecord:
        if request.request_version != REQUEST_VERSION:
            raise ValueError("Only gazet-e.edition-request.v2 may create a new job.")
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

    def get_request(self, job_id: str) -> EditionRequest:
        """Return the immutable request without widening the public status model."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT request_body FROM edition_jobs WHERE job_id = %s",
                (job_id,),
            ).fetchone()
        if row is None:
            raise JobNotFound(job_id)
        return EditionRequest.model_validate(row["request_body"])

    def ensure_integration_run(
        self,
        job_id: str,
        worker_id: str,
        *,
        expected_attempt: int,
        policy_version: str,
        policy_fingerprint: str,
        policy: dict[str, Any],
    ) -> dict[str, Any]:
        canonical_safe_payload(policy)
        _safe_version(policy_version)
        _safe_cache_key(policy_fingerprint)
        with self._connect() as connection:
            self._locked_live_job(
                connection,
                job_id,
                _safe_worker_id(worker_id),
                expected_attempt=expected_attempt,
            )
            connection.execute(
                """
                INSERT INTO edition_integration_runs (
                    job_id, policy_version, policy_fingerprint, policy
                ) VALUES (%s, %s, %s, %s)
                ON CONFLICT (job_id) DO NOTHING
                """,
                (job_id, policy_version, policy_fingerprint, Jsonb(policy)),
            )
            run = connection.execute(
                "SELECT * FROM edition_integration_runs WHERE job_id = %s",
                (job_id,),
            ).fetchone()
            if (
                run["policy_version"] != policy_version
                or run["policy_fingerprint"].strip() != policy_fingerprint
                or run["policy"] != policy
            ):
                raise IntegrationConflict("Integration policy is immutable per job.")
            return dict(run)

    def get_integration_run(self, job_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM edition_integration_runs WHERE job_id = %s",
                (job_id,),
            ).fetchone()
        if row is None:
            raise JobNotFound(job_id)
        return dict(row)

    def get_stage_manifest(self, job_id: str, stage: JobState | str) -> dict[str, Any]:
        stage_value = stage.value if isinstance(stage, JobState) else str(stage)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT manifest_version, manifest, manifest_hash
                FROM edition_stage_manifests
                WHERE job_id = %s AND stage = %s
                """,
                (job_id, stage_value),
            ).fetchone()
        if row is None:
            raise JobNotFound(f"{job_id}:{stage_value}")
        return dict(row)

    def get_cached_artifact(
        self,
        artifact_kind: str,
        cache_key: str,
    ) -> dict[str, Any] | None:
        artifact_kind = _safe_kind(artifact_kind)
        cache_key = _safe_cache_key(cache_key)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT artifact FROM edition_artifact_cache
                WHERE artifact_kind = %s AND cache_key = %s
                """,
                (artifact_kind, cache_key),
            ).fetchone()
        return None if row is None else row["artifact"]

    def get_paid_operation(self, job_id: str, operation_id: str) -> dict[str, Any] | None:
        operation_id = _safe_operation_id(operation_id)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM edition_paid_operations
                WHERE job_id = %s AND operation_id = %s
                """,
                (job_id, operation_id),
            ).fetchone()
        return None if row is None else dict(row)

    def reserve_paid_operation(
        self,
        job_id: str,
        worker_id: str,
        *,
        expected_attempt: int,
        operation_id: str,
        artifact_kind: str,
        cache_key: str,
        logical_calls: int,
        transport_attempts: int,
        generated_images: int,
        estimated_cost_usd: float,
    ) -> dict[str, Any]:
        """Fence a paid dispatch and reserve its worst-case budget atomically."""
        worker_id = _safe_worker_id(worker_id)
        operation_id = _safe_operation_id(operation_id)
        artifact_kind = _safe_kind(artifact_kind)
        cache_key = _safe_cache_key(cache_key)
        _validate_usage(
            logical_calls,
            transport_attempts,
            generated_images,
            estimated_cost_usd,
        )
        with self._connect() as connection:
            job = self._locked_live_job(
                connection,
                job_id,
                worker_id,
                expected_attempt=expected_attempt,
            )
            if job["cancellation_requested_at"] is not None:
                raise PaidDispatchBlocked("Cancellation blocks provider dispatch.")
            existing = connection.execute(
                """
                SELECT * FROM edition_paid_operations
                WHERE job_id = %s AND operation_id = %s
                FOR UPDATE
                """,
                (job_id, operation_id),
            ).fetchone()
            if existing is not None:
                if (
                    existing["artifact_kind"] != artifact_kind
                    or existing["cache_key"].strip() != cache_key
                ):
                    raise IntegrationConflict("Paid operation identity conflict.")
                if existing["state"] == "reserved":
                    existing = connection.execute(
                        """
                        UPDATE edition_paid_operations
                        SET state = 'uncertain'
                        WHERE job_id = %s AND operation_id = %s
                        RETURNING *
                        """,
                        (job_id, operation_id),
                    ).fetchone()
                return dict(existing)

            run = connection.execute(
                """
                SELECT * FROM edition_integration_runs
                WHERE job_id = %s FOR UPDATE
                """,
                (job_id,),
            ).fetchone()
            if run is None:
                raise IntegrationConflict("Integration policy is unavailable.")
            policy = run["policy"]
            if not policy.get("paid_execution_enabled", False):
                raise PaidDispatchBlocked("Provider dispatch is disabled by policy.")
            budget_scope_id = policy.get("budget_scope_id")
            if not isinstance(budget_scope_id, str) or not re.fullmatch(
                r"[A-Za-z0-9_.:-]{1,96}", budget_scope_id
            ):
                raise IntegrationConflict("Integration budget scope is invalid.")
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (budget_scope_id,),
            )
            aggregate = connection.execute(
                """
                SELECT
                    COALESCE(SUM(logical_provider_calls), 0) AS logical,
                    COALESCE(SUM(transport_attempts), 0) AS transport,
                    COALESCE(SUM(generated_images), 0) AS images,
                    COALESCE(SUM(estimated_cost_usd), 0) AS cost
                FROM edition_integration_runs
                WHERE policy ->> 'budget_scope_id' = %s
                """,
                (budget_scope_id,),
            ).fetchone()
            totals = {
                "logical": aggregate["logical"] + logical_calls,
                "transport": aggregate["transport"] + transport_attempts,
                "images": aggregate["images"] + generated_images,
                "cost": float(aggregate["cost"]) + estimated_cost_usd,
            }
            if (
                totals["logical"] > policy["max_logical_provider_calls"]
                or totals["transport"] > policy["max_transport_attempts"]
                or totals["images"] > policy["max_generated_images"]
                or totals["cost"] > policy["max_estimated_cost_usd"] + 1e-12
            ):
                raise PaidDispatchBlocked("Integration provider budget is exhausted.")
            operation = connection.execute(
                """
                INSERT INTO edition_paid_operations (
                    job_id, operation_id, artifact_kind, cache_key, attempt, state,
                    logical_calls, transport_attempts, generated_images,
                    estimated_cost_usd
                ) VALUES (%s, %s, %s, %s, %s, 'reserved', %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    job_id,
                    operation_id,
                    artifact_kind,
                    cache_key,
                    job["attempt"],
                    logical_calls,
                    transport_attempts,
                    generated_images,
                    estimated_cost_usd,
                ),
            ).fetchone()
            connection.execute(
                """
                UPDATE edition_integration_runs
                SET logical_provider_calls = logical_provider_calls + %s,
                    transport_attempts = transport_attempts + %s,
                    generated_images = generated_images + %s,
                    estimated_cost_usd = estimated_cost_usd + %s,
                    updated_at = clock_timestamp()
                WHERE job_id = %s
                """,
                (
                    logical_calls,
                    transport_attempts,
                    generated_images,
                    estimated_cost_usd,
                    job_id,
                ),
            )
            return dict(operation)

    def assert_dispatch_allowed(
        self,
        job_id: str,
        worker_id: str,
        operation_id: str,
        *,
        expected_attempt: int,
    ) -> None:
        operation_id = _safe_operation_id(operation_id)
        with self._connect() as connection:
            job = self._locked_live_job(
                connection,
                job_id,
                _safe_worker_id(worker_id),
                expected_attempt=expected_attempt,
            )
            if job["cancellation_requested_at"] is not None:
                raise PaidDispatchBlocked("Cancellation blocks provider dispatch.")
            operation = connection.execute(
                """
                SELECT state, attempt FROM edition_paid_operations
                WHERE job_id = %s AND operation_id = %s
                FOR UPDATE
                """,
                (job_id, operation_id),
            ).fetchone()
            if (
                operation is None
                or operation["state"] != "reserved"
                or operation["attempt"] != job["attempt"]
            ):
                raise PaidDispatchBlocked("Provider dispatch fence is not live.")

    def complete_paid_operation(
        self,
        job_id: str,
        worker_id: str,
        *,
        expected_attempt: int,
        operation_id: str,
        result: dict[str, Any],
        logical_calls: int,
        transport_attempts: int,
        generated_images: int,
        estimated_cost_usd: float,
        artifact: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        canonical_safe_payload(result)
        if artifact is not None:
            canonical_safe_payload(artifact)
        _validate_usage(
            logical_calls,
            transport_attempts,
            generated_images,
            estimated_cost_usd,
        )
        operation_id = _safe_operation_id(operation_id)
        with self._connect() as connection:
            self._locked_live_job(
                connection,
                job_id,
                _safe_worker_id(worker_id),
                expected_attempt=expected_attempt,
            )
            operation = connection.execute(
                """
                SELECT * FROM edition_paid_operations
                WHERE job_id = %s AND operation_id = %s
                FOR UPDATE
                """,
                (job_id, operation_id),
            ).fetchone()
            if operation is None or operation["state"] != "reserved":
                raise PaidDispatchBlocked("Paid operation cannot be completed.")
            job = connection.execute(
                "SELECT attempt FROM edition_jobs WHERE job_id = %s",
                (job_id,),
            ).fetchone()
            if job is None or operation["attempt"] != job["attempt"]:
                raise PaidDispatchBlocked("Paid operation attempt fence is stale.")
            if (
                logical_calls > operation["logical_calls"]
                or transport_attempts > operation["transport_attempts"]
                or generated_images > operation["generated_images"]
                or estimated_cost_usd > float(operation["estimated_cost_usd"]) + 1e-12
            ):
                raise PaidDispatchBlocked("Provider usage exceeded its reservation.")
            if artifact is not None:
                self._insert_immutable_artifact(
                    connection,
                    operation["artifact_kind"],
                    operation["cache_key"].strip(),
                    artifact,
                    job_id,
                )
            locked_run = connection.execute(
                "SELECT * FROM edition_integration_runs WHERE job_id = %s FOR UPDATE",
                (job_id,),
            ).fetchone()
            if locked_run is None:
                raise IntegrationConflict("Integration run is unavailable.")
            connection.execute(
                """
                UPDATE edition_integration_runs
                SET logical_provider_calls = logical_provider_calls + %s,
                    transport_attempts = transport_attempts + %s,
                    generated_images = generated_images + %s,
                    estimated_cost_usd = estimated_cost_usd + %s,
                    updated_at = clock_timestamp()
                WHERE job_id = %s
                """,
                (
                    logical_calls - operation["logical_calls"],
                    transport_attempts - operation["transport_attempts"],
                    generated_images - operation["generated_images"],
                    estimated_cost_usd - float(operation["estimated_cost_usd"]),
                    job_id,
                ),
            )
            updated = connection.execute(
                """
                UPDATE edition_paid_operations
                SET state = 'completed', result = %s,
                    logical_calls = %s, transport_attempts = %s,
                    generated_images = %s, estimated_cost_usd = %s,
                    completed_at = clock_timestamp()
                WHERE job_id = %s AND operation_id = %s
                RETURNING *
                """,
                (
                    Jsonb(result),
                    logical_calls,
                    transport_attempts,
                    generated_images,
                    estimated_cost_usd,
                    job_id,
                    operation_id,
                ),
            ).fetchone()
            return dict(updated)

    def mark_paid_operation_uncertain(
        self,
        job_id: str,
        worker_id: str,
        *,
        operation_id: str,
        expected_attempt: int,
    ) -> dict[str, Any]:
        """Keep the full reservation when remote usage/outcome is unknown."""

        operation_id = _safe_operation_id(operation_id)
        with self._connect() as connection:
            self._locked_live_job(
                connection,
                job_id,
                _safe_worker_id(worker_id),
                expected_attempt=expected_attempt,
            )
            updated = connection.execute(
                """
                UPDATE edition_paid_operations
                SET state = 'uncertain', completed_at = clock_timestamp()
                WHERE job_id = %s AND operation_id = %s
                  AND state = 'reserved' AND attempt = %s
                RETURNING *
                """,
                (job_id, operation_id, expected_attempt),
            ).fetchone()
            if updated is None:
                raise PaidDispatchBlocked("Paid operation uncertainty fence is stale.")
            return dict(updated)

    def freeze_assembly(
        self,
        job_id: str,
        worker_id: str,
        *,
        expected_attempt: int,
        assembly_fingerprint: str,
        edition_id: str,
    ) -> dict[str, Any]:
        _safe_cache_key(assembly_fingerprint)
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", edition_id):
            raise ValueError("edition identity contains unsupported characters")
        with self._connect() as connection:
            self._locked_live_job(
                connection,
                job_id,
                _safe_worker_id(worker_id),
                expected_attempt=expected_attempt,
            )
            row = connection.execute(
                """
                SELECT * FROM edition_integration_runs
                WHERE job_id = %s FOR UPDATE
                """,
                (job_id,),
            ).fetchone()
            if row["assembly_fingerprint"] is None:
                row = connection.execute(
                    """
                    UPDATE edition_integration_runs
                    SET assembly_fingerprint = %s, edition_id = %s,
                        generated_at = clock_timestamp(),
                        updated_at = clock_timestamp()
                    WHERE job_id = %s
                    RETURNING *
                    """,
                    (assembly_fingerprint, edition_id, job_id),
                ).fetchone()
            elif (
                row["assembly_fingerprint"].strip() != assembly_fingerprint
                or row["edition_id"] != edition_id
            ):
                raise IntegrationConflict("Assembly identity is immutable per job.")
            return dict(row)

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
        expected_attempt: int | None = None,
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
                  AND (%s::integer IS NULL OR attempt = %s)
                RETURNING *
                """,
                (
                    lease,
                    job_id,
                    worker_id,
                    [state.value for state in ACTIVE_STATES],
                    expected_attempt,
                    expected_attempt,
                ),
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
        manifest_version: str | None = None,
        manifest: dict[str, Any] | None = None,
        expected_attempt: int | None = None,
    ) -> JobRecord:
        worker_id = _safe_worker_id(worker_id)
        lease = _lease_duration(lease_seconds)
        with self._connect() as connection:
            row = self._locked_live_job(
                connection,
                job_id,
                worker_id,
                expected_attempt=expected_attempt,
            )
            current = JobState(row["state"])
            if row["cancellation_requested_at"] is not None:
                return self._cancel_at_checkpoint(connection, row)
            validate_transition(current, target)
            if target not in ACTIVE_STATES:
                raise ValueError("Ready publication and terminal failure use dedicated paths.")
            if (manifest_version is None) != (manifest is None):
                raise ValueError("Manifest version and payload must be supplied together.")
            if manifest_version is not None and manifest is not None:
                self._store_stage_manifest(
                    connection,
                    job_id,
                    current,
                    manifest_version,
                    manifest,
                )
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
        expected_attempt: int | None = None,
    ) -> JobRecord:
        code = _safe_code(code)
        diagnostic = _safe_text(
            diagnostic,
            fallback="Stage failed safely.",
            maximum=160,
        )
        with self._connect() as connection:
            row = self._locked_live_job(
                connection,
                job_id,
                _safe_worker_id(worker_id),
                expected_attempt=expected_attempt,
            )
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
        *,
        manifest_version: str | None = None,
        manifest: dict[str, Any] | None = None,
        expected_attempt: int | None = None,
    ) -> JobRecord:
        validated = validator.validate(document)
        with self._connect() as connection:
            row = self._locked_live_job(
                connection,
                job_id,
                _safe_worker_id(worker_id),
                expected_attempt=expected_attempt,
            )
            current = JobState(row["state"])
            if row["cancellation_requested_at"] is not None:
                return self._cancel_at_checkpoint(connection, row)
            validate_transition(current, JobState.READY)
            if current is not JobState.LAYING_OUT:
                raise ValueError("Only laying_out may publish a ready edition.")
            if (manifest_version is None) != (manifest is None):
                raise ValueError("Manifest version and payload must be supplied together.")
            if manifest_version is not None and manifest is not None:
                self._store_stage_manifest(
                    connection,
                    job_id,
                    current,
                    manifest_version,
                    manifest,
                )
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
        *,
        expected_attempt: int | None = None,
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
        if expected_attempt is not None and row["attempt"] != expected_attempt:
            raise LeaseConflict("Worker attempt identity is stale.")
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

    def _store_stage_manifest(
        self,
        connection: psycopg.Connection[dict[str, Any]],
        job_id: str,
        stage: JobState,
        manifest_version: str,
        manifest: dict[str, Any],
    ) -> None:
        _safe_version(manifest_version)
        _canonical, manifest_hash = canonical_safe_payload(manifest)
        existing = connection.execute(
            """
            SELECT manifest_version, manifest_hash
            FROM edition_stage_manifests
            WHERE job_id = %s AND stage = %s
            FOR UPDATE
            """,
            (job_id, stage.value),
        ).fetchone()
        if existing is not None:
            if (
                existing["manifest_version"] != manifest_version
                or existing["manifest_hash"].strip() != manifest_hash
            ):
                raise IntegrationConflict("Stage manifest is immutable per checkpoint.")
            return
        connection.execute(
            """
            INSERT INTO edition_stage_manifests (
                job_id, stage, manifest_version, manifest, manifest_hash
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (job_id, stage.value, manifest_version, Jsonb(manifest), manifest_hash),
        )

    def _insert_immutable_artifact(
        self,
        connection: psycopg.Connection[dict[str, Any]],
        artifact_kind: str,
        cache_key: str,
        artifact: dict[str, Any],
        source_job_id: str,
    ) -> None:
        _canonical, artifact_hash = canonical_safe_payload(artifact)
        existing = connection.execute(
            """
            SELECT artifact_hash FROM edition_artifact_cache
            WHERE artifact_kind = %s AND cache_key = %s
            FOR UPDATE
            """,
            (artifact_kind, cache_key),
        ).fetchone()
        if existing is not None:
            if existing["artifact_hash"].strip() != artifact_hash:
                raise IntegrationConflict("Artifact cache identity is immutable.")
            return
        connection.execute(
            """
            INSERT INTO edition_artifact_cache (
                artifact_kind, cache_key, artifact, artifact_hash, source_job_id
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                artifact_kind,
                cache_key,
                Jsonb(artifact),
                artifact_hash,
                source_job_id,
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


def _safe_version(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", value):
        raise ValueError("version contains unsupported characters")
    return value


def _safe_kind(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", value):
        raise ValueError("artifact kind contains unsupported characters")
    return value


def _safe_cache_key(value: str) -> str:
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise ValueError("cache identity is invalid")
    return value


def _safe_operation_id(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,31}:sha256:[0-9a-f]{64}", value):
        raise ValueError("operation identity is invalid")
    return value


def _validate_usage(
    logical_calls: int,
    transport_attempts: int,
    generated_images: int,
    estimated_cost_usd: float,
) -> None:
    if (
        logical_calls < 0
        or transport_attempts < logical_calls
        or generated_images < 0
        or estimated_cost_usd < 0
        or estimated_cost_usd != estimated_cost_usd
    ):
        raise ValueError("provider usage is invalid")
