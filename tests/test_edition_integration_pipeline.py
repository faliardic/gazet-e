from __future__ import annotations

import hashlib
import ipaddress
import json
import multiprocessing
import os
from collections.abc import Iterator
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from services.edition_asset_store import AssetStoreError, DevelopmentAssetStore
from services.edition_integration_models import IntegrationPolicy
from services.edition_integration_pipeline import EditionIntegrationPipeline
from services.edition_integration_runtime import create_authorized_worker
from services.edition_job_api import create_app
from services.edition_job_models import EditionRequest, JobState
from services.edition_job_store import EditionJobStore, PaidDispatchBlocked
from services.edition_job_validation import CanonicalEditionValidator
from services.edition_job_worker import EditionJobWorker
from services.edition_news_fetch import EditionNewsCollector
from services.edition_news_registry import RSS_REGISTRY
from services.edition_visual_models import VisualQAVerdict
from services.edition_visual_provider import (
    GeneratedImageResponse,
    ImageProviderUsage,
    QAProviderResponse,
)

NOW = datetime(2026, 9, 7, 14, 0, tzinfo=timezone.utc)


class _Response:
    status_code = 200
    headers: dict[str, str] = {}

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.url = "https://feeds.example.test/news.xml"

    def iter_content(self, chunk_size: int):
        for offset in range(0, len(self.payload), chunk_size):
            yield self.payload[offset : offset + chunk_size]

    def close(self) -> None:
        return None


class _Session:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.calls = 0

    def get(self, _url: str, **_kwargs: object) -> _Response:
        self.calls += 1
        return _Response(self.payload)


class _VisualProvider:
    def __init__(
        self,
        image_bytes: bytes,
        *,
        verdict: VisualQAVerdict | None = None,
    ) -> None:
        self.image_bytes = image_bytes
        self.verdict = verdict or VisualQAVerdict(status="passed", reason_codes=())
        self.generate_calls = 0
        self.verify_calls = 0

    def generate(self, _brief):
        self.generate_calls += 1
        return GeneratedImageResponse(
            image_bytes=self.image_bytes,
            response_model="gpt-image-2-test",
            usage=ImageProviderUsage(input_tokens=20, output_tokens=10),
        )

    def verify(self, _brief, _image_bytes):
        self.verify_calls += 1
        return QAProviderResponse(
            verdict=self.verdict,
            response_model="gpt-5.6-terra-test",
            input_tokens=90,
            output_tokens=12,
        )


class _FailingAssetStore(DevelopmentAssetStore):
    def put(self, **_kwargs):
        raise AssetStoreError("simulated bounded write failure")


class _PersistentVisualProvider(_VisualProvider):
    def __init__(self, image_bytes: bytes, counter_path: str) -> None:
        super().__init__(image_bytes)
        self._counter_path = Path(counter_path)

    def generate(self, brief):
        _increment_counter(self._counter_path, "generate")
        return super().generate(brief)

    def verify(self, brief, image_bytes):
        _increment_counter(self._counter_path, "verify")
        return super().verify(brief, image_bytes)


def _increment_counter(path: Path, field: str) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    value[field] += 1
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _process_worker(
    dsn: str,
    asset_root: str,
    counter_path: str,
    worker_id: str,
    max_stages: int | None,
    queue,
) -> None:
    try:
        _assert_dedicated_postgres(dsn)
        image = BytesIO()
        Image.new("RGB", (1536, 1024), (35, 55, 89)).save(
            image, format="WEBP", quality=80
        )
        pipeline = _pipeline(
            EditionJobStore(dsn),
            worker_id,
            EditionNewsCollector(
                registry=(RSS_REGISTRY[0],),
                session=_Session(_rss(single=True)),
                clock=lambda: NOW,
                sleeper=lambda _delay: None,
            ),
            _PersistentVisualProvider(image.getvalue(), counter_path),
            DevelopmentAssetStore(Path(asset_root).resolve()),
        )
        result = EditionJobWorker(
            EditionJobStore(dsn), worker_id, pipeline.executors()
        ).run_one(max_stages=max_stages)
        queue.put(
            {
                "ok": result is not None,
                "state": None if result is None else result.state.value,
                "edition_id": None if result is None else result.edition_id,
            }
        )
    except BaseException as error:
        queue.put({"ok": False, "code": type(error).__name__})


