from __future__ import annotations

import base64
import hashlib
import inspect
import json
from datetime import datetime, timezone
from functools import lru_cache
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image
from pydantic import ValidationError

from services.edition_news_models import (
    ArticleCandidate,
    ClusterBreakdown,
    QualityDecision,
    RankedCluster,
    RankedCollection,
    SourceAttribution,
)
from services.edition_visual_brief import (
    GENERATION_PROMPT_VERSION,
    MAX_PROMPT_CHARS,
    SAFETY_VERSION,
    STYLE_VERSION,
    VISUAL_BRIEF_VERSION,
    VISUAL_QA_VERSION,
    VisualEvidenceFact,
    VisualFactPacket,
    VisualBriefError,
    build_visual_brief,
    build_visual_fact_packet,
    image_cache_key,
    render_generation_prompt,
)
from services.edition_visual_models import VisualQAVerdict
from services.edition_visual_pipeline import (
    IMAGE_ESTIMATED_COST_USD,
    EditorialVisualPipeline,
    ExecutionBudget,
    VisualArtifactCache,
)
from services.edition_visual_provider import (
    IMAGE_TIMEOUT_SECONDS,
    MAX_DECODED_BYTES,
    MAX_GENERATION_CONCURRENCY,
    PROVIDER_ID,
    QA_INSTRUCTIONS,
    QA_MAX_OUTPUT_TOKENS,
    QA_MODEL,
    QA_TIMEOUT_SECONDS,
    REQUESTED_IMAGE_MODEL,
    SDK_MAX_RETRIES,
    GeneratedImageResponse,
    ImageProviderUsage,
    OpenAIVisualProvider,
    ProviderCallError,
    QAProviderResponse,
)
from services.edition_visual_smoke import (
    LIVE_MAX_CALLS,
    LIVE_MAX_COST_USD,
    LIVE_MAX_IMAGES,
    main as smoke_main,
)

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


class FakeProvider:
    def __init__(
        self,
        *,
        image_bytes: bytes | None = None,
        generation_error: ProviderCallError | None = None,
        verdict: VisualQAVerdict | None = None,
        qa_error: ProviderCallError | None = None,
        qa_input_tokens: int = 120,
        qa_output_tokens: int = 20,
    ) -> None:
        self.image_bytes = image_bytes if image_bytes is not None else _image_bytes()
        self.generation_error = generation_error
        self.verdict = verdict or _verdict("passed")
        self.qa_error = qa_error
        self.qa_input_tokens = qa_input_tokens
        self.qa_output_tokens = qa_output_tokens
        self.generate_calls = 0
        self.verify_calls = 0

    def generate(self, brief: object) -> GeneratedImageResponse:
        del brief
        self.generate_calls += 1
        if self.generation_error is not None:
            raise self.generation_error
        return GeneratedImageResponse(
            image_bytes=self.image_bytes,
            response_model=None,
            usage=ImageProviderUsage(input_tokens=22, output_tokens=33),
        )

    def verify(self, brief: object, image_bytes: bytes) -> QAProviderResponse:
        del brief, image_bytes
        self.verify_calls += 1
        if self.qa_error is not None:
            raise self.qa_error
        return QAProviderResponse(
            verdict=self.verdict,
            response_model="gpt-5.6-terra-returned",
            input_tokens=self.qa_input_tokens,
            output_tokens=self.qa_output_tokens,
        )


def test_visual_brief_is_deterministic_and_preserves_evidence_identity() -> None:
    first = build_visual_brief(_packet(reverse=False))
    second = build_visual_brief(_packet(reverse=True))
    assert first == second
    assert first.evidence_article_ids == ("article-a", "article-b")
    assert first.lead_article_id == "article-a"
    assert first.fact_fingerprint == "sha256:" + "a" * 64
    assert first.brief_version == VISUAL_BRIEF_VERSION
    assert first.style_version == STYLE_VERSION
    assert first.safety_version == SAFETY_VERSION
    assert first.prompt_version == GENERATION_PROMPT_VERSION


def test_non_sensitive_story_is_editorial_illustrative() -> None:
    brief = build_visual_brief(_packet())
    assert brief.safety_class == "ordinary"
    assert brief.safety_categories == ()
    assert brief.representation_mode == "editorial_illustrative"
    assert brief.composition_intent == (
        "Premium modern editorial illustration with a clear subject, refined "
        "light and materials, and generous clean negative space for layout."
    )


