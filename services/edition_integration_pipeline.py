"""Q10 adapters that compose the reviewed Q06-Q09 contracts durably."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from services.edition_asset_store import AssetStoreError, DevelopmentAssetStore
from services.edition_integration_models import (
    ASSEMBLY_MANIFEST_VERSION,
    COLLECTION_MANIFEST_VERSION,
    SELECTION_MANIFEST_VERSION,
    SUMMARY_MANIFEST_VERSION,
    VISUAL_MANIFEST_VERSION,
    IntegrationPolicy,
    IntegrationStageResult,
    sha256_json,
)
from services.edition_job_models import JobState
from services.edition_job_store import (
    EditionJobStore,
    IntegrationConflict,
    JobNotFound,
    PaidDispatchBlocked,
)
from services.edition_job_worker import StageExecutionError
from services.edition_layout_engine import LAYOUT_ENGINE_VERSION, build_layout_plan
from services.edition_layout_models import LayoutPolicy, LayoutStory
from services.edition_news_models import CollectionResult, RankedCollection
from services.edition_news_rank import build_ranked_collection
from services.edition_summary_facts import build_fact_packet, summary_cache_key
from services.edition_summary_models import SummaryArtifact
from services.edition_summary_pipeline import (
    EDITORIAL_POLICY_VERSION,
    GENERATOR_PROMPT_VERSION,
    INPUT_USD_PER_MILLION,
    OUTPUT_USD_PER_MILLION,
    VERIFIER_PROMPT_VERSION,
    EditorialSummaryPipeline,
    ExecutionBudget as SummaryBudget,
)
from services.edition_summary_provider import (
    PROVIDER_ID as SUMMARY_PROVIDER_ID,
    REQUESTED_MODEL as SUMMARY_MODEL,
    SummaryProvider,
)
from services.edition_visual_brief import build_visual_brief, image_cache_key
from services.edition_visual_models import VisualArtifact, VisualResult
from services.edition_visual_pipeline import (
    EditorialVisualPipeline,
    ExecutionBudget as VisualBudget,
)
from services.edition_visual_provider import (
    PROVIDER_ID as VISUAL_PROVIDER_ID,
    QA_MODEL,
    REQUESTED_IMAGE_MODEL,
    VisualProvider,
)


class EditionIntegrationPipeline:
    """State adapters used by the existing lease-aware Q05 worker."""

    def __init__(
        self,
        *,
        store: EditionJobStore,
        worker_id: str,
        collector: Any,
        summary_provider: SummaryProvider,
        visual_provider: VisualProvider,
        asset_store: DevelopmentAssetStore,
        policy: IntegrationPolicy = IntegrationPolicy(),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._worker_id = worker_id
        self._collector = collector
        self._summary_provider = summary_provider
        self._visual_provider = visual_provider
        self._assets = asset_store
        self._policy = policy
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def executors(self) -> Mapping[JobState, Callable[[Any], IntegrationStageResult]]:
        return {
            JobState.COLLECTING: self.collect,
            JobState.SELECTING: self.select,
            JobState.SUMMARIZING: self.summarize,
            JobState.ILLUSTRATING: self.illustrate,
            JobState.LAYING_OUT: self.assemble,
        }

    def collect(self, job: Any) -> IntegrationStageResult:
        self._ensure_run(job.job_id)
        collection = self._collector.collect()
        if not isinstance(collection, CollectionResult):
            raise _stage_error("collection_contract_error")
        if len(collection.candidates) > self._policy.max_collected_candidates:
            raise _stage_error("collection_capacity_exceeded")
        manifest = collection.model_dump(mode="json")
        return IntegrationStageResult(COLLECTION_MANIFEST_VERSION, manifest)

    def select(self, job: Any) -> IntegrationStageResult:
        collection = CollectionResult.model_validate(
            self._manifest(job.job_id, JobState.COLLECTING)
        )
        ranked = build_ranked_collection(collection, now=collection.collected_at)
        selected = tuple(ranked.clusters[: self._policy.max_selected_clusters])
        selected_ids = {
            article_id for cluster in selected for article_id in cluster.member_article_ids
        }
        projection = RankedCollection(
            ranking_policy_version=ranked.ranking_policy_version,
            cluster_policy_version=ranked.cluster_policy_version,
            generated_at=ranked.generated_at,
            articles=tuple(
                article for article in ranked.articles if article.article_id in selected_ids
            ),
            rejected_articles=(),
            clusters=selected,
            fetch_results=(),
        )
        if not projection.clusters:
            raise _stage_error("no_ranked_story")
        return IntegrationStageResult(
            SELECTION_MANIFEST_VERSION,
            projection.model_dump(mode="json"),
        )

    def summarize(self, job: Any) -> IntegrationStageResult:
        ranked = RankedCollection.model_validate(
            self._manifest(job.job_id, JobState.SELECTING)
        )
        entries: list[dict[str, Any]] = []
        for cluster in ranked.clusters:
            packet = build_fact_packet(ranked, cluster.cluster_id, locale=self._request_locale(job.job_id))
            artifact = self._summary(job.job_id, packet)
            if artifact is None:
                entries.append(
                    {
                        "cluster_id": cluster.cluster_id,
                        "status": "unavailable",
                        "reason_codes": ["provider_outcome_uncertain"],
                    }
                )
            else:
                entries.append(
                    {
                        "cluster_id": cluster.cluster_id,
                        "status": artifact.status,
                        "reason_codes": list(artifact.reason_codes),
                        "artifact": artifact.model_dump(mode="json"),
                    }
                )
        return IntegrationStageResult(SUMMARY_MANIFEST_VERSION, {"items": entries})

    def illustrate(self, job: Any) -> IntegrationStageResult:
        ranked = RankedCollection.model_validate(
            self._manifest(job.job_id, JobState.SELECTING)
        )
        summaries = _ready_summaries(
            self._manifest(job.job_id, JobState.SUMMARIZING)
        )
        entries: list[dict[str, Any]] = []
        for cluster in ranked.clusters:
            summary = summaries.get(cluster.cluster_id)
            if summary is None:
                entries.append(
                    {
                        "cluster_id": cluster.cluster_id,
                        "status": "unavailable",
                        "reason_codes": ["summary_unavailable"],
                    }
                )
                continue
            packet = build_fact_packet(ranked, cluster.cluster_id, locale=self._request_locale(job.job_id))
            brief = build_visual_brief(packet, summary=summary)
            result = self._visual(job.job_id, brief)
            if result is None:
                entries.append(
                    {
                        "cluster_id": cluster.cluster_id,
                        "status": "unavailable",
                        "reason_codes": ["provider_outcome_uncertain"],
                    }
                )
            else:
                entries.append(
                    {
                        "cluster_id": cluster.cluster_id,
                        "status": result.artifact.status,
                        "reason_codes": list(result.artifact.reason_codes),
                        "artifact": result.artifact.model_dump(mode="json"),
                    }
                )
        return IntegrationStageResult(VISUAL_MANIFEST_VERSION, {"items": entries})

    def assemble(self, job: Any) -> IntegrationStageResult:
        ranked = RankedCollection.model_validate(
            self._manifest(job.job_id, JobState.SELECTING)
        )
        summary_manifest = self._manifest(job.job_id, JobState.SUMMARIZING)
        visual_manifest = self._manifest(job.job_id, JobState.ILLUSTRATING)
        summaries = _ready_summaries(summary_manifest)
        visuals = _ready_visuals(visual_manifest)
        summary_entries = {
            item["cluster_id"]: item for item in summary_manifest.get("items", [])
        }
        visual_entries = {
            item["cluster_id"]: item for item in visual_manifest.get("items", [])
        }
        articles_by_id = {item.article_id: item for item in ranked.articles}
        stories: list[LayoutStory] = []
        pairs: dict[str, tuple[SummaryArtifact, VisualArtifact]] = {}
        for rank, cluster in enumerate(ranked.clusters):
            summary = summaries.get(cluster.cluster_id)
            visual = visuals.get(cluster.cluster_id)
            if summary is None or visual is None:
                continue
            lead = articles_by_id[cluster.lead_article_id]
            self._read_verified_asset(visual)
            stories.append(
                LayoutStory(
                    article_id=lead.article_id,
                    cluster_id=cluster.cluster_id,
                    content_version=_q04_hash(lead.content_version),
                    rank=rank,
                    tie_break_key=cluster.cluster_id,
                    headline=lead.headline,
                    dek=summary.dek,
                    source_display_name=lead.attribution.display_name,
                    section=lead.attribution.section,
                    has_visual=True,
                    visual_width=visual.width,
                    visual_height=visual.height,
                    visual_identity=visual.asset_id,
                )
            )
            pairs[lead.article_id] = (summary, visual)
        if not stories:
            raise _stage_error("no_publishable_story")
        plan = build_layout_plan(
            stories,
            policy=LayoutPolicy(max_pages=self._policy.max_pages),
        )
        placed_ids = {
            placement.article_id
            for page in plan.pages
            for placement in page.placements
        }
        assembly_fingerprint = sha256_json(
            {
                "job_id": job.job_id,
                "layout_key": plan.layout_key,
                "article_ids": sorted(placed_ids),
                "policy": self._policy.fingerprint(),
            }
        )
        edition_id = f"q10-{assembly_fingerprint.removeprefix('sha256:')[:32]}"
        frozen = self._store.freeze_assembly(
            job.job_id,
            self._worker_id,
            assembly_fingerprint=assembly_fingerprint,
            edition_id=edition_id,
        )
        request = self._store.get_request(job.job_id)
        generated_at = _utc(frozen["generated_at"])
        document = {
            "contract_version": "gazet-e.edition.v1",
            "edition": {
                "id": edition_id,
                "state": "ready",
                "title": generated_at.strftime("%d %B %Y").upper() + " • GAZET+E",
                "requested_at": _utc(job.created_at).isoformat(),
                "generated_at": generated_at.isoformat(),
                "locale": request.locale,
                "timezone": request.timezone,
                "brand": {"name": "Gazet+E", "masthead": "GAZET+E"},
                "versions": {
                    "editorial_policy": EDITORIAL_POLICY_VERSION,
                    "summary_prompt": GENERATOR_PROMPT_VERSION,
                    "visual_brief": next(iter(visuals.values())).brief_version,
                    "visual_style": next(iter(visuals.values())).style_version,
                    "layout_engine": LAYOUT_ENGINE_VERSION,
                },
            },
            "pages": [page.model_dump(mode="json") for page in plan.pages],
            "articles": [
                self._article_document(
                    articles_by_id[article_id],
                    pairs[article_id][0],
                    pairs[article_id][1],
                )
                for article_id in sorted(placed_ids)
            ],
            "cache": {
                "edition_key": assembly_fingerprint,
                "layout_key": plan.layout_key,
            },
        }
        skipped = []
        for cluster in ranked.clusters:
            if cluster.cluster_id not in summaries:
                entry = summary_entries.get(cluster.cluster_id, {})
                skipped.append(
                    {
                        "article_id": cluster.lead_article_id,
                        "stage": "summarizing",
                        "reason_codes": entry.get(
                            "reason_codes", ["summary_unavailable"]
                        ),
                    }
                )
            elif cluster.cluster_id not in visuals:
                entry = visual_entries.get(cluster.cluster_id, {})
                skipped.append(
                    {
                        "article_id": cluster.lead_article_id,
                        "stage": "illustrating",
                        "reason_codes": entry.get(
                            "reason_codes", ["visual_unavailable"]
                        ),
                    }
                )
        all_selected_ids = {cluster.lead_article_id for cluster in ranked.clusters}
        report = {
            "edition_id": edition_id,
            "assembly_fingerprint": assembly_fingerprint,
            "layout_key": plan.layout_key,
            "placed_article_ids": sorted(placed_ids),
            "omitted_article_ids": sorted(all_selected_ids - placed_ids),
            "skipped": skipped,
            "overflow": [item.model_dump(mode="json") for item in plan.overflow.items],
            "selected_story_count": len(ranked.clusters),
            "placed_story_count": len(placed_ids),
            "asset_ids": sorted(pairs[item][1].asset_id for item in placed_ids),
            "integration_policy_version": self._policy.version,
        }
        return IntegrationStageResult(
            ASSEMBLY_MANIFEST_VERSION,
            report,
            edition_document=document,
        )

    def _summary(self, job_id: str, packet: Any) -> SummaryArtifact | None:
        cache_key = summary_cache_key(
            packet,
            prompt_version=GENERATOR_PROMPT_VERSION,
            verifier_prompt_version=VERIFIER_PROMPT_VERSION,
            editorial_policy_version=EDITORIAL_POLICY_VERSION,
            provider=SUMMARY_PROVIDER_ID,
            model=SUMMARY_MODEL,
        )
        cached = self._store.get_cached_artifact("summary", cache_key)
        if cached is not None:
            return SummaryArtifact.model_validate(cached)
        operation_id = f"summary:{cache_key}"
        operation = self._reserve(
            job_id,
            operation_id=operation_id,
            artifact_kind="summary",
            cache_key=cache_key,
            logical_calls=4,
            transport_attempts=8,
            generated_images=0,
            estimated_cost_usd=0.04,
        )
        if operation["state"] == "completed":
            artifact = (operation.get("result") or {}).get("artifact")
            return None if artifact is None else SummaryArtifact.model_validate(artifact)
        if operation["state"] != "reserved":
            return None
        self._store.assert_dispatch_allowed(job_id, self._worker_id, operation_id)
        cache = _SummaryDurableCache(
            self._store, job_id, self._worker_id, operation_id
        )
        artifact = EditorialSummaryPipeline(
            _FencedSummaryProvider(
                self._store,
                job_id,
                self._worker_id,
                operation_id,
                self._summary_provider,
            ),
            cache=cache,
            clock=self._clock,
            budget=SummaryBudget(),
        ).summarize(packet)
        if artifact.status != "ready":
            self._complete_summary(job_id, operation_id, artifact)
        return artifact

    def _complete_summary(
        self, job_id: str, operation_id: str, artifact: SummaryArtifact
    ) -> None:
        cost = (
            artifact.usage.input_tokens * INPUT_USD_PER_MILLION
            + artifact.usage.output_tokens * OUTPUT_USD_PER_MILLION
        ) / 1_000_000
        self._store.complete_paid_operation(
            job_id,
            self._worker_id,
            operation_id=operation_id,
            result={"artifact": artifact.model_dump(mode="json")},
            logical_calls=artifact.provider_call_count,
            transport_attempts=artifact.provider_call_count,
            generated_images=0,
            estimated_cost_usd=cost,
            artifact=(artifact.model_dump(mode="json") if artifact.status == "ready" else None),
        )

    def _visual(self, job_id: str, brief: Any) -> VisualResult | None:
        cache_key = image_cache_key(
            brief, provider=VISUAL_PROVIDER_ID, model=REQUESTED_IMAGE_MODEL
        )
        cached = self._store.get_cached_artifact("visual", cache_key)
        if cached is not None:
            artifact = VisualArtifact.model_validate(cached)
            return VisualResult(artifact, self._read_verified_asset(artifact))
        operation_id = f"visual:{cache_key}"
        operation = self._reserve(
            job_id,
            operation_id=operation_id,
            artifact_kind="visual",
            cache_key=cache_key,
            logical_calls=2,
            transport_attempts=4,
            generated_images=1,
            estimated_cost_usd=0.08,
        )
        if operation["state"] == "completed":
            artifact_data = (operation.get("result") or {}).get("artifact")
            if artifact_data is None:
                return None
            artifact = VisualArtifact.model_validate(artifact_data)
            data = self._read_verified_asset(artifact) if artifact.status == "ready" else b""
            return VisualResult(artifact, data)
        if operation["state"] != "reserved":
            return None
        self._store.assert_dispatch_allowed(job_id, self._worker_id, operation_id)
        cache = _VisualDurableCache(
            self._store,
            self._assets,
            job_id,
            self._worker_id,
            operation_id,
        )
        result = EditorialVisualPipeline(
            _FencedVisualProvider(
                self._store,
                job_id,
                self._worker_id,
                operation_id,
                self._visual_provider,
            ),
            cache=cache,
            clock=self._clock,
            budget=VisualBudget(),
        ).create(brief)
        if result.artifact.status != "ready":
            self._complete_visual(job_id, operation_id, result.artifact)
        return result

    def _complete_visual(
        self, job_id: str, operation_id: str, artifact: VisualArtifact
    ) -> None:
        usage = artifact.usage
        self._store.complete_paid_operation(
            job_id,
            self._worker_id,
            operation_id=operation_id,
            result={"artifact": artifact.model_dump(mode="json")},
            logical_calls=artifact.provider_call_count,
            transport_attempts=artifact.provider_call_count,
            generated_images=usage.generation_calls,
            estimated_cost_usd=usage.estimated_cost_usd,
            artifact=(artifact.model_dump(mode="json") if artifact.status == "ready" else None),
        )

    def _reserve(self, job_id: str, **values: Any) -> dict[str, Any]:
        try:
            return self._store.reserve_paid_operation(
                job_id, self._worker_id, **values
            )
        except (IntegrationConflict, PaidDispatchBlocked) as error:
            raise _stage_error("provider_dispatch_blocked") from error

    def _ensure_run(self, job_id: str) -> None:
        policy = self._policy.model_dump(mode="json")
        self._store.ensure_integration_run(
            job_id,
            policy_version=self._policy.version,
            policy_fingerprint=self._policy.fingerprint(),
            policy=policy,
        )

    def _manifest(self, job_id: str, stage: JobState) -> dict[str, Any]:
        try:
            return self._store.get_stage_manifest(job_id, stage)["manifest"]
        except JobNotFound as error:
            raise _stage_error("stage_input_unavailable") from error

    def _request_locale(self, job_id: str) -> str:
        return self._store.get_request(job_id).locale

    def _read_verified_asset(self, artifact: VisualArtifact) -> bytes:
        if (
            artifact.asset_id is None
            or artifact.media_type is None
            or artifact.width is None
            or artifact.height is None
        ):
            raise _stage_error("asset_integrity_failed")
        try:
            return self._assets.read(
                asset_hex=artifact.asset_id.removeprefix("sha256:"),
                media_type=artifact.media_type,
                width=artifact.width,
                height=artifact.height,
            )
        except AssetStoreError as error:
            raise _stage_error("asset_integrity_failed") from error

    @staticmethod
    def _article_document(article: Any, summary: SummaryArtifact, visual: VisualArtifact) -> dict[str, Any]:
        sources = [
            {
                "id": evidence.source_id,
                "publisher_id": evidence.publisher_id,
                "name": evidence.source_name,
                "canonical_url": evidence.canonical_url,
                **(
                    {"published_at": _utc(evidence.published_at).isoformat()}
                    if evidence.published_at is not None
                    else {}
                ),
            }
            for evidence in summary.evidence
        ]
        assert visual.asset_id is not None and visual.content_hash is not None
        assert visual.width is not None and visual.height is not None
        return {
            "id": article.article_id,
            "cluster_id": summary.cluster_id,
            "content_version": _q04_hash(article.content_version),
            "headline": article.headline,
            "dek": summary.dek,
            "summary": summary.summary,
            "reading_body": [item.model_dump(mode="json") for item in summary.reading_body],
            "primary_source_id": article.attribution.source_id,
            "sources": sources,
            "visual": {
                "asset_id": visual.asset_id,
                "content_hash": visual.content_hash,
                "width": visual.width,
                "height": visual.height,
                "alt": visual.alt,
                "transparency_label": visual.transparency_label,
                "provenance": {
                    "generated_by_ai": visual.generated_by_ai,
                    "provider": visual.provider,
                    "model": visual.response_model or visual.requested_model,
                    "generated_at": _utc(visual.generated_at).isoformat(),
                    "brief_version": visual.brief_version,
                    "style_version": visual.style_version,
                    "safety_class": visual.safety_class,
                    "cache_key": visual.image_cache_key,
                },
            },
            "cache": {
                "summary_key": summary.summary_cache_key,
                "visual_brief_key": visual.visual_brief_key,
            },
        }


class _SummaryDurableCache:
    def __init__(self, store: EditionJobStore, job_id: str, worker_id: str, operation_id: str) -> None:
        self._store = store
        self._job_id = job_id
        self._worker_id = worker_id
        self._operation_id = operation_id

    def get(self, key: str) -> None:
        return None

    def put(self, artifact: SummaryArtifact) -> None:
        cost = (
            artifact.usage.input_tokens * INPUT_USD_PER_MILLION
            + artifact.usage.output_tokens * OUTPUT_USD_PER_MILLION
        ) / 1_000_000
        payload = artifact.model_dump(mode="json")
        self._store.complete_paid_operation(
            self._job_id,
            self._worker_id,
            operation_id=self._operation_id,
            result={"artifact": payload},
            logical_calls=artifact.provider_call_count,
            transport_attempts=artifact.provider_call_count,
            generated_images=0,
            estimated_cost_usd=cost,
            artifact=payload,
        )


class _VisualDurableCache:
    def __init__(
        self,
        store: EditionJobStore,
        assets: DevelopmentAssetStore,
        job_id: str,
        worker_id: str,
        operation_id: str,
    ) -> None:
        self._store = store
        self._assets = assets
        self._job_id = job_id
        self._worker_id = worker_id
        self._operation_id = operation_id

    def get(self, key: str) -> None:
        return None

    def put(self, result: VisualResult) -> None:
        artifact = result.artifact
        assert artifact.asset_id is not None and artifact.content_hash is not None
        assert artifact.media_type is not None and artifact.width is not None
        assert artifact.height is not None
        self._assets.put(
            asset_id=artifact.asset_id,
            content_hash=artifact.content_hash,
            media_type=artifact.media_type,
            width=artifact.width,
            height=artifact.height,
            data=result.image_bytes,
        )
        payload = artifact.model_dump(mode="json")
        self._store.complete_paid_operation(
            self._job_id,
            self._worker_id,
            operation_id=self._operation_id,
            result={"artifact": payload},
            logical_calls=artifact.provider_call_count,
            transport_attempts=artifact.provider_call_count,
            generated_images=artifact.usage.generation_calls,
            estimated_cost_usd=artifact.usage.estimated_cost_usd,
            artifact=payload,
        )


class _FencedSummaryProvider:
    def __init__(
        self,
        store: EditionJobStore,
        job_id: str,
        worker_id: str,
        operation_id: str,
        provider: SummaryProvider,
    ) -> None:
        self._store = store
        self._job_id = job_id
        self._worker_id = worker_id
        self._operation_id = operation_id
        self._provider = provider

    def generate(self, packet: Any, **kwargs: Any) -> Any:
        self._store.assert_dispatch_allowed(
            self._job_id, self._worker_id, self._operation_id
        )
        return self._provider.generate(packet, **kwargs)

    def verify(self, packet: Any, draft: Any) -> Any:
        self._store.assert_dispatch_allowed(
            self._job_id, self._worker_id, self._operation_id
        )
        return self._provider.verify(packet, draft)


class _FencedVisualProvider:
    def __init__(
        self,
        store: EditionJobStore,
        job_id: str,
        worker_id: str,
        operation_id: str,
        provider: VisualProvider,
    ) -> None:
        self._store = store
        self._job_id = job_id
        self._worker_id = worker_id
        self._operation_id = operation_id
        self._provider = provider

    def generate(self, brief: Any) -> Any:
        self._store.assert_dispatch_allowed(
            self._job_id, self._worker_id, self._operation_id
        )
        return self._provider.generate(brief)

    def verify(self, brief: Any, image_bytes: bytes) -> Any:
        self._store.assert_dispatch_allowed(
            self._job_id, self._worker_id, self._operation_id
        )
        return self._provider.verify(brief, image_bytes)


def _ready_summaries(manifest: dict[str, Any]) -> dict[str, SummaryArtifact]:
    return {
        item["cluster_id"]: SummaryArtifact.model_validate(item["artifact"])
        for item in manifest.get("items", [])
        if item.get("status") == "ready" and isinstance(item.get("artifact"), dict)
    }


def _ready_visuals(manifest: dict[str, Any]) -> dict[str, VisualArtifact]:
    return {
        item["cluster_id"]: VisualArtifact.model_validate(item["artifact"])
        for item in manifest.get("items", [])
        if item.get("status") == "ready" and isinstance(item.get("artifact"), dict)
    }


def _stage_error(code: str) -> StageExecutionError:
    return StageExecutionError(
        code=code,
        retryable=False,
        diagnostic="Integration stage failed within its bounded contract.",
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _q04_hash(value: str) -> str:
    if value.startswith("sha256:"):
        return value
    return f"sha256:{value}"
