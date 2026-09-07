"""Lease-aware Q05 worker orchestration with injected stage executors."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from threading import Event, Thread
from typing import Any, Protocol

from services.edition_job_models import NEXT_STATE, JobState
from services.edition_job_store import (
    EditionImmutableConflict,
    EditionJobStore,
    JobRecord,
    LeaseConflict,
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


class _LeaseKeepalive:
    """Renews one live lease until its executor returns or ownership is lost."""

    def __init__(
        self,
        store: EditionJobStore,
        job_id: str,
        worker_id: str,
        lease_seconds: float,
    ) -> None:
        self._store = store
        self._job_id = job_id
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._interval = min(5.0, lease_seconds / 3.0)
        self._stop = Event()
        self._failure: Exception | None = None
        self._thread = Thread(
            target=self._run,
            name=f"edition-lease-{job_id}",
            daemon=True,
        )

    def __enter__(self) -> _LeaseKeepalive:
        self._thread.start()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self._stop.set()
        self._thread.join()

    def ensure_owned(self) -> None:
        if self._failure is None:
            return
        if isinstance(self._failure, LeaseConflict):
            raise self._failure
        raise LeaseConflict("Lease keepalive failed safely.") from self._failure

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self._store.heartbeat(
                    self._job_id,
                    self._worker_id,
                    lease_seconds=self._lease_seconds,
                )
            except Exception as error:
                self._failure = error
                self._stop.set()
                return


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

            declared_failure: StageExecutionError | None = None
            unexpected_failure = False
            keepalive = _LeaseKeepalive(
                self._store,
                job.job_id,
                self._worker_id,
                self._lease_seconds,
            )
            with keepalive:
                try:
                    output = executor(job)
                except StageExecutionError as error:
                    declared_failure = error
                    output = None
                except Exception:
                    unexpected_failure = True
                    output = None
            keepalive.ensure_owned()

            if declared_failure is not None:
                return self._store.fail_job(
                    job.job_id,
                    self._worker_id,
                    code=declared_failure.code,
                    retryable=declared_failure.retryable,
                    diagnostic=declared_failure.diagnostic,
                )
            if unexpected_failure:
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
