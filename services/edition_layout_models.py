"""Immutable public-safe contracts for the Q09 newspaper layout boundary."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"
PlacementRole = Literal["hero", "secondary", "brief"]
HitAction = Literal["open_reading", "open_source"]
OverflowReason = Literal["page_limit_exhausted", "content_exceeds_capacity"]


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LayoutStory(FrozenModel):
    article_id: str = Field(min_length=1, max_length=128)
    cluster_id: str = Field(min_length=1, max_length=128)
    content_version: str = Field(pattern=SHA256_PATTERN)
    rank: int = Field(ge=0)
    tie_break_key: str = Field(min_length=1, max_length=128)
    headline: str = Field(min_length=1, max_length=320)
    dek: str = Field(min_length=1, max_length=1_200)
    source_display_name: str = Field(min_length=1, max_length=120)
    section: str = Field(min_length=1, max_length=80)
    has_visual: bool
    visual_width: int | None = Field(default=None, ge=1)
    visual_height: int | None = Field(default=None, ge=1)
    visual_identity: str | None = Field(default=None, pattern=SHA256_PATTERN)

    @field_validator(
        "article_id",
        "cluster_id",
        "tie_break_key",
        "headline",
        "dek",
        "source_display_name",
        "section",
    )
    @classmethod
    def text_must_be_trimmed_and_non_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("layout story text fields must not be blank")
        return cleaned

    @model_validator(mode="after")
    def validate_visual_projection(self) -> LayoutStory:
        visual_fields = (
            self.visual_width,
            self.visual_height,
            self.visual_identity,
        )
        if self.has_visual and any(value is None for value in visual_fields):
            raise ValueError("available visual requires dimensions and identity")
        if not self.has_visual and any(value is not None for value in visual_fields):
            raise ValueError("unavailable visual cannot carry visual metadata")
        return self


class LayoutPolicy(FrozenModel):
    max_pages: int = Field(default=8, ge=1, le=20)


class Rect(FrozenModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def is_inside(self, outer: Rect) -> bool:
        return (
            self.x >= outer.x
            and self.y >= outer.y
            and self.right <= outer.right
            and self.bottom <= outer.bottom
        )

    def overlaps(self, other: Rect) -> bool:
        return (
            self.x < other.right
            and other.x < self.right
            and self.y < other.bottom
            and other.y < self.bottom
        )


class Canvas(FrozenModel):
    width: Literal[1000] = 1000
    height: Literal[1414] = 1414
    unit: Literal["logical"] = "logical"

    @property
    def rect(self) -> Rect:
        return Rect(x=0, y=0, width=self.width, height=self.height)


class TemplateRef(FrozenModel):
    id: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=40)


class HitRegion(FrozenModel):
    id: str = Field(min_length=1, max_length=160)
    action: HitAction
    rect: Rect
    accessibility_label: str = Field(min_length=1, max_length=500)


class Placement(FrozenModel):
    id: str = Field(min_length=1, max_length=160)
    article_id: str = Field(min_length=1, max_length=128)
    role: PlacementRole
    rect: Rect
    z_index: int = Field(ge=0)
    hit_regions: tuple[HitRegion, ...] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def validate_hit_regions(self) -> Placement:
        actions = [region.action for region in self.hit_regions]
        if sorted(actions) != ["open_reading", "open_source"]:
            raise ValueError("placement requires distinct reading and source actions")
        if len({region.id for region in self.hit_regions}) != len(self.hit_regions):
            raise ValueError("hit region IDs must be unique")
        if any(not region.rect.is_inside(self.rect) for region in self.hit_regions):
            raise ValueError("hit regions must remain inside placement")
        if self.hit_regions[0].rect.overlaps(self.hit_regions[1].rect):
            raise ValueError("reading and source hit regions must be distinct")
        return self


class LayoutPage(FrozenModel):
    id: str = Field(min_length=1, max_length=80)
    order: int = Field(ge=1)
    label: str = Field(min_length=1, max_length=80)
    section: str = Field(min_length=1, max_length=80)
    canvas: Canvas
    template: TemplateRef
    placements: tuple[Placement, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_geometry(self) -> LayoutPage:
        if len({item.id for item in self.placements}) != len(self.placements):
            raise ValueError("placement IDs must be unique per page")
        hit_ids = [region.id for item in self.placements for region in item.hit_regions]
        if len(hit_ids) != len(set(hit_ids)):
            raise ValueError("hit region IDs must be unique per page")
        if sum(item.role == "hero" for item in self.placements) > 1:
            raise ValueError("a page may contain at most one hero")
        for index, placement in enumerate(self.placements):
            if not placement.rect.is_inside(self.canvas.rect):
                raise ValueError("placement must remain inside canvas")
            for other in self.placements[index + 1 :]:
                if placement.rect.overlaps(other.rect):
                    raise ValueError("placements must not collide")
        return self


class OverflowItem(FrozenModel):
    article_id: str = Field(min_length=1, max_length=128)
    reason: OverflowReason


class LayoutOverflow(FrozenModel):
    status: Literal["complete", "capacity_exhausted"]
    items: tuple[OverflowItem, ...]
    input_story_count: int = Field(ge=1)
    placed_story_count: int = Field(ge=0)
    page_limit: int = Field(ge=1, le=20)

    @model_validator(mode="after")
    def validate_counts(self) -> LayoutOverflow:
        if self.placed_story_count + len(self.items) != self.input_story_count:
            raise ValueError("overflow counts must preserve every input identity")
        if (self.status == "complete") != (not self.items):
            raise ValueError("overflow status must match overflow items")
        return self


class LayoutPlan(FrozenModel):
    layout_engine_version: str = Field(min_length=1, max_length=80)
    layout_policy_version: str = Field(min_length=1, max_length=80)
    template_registry_version: str = Field(min_length=1, max_length=80)
    layout_key: str = Field(pattern=SHA256_PATTERN)
    pages: tuple[LayoutPage, ...]
    overflow: LayoutOverflow

    @model_validator(mode="after")
    def validate_plan_identity(self) -> LayoutPlan:
        orders = [page.order for page in self.pages]
        if orders != list(range(1, len(self.pages) + 1)):
            raise ValueError("page order must be contiguous and deterministic")
        if len({page.id for page in self.pages}) != len(self.pages):
            raise ValueError("page IDs must be unique")
        placed = [
            placement.article_id
            for page in self.pages
            for placement in page.placements
        ]
        overflow = [item.article_id for item in self.overflow.items]
        if len(placed) != len(set(placed)):
            raise ValueError("article may be placed only once")
        if set(placed).intersection(overflow):
            raise ValueError("placed article cannot also overflow")
        if len(placed) != self.overflow.placed_story_count:
            raise ValueError("placed story count must match placements")
        return self