def _process_api_probe(dsn: str, asset_root: str, edition_id: str, queue) -> None:
    try:
        _assert_dedicated_postgres(dsn)
        client = TestClient(
            create_app(
                EditionJobStore(dsn),
                asset_store=DevelopmentAssetStore(Path(asset_root).resolve()),
            )
        )
        edition_response = client.get(f"/v1/editions/{edition_id}")
        document = edition_response.json()
        asset_id = document["articles"][0]["visual"]["asset_id"]
        asset_response = client.get(
            f"/v1/editions/{edition_id}/assets/"
            f"{asset_id.removeprefix('sha256:')}"
        )
        queue.put(
            {
                "ok": edition_response.status_code == 200
                and asset_response.status_code == 200,
                "contract_version": document.get("contract_version"),
                "asset_bytes": len(asset_response.content),
            }
        )
    except BaseException as error:
        queue.put({"ok": False, "code": type(error).__name__})


@pytest.fixture
def store() -> Iterator[EditionJobStore]:
    dsn = _dsn()
    result = EditionJobStore(dsn)
    result.initialize_schema()
    _truncate(dsn)
    yield result
    _truncate(dsn)


@pytest.fixture
def image_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (1536, 1024), (35, 55, 89)).save(
        output, format="WEBP", quality=80
    )
    return output.getvalue()


def test_real_worker_api_asset_and_exact_cache_path(
    store: EditionJobStore,
    tmp_path: Path,
    image_bytes: bytes,
) -> None:
    session = _Session(_rss())
    collector = EditionNewsCollector(
        registry=(RSS_REGISTRY[0],),
        session=session,
        clock=lambda: NOW,
        sleeper=lambda _delay: None,
    )
    visuals = _VisualProvider(image_bytes)
    assets = DevelopmentAssetStore((tmp_path / "objects").resolve())
    client = TestClient(create_app(store, asset_store=assets))
    request = _request()

    created = client.post(
        "/v1/edition-jobs",
        headers={"Idempotency-Key": "q10-e2e"},
        json=request.model_dump(mode="json"),
    )
    repeated = client.post(
        "/v1/edition-jobs",
        headers={"Idempotency-Key": "q10-e2e"},
        json=request.model_dump(mode="json"),
    )
    assert created.status_code == 202
    assert repeated.json()["job_id"] == created.json()["job_id"]

    worker_id = "q10-worker-a"
    pipeline = _pipeline(store, worker_id, collector, visuals, assets)
    result = EditionJobWorker(store, worker_id, pipeline.executors()).run_one()
    assert result is not None
    assert result.state is JobState.READY, result.failure_code
    assert visuals.generate_calls == visuals.verify_calls == 2
    assert session.calls == 1

    restarted_client = TestClient(
        create_app(EditionJobStore(_dsn()), asset_store=assets)
    )
    edition_response = restarted_client.get(f"/v1/editions/{result.edition_id}")
    assert edition_response.status_code == 200
    edition = edition_response.json()
    CanonicalEditionValidator().validate(edition)
    assert len(edition["articles"]) == 2
    asset_id = edition["articles"][0]["visual"]["asset_id"]
    asset_response = restarted_client.get(
        f"/v1/editions/{result.edition_id}/assets/{asset_id.removeprefix('sha256:')}"
    )
    assert asset_response.status_code == 200
    assert asset_response.content == image_bytes
    assert asset_response.headers["content-type"] == "image/webp"
    assert restarted_client.get(
        f"/v1/editions/not-this-edition/assets/{asset_id.removeprefix('sha256:')}"
    ).status_code == 404
    report = restarted_client.get(
        f"/v1/edition-jobs/{result.job_id}/integration"
    )
    assert report.status_code == 200
    assert report.json()["edition_id"] == result.edition_id

    first_counts = (visuals.generate_calls, visuals.verify_calls)
    second = store.create_job("q10-cache", request)
    next_worker = "q10-worker-cache"
    next_pipeline = _pipeline(store, next_worker, collector, visuals, assets)
    second_result = EditionJobWorker(
        store, next_worker, next_pipeline.executors()
    ).run_one()
    assert second_result is not None and second_result.state is JobState.READY
    assert first_counts == (visuals.generate_calls, visuals.verify_calls)
    assert second.job_id != result.job_id
    usage = store.get_integration_run(result.job_id)
    assert usage["logical_provider_calls"] == 4
    assert usage["generated_images"] == 2
    assert float(usage["estimated_cost_usd"]) < 0.15


