from __future__ import annotations

import inspect
import json
from dataclasses import replace

import pytest
from pydantic import ValidationError

from services.edition_job_validation import CanonicalEditionValidator
from services.edition_layout_engine import (
    LAYOUT_ENGINE_VERSION,
    LAYOUT_POLICY_VERSION,
    build_layout_plan,
)
from services.edition_layout_models import LayoutPlan, LayoutPolicy, LayoutStory
from services.edition_layout_templates import (
    DEFAULT_TEMPLATE_REGISTRY,
    TEMPLATE_REGISTRY_VERSION,
    TemplateRegistry,
)


def test_same_logical_input_is_json_equivalent_and_has_same_layout_key() -> None:
    stories = tuple(_story(index) for index in range(1, 8))
    first = build_layout_plan(stories, policy=LayoutPolicy(max_pages=3))
    second = build_layout_plan(stories, policy=LayoutPolicy(max_pages=3))
    assert _canonical_json(first) == _canonical_json(second)
    assert first.layout_key == second.layout_key


def test_shuffled_caller_input_canonicalizes_to_same_output() -> None:
    stories = tuple(_story(index) for index in range(1, 7))
    shuffled = (stories[4], stories[1], stories[5], stories[0], stories[3], stories[2])
    assert _canonical_json(build_layout_plan(stories)) == _canonical_json(
        build_layout_plan(shuffled)
    )


def test_rank_then_tie_break_then_article_id_drives_order() -> None:
    stories = (
        _story(3, rank=2, tie_break_key="a"),
        _story(2, rank=1, tie_break_key="b"),
        _story(1, rank=1, tie_break_key="a"),
    )
    plan = build_layout_plan(stories)
    assert _placed_ids(plan) == ["article-001", "article-002", "article-003"]


def test_front_page_hierarchy_is_stable() -> None:
    plan = build_layout_plan(tuple(_story(index) for index in range(1, 5)))
    front = plan.pages[0]
    assert front.template.id == "front"
    assert [item.role for item in front.placements] == [
        "hero",
        "secondary",
        "brief",
        "brief",
    ]
    assert _placed_ids(plan) == [f"article-{index:03d}" for index in range(1, 5)]


def test_every_page_has_at_most_one_hero() -> None:
    plan = build_layout_plan(tuple(_story(index) for index in range(1, 11)))
    assert all(
        sum(item.role == "hero" for item in page.placements) <= 1
        for page in plan.pages
    )


def test_long_content_fails_to_structured_overflow_without_geometry() -> None:
    long_story = _story(1, headline="H" * 220, dek="D" * 500)
    normal_story = _story(2)
    plan = build_layout_plan((long_story, normal_story), policy=LayoutPolicy(max_pages=2))
    assert _placed_ids(plan) == [normal_story.article_id]
    assert [(item.article_id, item.reason) for item in plan.overflow.items] == [
        (long_story.article_id, "content_exceeds_capacity")
    ]
    _assert_valid_geometry(plan)


def test_every_placement_is_positive_and_inside_fixed_canvas() -> None:
    plan = build_layout_plan(tuple(_story(index) for index in range(1, 9)))
    _assert_valid_geometry(plan)
    assert all(
        page.canvas.model_dump(mode="json")
        == {"width": 1000, "height": 1414, "unit": "logical"}
        for page in plan.pages
    )


def test_every_placement_has_distinct_reading_and_source_regions() -> None:
    plan = build_layout_plan(tuple(_story(index) for index in range(1, 6)))
    for page in plan.pages:
        for placement in page.placements:
            assert {item.action for item in placement.hit_regions} == {
                "open_reading",
                "open_source",
            }
            reading, source = placement.hit_regions
            assert not reading.rect.overlaps(source.rect)
            assert reading.accessibility_label
            assert source.accessibility_label