def test_ordinary_oldu_does_not_collapse_into_death_injury() -> None:
    brief = build_visual_brief(_packet(headline="Etkinlik başarılı oldu"))
    assert "death_injury" not in brief.safety_categories
    assert brief.safety_class == "ordinary"
    assert brief.representation_mode == "editorial_illustrative"


@pytest.mark.parametrize(
    ("headline", "category"),
    [
        ("Savaş sonrası görüşmeler başladı", "war_conflict"),
        ("Deprem için afet planı açıklandı", "disaster"),
        ("Tren kazası araştırılıyor", "accident"),
        ("Şiddet saldırısı soruşturuluyor", "crime_violence"),
        ("Seçim mitingi düzenlendi", "political_event"),
        ("Olayda yaralı olduğu bildirildi", "death_injury"),
        ("Yangında 5 kişi yaralandı", "death_injury"),
        ("Üç yolcu hayatını kaybetti", "death_injury"),
        ("İki kişi öldü", "death_injury"),
    ],
)
def test_sensitive_categories_force_conceptual_mode(
    headline: str, category: str
) -> None:
    brief = build_visual_brief(_packet(headline=headline))
    assert category in brief.safety_categories
    assert brief.safety_class == "sensitive_real_event"
    assert brief.representation_mode == "editorial_conceptual"
    assert "belgesel iddiası" in brief.alt_text


def test_sensitive_brief_uses_narrow_non_factual_conceptual_grammar() -> None:
    brief = build_visual_brief(_packet(headline="Yangında 5 kişi yaralandı"))
    intent = brief.composition_intent
    assert "non-literal abstract geometry and forms" in intent
    assert "controlled light, material, texture" in intent
    assert "clearly conceptual symbolic treatment" in intent
    assert "Do not reconstruct a scene" in intent
    for forbidden in (
        "identifiable people",
        "an exact place",
        "event-specific equipment",
        "vehicles",
        "damage",
        "casualties",
        "signage",
        "factual-looking details",
    ):
        assert forbidden in intent


def test_named_real_person_flag_forces_non_identifying_conceptual_mode() -> None:
    brief = build_visual_brief(_packet(), named_real_person=True)
    assert brief.safety_class == "named_real_person"
    assert "named_real_person" in brief.safety_categories
    assert brief.representation_mode == "editorial_conceptual"
    assert any("likeness" in item for item in brief.forbidden_details)


def test_q06_direct_visual_packet_is_bounded_and_has_no_q07_dependency() -> None:
    ranked = _ranked_collection()
    packet = build_visual_fact_packet(ranked, "cluster-1", locale="tr-TR")
    assert packet.lead_article_id == "article-a"
    assert packet.evidence[0].headline == ranked.articles[0].headline
    assert len(packet.evidence[0].feed_excerpt) <= 600
    from services import edition_visual_brief

    source = inspect.getsource(edition_visual_brief)
    assert "edition_summary" not in source
    assert "SummaryArtifact" not in source


def test_generation_prompt_is_bounded_and_has_safety_instructions() -> None:
    brief = build_visual_brief(_packet(headline="Deprem için plan açıklandı"))
    prompt = render_generation_prompt(brief)
    assert len(prompt) <= MAX_PROMPT_CHARS
    assert brief.composition_intent in prompt
    assert "abstraction, symbols, objects, or atmosphere" not in prompt
    assert "composition_intent is the single authoritative visual grammar" in prompt
    assert "not press or documentary evidence" in prompt
    assert "do not reconstruct a scene" in prompt
    for forbidden in (
        "identifiable person",
        "exact place",
        "event-specific equipment",
        "vehicle",
        "damage",
        "casualty",
        "signage",
        "unsupported factual-looking detail",
    ):
        assert forbidden in prompt
    assert "https://" not in prompt.casefold()


def test_brief_and_image_cache_keys_change_only_on_relevant_inputs() -> None:
    ordinary = build_visual_brief(_packet(reverse=False))
    reordered = build_visual_brief(_packet(reverse=True))
    sensitive = build_visual_brief(_packet(headline="Deprem planı açıklandı"))
    assert ordinary.visual_brief_key == reordered.visual_brief_key
    assert ordinary.visual_brief_key != sensitive.visual_brief_key
    key = image_cache_key(ordinary, provider=PROVIDER_ID, model=REQUESTED_IMAGE_MODEL)
    assert key == image_cache_key(
        reordered, provider=PROVIDER_ID, model=REQUESTED_IMAGE_MODEL
    )
    assert key != image_cache_key(ordinary, provider=PROVIDER_ID, model="changed")
    assert key != image_cache_key(sensitive, provider=PROVIDER_ID, model=REQUESTED_IMAGE_MODEL)


