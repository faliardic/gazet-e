from __future__ import annotations

import copy
import json
import os
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from services.edition_job_api import create_app
from services.edition_job_models import (
    NEXT_STATE,
    EditionRequest,
    InvalidTransition,
    JobState,
    validate_transition,
)
from services.edition_job_store import (
    EditionImmutableConflict,
    EditionJobStore,
    IdempotencyConflict,
    LeaseConflict,
)
from services.edition_job_validation import CanonicalEditionValidator
from services.edition_job_worker import EditionJobWorker, StageExecutionError

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "mobile" / "assets" / "fixtures" / "edition.json"


@pytest.fixture(scope="session")
def postgres_dsn() -> str:
    dsn = os.environ.get("GAZETE_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.fail(
            "GAZETE_TEST_POSTGRES_DSN must target the disposable local Q05 "
            "PostgreSQL database; this integration gate may not be skipped."
        )
    with psycopg.connect(dsn) as connection:
        identity = connection.execute(
            "SELECT current_database(), current_user, inet_server_addr()"
        ).fetchone()
    assert identity[0] == "gazete_q05_test"
    assert identity[1] == "gazete_q05_test"
    assert str(identity[2]) in {"127.0.0.1", "::1"}
    return dsn


@pytest.fixture
def store(postgres_dsn: str) -> Iterator[EditionJobStore]:
    result = EditionJobStore(postgres_dsn)
    result.initialize_schema()
    with psycopg.connect(postgres_dsn) as connection:
        connection.execute("TRUNCATE edition_jobs, editions CASCADE")
    yield result
    with psycopg.connect(postgres_dsn) as connection:
        connection.execute("TRUNCATE edition_jobs, editions CASCADE")


@pytest.fixture
def request_data() -> EditionRequest:
    return EditionRequest(
        request_version="gazet-e.edition-request.v1",
        locale="tr-TR",
        timezone="Europe/Istanbul",
    )


@pytest.fixture
def canonical_edition() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _create(
    store: EditionJobStore,
    request_data: EditionRequest,
    key: str = "request-1",
):
    return store.create_job(key, request_data)


def _advance_to_laying_out(
    store: EditionJobStore,
    job_id: str,
    worker_id: str,
) -> None:
    current = store.get_job(job_id)
    while current.state is not JobState.LAYING_OUT:
        current = store.checkpoint_and_advance(
            job_id,
            worker_id,
            NEXT_STATE[current.state],
        )


def _successful_executors(
    document: dict[str, object],
    calls: list[JobState] | None = None,
):
    def execute(job):
        if calls is not None:
            calls.append(job.state)
        if job.state is JobState.LAYING_OUT:
            return document
        return None

    return {state: execute for state in NEXT_STATE.values() if state is not JobState.READY}


def test_request_contract_rejects_unknown_fields_versions_and_bad_timezone() -> None:
    with pytest.raises(ValidationError):
        EditionRequest(
            request_version="gazet-e.edition-request.v2",
            locale="tr-TR",
            timezone="Europe/Istanbul",
        )
    with pytest.raises(ValidationError):
        EditionRequest(
            request_version="gazet-e.edition-request.v1",
            locale="turkish",
            timezone="Europe/Istanbul",
        )
    with pytest.raises(ValidationError):
        EditionRequest(
            request_version="gazet-e.edition-request.v1",
            locale="tr-TR",
            timezone="Not/AZone",
            provider_key="forbidden",
        )


def test_lifecycle_transition_whitelist_is_fail_closed() -> None:
    validate_transition(JobState.REQUESTED, JobState.COLLECTING)
    validate_transition(JobState.COLLECTING, JobState.FAILED)
    validate_transition(JobState.COLLECTING, JobState.CANCELLED)
    validate_transition(JobState.FAILED, JobState.REQUESTED, system_retry=True)
    with pytest.raises(InvalidTransition):
        validate_transition(JobState.REQUESTED, JobState.SELECTING)
    with pytest.raises(InvalidTransition):
        validate_transition(JobState.READY, JobState.CANCELLED)
    with pytest.raises(InvalidTransition):
        validate_transition(JobState.FAILED, JobState.REQUESTED)


