from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from services.edition_news_models import (
    ArticleCandidate,
    ClusterBreakdown,
    QualityDecision,
    RankedCluster,
    RankedCollection,
    RankingBreakdown,
    SourceAttribution,
)
from services.edition_summary_facts import (
    FactPacketError,
    build_fact_packet,
    summary_cache_key,
)
from services.edition_summary_models import (
    ProviderUsage,
    ReadingParagraph,
    SummaryDraft,
    SummaryFactPacket,
    VerificationVerdict,
)
from services.edition_summary_pipeline import (
    EditorialSummaryPipeline,
    ExecutionBudget,
    SummaryArtifactCache,
)
from services.edition_summary_provider import (
    EDITORIAL_POLICY_VERSION,
    GENERATOR_MAX_OUTPUT_TOKENS,
    GENERATOR_PROMPT_VERSION,
    PROVIDER_ID,
    REQUESTED_MODEL,
    VERIFIER_MAX_OUTPUT_TOKENS,
    VERIFIER_PROMPT_VERSION,
    OpenAIResponsesProvider,
    ProviderCallError,
    ProviderResponse,
)
from services.edition_summary_smoke import main as smoke_main

NOW = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)


class FakeProvider:
    def __init__(
        self,
        *,
        drafts: list[SummaryDraft | ProviderCallError] | None = None,
        verdicts: list[VerificationVerdict | ProviderCallError] | None = None,
        input_tokens: int = 100,
        output_tokens: int = 50,
    ) -> None:
        self.drafts = list(drafts or [_draft()])
        self.verdicts = list(verdicts or [_verdict("passed")])
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.generate_calls = 0
        self.verify_calls = 0
        self.repairs: list[tuple[SummaryDraft | None, tuple[str, ...]]] = []

    def generate(
        self,
        packet: SummaryFactPacket,
        *,
        prior_draft: SummaryDraft | None = None,
        reason_codes: tuple[str, ...] = (),
    ) -> ProviderResponse[SummaryDraft]:
        del packet
        self.generate_calls += 1
        self.repairs.append((prior_draft, reason_codes))
        result = self.drafts.pop(0)
        if isinstance(result, ProviderCallError):
            raise result
        return ProviderResponse(
            payload=result,
            response_model="gpt-5.6-terra-2026-09-01",
            usage=ProviderUsage(
                input_tokens=self.input_tokens,
                output_tokens=self.output_tokens,
            ),
        )

    def verify(
        self,
        packet: SummaryFactPacket,
        draft: SummaryDraft,
    ) -> ProviderResponse[VerificationVerdict]:
        del packet, draft
        self.verify_calls += 1
        result = self.verdicts.pop(0)
        if isinstance(result, ProviderCallError):
            raise result
        return ProviderResponse(
            payload=result,
            response_model="gpt-5.6-terra-2026-09-01",
            usage=ProviderUsage(
                input_tokens=self.input_tokens,
                output_tokens=self.output_tokens,
            ),
        )


def test_fact_packet_is_deterministic_and_order_independent() -> None:
    left = build_fact_packet(_collection(reverse=False), "cluster-1")
    right = build_fact_packet(_collection(reverse=True), "cluster-1")
    assert left == right
    assert left.lead_article_id == "article-a"
    assert [fact.article_id for fact in left.evidence] == ["article-a", "article-b"]
    assert left.evidence[0].feed_excerpt == "Kaynak özeti A"


def test_source_ids_and_urls_survive_into_ready_artifact() -> None:
    packet = build_fact_packet(_collection(), "cluster-1")
    artifact = _pipeline(FakeProvider()).summarize(packet)
    assert artifact.status == "ready"
    assert artifact.evidence_article_ids == ("article-a", "article-b")
    assert artifact.evidence_source_ids == ("source-a", "source-b")
    assert artifact.evidence[0].canonical_url == "https://example.org/a"
    assert artifact.evidence[0].content_version == "content-a"
    assert artifact.evidence[1].source_id == "source-b"
    assert artifact.response_model == "gpt-5.6-terra-2026-09-01"
    assert artifact.requested_model == REQUESTED_MODEL


