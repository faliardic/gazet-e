"""Loopback-development composition root for the Q10 API and worker."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import FastAPI

from services.edition_asset_store import DevelopmentAssetStore
from services.edition_integration_models import IntegrationPolicy
from services.edition_integration_pipeline import EditionIntegrationPipeline
from services.edition_job_api import create_app
from services.edition_job_store import EditionJobStore
from services.edition_job_worker import EditionJobWorker
from services.edition_news_fetch import EditionNewsCollector
from services.edition_visual_provider import OpenAIVisualProvider

DEFAULT_BIND_HOST = "127.0.0.1"
DEFAULT_BIND_PORT = 8000


def create_runtime_app() -> FastAPI:
    store, assets = _boundaries()
    store.initialize_schema()
    return create_app(store, asset_store=assets)


def create_authorized_worker() -> EditionJobWorker:
    """Build a worker only after the separately controlled paid gate is enabled."""
    if os.environ.get("GAZETE_Q10_PAID_EXECUTION") != "authorized":
        raise RuntimeError("Q10 paid execution is disabled.")
    store, assets = _boundaries()
    store.initialize_schema()
    worker_base = os.environ.get("GAZETE_WORKER_ID", "q10-loopback-worker")
    worker_id = f"{worker_base}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    pipeline = EditionIntegrationPipeline(
        store=store,
        worker_id=worker_id,
        collector=EditionNewsCollector(),
        visual_provider=OpenAIVisualProvider(),
        asset_store=assets,
        policy=IntegrationPolicy(paid_execution_enabled=True),
    )
    return EditionJobWorker(store, worker_id, pipeline.executors())


def _boundaries() -> tuple[EditionJobStore, DevelopmentAssetStore]:
    dsn = os.environ.get("GAZETE_DATABASE_DSN")
    asset_root = os.environ.get("GAZETE_ASSET_ROOT")
    if not dsn or not asset_root:
        raise RuntimeError("Q10 database and asset boundaries must be configured.")
    root = Path(asset_root)
    if not root.is_absolute():
        raise RuntimeError("Q10 asset root must be absolute.")
    resolved = root.resolve(strict=False)
    repository_root = Path(__file__).resolve().parents[1]
    if resolved == repository_root or resolved.is_relative_to(repository_root):
        raise RuntimeError("Q10 asset root must remain outside the repository.")
    return EditionJobStore(dsn), DevelopmentAssetStore(resolved)
