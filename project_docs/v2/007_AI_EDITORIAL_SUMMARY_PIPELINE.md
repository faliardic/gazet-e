# GV2-008 — Q07 AI Editorial Summary Pipeline

**Authority:** GitHub Issue #18 and the owner OpenAI provider amendment

**Lane:** CRITICAL — external AI provider and server-side secret boundary

**Completion gate:** Implementation and deterministic fake-provider tests are
present. Q07 remains `NEXT` until the required bounded live OpenAI smoke passes.

## 1. Boundary

Q07 converts an accepted Q06 ranked story cluster into a versioned, JSON-ready
Gazet+E editorial summary artifact. It is an isolated server-side stage and is
not wired into the Q05 worker, a Q04 edition, mobile, layout or image generation.

Only these Q06 facts may enter the provider packet:

- cluster, lead article, article and content-version identities;
- headline and a bounded feed excerpt;
- source/publisher identity, display name and canonical HTTPS URL;
- publication time when Q06 supplied it;
- locale and a deterministic fingerprint derived from the cluster members.

The packet contains at most four evidence articles and truncates each internal
feed excerpt to 600 characters. The lead is always included. Publisher pages,
full bodies, images, user data and hidden sources are never fetched or supplied.

## 2. Modules

- `edition_summary_models.py`: immutable fact, draft, verification, usage and
  terminal artifact contracts.
- `edition_summary_facts.py`: deterministic Q06 adapter, bounded fact packet,
  cluster fingerprint and exact summary cache key.
- `edition_summary_provider.py`: OpenAI Responses API adapter with strict
  Structured Outputs and separate generator/verifier instructions.
- `edition_summary_pipeline.py`: cache-first orchestration, local validation,
  verification, one optional repair, budgets and safe terminal fallback.
- `edition_summary_smoke.py`: synthetic two-call live-provider gate that emits
  token/cost metadata only.

No Q05 or Q06 production module is modified by this stage.

## 3. Artifact contract

A terminal artifact records:

- cluster and lead article identities;
- evidence article/source IDs plus public-safe source attribution and canonical
  HTTPS URLs;
- locale, `dek`, summary and structured reading paragraphs;
- generator prompt, verifier prompt and editorial-policy versions;
- provider, requested model, returned generation model and returned verifier
  model metadata;
- generation time and exact `sha256:` summary cache key;
- verification status, bounded reason codes, status, provider-call count and
  aggregate token usage.

`ready` requires non-empty editorial content and `passed` verification.
`unavailable` contains no `dek`, summary or reading paragraphs, so a feed excerpt
can never become a silent fallback. Unknown fields and reason codes fail closed.

## 4. Grounding and verification

The generator is instructed to use only the supplied packet and to avoid
outside knowledge, browsing, invented quotations, numbers, dates, names,
entities, causal claims or unsupported certainty. Its evidence references must
resolve to packet article/source IDs. Evidence and draft strings are explicitly
treated as untrusted data rather than provider instructions.

Every draft passes two independent checks:

1. local Pydantic/schema, size, HTTPS and source-reference validation;
2. a separately versioned OpenAI verifier receiving the same bounded packet and
   structured draft.

A failed provider verification permits at most one repair generation and one
final verification. A second failure produces `unavailable`. Malformed,
oversized, truncated, over-budget or structurally ungrounded output fails closed
and is never success-cached.

## 5. OpenAI request contract

- Provider: OpenAI API
- Surface: Responses API only
- Requested model: `gpt-5.6-terra`
- Reasoning effort: `low`
- Structured output: strict JSON Schema
- Tools/background/streaming: none
- Storage: `store=false`
- Service tier: `default`
- Truncation: disabled/fail-closed
- Client timeout: 20 seconds
- SDK retries: at most one
- Process-wide provider concurrency: four bounded slots
- Generator output bound: 650 tokens
- Verifier output bound: 250 tokens

The only new direct dependency is `openai>=2,<3`; its SDK default transport is
used. No separate HTTP dependency is introduced.

## 6. Cache and budgets

Cache lookup happens before any provider call. The key hashes:

```text
cluster/content fingerprint
+ locale
+ generator prompt version
+ verifier prompt version
+ editorial policy version
+ provider
+ requested model
```

Member or collection ordering does not affect the fingerprint. Article content,
prompt, verifier, policy, provider, model or locale changes do. Only exact-key,
verified `ready` artifacts enter the cache.

An uncached artifact is bounded to four logical provider operations, 8,000
aggregate input tokens, 1,800 aggregate output tokens and USD 0.04 at the owner
planning rates. Budget exhaustion stops further paid work and returns
`unavailable`.

## 7. Secret and diagnostics

`OPENAI_API_KEY` is read only from the process environment by the SDK boundary.
It is never accepted as artifact/input data and must not be printed, logged,
persisted or included in exceptions. Prompts, fact packets, excerpts and raw
provider bodies are likewise absent from smoke output and PR evidence. Provider
failures reduce to bounded reason codes.

## 8. Live smoke gate

Run:

```text
python -m services.edition_summary_smoke
```

The smoke uses one synthetic article and permits only generation + verification:
two calls, 4,000 input tokens, 900 output tokens and USD 0.03 maximum. Output is
limited to status, model, call-count, aggregate token and estimated-cost
metadata.

If `OPENAI_API_KEY` is absent, the command reports a bounded PENDING status and
makes no provider call. Q07 must remain `NEXT`, Q08 must remain `QUEUED`, and the
Draft PR must not be marked complete until a real smoke passes.

## 9. Explicit exclusions

Q07 does not implement or change publisher scraping, article bodies, publisher
images, Q05 job/store/API behavior, Q06 identity/ranking behavior, Q08 images,
Q09 layout, Q10 wiring, mobile/schema/legacy code, public deployment, accounts,
payments, analytics or commercial-rights decisions.
