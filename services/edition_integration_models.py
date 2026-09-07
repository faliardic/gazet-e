"""Versioned, public-safe contracts for Q10 durable integration."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

INTEGRATION_POLICY_VERSION = "gazet-e.edition-integration.v1"
COLLECTION_MANIFEST_VERSION = "gazet-e.collection-manifest.v1"
SELECTION_MANIFEST_VERSION = "gazet-e.selection-manifest.v1"
SUMMARY_MANIFEST_VERSION = "gazet-e.summary-manifest.v1"
VISUAL_MANIFEST_VERSION = "gazet-e.visual-manifest.v1"
ASSEMBLY_MANIFEST_VERSION = "gazet-e.assembly-manifest.v1"
MAX_MANIFEST_BYTES = 2 * 1024 * 1024

_FORBIDDEN_KEYS = frozenset(
    {
        "api_key",
        "access_token",
        "credential",
        "password",
        "prompt",
        "raw_prompt",
        "raw_response",
        "raw_feed",
        "raw_body",
        "publisher_body",
        "publisher_image",
        "asset_path",
        "local_path",
        "private_path",
        "signed_url",
        "image_bytes",
    }
)


class IntegrationPolicy(BaseModel):
    """Small development proof bounds, not a product quota contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = Field(default=INTEGRATION_POLICY_VERSION)
    max_selected_clusters: int = Field(default=4, ge=1, le=4)
    max_pages: int = Field(default=2, ge=1, le=2)
    max_collected_candidates: int = Field(default=40, ge=1, le=120)
    paid_execution_enabled: bool = False
    max_logical_provider_calls: int = Field(default=24, ge=1, le=24)
    max_transport_attempts: int = Field(default=48, ge=1, le=48)
    max_generated_images: int = Field(default=4, ge=1, le=4)
    max_estimated_cost_usd: float = Field(default=0.48, gt=0, le=0.48)

    @model_validator(mode="after")
    def validate_finite_budget(self) -> IntegrationPolicy:
        if not math.isfinite(self.max_estimated_cost_usd):
            raise ValueError("integration cost bound must be finite")
        if self.max_transport_attempts < self.max_logical_provider_calls:
            raise ValueError("transport bound cannot be below logical calls")
        return self

    def fingerprint(self) -> str:
        return sha256_json(self.model_dump(mode="json"))


@dataclass(frozen=True)
class IntegrationStageResult:
    manifest_version: str
    manifest: dict[str, Any]
    edition_document: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.manifest_version or len(self.manifest_version) > 96:
            raise ValueError("stage manifest version is invalid")
        canonical_safe_payload(self.manifest)
        if self.edition_document is not None and not isinstance(
            self.edition_document, dict
        ):
            raise ValueError("edition document must be an object")


def canonical_safe_payload(payload: dict[str, Any]) -> tuple[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("integration manifest must be an object")
    _validate_safe_value(payload)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )
    if len(canonical.encode("utf-8")) > MAX_MANIFEST_BYTES:
        raise ValueError("integration manifest exceeds the bounded size")
    return canonical, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def sha256_json(payload: Any) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_safe_value(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key).casefold()
            if (
                key in _FORBIDDEN_KEYS
                or "secret" in key
                or key.endswith("_credential")
            ):
                raise ValueError(f"forbidden integration field at {path}")
            _validate_safe_value(child, f"{path}.{raw_key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _validate_safe_value(child, f"{path}[{index}]")
        return
    if isinstance(value, bytes):
        raise ValueError(f"binary data is forbidden in integration payload at {path}")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite integration value at {path}")
    if value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError(f"non-JSON integration value at {path}")
