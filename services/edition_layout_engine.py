"""Pure deterministic packing from layout-ready stories to Q04 page geometry."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from services.edition_layout_models import (
    HitRegion,
    LayoutOverflow,
    LayoutPage,
    LayoutPlan,
    LayoutPolicy,
    LayoutStory,
    OverflowReason,
    OverflowItem,
    Placement,
    Rect,
    TemplateRef,
)
from services.edition_layout_templates import (
    DEFAULT_TEMPLATE_REGISTRY,
    SOURCE_AFFORDANCE_HEIGHT,
    TemplateDefinition,
    TemplateRegistry,
    TemplateSlot,
)

LAYOUT_ENGINE_VERSION = "gazet-e.layout-engine.v2"
LAYOUT_POLICY_VERSION = "gazet-e.layout-policy.v1"


def build_layout_plan(
    stories: Sequence[LayoutStory],
    *,
    policy: LayoutPolicy = LayoutPolicy(),
    registry: TemplateRegistry = DEFAULT_TEMPLATE_REGISTRY,
) -> LayoutPlan:
    if not stories:
        raise ValueError("layout requires at least one story")
    canonical = tuple(sorted(stories, key=_story_order))
    if len({story.article_id for story in canonical}) != len(canonical):
        raise ValueError("article IDs must be unique")

    remaining = list(canonical)
    pages: list[LayoutPage] = []
    for order in range(1, policy.max_pages + 1):
        template = registry.for_page(order)
        assignments: list[tuple[TemplateSlot, LayoutStory]] = []
        for slot in template.slots:
            story_index = _first_eligible_index(remaining, slot)
            if story_index is None:
                continue
            assignments.append((slot, remaining.pop(story_index)))
        if not assignments:
            break
        pages.append(_build_page(order, template, assignments))
        if not remaining:
            break

    overflow_items = tuple(
        OverflowItem(
            article_id=story.article_id,
            reason=_overflow_reason(story, registry),
        )
        for story in remaining
    )
    key = _layout_key(canonical, policy, registry)
    return LayoutPlan(
        layout_engine_version=LAYOUT_ENGINE_VERSION,
        layout_policy_version=LAYOUT_POLICY_VERSION,
        template_registry_version=registry.version,
        layout_key=key,
        pages=tuple(pages),
        overflow=LayoutOverflow(
            status="capacity_exhausted" if overflow_items else "complete",
            items=overflow_items,
            input_story_count=len(canonical),
            placed_story_count=sum(len(page.placements) for page in pages),
            page_limit=policy.max_pages,
        ),
    )


def _story_order(story: LayoutStory) -> tuple[int, str, str]:
    return story.rank, story.tie_break_key, story.article_id


def _first_eligible_index(
    stories: list[LayoutStory], slot: TemplateSlot
) -> int | None:
    return next(
        (index for index, story in enumerate(stories) if _fits(story, slot)),
        None,
    )


def _fits(story: LayoutStory, slot: TemplateSlot) -> bool:
    return (
        (story.has_visual or not slot.requires_visual)
        and len(story.headline) <= slot.max_headline_chars
        and len(story.dek) <= slot.max_dek_chars
    )


def _fits_any_template(story: LayoutStory, registry: TemplateRegistry) -> bool:
    return any(_fits(story, slot) for item in registry.templates for slot in item.slots)


def _overflow_reason(
    story: LayoutStory, registry: TemplateRegistry
) -> OverflowReason:
    if not _fits_any_template(story, registry):
        return "content_exceeds_capacity"
    continuation = registry.for_page(2)
    if not any(_fits(story, slot) for slot in continuation.slots):
        return "continuation_capacity_exhausted"
    return "page_limit_exhausted"


def _build_page(
    order: int,
    template: TemplateDefinition,
    assignments: list[tuple[TemplateSlot, LayoutStory]],
) -> LayoutPage:
    page_id = f"page-{order:03d}"
    placements = tuple(
        _build_placement(page_id, index, slot, story)
        for index, (slot, story) in enumerate(assignments, start=1)
    )
    return LayoutPage(
        id=page_id,
        order=order,
        label=f"Sayfa {order}",
        section=assignments[0][1].section,
        canvas=template.canvas,
        template=TemplateRef(id=template.id, version=template.version),
        placements=placements,
    )


def _build_placement(
    page_id: str,
    index: int,
    slot: TemplateSlot,
    story: LayoutStory,
) -> Placement:
    placement_id = f"{page_id}-placement-{index:02d}-{slot.id}"
    reading_rect = Rect(
        x=slot.rect.x,
        y=slot.rect.y,
        width=slot.rect.width,
        height=slot.rect.height - SOURCE_AFFORDANCE_HEIGHT,
    )
    source_rect = Rect(
        x=slot.rect.x,
        y=slot.rect.bottom - SOURCE_AFFORDANCE_HEIGHT,
        width=slot.rect.width,
        height=SOURCE_AFFORDANCE_HEIGHT,
    )
    return Placement(
        id=placement_id,
        article_id=story.article_id,
        role=slot.role,
        rect=slot.rect,
        z_index=1,
        hit_regions=(
            HitRegion(
                id=f"{placement_id}-open-reading",
                action="open_reading",
                rect=reading_rect,
                accessibility_label=f"{story.headline} haberini okuma modunda aç",
            ),
            HitRegion(
                id=f"{placement_id}-open-source",
                action="open_source",
                rect=source_rect,
                accessibility_label=f"{story.source_display_name} kaynağına git",
            ),
        ),
    )


def _layout_key(
    stories: tuple[LayoutStory, ...],
    policy: LayoutPolicy,
    registry: TemplateRegistry,
) -> str:
    payload = {
        "engine_version": LAYOUT_ENGINE_VERSION,
        "policy_version": LAYOUT_POLICY_VERSION,
        "policy": policy.model_dump(mode="json"),
        "registry": {
            "templates": [
                {
                    "canvas": item.canvas.model_dump(mode="json"),
                    "id": item.id,
                    "slots": [
                        {
                            "id": slot.id,
                            "max_dek_chars": slot.max_dek_chars,
                            "max_headline_chars": slot.max_headline_chars,
                            "rect": slot.rect.model_dump(mode="json"),
                            "requires_visual": slot.requires_visual,
                            "role": slot.role,
                        }
                        for slot in item.slots
                    ],
                    "version": item.version,
                }
                for item in registry.templates
            ],
            "version": registry.version,
        },
        "stories": [story.model_dump(mode="json") for story in stories],
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