def test_idempotency_reuses_same_job_and_conflicts_on_different_request(
    store: EditionJobStore,
    request_data: EditionRequest,
    postgres_dsn: str,
) -> None:
    first = _create(store, request_data, "stable-key")
    same = _create(store, request_data, "stable-key")
    assert same.job_id == first.job_id

    changed = request_data.model_copy(update={"locale": "en-US"})
    with pytest.raises(IdempotencyConflict):
        _create(store, changed, "stable-key")

    with psycopg.connect(postgres_dsn) as connection:
        stored = connection.execute(
            "SELECT idempotency_hash::text, request_body FROM edition_jobs"
        ).fetchone()
    assert stored[0] != "stable-key"
    assert "stable-key" not in json.dumps(stored[1])


def test_job_is_durable_across_store_instances(
    store: EditionJobStore,
    request_data: EditionRequest,
    postgres_dsn: str,
) -> None:
    created = _create(store, request_data)
    reopened = EditionJobStore(postgres_dsn).get_job(created.job_id)
    assert reopened.job_id == created.job_id
    assert reopened.state is JobState.REQUESTED


def test_concurrent_idempotent_request_storm_creates_one_logical_job(
    store: EditionJobStore,
    request_data: EditionRequest,
    postgres_dsn: str,
) -> None:
    with ThreadPoolExecutor(max_workers=8) as pool:
        job_ids = list(
            pool.map(
                lambda _index: store.create_job("storm-key", request_data).job_id,
                range(16),
            )
        )
    assert len(set(job_ids)) == 1
    with psycopg.connect(postgres_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM edition_jobs").fetchone()[0] == 1


def test_status_is_truthful_and_has_no_fake_progress(
    store: EditionJobStore,
    request_data: EditionRequest,
) -> None:
    status = _create(store, request_data).to_status().model_dump(mode="json")
    assert status["state"] == "requested"
    assert status["stage"] == "requested"
    assert "progress" not in status
    assert "percentage" not in status


def test_requested_cancellation_is_immediate_and_idempotent(
    store: EditionJobStore,
    request_data: EditionRequest,
) -> None:
    created = _create(store, request_data)
    first = store.request_cancellation(created.job_id)
    second = store.request_cancellation(created.job_id)
    assert first.state is JobState.CANCELLED
    assert first.cancellation_requested_at is not None
    assert first.cancellation_effective_at is not None
    assert second.cancellation_effective_at == first.cancellation_effective_at


def test_active_cancellation_becomes_effective_at_safe_checkpoint(
    store: EditionJobStore,
    request_data: EditionRequest,
) -> None:
    created = _create(store, request_data)
    claimed = store.claim_job("worker-a")
    assert claimed is not None and claimed.job_id == created.job_id
    requested = store.request_cancellation(created.job_id)
    assert requested.state is JobState.COLLECTING
    assert requested.cancellation_requested_at is not None
    assert requested.cancellation_effective_at is None
    cancelled = store.checkpoint_and_advance(
        created.job_id,
        "worker-a",
        JobState.SELECTING,
    )
    assert cancelled.state is JobState.CANCELLED
    assert cancelled.cancellation_effective_at is not None


def test_worker_honors_cancellation_requested_inside_stage_at_checkpoint(
    store: EditionJobStore,
    request_data: EditionRequest,
) -> None:
    created = _create(store, request_data)

    def request_cancel(job):
        store.request_cancellation(job.job_id)
        return None

    result = EditionJobWorker(
        store,
        "worker-a",
        {JobState.COLLECTING: request_cancel},
    ).run_one()
    assert result is not None
    assert result.job_id == created.job_id
    assert result.state is JobState.CANCELLED
    assert result.cancellation_effective_at is not None


def test_live_lease_excludes_second_worker_and_checks_ownership(
    store: EditionJobStore,
    request_data: EditionRequest,
) -> None:
    created = _create(store, request_data)
    claimed = store.claim_job("worker-a")
    assert claimed is not None and claimed.job_id == created.job_id
    assert store.claim_job("worker-b") is None
    with pytest.raises(LeaseConflict):
        store.heartbeat(created.job_id, "worker-b")
    renewed = store.heartbeat(created.job_id, "worker-a")
    assert renewed.lease_expires_at > claimed.lease_expires_at


def test_for_update_skip_locked_allows_two_workers_to_claim_different_jobs(
    store: EditionJobStore,
    request_data: EditionRequest,
    postgres_dsn: str,
) -> None:
    first = _create(store, request_data, "first")
    time.sleep(0.01)
    second = _create(store, request_data, "second")
    with psycopg.connect(postgres_dsn) as locked:
        locked.execute("BEGIN")
        locked.execute(
            "SELECT job_id FROM edition_jobs WHERE job_id = %s FOR UPDATE",
            (first.job_id,),
        )
        other = store.claim_job("worker-b")
        assert other is not None
        assert other.job_id == second.job_id
        locked.rollback()


def test_expired_lease_recovers_same_checkpoint_with_incremented_attempt(
    store: EditionJobStore,
    request_data: EditionRequest,
    postgres_dsn: str,
) -> None:
    created = _create(store, request_data)
    first = store.claim_job("worker-a")
    assert first is not None and first.attempt == 1
    with psycopg.connect(postgres_dsn) as connection:
        connection.execute(
            "UPDATE edition_jobs SET lease_expires_at = clock_timestamp() - "
            "INTERVAL '1 second' WHERE job_id = %s",
            (created.job_id,),
        )
    recovered = store.claim_job("worker-b")
    assert recovered is not None
    assert recovered.job_id == created.job_id
    assert recovered.state is JobState.COLLECTING
    assert recovered.attempt == 2
    assert recovered.lease_owner == "worker-b"


def test_retry_is_explicit_and_bounded(
    store: EditionJobStore,
    request_data: EditionRequest,
) -> None:
    created = _create(store, request_data)
    assert store.claim_job("worker-a", max_attempts=2) is not None
    failed = store.fail_job(
        created.job_id,
        "worker-a",
        code="temporary_failure",
        retryable=True,
        diagnostic="Temporary stage dependency failure.",
        max_attempts=2,
    )
    assert failed.failure_retryable is True
    assert store.requeue_retryable(created.job_id, max_attempts=2) is True
    second = store.claim_job("worker-b", max_attempts=2)
    assert second is not None and second.attempt == 2
    terminal = store.fail_job(
        created.job_id,
        "worker-b",
        code="temporary_failure",
        retryable=True,
        diagnostic="Temporary stage dependency failure.",
        max_attempts=2,
    )
    assert terminal.failure_retryable is False
    assert store.requeue_retryable(created.job_id, max_attempts=2) is False


def test_cancel_does_not_reclassify_ready_or_failed_terminal_jobs(
    store: EditionJobStore,
    request_data: EditionRequest,
    canonical_edition: dict[str, object],
) -> None:
    ready_job = _create(store, request_data, "ready")
    assert store.claim_job("worker-a") is not None
    _advance_to_laying_out(store, ready_job.job_id, "worker-a")
    ready = store.publish_ready_edition(
        ready_job.job_id,
        "worker-a",
        canonical_edition,
        CanonicalEditionValidator(),
    )
    assert store.request_cancellation(ready.job_id).state is JobState.READY

    failed_job = _create(store, request_data, "failed")
    assert store.claim_job("worker-b") is not None
    failed = store.fail_job(
        failed_job.job_id,
        "worker-b",
        code="permanent_failure",
        retryable=False,
        diagnostic="Stage cannot complete.",
    )
    assert store.request_cancellation(failed.job_id).state is JobState.FAILED


def test_worker_uses_injected_stages_and_publishes_valid_immutable_edition(
    store: EditionJobStore,
    request_data: EditionRequest,
    canonical_edition: dict[str, object],
) -> None:
    created = _create(store, request_data)
    calls: list[JobState] = []
    result = EditionJobWorker(
        store,
        "worker-a",
        _successful_executors(canonical_edition, calls),
    ).run_one()
    assert result is not None
    assert result.job_id == created.job_id
    assert result.state is JobState.READY
    assert calls == [
        JobState.COLLECTING,
        JobState.SELECTING,
        JobState.SUMMARIZING,
        JobState.ILLUSTRATING,
        JobState.LAYING_OUT,
    ]
    assert store.get_edition(result.edition_id) == canonical_edition
    response = TestClient(create_app(store)).get(f"/v1/editions/{result.edition_id}")
    assert response.status_code == 200
    assert response.json() == canonical_edition


def test_published_edition_id_rejects_different_content(
    store: EditionJobStore,
    request_data: EditionRequest,
    canonical_edition: dict[str, object],
) -> None:
    first = _create(store, request_data, "first")
    assert store.claim_job("worker-a") is not None
    _advance_to_laying_out(store, first.job_id, "worker-a")
    store.publish_ready_edition(
        first.job_id,
        "worker-a",
        canonical_edition,
        CanonicalEditionValidator(),
    )

    second = _create(store, request_data, "second")
    assert store.claim_job("worker-b") is not None
    _advance_to_laying_out(store, second.job_id, "worker-b")
    changed = copy.deepcopy(canonical_edition)
    changed["edition"]["title"] = "Different immutable content"
    with pytest.raises(EditionImmutableConflict):
        store.publish_ready_edition(
            second.job_id,
            "worker-b",
            changed,
            CanonicalEditionValidator(),
        )


def test_worker_fails_closed_for_invalid_document_and_secret_exception(
    store: EditionJobStore,
    request_data: EditionRequest,
    canonical_edition: dict[str, object],
) -> None:
    invalid = copy.deepcopy(canonical_edition)
    invalid["contract_version"] = "gazet-e.edition.v99"
    first = _create(store, request_data, "invalid")
    result = EditionJobWorker(
        store,
        "worker-a",
        _successful_executors(invalid),
    ).run_one()
    assert result is not None and result.state is JobState.FAILED
    assert result.failure_code == "invalid_edition"

    second = _create(store, request_data, "exception")

    def explode(_job):
        raise RuntimeError("password=hunter2 provider_token=private")

    result = EditionJobWorker(
        store,
        "worker-b",
        {JobState.COLLECTING: explode},
    ).run_one()
    assert result is not None and result.job_id == second.job_id
    assert result.failure_diagnostic == "Stage execution failed safely."
    assert "hunter2" not in json.dumps(result.to_status().model_dump(mode="json"))


def test_worker_preserves_retryable_failure_semantics(
    store: EditionJobStore,
    request_data: EditionRequest,
) -> None:
    _create(store, request_data)

    def temporary(_job):
        raise StageExecutionError(
            code="temporary_dependency",
            retryable=True,
            diagnostic="Temporary dependency unavailable.",
        )

    result = EditionJobWorker(
        store,
        "worker-a",
        {JobState.COLLECTING: temporary},
    ).run_one()
    assert result is not None
    assert result.state is JobState.FAILED
    assert result.failure_retryable is True


def test_fastapi_create_status_cancel_and_error_contracts(
    store: EditionJobStore,
    request_data: EditionRequest,
) -> None:
    client = TestClient(create_app(store))
    payload = request_data.model_dump(mode="json")
    created = client.post(
        "/v1/edition-jobs",
        headers={"Idempotency-Key": "api-key"},
        json=payload,
    )
    assert created.status_code == 202
    job_id = created.json()["job_id"]
    assert client.get(f"/v1/edition-jobs/{job_id}").status_code == 200

    reused = client.post(
        "/v1/edition-jobs",
        headers={"Idempotency-Key": "api-key"},
        json=payload,
    )
    assert reused.status_code == 202
    assert reused.json()["job_id"] == job_id

    changed = dict(payload, locale="en-US")
    assert (
        client.post(
            "/v1/edition-jobs",
            headers={"Idempotency-Key": "api-key"},
            json=changed,
        ).status_code
        == 409
    )
    assert client.post("/v1/edition-jobs", json=payload).status_code == 422
    cancelled = client.post(f"/v1/edition-jobs/{job_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"
    assert client.get("/v1/edition-jobs/missing").status_code == 404
    assert client.get("/v1/editions/missing").status_code == 404