def test_worker_process_replacement_resumes_from_durable_checkpoints(
    store: EditionJobStore,
    tmp_path: Path,
    image_bytes: bytes,
) -> None:
    collector = EditionNewsCollector(
        registry=(RSS_REGISTRY[0],),
        session=_Session(_rss(single=True)),
        clock=lambda: NOW,
    )
    visuals = _VisualProvider(image_bytes)
    assets = DevelopmentAssetStore((tmp_path / "objects").resolve())
    job = store.create_job("q10-recovery", _request())
    first_store = EditionJobStore(_dsn())
    first_pipeline = _pipeline(
        first_store, "replacement-first", collector, visuals, assets
    )
    current = EditionJobWorker(
        first_store, "replacement-first", first_pipeline.executors()
    ).run_one(max_stages=2)
    assert current is not None and current.state is JobState.ILLUSTRATING
    _expire_lease(job.job_id)
    final_store = EditionJobStore(_dsn())
    pipeline = _pipeline(
        final_store, "replacement-final", collector, visuals, assets
    )
    final = EditionJobWorker(
        final_store, "replacement-final", pipeline.executors()
    ).run_one()
    assert final is not None
    assert final.state is JobState.READY, final.failure_code
    assert visuals.generate_calls == 1


def test_separate_worker_and_api_processes_reuse_completed_visual_work(
    store: EditionJobStore,
    tmp_path: Path,
) -> None:
    dsn = _dsn()
    asset_root = (tmp_path / "process-objects").resolve()
    counter_path = (tmp_path / "provider-counts.json").resolve()
    counter_path.write_text(
        json.dumps({"generate": 0, "verify": 0}), encoding="utf-8"
    )
    job = store.create_job("q10-real-process-recovery", _request())
    context = multiprocessing.get_context("spawn")

    first_queue = context.Queue()
    first = context.Process(
        target=_process_worker,
        args=(
            dsn,
            str(asset_root),
            str(counter_path),
            "process-worker-a",
            3,
            first_queue,
        ),
    )
    first.start()
    first.join(timeout=30)
    assert first.exitcode == 0
    first_result = first_queue.get(timeout=5)
    assert first_result == {"ok": True, "state": "laying_out", "edition_id": None}

    _expire_lease(job.job_id)
    second_queue = context.Queue()
    second = context.Process(
        target=_process_worker,
        args=(
            dsn,
            str(asset_root),
            str(counter_path),
            "process-worker-b",
            None,
            second_queue,
        ),
    )
    second.start()
    second.join(timeout=30)
    assert second.exitcode == 0
    second_result = second_queue.get(timeout=5)
    assert second_result["ok"] is True
    assert second_result["state"] == "ready"
    edition_id = second_result["edition_id"]
    assert isinstance(edition_id, str)
    assert json.loads(counter_path.read_text(encoding="utf-8")) == {
        "generate": 1,
        "verify": 1,
    }

    api_queue = context.Queue()
    api_process = context.Process(
        target=_process_api_probe,
        args=(dsn, str(asset_root), edition_id, api_queue),
    )
    api_process.start()
    api_process.join(timeout=30)
    assert api_process.exitcode == 0
    api_result = api_queue.get(timeout=5)
    assert api_result["ok"] is True
    assert api_result["contract_version"] == "gazet-e.edition.v2"
    assert api_result["asset_bytes"] > 0


def test_laying_out_reentry_freezes_edition_identity_and_timestamp(
    store: EditionJobStore,
    tmp_path: Path,
    image_bytes: bytes,
) -> None:
    collector = EditionNewsCollector(
        registry=(RSS_REGISTRY[0],),
        session=_Session(_rss(single=True)),
        clock=lambda: NOW,
    )
    visuals = _VisualProvider(image_bytes)
    assets = DevelopmentAssetStore((tmp_path / "objects").resolve())
    job = store.create_job("q10-layout-reentry", _request())
    pipeline = _pipeline(store, "layout-worker", collector, visuals, assets)
    laying_out = EditionJobWorker(
        store, "layout-worker", pipeline.executors()
    ).run_one(max_stages=3)
    assert laying_out is not None and laying_out.state is JobState.LAYING_OUT

    first = pipeline.assemble(laying_out)
    second = pipeline.assemble(laying_out)

    assert first == second
    assert first.edition_document is not None
    ready = store.publish_ready_edition(
        job.job_id,
        "layout-worker",
        first.edition_document,
        CanonicalEditionValidator(),
        manifest_version=first.manifest_version,
        manifest=first.manifest,
        expected_attempt=laying_out.attempt,
    )
    assert ready.state is JobState.READY
    assert ready.edition_id == first.edition_document["edition"]["id"]