def test_corrected_contract_versions_invalidate_legacy_cache_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import edition_visual_brief

    current_brief = edition_visual_brief.build_visual_brief(_packet())
    current_key = edition_visual_brief.image_cache_key(
        current_brief, provider=PROVIDER_ID, model=REQUESTED_IMAGE_MODEL
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            edition_visual_brief, "VISUAL_BRIEF_VERSION", "gazet-e.visual-brief.v1"
        )
        patch.setattr(
            edition_visual_brief,
            "GENERATION_PROMPT_VERSION",
            "gazet-e.image-prompt.v1",
        )
        patch.setattr(
            edition_visual_brief, "VISUAL_QA_VERSION", "gazet-e.visual-qa.v1"
        )
        legacy_brief = edition_visual_brief.build_visual_brief(_packet())
        legacy_key = edition_visual_brief.image_cache_key(
            legacy_brief, provider=PROVIDER_ID, model=REQUESTED_IMAGE_MODEL
        )
    assert current_brief.visual_brief_key != legacy_brief.visual_brief_key
    assert current_key != legacy_key


def test_prompt_v3_cache_identity_differs_from_prompt_v2() -> None:
    brief_v3 = build_visual_brief(_packet())
    key_v3 = image_cache_key(
        brief_v3, provider=PROVIDER_ID, model=REQUESTED_IMAGE_MODEL
    )
    brief_v2 = brief_v3.model_copy(
        update={"prompt_version": "gazet-e.image-prompt.v2"}
    )
    key_v2 = image_cache_key(
        brief_v2, provider=PROVIDER_ID, model=REQUESTED_IMAGE_MODEL
    )
    assert key_v3 != key_v2


def test_exact_cache_hit_precedes_all_paid_provider_calls() -> None:
    cache = VisualArtifactCache()
    brief = build_visual_brief(_packet())
    first_provider = FakeProvider()
    first = _pipeline(first_provider, cache=cache).create(brief)
    second_provider = FakeProvider()
    second = _pipeline(second_provider, cache=cache).create(brief)
    assert second == first
    assert second_provider.generate_calls == 0
    assert second_provider.verify_calls == 0


def test_ready_artifact_has_exact_webp_hash_and_public_provenance() -> None:
    image = _image_bytes()
    result = _pipeline(FakeProvider(image_bytes=image)).create(build_visual_brief(_packet()))
    artifact = result.artifact
    expected = "sha256:" + hashlib.sha256(image).hexdigest()
    assert artifact.status == "ready"
    assert artifact.asset_id == artifact.content_hash == expected
    assert artifact.width == 1536 and artifact.height == 1024
    assert artifact.media_type == "image/webp"
    assert artifact.generated_by_ai is True
    assert artifact.transparency_label == "AI-generated editorial image"
    assert artifact.provider == "openai"
    assert artifact.requested_model == REQUESTED_IMAGE_MODEL
    assert artifact.response_model is None
    assert artifact.qa_model == QA_MODEL
    assert artifact.qa_status == "passed"


@pytest.mark.parametrize(
    ("kind", "reason"),
    [
        ("malformed", "malformed_image"),
        ("dimensions", "invalid_dimensions"),
        ("format", "invalid_media_type"),
        ("oversized", "image_too_large"),
    ],
)
def test_local_image_validation_fails_closed_before_semantic_qa(
    kind: str, reason: str
) -> None:
    image_bytes = {
        "malformed": b"not-an-image",
        "dimensions": _image_bytes(size=(1024, 1024)),
        "format": _image_bytes(format_name="PNG"),
        "oversized": b"x" * (MAX_DECODED_BYTES + 1),
    }[kind]
    provider = FakeProvider(image_bytes=image_bytes)
    cache = VisualArtifactCache()
    result = _pipeline(provider, cache=cache).create(build_visual_brief(_packet()))
    assert result.artifact.status == "unavailable"
    assert result.artifact.reason_codes == (reason,)
    assert result.image_bytes == b""
    assert provider.generate_calls == 1
    assert provider.verify_calls == 0
    assert len(cache) == 0