def test_versions_are_explicit_and_json_ready_for_future_edition_fields() -> None:
    artifact = _pipeline(FakeProvider()).summarize(_packet())
    output = artifact.model_dump(mode="json")
    json.dumps(output, ensure_ascii=False)
    assert output["prompt_version"] == GENERATOR_PROMPT_VERSION
    assert output["verifier_prompt_version"] == VERIFIER_PROMPT_VERSION
    assert output["editorial_policy_version"] == EDITORIAL_POLICY_VERSION
    assert output["provider"] == PROVIDER_ID
    assert output["dek"]
    assert output["summary"]
    assert output["reading_body"][0]["type"] == "paragraph"


def test_cache_key_changes_on_relevant_inputs_but_not_collection_order() -> None:
    first = build_fact_packet(_collection(reverse=False), "cluster-1")
    reordered = build_fact_packet(_collection(reverse=True), "cluster-1")
    key = _cache_key(first)
    assert key == _cache_key(reordered)
    changed_fact = first.model_copy(
        update={"fact_fingerprint": "sha256:" + "b" * 64}
    )
    assert key != _cache_key(changed_fact)
    assert key != _cache_key(first, prompt_version="summary.changed")
    assert key != _cache_key(first, policy_version="policy.changed")
    assert key != _cache_key(first, verifier_version="verifier.changed")
    assert key != _cache_key(first, model="model.changed")
    assert key != _cache_key(first, provider="provider.changed")
    assert key != _cache_key(first.model_copy(update={"locale": "en-US"}))


def test_exact_cache_hit_happens_before_provider_call() -> None:
    cache = SummaryArtifactCache()
    packet = _packet()
    initial_provider = FakeProvider()
    initial = _pipeline(initial_provider, cache=cache).summarize(packet)
    provider = FakeProvider()
    cached = _pipeline(provider, cache=cache).summarize(packet)
    assert cached == initial
    assert provider.generate_calls == 0
    assert provider.verify_calls == 0


def test_unknown_source_reference_fails_closed_before_verifier() -> None:
    invalid = _draft(evidence_source_ids=("unknown-source",))
    provider = FakeProvider(drafts=[invalid])
    cache = SummaryArtifactCache()
    artifact = _pipeline(provider, cache=cache).summarize(_packet())
    assert artifact.status == "unavailable"
    assert artifact.reason_codes == ("unknown_source_reference",)
    assert artifact.summary == ""
    assert artifact.reading_body == ()
    assert provider.generate_calls == 1
    assert provider.verify_calls == 0
    assert len(cache) == 0


def test_mismatched_article_and_source_references_fail_closed() -> None:
    invalid = SummaryDraft(
        dek="Kısa sunuş",
        summary="Yalnız ilk habere dayalı özet.",
        reading_body=(ReadingParagraph(type="paragraph", text="Kısa metin."),),
        evidence_article_ids=("article-a",),
        evidence_source_ids=("source-b",),
    )
    provider = FakeProvider(drafts=[invalid])
    artifact = _pipeline(provider).summarize(_packet())
    assert artifact.status == "unavailable"
    assert artifact.reason_codes == ("unknown_source_reference",)
    assert provider.verify_calls == 0


def test_broken_cluster_article_reference_fails_closed() -> None:
    collection = _collection()
    broken_cluster = collection.clusters[0].model_copy(
        update={"member_article_ids": ("article-a", "missing")}
    )
    broken = collection.model_copy(update={"clusters": (broken_cluster,)})
    with pytest.raises(FactPacketError) as error:
        build_fact_packet(broken, "cluster-1")
    assert error.value.reason_code == "unknown_article_reference"


def test_lead_must_be_a_cluster_member() -> None:
    collection = _collection()
    broken_cluster = collection.clusters[0].model_copy(
        update={"member_article_ids": ("article-b",)}
    )
    broken = collection.model_copy(update={"clusters": (broken_cluster,)})
    with pytest.raises(FactPacketError) as error:
        build_fact_packet(broken, "cluster-1")
    assert error.value.reason_code == "unknown_lead_reference"