def test_cancellation_and_unknown_outcome_block_additional_dispatch(
    store: EditionJobStore,
) -> None:
    job = store.create_job("q10-fence", _request())
    claimed = store.claim_job("fence-a", lease_seconds=30)
    assert claimed is not None
    policy = IntegrationPolicy(paid_execution_enabled=True)
    store.ensure_integration_run(
        job.job_id,
        "fence-a",
        expected_attempt=claimed.attempt,
        policy_version=policy.version,
        policy_fingerprint=policy.fingerprint(),
        policy=policy.model_dump(mode="json"),
    )
    cache_key = "sha256:" + "a" * 64
    operation_id = "visual:" + cache_key
    reserved = store.reserve_paid_operation(
        job.job_id,
        "fence-a",
        expected_attempt=claimed.attempt,
        operation_id=operation_id,
        artifact_kind="visual",
        cache_key=cache_key,
        logical_calls=2,
        transport_attempts=4,
        generated_images=1,
        estimated_cost_usd=0.08,
    )
    assert reserved["state"] == "reserved"
    store.request_cancellation(job.job_id)
    with pytest.raises(PaidDispatchBlocked):
        store.assert_dispatch_allowed(
            job.job_id,
            "fence-a",
            operation_id,
            expected_attempt=claimed.attempt,
        )

    _expire_lease(job.job_id)
    cancelled = store.claim_job("fence-b")
    assert cancelled is not None and cancelled.state is JobState.CANCELLED

    uncertain_job = store.create_job("q10-uncertain", _request())
    uncertain_claim = store.claim_job("uncertain-a", lease_seconds=30)
    assert uncertain_claim is not None
    store.ensure_integration_run(
        uncertain_job.job_id,
        "uncertain-a",
        expected_attempt=uncertain_claim.attempt,
        policy_version=policy.version,
        policy_fingerprint=policy.fingerprint(),
        policy=policy.model_dump(mode="json"),
    )
    store.reserve_paid_operation(
        uncertain_job.job_id,
        "uncertain-a",
        expected_attempt=uncertain_claim.attempt,
        operation_id=operation_id,
        artifact_kind="visual",
        cache_key=cache_key,
        logical_calls=2,
        transport_attempts=4,
        generated_images=1,
        estimated_cost_usd=0.08,
    )
    _expire_lease(uncertain_job.job_id)
    resumed = store.claim_job("uncertain-b", lease_seconds=30)
    assert resumed is not None and resumed.state is JobState.COLLECTING
    uncertain = store.reserve_paid_operation(
        uncertain_job.job_id,
        "uncertain-b",
        expected_attempt=resumed.attempt,
        operation_id=operation_id,
        artifact_kind="visual",
        cache_key=cache_key,
        logical_calls=2,
        transport_attempts=4,
        generated_images=1,
        estimated_cost_usd=0.08,
    )
    assert uncertain["state"] == "uncertain"
    with pytest.raises(PaidDispatchBlocked):
        store.assert_dispatch_allowed(
            uncertain_job.job_id,
            "uncertain-b",
            operation_id,
            expected_attempt=resumed.attempt,
        )