def test_semantic_qa_failure_does_not_regenerate_or_success_cache() -> None:
    provider = FakeProvider(
        verdict=_verdict("failed", "documentary_risk", "embedded_text_or_logo")
    )
    cache = VisualArtifactCache()
    result = _pipeline(provider, cache=cache).create(build_visual_brief(_packet()))
    assert result.artifact.status == "unavailable"
    assert result.artifact.qa_status == "failed"
    assert result.artifact.reason_codes == (
        "documentary_risk",
        "embedded_text_or_logo",
        "qa_failed",
    )
    assert provider.generate_calls == provider.verify_calls == 1
    assert result.image_bytes == b""
    assert len(cache) == 0


def test_provider_error_is_bounded_and_does_not_leak_raw_text() -> None:
    secret = "SYNTHETIC_SECRET_MARKER"
    provider = FakeProvider(generation_error=ProviderCallError("provider_timeout"))
    result = _pipeline(provider).create(build_visual_brief(_packet()))
    serialized = json.dumps(result.artifact.model_dump(mode="json"))
    assert result.artifact.reason_codes == ("provider_timeout",)
    assert secret not in serialized
    assert "prompt" not in type(result.artifact).model_fields
    assert "path" not in type(result.artifact).model_fields


def test_qa_cost_budget_exhaustion_fails_closed_without_regeneration() -> None:
    provider = FakeProvider(qa_input_tokens=20_000, qa_output_tokens=300)
    result = _pipeline(provider).create(build_visual_brief(_packet()))
    assert result.artifact.status == "unavailable"
    assert result.artifact.reason_codes == ("budget_exceeded",)
    assert provider.generate_calls == provider.verify_calls == 1


def test_budget_can_stop_before_any_paid_call() -> None:
    provider = FakeProvider()
    pipeline = EditorialVisualPipeline(
        provider,
        budget=ExecutionBudget(max_cost_usd=IMAGE_ESTIMATED_COST_USD - 0.001),
    )
    result = pipeline.create(build_visual_brief(_packet()))
    assert result.artifact.reason_codes == ("budget_exceeded",)
    assert result.artifact.provider_call_count == 0
    assert provider.generate_calls == provider.verify_calls == 0


def test_artifact_json_excludes_bytes_prompt_secret_and_private_locator() -> None:
    result = _pipeline(FakeProvider()).create(build_visual_brief(_packet()))
    output = result.artifact.model_dump(mode="json")
    encoded = json.dumps(output, ensure_ascii=False)
    assert result.image_bytes
    assert "image_bytes" not in output
    for forbidden in ("raw_prompt", "api_key", "signed_url", "local_path", "storage_locator"):
        assert forbidden not in encoded.casefold()


def test_visual_qa_verdict_rejects_unbounded_or_inconsistent_reasons() -> None:
    with pytest.raises(ValidationError):
        VisualQAVerdict.model_validate(
            {"status": "failed", "reason_codes": ["raw-provider-message"]}
        )
    with pytest.raises(ValidationError):
        VisualQAVerdict(status="passed", reason_codes=("style_mismatch",))
    with pytest.raises(ValidationError):
        VisualQAVerdict(status="failed", reason_codes=())


def test_openai_generation_adapter_uses_exact_image_configuration() -> None:
    images = _CapturingImages()
    adapter = OpenAIVisualProvider(
        client=SimpleNamespace(images=images, responses=SimpleNamespace())
    )
    response = adapter.generate(build_visual_brief(_packet()))
    request = images.calls[0]
    assert response.image_bytes == _image_bytes()
    assert response.response_model is None
    assert request["model"] == REQUESTED_IMAGE_MODEL
    assert request["n"] == 1
    assert request["size"] == "1536x1024"
    assert request["quality"] == "medium"
    assert request["output_format"] == "webp"
    assert request["output_compression"] == 90
    assert request["background"] == "opaque"
    assert request["moderation"] == "auto"
    assert "response_format" not in request
    assert request["stream"] is False
    assert request["timeout"] == IMAGE_TIMEOUT_SECONDS
    assert "partial_images" not in request
    assert "image" not in request
    assert "api_key" not in request


def test_sensitive_generation_receives_exact_bounded_conceptual_intent() -> None:
    images = _CapturingImages()
    adapter = OpenAIVisualProvider(
        client=SimpleNamespace(images=images, responses=SimpleNamespace())
    )
    brief = build_visual_brief(_packet(headline="Yangında 5 kişi yaralandı"))
    adapter.generate(brief)
    prompt = images.calls[0]["prompt"]
    assert isinstance(prompt, str)
    assert brief.composition_intent in prompt