def test_placement_and_hit_ids_are_unique_and_deterministic() -> None:
    stories = tuple(_story(index) for index in range(1, 8))
    first = build_layout_plan(stories)
    second = build_layout_plan(reversed(stories))
    first_ids = _geometry_ids(first)
    assert len(first_ids) == len(set(first_ids))
    assert first_ids == _geometry_ids(second)


def test_page_ids_and_orders_are_unique_contiguous_and_deterministic() -> None:
    plan = build_layout_plan(tuple(_story(index) for index in range(1, 11)))
    assert [page.id for page in plan.pages] == [
        f"page-{order:03d}" for order in range(1, len(plan.pages) + 1)
    ]
    assert [page.order for page in plan.pages] == list(range(1, len(plan.pages) + 1))


def test_template_registry_is_static_bounded_and_versioned() -> None:
    registry = DEFAULT_TEMPLATE_REGISTRY
    assert registry.version == TEMPLATE_REGISTRY_VERSION
    assert 1 <= len(registry.templates) <= 8
    assert {item.id for item in registry.templates} == {"front", "inside"}
    assert all(item.version and 1 <= len(item.slots) <= 8 for item in registry.templates)
    with pytest.raises(ValueError):
        TemplateRegistry(version="unbounded", templates=registry.templates * 5)


def test_visual_availability_changes_role_and_key_without_external_call() -> None:
    without_visual = _story(1, has_visual=False)
    with_visual = _story(2, has_visual=True)
    visual_plan = build_layout_plan((without_visual, with_visual))
    assert visual_plan.pages[0].placements[0].article_id == with_visual.article_id
    assert visual_plan.pages[0].placements[0].role == "hero"

    no_visual_plan = build_layout_plan(
        (without_visual, _story(2, has_visual=False))
    )
    assert all(item.role != "hero" for item in no_visual_plan.pages[0].placements)
    assert visual_plan.layout_key != no_visual_plan.layout_key


def test_page_limit_overflow_is_complete_ordered_and_never_duplicates() -> None:
    stories = tuple(_story(index) for index in range(1, 8))
    plan = build_layout_plan(stories, policy=LayoutPolicy(max_pages=1))
    assert plan.overflow.status == "capacity_exhausted"
    assert [item.article_id for item in plan.overflow.items] == [
        "article-005",
        "article-006",
        "article-007",
    ]
    all_ids = _placed_ids(plan) + [item.article_id for item in plan.overflow.items]
    assert all_ids == [story.article_id for story in stories]
    assert len(all_ids) == len(set(all_ids))


@pytest.mark.parametrize(
    "mutation",
    [
        {"content_version": "sha256:" + "f" * 64},
        {"headline": "Değişen başlık"},
        {"dek": "Değişen sunuş"},
        {"source_display_name": "Başka Kaynak"},
        {"section": "Ekonomi"},
        {"has_visual": False, "visual_width": None, "visual_height": None, "visual_identity": None},
    ],
)
def test_layout_key_changes_for_layout_relevant_story_input(
    mutation: dict[str, object],
) -> None:
    story = _story(1)
    changed = story.model_copy(update=mutation)
    assert build_layout_plan((story,)).layout_key != build_layout_plan((changed,)).layout_key


def test_layout_key_changes_for_policy_and_template_registry() -> None:
    stories = tuple(_story(index) for index in range(1, 6))
    baseline = build_layout_plan(stories, policy=LayoutPolicy(max_pages=2))
    policy_change = build_layout_plan(stories, policy=LayoutPolicy(max_pages=1))
    registry_change = build_layout_plan(
        stories,
        policy=LayoutPolicy(max_pages=2),
        registry=replace(DEFAULT_TEMPLATE_REGISTRY, version="gazet-e.layout-templates.v2"),
    )
    assert len({baseline.layout_key, policy_change.layout_key, registry_change.layout_key}) == 3