def test_persistent_budget_scope_covers_distinct_jobs_in_one_authorized_run(
    store: EditionJobStore,
) -> None:
    policy = IntegrationPolicy(paid_execution_enabled=True)
    cache_key = "sha256:" + "9" * 64
    for index in range(2):
        created = store.create_job(f"q10-budget-scope-{index}", _request())
        claimed = store.claim_job(f"budget-worker-{index}", lease_seconds=30)
        assert claimed is not None and claimed.job_id == created.job_id
        store.ensure_integration_run(
            created.job_id,
            f"budget-worker-{index}",
            expected_attempt=claimed.attempt,
            policy_version=policy.version,
            policy_fingerprint=policy.fingerprint(),
            policy=policy.model_dump(mode="json"),
        )
        if index == 0:
            store.reserve_paid_operation(
                created.job_id,
                f"budget-worker-{index}",
                expected_attempt=claimed.attempt,
                operation_id=f"visual:{cache_key}",
                artifact_kind="visual",
                cache_key=cache_key,
                logical_calls=6,
                transport_attempts=12,
                generated_images=3,
                estimated_cost_usd=0.24,
            )
        else:
            with pytest.raises(PaidDispatchBlocked, match="budget is exhausted"):
                store.reserve_paid_operation(
                    created.job_id,
                    f"budget-worker-{index}",
                    expected_attempt=claimed.attempt,
                    operation_id=f"visual:{cache_key}",
                    artifact_kind="visual",
                    cache_key=cache_key,
                    logical_calls=4,
                    transport_attempts=8,
                    generated_images=2,
                    estimated_cost_usd=0.16,
                )


def test_mid_batch_process_loss_reuses_success_and_never_replays_unknown_call(
    store: EditionJobStore,
    tmp_path: Path,
    image_bytes: bytes,
) -> None:
    collector = EditionNewsCollector(
        registry=(RSS_REGISTRY[0],),
        session=_Session(_rss()),
        clock=lambda: NOW,
    )
    visuals = _CrashOnSecondVisual(image_bytes)
    assets = DevelopmentAssetStore((tmp_path / "objects").resolve())
    job = store.create_job("q10-mid-batch", _request())
    first_pipeline = _pipeline(store, "crash-worker", collector, visuals, assets)

    with pytest.raises(SystemExit):
        EditionJobWorker(
            store, "crash-worker", first_pipeline.executors()
        ).run_one()
    assert store.get_job(job.job_id).state is JobState.ILLUSTRATING
    assert visuals.generate_calls == 2
    assert visuals.verify_calls == 1

    _expire_lease(job.job_id)
    replacement = EditionJobStore(_dsn())
    resumed_visuals = _VisualProvider(image_bytes)
    resumed_pipeline = _pipeline(
        replacement,
        "resume-worker",
        collector,
        resumed_visuals,
        assets,
    )
    result = EditionJobWorker(
        replacement, "resume-worker", resumed_pipeline.executors()
    ).run_one()

    assert result is not None and result.state is JobState.READY
    assert visuals.generate_calls == 2
    assert visuals.verify_calls == 1
    assert resumed_visuals.generate_calls == resumed_visuals.verify_calls == 0
    visual_manifest = replacement.get_stage_manifest(
        job.job_id, JobState.ILLUSTRATING
    )["manifest"]
    assert [item["status"] for item in visual_manifest["items"]] == [
        "ready",
        "unavailable",
    ]
    assert visual_manifest["items"][1]["reason_codes"] == [
        "provider_outcome_uncertain"
    ]
    run = replacement.get_integration_run(job.job_id)
    assert run["logical_provider_calls"] == 4
    assembly = replacement.get_stage_manifest(
        job.job_id, JobState.LAYING_OUT
    )["manifest"]
    assert assembly["selected_story_count"] == 2
    assert assembly["placed_story_count"] == 1
    assert assembly["skipped"][0]["reason_codes"] == [
        "provider_outcome_uncertain"
    ]


def test_object_store_is_content_addressed_immutable_and_tamper_evident(
    tmp_path: Path,
    image_bytes: bytes,
) -> None:
    assets = DevelopmentAssetStore((tmp_path / "objects").resolve())
    asset_id = "sha256:" + hashlib.sha256(image_bytes).hexdigest()
    first = assets.put(
        asset_id=asset_id,
        content_hash=asset_id,
        media_type="image/webp",
        width=1536,
        height=1024,
        data=image_bytes,
    )
    second = assets.put(
        asset_id=asset_id,
        content_hash=asset_id,
        media_type="image/webp",
        width=1536,
        height=1024,
        data=image_bytes,
    )
    assert first == second
    stored_path = assets.root / asset_id[7:9] / f"{asset_id[7:]}.webp"
    stored_path.write_bytes(b"tampered")
    with pytest.raises(AssetStoreError):
        assets.read(
            asset_hex=asset_id.removeprefix("sha256:"),
            media_type="image/webp",
            width=1536,
            height=1024,
        )
    with pytest.raises(AssetStoreError):
        assets.read(
            asset_hex="../outside",
            media_type="image/webp",
            width=1536,
            height=1024,
        )
    with pytest.raises(AssetStoreError):
        assets.put(
            asset_id=asset_id,
            content_hash=asset_id,
            media_type="image/webp",
            width=1,
            height=1,
            data=image_bytes,
        )


