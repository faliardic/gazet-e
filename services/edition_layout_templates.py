"""Bounded Q03-compatible logical-canvas template registry for Q09."""

from __future__ import annotations

from dataclasses import dataclass

from services.edition_layout_models import Canvas, PlacementRole, Rect

TEMPLATE_REGISTRY_VERSION = "gazet-e.layout-templates.v2"
SOURCE_AFFORDANCE_HEIGHT = 56


@dataclass(frozen=True)
class TemplateSlot:
    id: str
    role: PlacementRole
    rect: Rect
    max_headline_chars: int
    max_dek_chars: int
    requires_visual: bool = False

    def __post_init__(self) -> None:
        if not self.id or self.max_headline_chars < 1 or self.max_dek_chars < 1:
            raise ValueError("template slot metadata must be positive")
        if self.rect.height <= SOURCE_AFFORDANCE_HEIGHT:
            raise ValueError("slot must reserve a positive reading region")


@dataclass(frozen=True)
class TemplateDefinition:
    id: str
    version: str
    canvas: Canvas
    slots: tuple[TemplateSlot, ...]

    def __post_init__(self) -> None:
        if not self.id or not self.version or not self.slots or len(self.slots) > 8:
            raise ValueError("template must be named, versioned, and bounded")
        if len({slot.id for slot in self.slots}) != len(self.slots):
            raise ValueError("template slot IDs must be unique")
        for index, slot in enumerate(self.slots):
            if not slot.rect.is_inside(self.canvas.rect):
                raise ValueError("template slot must remain inside canvas")
            for other in self.slots[index + 1 :]:
                if slot.rect.overlaps(other.rect):
                    raise ValueError("template slots must not collide")
        if sum(slot.role == "hero" for slot in self.slots) > 1:
            raise ValueError("template may define at most one hero")


@dataclass(frozen=True)
class TemplateRegistry:
    version: str
    templates: tuple[TemplateDefinition, ...]

    def __post_init__(self) -> None:
        if not self.version or not self.templates or len(self.templates) > 8:
            raise ValueError("template registry must be named and bounded")
        if len({item.id for item in self.templates}) != len(self.templates):
            raise ValueError("template IDs must be unique")
        if {item.id for item in self.templates} != {"front", "inside"}:
            raise ValueError("registry requires the bounded front/inside vocabulary")

    def for_page(self, order: int) -> TemplateDefinition:
        template_id = "front" if order == 1 else "inside"
        return next(item for item in self.templates if item.id == template_id)


CANVAS = Canvas()

FRONT_TEMPLATE = TemplateDefinition(
    id="front",
    version="3",
    canvas=CANVAS,
    slots=(
        TemplateSlot(
            id="hero",
            role="hero",
            rect=Rect(x=40, y=180, width=600, height=660),
            max_headline_chars=140,
            max_dek_chars=320,
            requires_visual=True,
        ),
        TemplateSlot(
            id="secondary",
            role="secondary",
            rect=Rect(x=660, y=180, width=300, height=315),
            max_headline_chars=80,
            max_dek_chars=150,
            requires_visual=True,
        ),
        TemplateSlot(
            id="rail-brief",
            role="brief",
            rect=Rect(x=660, y=515, width=300, height=325),
            max_headline_chars=70,
            max_dek_chars=150,
        ),
        TemplateSlot(
            id="wide-brief",
            role="brief",
            rect=Rect(x=40, y=870, width=920, height=420),
            max_headline_chars=160,
            max_dek_chars=380,
        ),
    ),
)

INSIDE_TEMPLATE = TemplateDefinition(
    id="inside",
    version="3",
    canvas=CANVAS,
    slots=(
        TemplateSlot(
            id="hero",
            role="hero",
            rect=Rect(x=40, y=180, width=920, height=500),
            max_headline_chars=160,
            max_dek_chars=340,
            requires_visual=True,
        ),
        TemplateSlot(
            id="secondary",
            role="secondary",
            rect=Rect(x=40, y=710, width=440, height=570),
            max_headline_chars=100,
            max_dek_chars=300,
            requires_visual=True,
        ),
        TemplateSlot(
            id="brief",
            role="brief",
            rect=Rect(x=520, y=710, width=440, height=570),
            max_headline_chars=110,
            max_dek_chars=320,
        ),
    ),
)

DEFAULT_TEMPLATE_REGISTRY = TemplateRegistry(
    version=TEMPLATE_REGISTRY_VERSION,
    templates=(FRONT_TEMPLATE, INSIDE_TEMPLATE),
)