def test_layout_key_changes_with_engine_and_policy_contract_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import edition_layout_engine

    story = _story(1)
    baseline = edition_layout_engine.build_layout_plan((story,))
    with monkeypatch.context() as patch:
        patch.setattr(
            edition_layout_engine,
            "LAYOUT_ENGINE_VERSION",
            "gazet-e.layout-engine.v2",
        )
        engine_change = edition_layout_engine.build_layout_plan((story,))
    with monkeypatch.context() as patch:
        patch.setattr(
            edition_layout_engine,
            "LAYOUT_POLICY_VERSION",
            "gazet-e.layout-policy.v2",
        )
        policy_change = edition_layout_engine.build_layout_plan((story,))
    assert len(
        {baseline.layout_key, engine_change.layout_key, policy_change.layout_key}
    ) == 3


def test_layout_key_is_stable_for_irrelevant_iteration_order() -> None:
    stories = tuple(_story(index) for index in range(1, 7))
    assert build_layout_plan(stories).layout_key == build_layout_plan(
        tuple(reversed(stories))
    ).layout_key


def test_pages_project_directly_into_existing_q04_contract() -> None:
    stories = tuple(_story(index) for index in range(1, 5))
    plan = build_layout_plan(stories)
    document = _q04_document(plan, stories)
    validated = CanonicalEditionValidator().validate(document)
    assert validated.document["pages"] == [
        page.model_dump(mode="json") for page in plan.pages
    ]
    assert validated.document["cache"]["layout_key"] == plan.layout_key


def test_layout_models_reject_unknown_or_inconsistent_fields() -> None:
    with pytest.raises(ValidationError):
        LayoutPolicy(max_pages=0)
    with pytest.raises(ValidationError):
        LayoutStory.model_validate(
            {
                **_story(1, has_visual=False).model_dump(mode="json"),
                "visual_width": 1536,
            }
        )
    with pytest.raises(ValidationError):
        LayoutStory.model_validate(
            {**_story(1).model_dump(mode="json"), "raw_prompt": "forbidden"}
        )
    with pytest.raises(ValidationError):
        LayoutStory.model_validate(
            {**_story(1).model_dump(mode="json"), "headline": "   "}
        )


def test_q09_modules_have_no_network_provider_browser_or_pdf_path() -> None:
    from services import (
        edition_layout_engine,
        edition_layout_models,
        edition_layout_templates,
    )

    sources = "\n".join(
        inspect.getsource(module)
        for module in (
            edition_layout_engine,
            edition_layout_models,
            edition_layout_templates,
        )
    ).casefold()
    for forbidden in (
        "openai",
        ".images.generate(",
        ".responses.create(",
        "requests.",
        "httpx.",
        "urllib",
        "playwright",
        "pdf",
        "jinja",
        "publisher_body",
        "raw_prompt",
        "api_key",
        "local_path",
        "signed_url",
    ):
        assert forbidden not in sources
    assert LAYOUT_ENGINE_VERSION == "gazet-e.layout-engine.v1"
    assert LAYOUT_POLICY_VERSION == "gazet-e.layout-policy.v1"


def _story(
    index: int,
    *,
    rank: int | None = None,
    tie_break_key: str | None = None,
    headline: str | None = None,
    dek: str | None = None,
    has_visual: bool = True,
) -> LayoutStory:
    visual_hash = "sha256:" + f"{index:064x}"
    return LayoutStory(
        article_id=f"article-{index:03d}",
        cluster_id=f"cluster-{index:03d}",
        content_version="sha256:" + f"{index + 100:064x}",
        rank=index if rank is None else rank,
        tie_break_key=tie_break_key or f"tie-{index:03d}",
        headline=headline or f"Deterministic haber başlığı {index}",
        dek=dek or f"Kaynak gerçekleriyle sınırlı kısa sunuş {index}.",
        source_display_name=f"Kaynak {index}",
        section="Gündem" if index < 5 else "Yaşam",
        has_visual=has_visual,
        visual_width=1536 if has_visual else None,
        visual_height=1024 if has_visual else None,
        visual_identity=visual_hash if has_visual else None,
    )