def test_openai_qa_adapter_uses_exact_responses_configuration() -> None:
    responses = _CapturingResponses(_verdict("passed"))
    adapter = OpenAIVisualProvider(
        client=SimpleNamespace(images=SimpleNamespace(), responses=responses)
    )
    brief = build_visual_brief(_packet(headline="Yangında 5 kişi yaralandı"))
    result = adapter.verify(brief, _image_bytes())
    request = responses.calls[0]
    assert result.verdict.status == "passed"
    assert request["model"] == QA_MODEL
    assert request["reasoning"] == {"effort": "low"}
    assert request["tools"] == []
    assert request["store"] is False
    assert request["service_tier"] == "default"
    assert request["background"] is False
    assert request["truncation"] == "disabled"
    assert request["max_output_tokens"] == QA_MAX_OUTPUT_TOKENS
    assert request["timeout"] == QA_TIMEOUT_SECONDS
    assert request["text"]["format"]["type"] == "json_schema"
    assert request["text"]["format"]["strict"] is True
    content = request["input"][0]["content"]
    text_input = next(item for item in content if item["type"] == "input_text")
    payload = json.loads(text_input["text"])
    assert payload["composition_intent"] == brief.composition_intent
    assert payload["qa_version"] == VISUAL_QA_VERSION
    image_input = next(item for item in content if item["type"] == "input_image")
    assert image_input["detail"] == "high"
    assert image_input["image_url"].startswith("data:image/webp;base64,")


def test_qa_instructions_separate_allowed_abstraction_from_factual_reconstruction(
) -> None:
    assert (
        "conceptual symbolic motifs explicitly allowed by composition_intent"
        in QA_INSTRUCTIONS
    )
    assert (
        "are not,\nby themselves, unsupported_visual_detail" in QA_INSTRUCTIONS
    )
    assert (
        "exact factual-looking person, place, event scene, damage"
        in QA_INSTRUCTIONS
    )
    assert "casualty, equipment, vehicle, signage" in QA_INSTRUCTIONS
    assert "press/documentary" in QA_INSTRUCTIONS
    assert "remain fail-closed" in QA_INSTRUCTIONS


def test_openai_adapter_discards_raw_generation_exception_text() -> None:
    secret = "SYNTHETIC_RAW_EXCEPTION_SECRET"

    class FailingImages:
        def generate(self, **kwargs: object) -> object:
            del kwargs
            raise RuntimeError(secret)

    adapter = OpenAIVisualProvider(
        client=SimpleNamespace(images=FailingImages(), responses=SimpleNamespace())
    )
    with pytest.raises(ProviderCallError) as error:
        adapter.generate(build_visual_brief(_packet()))
    assert str(error.value) == "provider_error"
    assert secret not in repr(error.value)
    assert error.value.__cause__ is None


def test_missing_secret_and_client_retry_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import edition_visual_provider

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ProviderCallError) as error:
        OpenAIVisualProvider()
    assert error.value.reason_code == "provider_authentication_error"
    captured: dict[str, object] = {}

    def fake_openai(**kwargs: object) -> object:
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setenv("OPENAI_API_KEY", "SYNTHETIC_ENV_MARKER")
    monkeypatch.setattr(edition_visual_provider, "OpenAI", fake_openai)
    OpenAIVisualProvider()
    assert captured == {"max_retries": SDK_MAX_RETRIES}


def test_smoke_without_secret_is_pending_and_makes_no_provider_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert smoke_main() == 2
    assert json.loads(capsys.readouterr().out) == {
        "passed": False,
        "reason": "missing_openai_api_key",
        "status": "pending",
    }


def test_visual_modules_have_only_authorized_provider_call_sites() -> None:
    from services import edition_visual_brief, edition_visual_provider

    sources = inspect.getsource(edition_visual_brief) + inspect.getsource(
        edition_visual_provider
    )
    assert sources.count(".images.generate(") == 1
    assert sources.count(".responses.create(") == 1
    assert "requests.get" not in sources
    assert "httpx." not in sources
    assert "feedparser" not in sources
    assert "images.edit" not in sources
    assert "publisher image" not in sources.casefold()
    assert MAX_GENERATION_CONCURRENCY == 2
    assert VISUAL_BRIEF_VERSION == "gazet-e.visual-brief.v3"
    assert GENERATION_PROMPT_VERSION == "gazet-e.image-prompt.v3"
    assert VISUAL_QA_VERSION == "gazet-e.visual-qa.v2"
    assert REQUESTED_IMAGE_MODEL == "gpt-image-2-2026-04-21"
    assert QA_MODEL == "gpt-5.6-terra"
    assert ExecutionBudget() == ExecutionBudget(
        max_calls=2, max_images=1, max_cost_usd=0.08
    )
    assert LIVE_MAX_CALLS == 4
    assert LIVE_MAX_IMAGES == 2
    assert LIVE_MAX_COST_USD == 0.15


