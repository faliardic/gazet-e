"""Lease-aware Q05 worker orchestration with injected stage executors."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from services.edition_job_models import NEXT_STATE, JobState
from services.edition_job_store import (
    EditionImmutableConflict,
    EditionJobStore,
    JobRecord,
)
from services.edition_job_validation import (
    CanonicalEditionError,
    CanonicalEditionValidator,
)


class StageExecutor(Protocol):
    def __call__(self, job: JobRecord) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class StageExecutionError(Exception):
    code: str
    retryable: bool
    diagnostic: str = "Stage execution failed safely."


class EditionJobWorker:
    """Runs one claimed job using only explicitly supplied stage executors."""

    def __init__(
        self,
        store: EditionJobStore,
        worker_id: str,
        executors: Mapping[JobState, StageExecutor],
        *,
        validator: CanonicalEditionValidator | None = None,
        lease_seconds: float = 30.0,
    ) -> None:
        self._store = store
        self._worker_id = worker_id
        self._executors = dict(executors)
        self._validator = validator or CanonicalEditionValidator()
        self._lease_seconds = lease_seconds

    def run_one(self) -> JobRecord | None:
        job = self._store.claim_job(
            self._worker_id,
            lease_seconds=self._lease_seconds,
        )
        if job is None or job.state in (
            JobState.READY,
            JobState.FAILED,
            JobState.CANCELLED,
        ):
            return job

        while job.state not in (
            JobState.READY,
            JobState.FAILED,
            JobState.CANCELLED,
        ):
            job = self._store.heartbeat(
                job.job_id,
                self._worker_id,
                lease_seconds=self._lease_seconds,
            )
            executor = self._executors.get(job.state)
            if executor is None:
                return self._store.fail_job(
                    job.job_id,
                    self._worker_id,
                    code="stage_executor_missing",
                    retryable=False,
                    diagnostic="No executor was supplied for the current stage.",
                )

            try:
                output = executor(job)
            except StageExecutionError as error:
                return self._store.fail_job(
                    job.job_id,
                    self._worker_id,
                    code=error.code,
                    retryable=error.retryable,
                    diagnostic=error.diagnostic,
                )
            except Exception:
                return self._store.fail_job(
                    job.job_id,
                    self._worker_id,
                    code="internal_stage_error",
                    retryable=False,
                    diagnostic="Stage execution failed safely.",
                )

            if job.state is JobState.LAYING_OUT:
                if not isinstance(output, dict):
                    return self._store.fail_job(
                        job.job_id,
                        self._worker_id,
                        code="invalid_edition",
                        retryable=False,
                        diagnostic="Layout did not produce a canonical edition document.",
                    )
                try:
                    return self._store.publish_ready_edition(
                        job.job_id,
                        self._worker_id,
                        output,
                        self._validator,
                    )
                except (CanonicalEditionError, EditionImmutableConflict):
                    return self._store.fail_job(
                        job.job_id,
                        self._worker_id,
                        code="invalid_edition",
                        retryable=False,
                        diagnostic="Edition document failed canonical validation.",
                    )

            job = self._store.checkpoint_and_advance(
                job.job_id,
                self._worker_id,
                NEXT_STATE[job.state],
                lease_seconds=self._lease_seconds,
            )

        return job