@pytest.mark.parametrize("reason", ["malformed_output", "oversized_output"])
def test_malformed_or_oversized_provider_output_fails_closed(reason: str) -> None:
    provider = FakeProvider(drafts=[ProviderCallError(reason)])
    artifact = _pipeline(provider).summarize(_packet())
    assert artifact.status == "unavailable"
    assert artifact.reason_codes == (reason,)
    assert artifact.provider_call_count == 1


@pytest.mark.parametrize(
    "reason",
    [
        "invented_quote",
        "invented_date",
        "invented_number",
        "invented_name",
        "invented_entity",
        "unsupported_claim",
    ],
)
def test_verifier_rejects_unsupported_claim_categories(reason: str) -> None:
    provider = FakeProvider(
        drafts=[_draft(), _draft(summary="Kanıta göre düzeltilmiş özet.")],
        verdicts=[_verdict("failed", reason), _verdict("failed", reason)],
    )
    artifact = _pipeline(provider).summarize(_packet())
    assert artifact.status == "unavailable"
    assert reason in artifact.reason_codes
    assert artifact.verification_status == "failed"
    assert artifact.provider_call_count == 4


def test_one_repair_is_bounded_and_can_produce_verified_artifact() -> None:
    repaired = _draft(summary="Yalnız kaynak olgularına dayanan düzeltilmiş özet.")
    provider = FakeProvider(
        drafts=[_draft(), repaired],
        verdicts=[
            _verdict("failed", "unsupported_claim"),
            _verdict("passed"),
        ],
    )
    artifact = _pipeline(provider).summarize(_packet())
    assert artifact.status == "ready"
    assert artifact.summary == repaired.summary
    assert provider.generate_calls == 2
    assert provider.verify_calls == 2
    assert provider.repairs[1][0] is not None
    assert provider.repairs[1][1] == ("unsupported_claim",)


def test_repeated_verification_failure_is_not_success_cached() -> None:
    cache = SummaryArtifactCache()
    provider = FakeProvider(
        drafts=[_draft(), _draft()],
        verdicts=[
            _verdict("failed", "unsupported_claim"),
            _verdict("failed", "unsupported_claim"),
        ],
    )
    artifact = _pipeline(provider, cache=cache).summarize(_packet())
    assert artifact.status == "unavailable"
    assert "repair_failed" in artifact.reason_codes
    assert artifact.dek == artifact.summary == ""
    assert len(cache) == 0


def test_provider_timeout_has_safe_bounded_diagnostic_without_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "SYNTHETIC_CREDENTIAL_MARKER"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    provider = FakeProvider(drafts=[ProviderCallError("provider_timeout")])
    artifact = _pipeline(provider).summarize(_packet())
    serialized = json.dumps(artifact.model_dump(mode="json"))
    assert artifact.reason_codes == ("provider_timeout",)
    assert secret not in serialized
    assert "feed_excerpt" not in serialized


def test_budget_excess_stops_paid_work_and_is_not_cached() -> None:
    provider = FakeProvider(input_tokens=8_001, output_tokens=1)
    cache = SummaryArtifactCache()
    artifact = _pipeline(provider, cache=cache).summarize(_packet())
    assert artifact.status == "unavailable"
    assert artifact.reason_codes == ("budget_exceeded",)
    assert provider.generate_calls == 1
    assert provider.verify_calls == 0
    assert len(cache) == 0


def test_openai_adapter_uses_exact_responses_configuration() -> None:
    response = SimpleNamespace(
        status="completed",
        output_text=json.dumps(_draft().model_dump(mode="json")),
        model="gpt-5.6-terra-returned",
        usage=SimpleNamespace(input_tokens=120, output_tokens=40),
    )
    fake_responses = _CapturingResponses(response)
    adapter = OpenAIResponsesProvider(
        client=SimpleNamespace(responses=fake_responses)
    )
    result = adapter.generate(_packet())
    request = fake_responses.calls[0]
    assert result.response_model == "gpt-5.6-terra-returned"
    assert request["model"] == REQUESTED_MODEL
    assert request["store"] is False
    assert request["service_tier"] == "default"
    assert request["reasoning"] == {"effort": "low"}
    assert request["tools"] == []
    assert request["background"] is False
    assert request["truncation"] == "disabled"
    assert request["max_output_tokens"] == GENERATOR_MAX_OUTPUT_TOKENS
    assert request["text"]["format"]["type"] == "json_schema"
    assert request["text"]["format"]["strict"] is True
    assert "api_key" not in request