class _CapturingImages:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def generate(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(
            data=[
                SimpleNamespace(
                    b64_json=base64.b64encode(_image_bytes()).decode("ascii"),
                    url=None,
                )
            ],
            usage=SimpleNamespace(input_tokens=22, output_tokens=33),
        )


class _CapturingResponses:
    def __init__(self, verdict: VisualQAVerdict) -> None:
        self.calls: list[dict[str, object]] = []
        self.verdict = verdict

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(
            status="completed",
            output_text=json.dumps(self.verdict.model_dump(mode="json")),
            model="gpt-5.6-terra-returned",
            usage=SimpleNamespace(input_tokens=120, output_tokens=20),
        )


def _pipeline(
    provider: FakeProvider, *, cache: VisualArtifactCache | None = None
) -> EditorialVisualPipeline:
    return EditorialVisualPipeline(provider, cache=cache, clock=lambda: NOW)


def _verdict(status: str, *reasons: str) -> VisualQAVerdict:
    return VisualQAVerdict.model_validate(
        {"status": status, "reason_codes": list(reasons)}
    )


def _packet(
    *, reverse: bool = False, headline: str = "Kent kütüphanesi programı duyurdu"
) -> VisualFactPacket:
    evidence = (
        _fact("a", headline=headline),
        _fact("b", headline="Bilim merkezinde yeni sergi açıldı"),
    )
    return VisualFactPacket(
        cluster_id="cluster-1",
        lead_article_id="article-a",
        locale="tr-TR",
        fact_fingerprint="sha256:" + "a" * 64,
        evidence=tuple(reversed(evidence)) if reverse else evidence,
    )


def _fact(suffix: str, *, headline: str) -> VisualEvidenceFact:
    return VisualEvidenceFact(
        article_id=f"article-{suffix}",
        content_version=f"content-{suffix}",
        source_id=f"source-{suffix}",
        publisher_id=f"publisher-{suffix}",
        source_name=f"Kaynak {suffix.upper()}",
        canonical_url=f"https://example.org/{suffix}",
        headline=headline,
        feed_excerpt=f"Sentnak tarafından sağlanan sentetik bağlam {suffix.upper()}.",
        published_at=NOW,
    )


def _ranked_collection() -> RankedCollection:
    articles = tuple(
        ArticleCandidate(
            article_id=f"article-{suffix}",
            content_version=f"content-{suffix}",
            canonical_url=f"https://example.org/{suffix}",
            headline=headline,
            feed_excerpt=("Kaynağın bounded açıklaması. " * 40)[:1200],
            published_at=NOW,
            collected_at=NOW,
            attribution=SourceAttribution(
                publisher_id=f"publisher-{suffix}",
                source_id=f"source-{suffix}",
                display_name=f"Kaynak {suffix.upper()}",
                section="gundem",
                feed_url=f"https://example.org/{suffix}.xml",
            ),
            quality=QualityDecision(
                policy_version="test-quality.v1",
                accepted=True,
            ),
        )
        for suffix, headline in (
            ("a", "Kent kütüphanesi programı duyurdu"),
            ("b", "Bilim merkezinde yeni sergi açıldı"),
        )
    )
    return RankedCollection(
        ranking_policy_version="test-ranking.v1",
        cluster_policy_version="test-cluster.v1",
        generated_at=NOW,
        articles=articles,
        rejected_articles=(),
        clusters=(
            RankedCluster(
                cluster_id="cluster-1",
                cluster_policy_version="test-cluster.v1",
                member_article_ids=("article-a", "article-b"),
                lead_article_id="article-a",
                publisher_ids=("publisher-a", "publisher-b"),
                score=1,
                signals=ClusterBreakdown(
                    lead_score=1,
                    source_diversity=0,
                    total=1,
                ),
            ),
        ),
    )


@lru_cache(maxsize=None)
def _image_bytes(
    *, size: tuple[int, int] = (1536, 1024), format_name: str = "WEBP"
) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, (32, 64, 96)).save(output, format=format_name, quality=90)
    return output.getvalue()
