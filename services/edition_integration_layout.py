"""Q10 physical-page projection over the immutable historical Q09 plan."""

from __future__ import annotations

from typing import Any

from services.edition_integration_ads import (
    AD_POLICY_VERSION,
    MAX_AD_AREA_RATIO,
    reserve_synthetic_ad,
)
from services.edition_integration_models import sha256_json
from services.edition_layout_models import LayoutPlan

PHYSICAL_LAYOUT_VERSION = "gazet-e.physical-layout.v1"
PHYSICAL_PROFILE_VERSION = "gazet-e.physical-profile.350x500.v1"
PHYSICAL_WIDTH_MM = 350
PHYSICAL_HEIGHT_MM = 500
LOGICAL_UNITS_PER_MM = 2
LOGICAL_WIDTH = 700
LOGICAL_HEIGHT = 1000
_SOURCE_WIDTH = 1000
_SOURCE_HEIGHT = 1414
_AD_GUTTER = 20


def build_physical_layout(
    plan: LayoutPlan,
    *,
    edition_seed: str,
    ads_enabled: bool = True,
) -> tuple[list[dict[str, Any]], str]:
    """Reserve ads first, then map editorial geometry into the remaining page."""

    pages: list[dict[str, Any]] = []
    for source_page in plan.pages:
        ad = reserve_synthetic_ad(
            edition_seed,
            source_page.order,
            suitable=ads_enabled,
        )
        editorial_bottom = (
            int(ad["rect"]["y"]) - _AD_GUTTER  # type: ignore[index]
            if ad is not None
            else LOGICAL_HEIGHT
        )
        scale_x = LOGICAL_WIDTH / _SOURCE_WIDTH
        scale_y = editorial_bottom / _SOURCE_HEIGHT
        placements = []
        for placement in source_page.placements:
            projected = {
                "id": placement.id,
                "article_id": placement.article_id,
                "role": placement.role,
                "rect": _project_rect(placement.rect.model_dump(), scale_x, scale_y),
                "z_index": placement.z_index,
                "hit_regions": [
                    {
                        "id": hit.id,
                        "action": hit.action,
                        "rect": _project_rect(hit.rect.model_dump(), scale_x, scale_y),
                        "accessibility_label": hit.accessibility_label,
                    }
                    for hit in placement.hit_regions
                ],
            }
            placements.append(projected)
        page = {
            "id": source_page.id,
            "order": source_page.order,
            "label": source_page.label,
            "section": source_page.section,
            "physical_profile": {
                "version": PHYSICAL_PROFILE_VERSION,
                "width_mm": PHYSICAL_WIDTH_MM,
                "height_mm": PHYSICAL_HEIGHT_MM,
                "logical_units_per_mm": LOGICAL_UNITS_PER_MM,
            },
            "canvas": {
                "width": LOGICAL_WIDTH,
                "height": LOGICAL_HEIGHT,
                "unit": "logical",
            },
            "template": {
                "id": source_page.template.id,
                "version": f"{source_page.template.version}+{PHYSICAL_LAYOUT_VERSION}",
            },
            "placements": placements,
            "ads": [] if ad is None else [ad],
        }
        _validate_page(page)
        pages.append(page)
    layout_key = sha256_json(
        {
            "ad_policy_version": AD_POLICY_VERSION,
            "edition_seed": edition_seed,
            "pages": pages,
            "physical_layout_version": PHYSICAL_LAYOUT_VERSION,
            "source_layout_key": plan.layout_key,
        }
    )
    return pages, layout_key


def _project_rect(
    rect: dict[str, int],
    scale_x: float,
    scale_y: float,
) -> dict[str, int]:
    return {
        "x": round(rect["x"] * scale_x),
        "y": round(rect["y"] * scale_y),
        "width": max(1, round(rect["width"] * scale_x)),
        "height": max(1, round(rect["height"] * scale_y)),
    }


def _validate_page(page: dict[str, Any]) -> None:
    ads = page["ads"]
    if len(ads) > 1:
        raise ValueError("physical page allows at most one ad")
    for placement in page["placements"]:
        _inside(placement["rect"])
        for hit in placement["hit_regions"]:
            _inside(hit["rect"])
    for ad in ads:
        rect = ad["rect"]
        _inside(rect)
        if rect["width"] * rect["height"] > (
            LOGICAL_WIDTH * LOGICAL_HEIGHT * MAX_AD_AREA_RATIO
        ):
            raise ValueError("physical ad exceeds the page area ceiling")
        if ad["label"] != "REKLAM":
            raise ValueError("physical ad requires the REKLAM label")
        for placement in page["placements"]:
            if _overlaps(rect, placement["rect"]):
                raise ValueError("physical ad overlaps editorial placement")
            for hit in placement["hit_regions"]:
                if _overlaps(rect, hit["rect"]):
                    raise ValueError("physical ad overlaps editorial hit region")


def _inside(rect: dict[str, int]) -> None:
    if (
        rect["x"] < 0
        or rect["y"] < 0
        or rect["width"] <= 0
        or rect["height"] <= 0
        or rect["x"] + rect["width"] > LOGICAL_WIDTH
        or rect["y"] + rect["height"] > LOGICAL_HEIGHT
    ):
        raise ValueError("physical rectangle is outside the fixed canvas")


def _overlaps(left: dict[str, int], right: dict[str, int]) -> bool:
    return (
        left["x"] < right["x"] + right["width"]
        and right["x"] < left["x"] + left["width"]
        and left["y"] < right["y"] + right["height"]
        and right["y"] < left["y"] + left["height"]
    )