def test_openai_verifier_has_separate_prompt_and_token_bound() -> None:
    response = SimpleNamespace(
        status="completed",
        output_text=json.dumps(_verdict("passed").model_dump(mode="json")),
        model="gpt-5.6-terra-returned",
        usage=SimpleNamespace(input_tokens=130, output_tokens=10),
    )
    fake_responses = _CapturingResponses(response)
    adapter = OpenAIResponsesProvider(
        client=SimpleNamespace(responses=fake_responses)
    )
    adapter.verify(_packet(), _draft())
    request = fake_responses.calls[0]
    assert request["max_output_tokens"] == VERIFIER_MAX_OUTPUT_TOKENS
    assert "Verify" in request["instructions"]
    assert VERIFIER_PROMPT_VERSION != GENERATOR_PROMPT_VERSION


def test_openai_adapter_rejects_oversized_structured_output() -> None:
    oversized = _draft().model_dump(mode="json")
    oversized["summary"] = "x" * 501
    response = SimpleNamespace(
        status="completed",
        output_text=json.dumps(oversized),
        model="gpt-5.6-terra-returned",
        usage=SimpleNamespace(input_tokens=10, output_tokens=10),
    )
    adapter = OpenAIResponsesProvider(
        client=SimpleNamespace(responses=_CapturingResponses(response))
    )
    with pytest.raises(ProviderCallError) as error:
        adapter.generate(_packet())
    assert error.value.reason_code == "oversized_output"


def test_openai_adapter_discards_raw_exception_text() -> None:
    secret = "SYNTHETIC_RAW_ERROR_MARKER"

    class FailingResponses:
        def create(self, **kwargs: object) -> object:
            del kwargs
            raise RuntimeError(secret)

    adapter = OpenAIResponsesProvider(
        client=SimpleNamespace(responses=FailingResponses())
    )
    with pytest.raises(ProviderCallError) as error:
        adapter.generate(_packet())
    assert str(error.value) == "provider_error"
    assert error.value.__cause__ is None
    assert secret not in repr(error.value)


def test_missing_environment_secret_fails_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ProviderCallError) as error:
        OpenAIResponsesProvider()
    assert error.value.reason_code == "provider_error"
    assert str(error.value) == "provider_error"


def test_openai_client_timeout_and_retry_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import edition_summary_provider

    captured: dict[str, object] = {}

    def fake_openai(**kwargs: object) -> object:
        captured.update(kwargs)
        return SimpleNamespace(responses=SimpleNamespace())

    monkeypatch.setenv("OPENAI_API_KEY", "SYNTHETIC_ENV_MARKER")
    monkeypatch.setattr(edition_summary_provider, "OpenAI", fake_openai)
    edition_summary_provider.OpenAIResponsesProvider()
    assert captured == {"timeout": 20.0, "max_retries": 1}


def test_live_smoke_without_secret_is_pending_and_does_not_leak(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert smoke_main() == 2
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "passed": False,
        "reason": "missing_openai_api_key",
        "status": "pending",
    }


def test_summary_modules_do_not_scrape_or_add_hidden_network_paths() -> None:
    from services import edition_summary_facts, edition_summary_provider

    sources = inspect.getsource(edition_summary_facts) + inspect.getsource(
        edition_summary_provider
    )
    assert "requests.get" not in sources
    assert "feedparser" not in sources
    assert "publisher body" not in sources.casefold()
    assert ".responses.create(" in sources
    assert "tools=[]" in sources


