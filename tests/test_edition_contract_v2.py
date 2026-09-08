from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from services.edition_integration_ads import reserve_synthetic_ad
from services.edition_integration_layout import build_physical_layout
from services.edition_job_validation import CanonicalEditionError, CanonicalEditionValidator
from services.edition_layout_engine import build_layout_plan
from services.edition_layout_models import LayoutPolicy, LayoutStory

ROOT = Path(__file__).resolve().parents[1]
V1_FIXTURE = ROOT / "mobile" / "assets" / "fixtures" / "edition.json"
V2_FIXTURE = ROOT / "mobile" / "assets" / "fixtures" / "edition.v2.json"


@pytest.fixture
def document() -> dict[str, object]:
    return json.loads(V2_FIXTURE.read_text(encoding="utf-8"))


def test_v2_and_historical_v1_validate_and_round_trip(document: dict[str, object]) -> None:
    validator = CanonicalEditionValidator()
    validated = validator.validate(document)
    assert validated.contract_version == "gazet-e.edition.v2"
    assert json.loads(validated.canonical_json) == document
    assert validated.edition_id == "fixture-edition-v2"
    historical = json.loads(V1_FIXTURE.read_text(encoding="utf-8"))
    assert validator.validate(historical).contract_version == "gazet-e.edition.v1"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda item: item.update(contract_version="gazet-e.edition.v99"),
        lambda item: item["edition"]["versions"].update(summary_prompt="forbidden"),
        lambda item: item["articles"][0].update(summary="forbidden"),
        lambda item: item["articles"][0].update(dek="forbidden"),
        lambda item: item["articles"][0].update(reading_body=[]),
        lambda item: item["articles"][0]["cache"].update(summary_key="sha256:" + "1" * 64),
        lambda item: item["pages"][0]["physical_profile"].update(width_mm=351),
        lambda item: item["pages"][0]["canvas"].update(width=701),
        lambda item: item["pages"][0].update(ads=item["pages"][0]["ads"] * 2),
        lambda item: item["pages"][0]["ads"][0]["rect"].update(width=700, height=200, x=0),
        lambda item: item["pages"][0]["ads"][0]["rect"].update(y=700),
        lambda item: item["pages"][0]["ads"][0].update(url="https://ads.example.test"),
        lambda item: item["pages"][0]["placements"][0].update(article_id="missing"),
    ],
)
def test_v2_contract_fails_closed_for_invalid_physical_text_ad_and_refs(
    document: dict[str, object], mutate
) -> None:
    invalid = copy.deepcopy(document)
    mutate(invalid)
    with pytest.raises(CanonicalEditionError):
        CanonicalEditionValidator().validate(invalid)


def test_q10_physical_projection_reserves_display_only_ad_before_editorial() -> None:
    story = LayoutStory(
        article_id="article-a",
        cluster_id="cluster-a",
        content_version="sha256:" + "a" * 64,
        rank=0,
        tie_break_key="a",
        headline="Kent kütüphanesi programı duyurdu",
        dek="Kaynak akışının bounded açıklaması.",
        source_display_name="Kaynak A",
        section="gundem",
        has_visual=True,
        visual_width=1536,
        visual_height=1024,
        visual_identity="sha256:" + "b" * 64,
    )
    plan = build_layout_plan((story,), policy=LayoutPolicy(max_pages=1))
    first_pages, first_key = build_physical_layout(plan, edition_seed="job-a")
    same_pages, same_key = build_physical_layout(plan, edition_seed="job-a")
    other_pages, other_key = build_physical_layout(plan, edition_seed="job-b")
    page = first_pages[0]
    assert page["physical_profile"] == {
        "version": "gazet-e.physical-profile.350x500.v1",
        "width_mm": 350,
        "height_mm": 500,
        "logical_units_per_mm": 2,
    }
    assert page["canvas"] == {"width": 700, "height": 1000, "unit": "logical"}
    assert len(page["ads"]) == 1
    ad = page["ads"][0]
    assert ad["label"] == "REKLAM"
    assert "url" not in ad and "action" not in ad
    assert ad["rect"]["width"] * ad["rect"]["height"] <= 700 * 1000 * 0.15
    assert first_pages == same_pages and first_key == same_key
    assert first_key != other_key
    assert first_pages[0]["ads"][0]["creative_id"] != ""
    assert other_pages[0]["ads"][0]["creative_id"] != ""
    no_ad_pages, _ = build_physical_layout(
        plan,
        edition_seed="job-a",
        ads_enabled=False,
    )
    assert no_ad_pages[0]["ads"] == []
    assert reserve_synthetic_ad("job-a", 1, suitable=False) is None