def test_provider_execution_is_disabled_even_when_a_key_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    monkeypatch.delenv("GAZETE_Q10_PAID_EXECUTION", raising=False)
    with pytest.raises(RuntimeError, match="paid execution is disabled"):
        create_authorized_worker()


def test_failed_visual_never_publishes_a_ready_edition(
    store: EditionJobStore,
    tmp_path: Path,
    image_bytes: bytes,
) -> None:
    collector = EditionNewsCollector(
        registry=(RSS_REGISTRY[0],),
        session=_Session(_rss(single=True)),
        clock=lambda: NOW,
    )
    visuals = _VisualProvider(
        image_bytes,
        verdict=VisualQAVerdict(
            status="failed",
            reason_codes=("unsupported_visual_detail",),
        ),
    )
    assets = DevelopmentAssetStore((tmp_path / "objects").resolve())
    job = store.create_job("q10-fail-closed", _request())
    pipeline = _pipeline(store, "q10-fail-worker", collector, visuals, assets)

    result = EditionJobWorker(
        store, "q10-fail-worker", pipeline.executors()
    ).run_one()

    assert result is not None and result.state is JobState.FAILED
    assert result.failure_code == "no_publishable_story"
    assert result.edition_id is None
    assert not any(assets.root.rglob("*.webp"))
    with psycopg.connect(_dsn()) as connection:
        assert connection.execute("SELECT count(*) FROM editions").fetchone()[0] == 0


def test_layout_overflow_is_reported_without_publishing_unplaced_article(
    store: EditionJobStore,
    tmp_path: Path,
    image_bytes: bytes,
) -> None:
    collector = EditionNewsCollector(
        registry=(RSS_REGISTRY[0],),
        session=_Session(_rss_with_long_headline()),
        clock=lambda: NOW,
    )
    visuals = _VisualProvider(image_bytes)
    assets = DevelopmentAssetStore((tmp_path / "objects").resolve())
    job = store.create_job("q10-layout-overflow", _request())
    pipeline = _pipeline(store, "overflow-worker", collector, visuals, assets)
    result = EditionJobWorker(
        store, "overflow-worker", pipeline.executors()
    ).run_one()

    assert result is not None and result.state is JobState.READY
    report = store.get_stage_manifest(job.job_id, JobState.LAYING_OUT)["manifest"]
    assert report["selected_story_count"] == 2
    assert report["placed_story_count"] == 1
    assert report["overflow"][0]["reason"] == "content_exceeds_capacity"
    edition = store.get_edition(result.edition_id)
    assert len(edition["articles"]) == 1
    assert report["overflow"][0]["article_id"] not in {
        article["id"] for article in edition["articles"]
    }


def test_asset_write_failure_does_not_advance_to_ready(
    store: EditionJobStore,
    tmp_path: Path,
    image_bytes: bytes,
) -> None:
    collector = EditionNewsCollector(
        registry=(RSS_REGISTRY[0],),
        session=_Session(_rss(single=True)),
        clock=lambda: NOW,
    )
    visuals = _VisualProvider(image_bytes)
    assets = _FailingAssetStore((tmp_path / "objects").resolve())
    store.create_job("q10-asset-write-failure", _request())
    pipeline = _pipeline(
        store, "asset-failure-worker", collector, visuals, assets
    )

    result = EditionJobWorker(
        store, "asset-failure-worker", pipeline.executors()
    ).run_one()

    assert result is not None and result.state is JobState.FAILED
    assert result.failure_code == "no_publishable_story"
    assert result.edition_id is None


def _pipeline(store, worker_id, collector, visuals, assets):
    return EditionIntegrationPipeline(
        store=store,
        worker_id=worker_id,
        collector=collector,
        visual_provider=visuals,
        asset_store=assets,
        policy=IntegrationPolicy(paid_execution_enabled=True),
        clock=lambda: NOW,
    )