def test_contract_rejects_non_https_evidence_and_unknown_verifier_reason() -> None:
    with pytest.raises(ValidationError):
        type(_packet().evidence[0]).model_validate(
            {
                **_packet().evidence[0].model_dump(),
                "canonical_url": "http://unsafe.example/a",
            }
        )
    with pytest.raises(ValidationError):
        VerificationVerdict.model_validate(
            {"status": "failed", "reason_codes": ["unbounded-provider-text"]}
        )


class _CapturingResponses:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []
        self.generator_instructions = ""

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if not self.generator_instructions:
            self.generator_instructions = str(kwargs["instructions"])
        return self.response


def _pipeline(
    provider: FakeProvider,
    *,
    cache: SummaryArtifactCache | None = None,
) -> EditorialSummaryPipeline:
    return EditorialSummaryPipeline(
        provider,
        cache=cache,
        clock=lambda: NOW,
    )


def _packet() -> SummaryFactPacket:
    return build_fact_packet(_collection(), "cluster-1")


def _draft(
    *,
    summary: str = "Kaynaklara göre program ve çalışma duyuruldu.",
    evidence_source_ids: tuple[str, ...] = ("source-a", "source-b"),
) -> SummaryDraft:
    return SummaryDraft(
        dek="Duyurunun öne çıkan noktaları",
        summary=summary,
        reading_body=(
            ReadingParagraph(
                type="paragraph",
                text="Programın ayrıntıları iki kaynakta yer aldı.",
            ),
        ),
        evidence_article_ids=("article-a", "article-b"),
        evidence_source_ids=evidence_source_ids,
    )


def _verdict(status: str, *reasons: str) -> VerificationVerdict:
    return VerificationVerdict.model_validate(
        {"status": status, "reason_codes": list(reasons)}
    )


def _cache_key(
    packet: SummaryFactPacket,
    *,
    prompt_version: str = GENERATOR_PROMPT_VERSION,
    verifier_version: str = VERIFIER_PROMPT_VERSION,
    policy_version: str = EDITORIAL_POLICY_VERSION,
    provider: str = PROVIDER_ID,
    model: str = REQUESTED_MODEL,
) -> str:
    return summary_cache_key(
        packet,
        prompt_version=prompt_version,
        verifier_prompt_version=verifier_version,
        editorial_policy_version=policy_version,
        provider=provider,
        model=model,
    )


def _collection(*, reverse: bool = False) -> RankedCollection:
    articles = (_article("a"), _article("b"))
    members = ("article-b", "article-a") if reverse else ("article-a", "article-b")
    return RankedCollection(
        ranking_policy_version="gazet-e.news-ranking.v1",
        cluster_policy_version="gazet-e.story-cluster.v1",
        generated_at=NOW,
        articles=tuple(reversed(articles)) if reverse else articles,
        rejected_articles=(),
        clusters=(
            RankedCluster(
                cluster_id="cluster-1",
                cluster_policy_version="gazet-e.story-cluster.v1",
                member_article_ids=members,
                lead_article_id="article-a",
                publisher_ids=("publisher-a", "publisher-b"),
                score=80,
                signals=ClusterBreakdown(
                    lead_score=77,
                    source_diversity=3,
                    total=80,
                ),
            ),
        ),
    )


def _article(suffix: str) -> ArticleCandidate:
    return ArticleCandidate(
        article_id=f"article-{suffix}",
        content_version=f"content-{suffix}",
        canonical_url=f"https://example.org/{suffix}",
        headline=f"Kent programı duyuruldu {suffix.upper()}",
        feed_excerpt=f"Kaynak özeti {suffix.upper()}",
        published_at=NOW,
        collected_at=NOW,
        attribution=SourceAttribution(
            publisher_id=f"publisher-{suffix}",
            source_id=f"source-{suffix}",
            display_name=f"Kaynak {suffix.upper()}",
            section="gundem",
            feed_url=f"https://feeds.example.org/{suffix}.xml",
        ),
        quality=QualityDecision(
            policy_version="gazet-e.quality.v1",
            accepted=True,
        ),
        ranking=RankingBreakdown(
            policy_version="gazet-e.news-ranking.v1",
            base=20,
            recency=18,
            publisher=9,
            section=12,
            headline_topic=0,
            total=59,
        ),
    )
