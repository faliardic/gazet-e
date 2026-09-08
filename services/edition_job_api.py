"""FastAPI boundary for durable Q05 edition jobs."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException, Response, status

from services.edition_asset_store import AssetStoreError, DevelopmentAssetStore
from services.edition_job_models import EditionRequest, JobStatus
from services.edition_job_store import (
    EditionJobStore,
    IdempotencyConflict,
    JobNotFound,
)


def create_app(
    store: EditionJobStore,
    *,
    asset_store: DevelopmentAssetStore | None = None,
) -> FastAPI:
    app = FastAPI(title="Gazet+E Edition Job Service", version="0.1.0")

    @app.post(
        "/v1/edition-jobs",
        response_model=JobStatus,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def create_edition_job(
        request: EditionRequest,
        idempotency_key: Annotated[
            str | None,
            Header(alias="Idempotency-Key"),
        ] = None,
    ) -> JobStatus:
        try:
            return store.create_job(idempotency_key, request).to_status()
        except ValueError as error:
            if isinstance(error, IdempotencyConflict):
                raise HTTPException(status_code=409, detail=str(error)) from error
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/v1/edition-jobs/{job_id}", response_model=JobStatus)
    def get_edition_job(job_id: str) -> JobStatus:
        try:
            return store.get_job(job_id).to_status()
        except JobNotFound as error:
            raise HTTPException(status_code=404, detail="Edition job not found.") from error

    @app.post("/v1/edition-jobs/{job_id}/cancel", response_model=JobStatus)
    def cancel_edition_job(job_id: str) -> JobStatus:
        try:
            return store.request_cancellation(job_id).to_status()
        except JobNotFound as error:
            raise HTTPException(status_code=404, detail="Edition job not found.") from error

    @app.get("/v1/editions/{edition_id}", response_model=dict[str, Any])
    def get_edition(edition_id: str) -> dict[str, Any]:
        try:
            return store.get_edition(edition_id)
        except JobNotFound as error:
            raise HTTPException(status_code=404, detail="Edition not found.") from error

    @app.get("/v1/edition-jobs/{job_id}/integration", response_model=dict[str, Any])
    def get_integration_report(job_id: str) -> dict[str, Any]:
        try:
            job = store.get_job(job_id)
            report = store.get_stage_manifest(job_id, "laying_out")["manifest"]
        except JobNotFound as error:
            raise HTTPException(
                status_code=404,
                detail="Integration report is not available.",
            ) from error
        if job.state.value != "ready":
            raise HTTPException(
                status_code=409,
                detail="Integration report is not final.",
            )
        return report

    @app.get("/v1/editions/{edition_id}/assets/{asset_hex}")
    def get_edition_asset(edition_id: str, asset_hex: str) -> Response:
        if asset_store is None:
            raise HTTPException(status_code=404, detail="Edition asset not found.")
        try:
            edition = store.get_edition(edition_id)
            expected_id = f"sha256:{asset_hex}"
            matches = [
                article["visual"]
                for article in edition["articles"]
                if article["visual"]["asset_id"] == expected_id
            ]
            if not matches:
                raise AssetStoreError("asset is outside this edition")
            metadata = matches[0]
            data = asset_store.read(
                asset_hex=asset_hex,
                media_type="image/webp",
                width=metadata["width"],
                height=metadata["height"],
            )
        except (JobNotFound, AssetStoreError, KeyError, TypeError):
            raise HTTPException(
                status_code=404,
                detail="Edition asset not found.",
            ) from None
        return Response(
            content=data,
            media_type="image/webp",
            headers={
                "Cache-Control": "private, immutable, max-age=31536000",
                "ETag": f'"sha256:{asset_hex}"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    return app