def _request() -> EditionRequest:
    return EditionRequest(
        request_version="gazet-e.edition-request.v2",
        locale="tr-TR",
        timezone="Europe/Istanbul",
    )


def _rss(*, single: bool = False) -> bytes:
    second = "" if single else """
      <item><title>Teknoloji yatırımları için yeni program açıklandı</title>
      <link>https://news.example.test/technology</link>
      <description>Programın kapsamı ve takvimi kamuoyuna duyuruldu.</description>
      <pubDate>Mon, 07 Sep 2026 12:30:00 GMT</pubDate></item>"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><title>Test</title>
      <item><title>Merkez Bankası politika kararını kamuoyuna açıkladı</title>
      <link>https://news.example.test/economy</link>
      <description>Kurul toplantısının sonucu resmi açıklamayla paylaşıldı.</description>
      <pubDate>Mon, 07 Sep 2026 13:00:00 GMT</pubDate></item>
      {second}</channel></rss>""".encode()


def _rss_with_long_headline() -> bytes:
    long_headline = (
        "Ekonomi programının ayrıntıları kamuoyuna açıklandı ve uygulama "
        "takviminin bütün aşamaları kurumların ortak değerlendirmesiyle "
        "önümüzdeki döneme yayılan kapsamlı bir çerçevede duyuruldu"
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><title>Test</title>
      <item><title>Kısa ekonomi programı açıklandı</title>
      <link>https://news.example.test/short</link>
      <description>Programın temel başlıkları kamuoyuyla paylaşıldı.</description>
      <pubDate>Mon, 07 Sep 2026 13:00:00 GMT</pubDate></item>
      <item><title>{long_headline}</title>
      <link>https://news.example.test/long</link>
      <description>Uygulama takvimi resmi açıklamayla duyuruldu.</description>
      <pubDate>Mon, 07 Sep 2026 12:30:00 GMT</pubDate></item>
    </channel></rss>""".encode()


def _dsn() -> str:
    value = os.environ.get("GAZETE_TEST_POSTGRES_DSN")
    if not value:
        pytest.fail("Dedicated local PostgreSQL test boundary is required.")
    _assert_dedicated_postgres(value)
    return value


def _assert_dedicated_postgres(dsn: str, *, connect=psycopg.connect) -> None:
    """Reject every non-Q05 disposable loopback target before a write."""

    with connect(dsn) as connection:
        identity = connection.execute(
            "SELECT current_database(), current_user, inet_server_addr()"
        ).fetchone()
    if identity is None or (
        identity[0] != "gazete_q05_test"
        or identity[1] != "gazete_q05_test"
        or not ipaddress.ip_interface(str(identity[2])).ip.is_loopback
    ):
        raise RuntimeError(
            "Refusing Q10 test mutation outside the dedicated disposable "
            "gazete_q05_test database/role on loopback."
        )


class _CrashOnSecondVisual(_VisualProvider):
    def generate(self, brief):
        if self.generate_calls == 1:
            self.generate_calls += 1
            raise SystemExit("simulated process loss")
        return super().generate(brief)


def _truncate(dsn: str) -> None:
    _assert_dedicated_postgres(dsn)
    with psycopg.connect(dsn) as connection:
        connection.execute("TRUNCATE edition_jobs, editions CASCADE")


def _expire_lease(job_id: str) -> None:
    dsn = _dsn()
    _assert_dedicated_postgres(dsn)
    with psycopg.connect(dsn) as connection:
        connection.execute(
            """
            UPDATE edition_jobs
            SET lease_expires_at = clock_timestamp() - interval '1 second'
            WHERE job_id = %s
            """,
            (job_id,),
        )


def test_database_guard_rejects_wrong_target_before_mutation() -> None:
    statements: list[str] = []

    class _Cursor:
        def fetchone(self):
            return ("shared_database", "shared_role", "10.0.0.10")

    class _Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, statement, *_args):
            statements.append(str(statement))
            return _Cursor()

    with pytest.raises(RuntimeError, match="Refusing Q10 test mutation"):
        _assert_dedicated_postgres(
            "postgresql://not-used",
            connect=lambda _dsn: _Connection(),
        )

    assert len(statements) == 1
    assert statements[0].startswith("SELECT current_database()")
    assert all("TRUNCATE" not in statement and "UPDATE" not in statement for statement in statements)
