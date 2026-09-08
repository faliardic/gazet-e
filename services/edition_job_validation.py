"""Version-aware validation for immutable Gazet+E edition documents."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker

V1_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "schemas"
    / "gazet-e.edition.v1.schema.json"
)
V2_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "schemas"
    / "gazet-e.edition.v2.schema.json"
)
SCHEMA_PATH = V1_SCHEMA_PATH

_FORBIDDEN_FIELDS = {
    "api_key",
    "provider_api_key",
    "provider_secret",
    "access_token",
    "refresh_token",
    "raw_prompt",
    "prompt",
    "asset_path",
    "local_path",
    "private_path",
    "storage_path",
    "signed_url",
    "raw_body",
    "raw_content",
    "raw_publisher_body",
    "publisher_body",
    "full_publisher_body",
    "scrape_body",
    "source_body",
}


class CanonicalEditionError(ValueError):
    """Raised without echoing untrusted document values."""


@dataclass(frozen=True)
class ValidatedEdition:
    edition_id: str
    contract_version: str
    document: dict[str, Any]
    canonical_json: str
    document_hash: str


class CanonicalEditionValidator:
    def __init__(self, schema_path: Path | None = None) -> None:
        paths = (schema_path,) if schema_path is not None else (
            V1_SCHEMA_PATH,
            V2_SCHEMA_PATH,
        )
        self._validators: dict[str, Draft202012Validator] = {}
        for path in paths:
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            version = schema["properties"]["contract_version"]["const"]
            self._validators[version] = Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            )

    def validate(self, document: dict[str, Any]) -> ValidatedEdition:
        if not isinstance(document, dict):
            raise CanonicalEditionError("edition document must be an object")
        self._reject_forbidden_fields(document)
        self._reject_non_finite_numbers(document)
        contract_version = document.get("contract_version")
        validator = self._validators.get(contract_version)
        if validator is None:
            raise CanonicalEditionError("unsupported edition contract version")

        errors = sorted(validator.iter_errors(document), key=_error_path)
        if errors:
            error = errors[0]
            path = ".".join(str(part) for part in error.absolute_path) or "$"
            raise CanonicalEditionError(
                f"schema validation failed at {path} ({error.validator})"
            )

        self._validate_cross_invariants(document, contract_version)
        try:
            canonical_json = json.dumps(
                document,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as error:
            raise CanonicalEditionError(
                "edition document is not canonical JSON data"
            ) from error
        canonical_document = json.loads(canonical_json)
        return ValidatedEdition(
            edition_id=canonical_document["edition"]["id"],
            contract_version=canonical_document["contract_version"],
            document=canonical_document,
            canonical_json=canonical_json,
            document_hash=hashlib.sha256(canonical_json.encode("utf-8")).hexdigest(),
        )

    def _reject_forbidden_fields(self, value: Any, path: str = "$") -> None:
        if isinstance(value, dict):
            for raw_key, child in value.items():
                key = str(raw_key).lower()
                if key in _FORBIDDEN_FIELDS or "secret" in key:
                    raise CanonicalEditionError(
                        f"forbidden field at {path}.{raw_key}"
                    )
                self._reject_forbidden_fields(child, f"{path}.{raw_key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                self._reject_forbidden_fields(child, f"{path}[{index}]")

    def _reject_non_finite_numbers(self, value: Any, path: str = "$") -> None:
        if isinstance(value, float) and not math.isfinite(value):
            raise CanonicalEditionError(f"non-finite number at {path}")
        if isinstance(value, dict):
            for key, child in value.items():
                self._reject_non_finite_numbers(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                self._reject_non_finite_numbers(child, f"{path}[{index}]")

    def _validate_cross_invariants(
        self,
        document: dict[str, Any],
        contract_version: str,
    ) -> None:
        edition = document["edition"]
        requested_at = _timestamp(edition["requested_at"], "edition.requested_at")
        generated_at = _timestamp(edition["generated_at"], "edition.generated_at")
        if generated_at < requested_at:
            raise CanonicalEditionError("generated_at precedes requested_at")

        articles = document["articles"]
        article_ids = [article["id"] for article in articles]
        if len(article_ids) != len(set(article_ids)):
            raise CanonicalEditionError("duplicate article id")
        article_id_set = set(article_ids)

        for article in articles:
            identities = {
                article["id"],
                article["cluster_id"],
                article["content_version"],
            }
            if len(identities) != 3:
                raise CanonicalEditionError("article identities must remain distinct")
            source_ids = [source["id"] for source in article["sources"]]
            if len(source_ids) != len(set(source_ids)):
                raise CanonicalEditionError("duplicate source id")
            if article["primary_source_id"] not in source_ids:
                raise CanonicalEditionError("primary source reference is invalid")
            for source in article["sources"]:
                url = urlsplit(source["canonical_url"])
                if (
                    url.scheme != "https"
                    or not url.hostname
                    or url.username is not None
                    or url.password is not None
                ):
                    raise CanonicalEditionError("canonical source URL is not safe HTTPS")
            visual = article["visual"]
            if (
                contract_version == "gazet-e.edition.v2"
                and visual["asset_id"] != visual["content_hash"]
            ):
                raise CanonicalEditionError("visual asset identity must match content hash")

        pages = document["pages"]
        page_ids = [page["id"] for page in pages]
        page_orders = [page["order"] for page in pages]
        if len(page_ids) != len(set(page_ids)):
            raise CanonicalEditionError("duplicate page id")
        if len(page_orders) != len(set(page_orders)):
            raise CanonicalEditionError("duplicate page order")
        if page_orders != sorted(page_orders):
            raise CanonicalEditionError("pages are not in deterministic order")

        placed_article_ids: list[str] = []
        ad_ids: set[str] = set()
        for page in pages:
            canvas = page["canvas"]
            placement_ids: set[str] = set()
            hit_ids: set[str] = set()
            placements = page["placements"]
            for index, placement in enumerate(placements):
                if placement["id"] in placement_ids:
                    raise CanonicalEditionError("duplicate placement id")
                placement_ids.add(placement["id"])
                if placement["article_id"] not in article_id_set:
                    raise CanonicalEditionError("placement article reference is invalid")
                placed_article_ids.append(placement["article_id"])
                _validate_rect(placement["rect"], canvas)
                if contract_version == "gazet-e.edition.v2":
                    for other in placements[index + 1 :]:
                        if _rects_overlap(placement["rect"], other["rect"]):
                            raise CanonicalEditionError("editorial placements overlap")
                actions: set[str] = set()
                for hit in placement["hit_regions"]:
                    if hit["id"] in hit_ids:
                        raise CanonicalEditionError("duplicate hit region id")
                    hit_ids.add(hit["id"])
                    actions.add(hit["action"])
                    _validate_rect(hit["rect"], canvas)
                    if contract_version == "gazet-e.edition.v2" and not _rect_inside(
                        hit["rect"], placement["rect"]
                    ):
                        raise CanonicalEditionError(
                            "hit region must remain inside editorial placement"
                        )
                if "open_reading" not in actions or "open_source" not in actions:
                    raise CanonicalEditionError(
                        "placement requires reading and source actions"
                    )
            if contract_version == "gazet-e.edition.v2":
                ads = page["ads"]
                if len(ads) > 1:
                    raise CanonicalEditionError("page allows at most one ad")
                for ad in ads:
                    if ad["id"] in ad_ids:
                        raise CanonicalEditionError("duplicate page ad id")
                    ad_ids.add(ad["id"])
                    _validate_rect(ad["rect"], canvas)
                    area = ad["rect"]["width"] * ad["rect"]["height"]
                    if area > canvas["width"] * canvas["height"] * 0.15 + 1e-9:
                        raise CanonicalEditionError("page ad exceeds area ceiling")
                    for placement in placements:
                        if _rects_overlap(ad["rect"], placement["rect"]):
                            raise CanonicalEditionError("page ad overlaps editorial placement")
                        if any(
                            _rects_overlap(ad["rect"], hit["rect"])
                            for hit in placement["hit_regions"]
                        ):
                            raise CanonicalEditionError("page ad overlaps hit region")

        if contract_version == "gazet-e.edition.v2":
            if len(placed_article_ids) != len(set(placed_article_ids)):
                raise CanonicalEditionError("article may be placed only once")
            if set(placed_article_ids) != article_id_set:
                raise CanonicalEditionError("v2 article set must equal placed articles")


def _timestamp(value: str, path: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CanonicalEditionError(f"invalid timestamp at {path}") from error
    if timestamp.tzinfo is None:
        raise CanonicalEditionError(f"timestamp lacks timezone at {path}")
    return timestamp


def _validate_rect(rect: dict[str, Any], canvas: dict[str, Any]) -> None:
    if rect["x"] + rect["width"] > canvas["width"]:
        raise CanonicalEditionError("rectangle exceeds canvas width")
    if rect["y"] + rect["height"] > canvas["height"]:
        raise CanonicalEditionError("rectangle exceeds canvas height")


def _rect_inside(inner: dict[str, Any], outer: dict[str, Any]) -> bool:
    return (
        inner["x"] >= outer["x"]
        and inner["y"] >= outer["y"]
        and inner["x"] + inner["width"] <= outer["x"] + outer["width"]
        and inner["y"] + inner["height"] <= outer["y"] + outer["height"]
    )


def _rects_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left["x"] < right["x"] + right["width"]
        and right["x"] < left["x"] + left["width"]
        and left["y"] < right["y"] + right["height"]
        and right["y"] < left["y"] + left["height"]
    )


def _error_path(error: Any) -> tuple[str, ...]:
    return tuple(str(part) for part in error.absolute_path)