def _canonical_json(plan: LayoutPlan) -> str:
    return json.dumps(
        plan.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _placed_ids(plan: LayoutPlan) -> list[str]:
    return [
        placement.article_id
        for page in plan.pages
        for placement in page.placements
    ]


def _geometry_ids(plan: LayoutPlan) -> list[str]:
    return [
        identifier
        for page in plan.pages
        for placement in page.placements
        for identifier in (
            placement.id,
            *(region.id for region in placement.hit_regions),
        )
    ]


def _assert_valid_geometry(plan: LayoutPlan) -> None:
    for page in plan.pages:
        for index, placement in enumerate(page.placements):
            assert placement.rect.width > 0 and placement.rect.height > 0
            assert placement.rect.is_inside(page.canvas.rect)
            assert all(
                region.rect.is_inside(page.canvas.rect)
                for region in placement.hit_regions
            )
            assert all(
                not placement.rect.overlaps(other.rect)
                for other in page.placements[index + 1 :]
            )


def _q04_document(plan: LayoutPlan, stories: tuple[LayoutStory, ...]) -> dict[str, object]:
    story_by_id = {story.article_id: story for story in stories}
    placed = [story_by_id[article_id] for article_id in _placed_ids(plan)]
    articles = []
    for index, story in enumerate(placed, start=1):
        source_id = f"source-{index:03d}"
        visual_hash = story.visual_identity or "sha256:" + f"{index + 500:064x}"
        articles.append(
            {
                "id": story.article_id,
                "cluster_id": story.cluster_id,
                "content_version": story.content_version,
                "headline": story.headline,
                "dek": story.dek,
                "summary": "Sentetik ve kaynak gerçekleriyle sınırlı özet.",
                "reading_body": [{"type": "paragraph", "text": "Sentetik okuma metni."}],
                "primary_source_id": source_id,
                "sources": [
                    {
                        "id": source_id,
                        "publisher_id": f"publisher-{index:03d}",
                        "name": story.source_display_name,
                        "canonical_url": f"https://example.org/story-{index:03d}",
                    }
                ],
                "visual": {
                    "asset_id": visual_hash,
                    "content_hash": visual_hash,
                    "width": story.visual_width or 1536,
                    "height": story.visual_height or 1024,
                    "alt": "Sentetik editoryal görsel.",
                    "transparency_label": "AI-generated editorial image",
                    "provenance": {
                        "generated_by_ai": True,
                        "provider": "synthetic",
                        "model": "synthetic-model",
                        "generated_at": "2026-09-07T10:01:00Z",
                        "brief_version": "synthetic-brief.v1",
                        "style_version": "synthetic-style.v1",
                        "safety_class": "ordinary",
                        "cache_key": "sha256:" + f"{index + 600:064x}",
                    },
                },
                "cache": {
                    "summary_key": "sha256:" + f"{index + 700:064x}",
                    "visual_brief_key": "sha256:" + f"{index + 800:064x}",
                },
            }
        )
    return {
        "contract_version": "gazet-e.edition.v1",
        "edition": {
            "id": "q09-layout-projection",
            "state": "ready",
            "title": "Q09 Sentetik Baskı",
            "requested_at": "2026-09-07T10:00:00Z",
            "generated_at": "2026-09-07T10:02:00Z",
            "locale": "tr-TR",
            "timezone": "Europe/Istanbul",
            "brand": {"name": "Gazet+E", "masthead": "GAZET+E"},
            "versions": {
                "editorial_policy": "synthetic-editorial.v1",
                "summary_prompt": "synthetic-summary.v1",
                "visual_brief": "synthetic-visual.v1",
                "visual_style": "synthetic-style.v1",
                "layout_engine": plan.layout_engine_version,
            },
        },
        "pages": [page.model_dump(mode="json") for page in plan.pages],
        "articles": articles,
        "cache": {
            "edition_key": "sha256:" + "e" * 64,
            "layout_key": plan.layout_key,
        },
    }
