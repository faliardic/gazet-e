# GV2-009 — Q08 AI Visual Editor, Generation, Safety and Cache

**Authority:** GitHub Issue #20 and the owner OpenAI provider amendment

**Lane:** CRITICAL — external AI image provider, server-side secret and
editorial-safety boundary

**Completion gate:** `PASS`. Implementation, deterministic fake-provider tests
and both required bounded live-image scenarios passed on reviewed revision
`ead5f5d69eeb89785dcd82af2838ee933a5d4b88`. Q08 is `COMPLETE`; Q09 is `NEXT`.

## 1. Boundary

Q08 is an isolated server-side stage:

```text
Q06 facts + verified Q07 identity
  -> deterministic visual brief and safety classification
  -> exact cache lookup
  -> one OpenAI Image API generation
  -> local WebP validation
  -> one OpenAI Responses semantic visual-QA call
  -> ready memory artifact or fail-closed unavailable
```

The Q06 fact packet remains factual authority. A Q07 summary may be supplied
only to validate matching ready/verified identity; its prose does not authorize
new visual detail. Q08 does not fetch publisher pages, bodies, images, reference
photos, social images or new sources.

Q08 does not modify the Q05 worker/store, Q06 ingestion, Q07 summary pipeline,
edition schema, mobile reader, Q09 layout or Q10 publication/storage wiring.

## 2. Deterministic visual brief and safety

Versions are fixed:

- brief: `gazet-e.visual-brief.v1`
- generation prompt: `gazet-e.image-prompt.v1`
- style: `gazet-e.editorial-visual.v1`
- safety: `gazet-e.visual-safety.v1`
- semantic QA: `gazet-e.visual-qa.v1`

The local brief preserves cluster, lead/evidence article and fact-fingerprint
identity. Supported subject/context cues come only from the supplied bounded
headlines and excerpts. The brief adds deterministic composition, forbidden
detail and public-safe alt-text instructions; there is no paid text-model brief
call.

Ordinary stories use `editorial_illustrative`. War/conflict, disaster, accident,
crime/violence, political event and death/injury categories force
`editorial_conceptual`. A caller-declared named-real-person story also forces a
non-identifying conceptual representation. Sensitive briefs prohibit press or
documentary framing and exact faces, people, clothing, location, damage,
casualties, weapons, vehicles, weather, signage and other reconstructed event
facts. If a bounded safe brief cannot be formed, generation does not run.

The runtime-private prompt is deterministic and at most 6,000 characters. It is
never part of artifact/cache metadata, logs, diagnostics or PR evidence.

## 3. OpenAI generation contract

Generation uses only `client.images.generate`:

- model `gpt-image-2-2026-04-21`
- `n=1`
- `size="1536x1024"`
- `quality="medium"`
- `output_format="webp"`
- `output_compression=90`
- `background="opaque"`
- `moderation="auto"`
- base64 response, no URL locator
- streaming disabled and no partial images
- no edit/input/reference/publisher/web image
- request timeout 150 seconds
- SDK `max_retries=1`
- process-wide generation concurrency two
- decoded response at most 8 MiB

Only the existing `openai>=2,<3` and Pillow dependencies are used. Provider
exceptions are reduced to bounded non-secret reason codes.

## 4. Local and semantic visual QA

Before paid semantic QA, bytes must:

- decode successfully as WebP;
- be exactly 1536x1024;
- remain at or below 8 MiB;
- produce `asset_id = content_hash = sha256:<64 lowercase hex>` from exact bytes.

Semantic QA uses one OpenAI Responses request with `gpt-5.6-terra`, image detail
`high`, low reasoning, strict JSON Schema, `tools=[]`, `store=false`, default
service tier, background disabled, truncation disabled, 300 output-token limit,
30-second timeout and one SDK transient retry maximum.

The verifier receives only the in-memory image, bounded supported cues,
representation/safety/style versions and forbidden-detail rules. Its output is
only `passed|failed` with bounded reason codes: documentary risk, unsupported
visual detail, identifiable real person, embedded text/logo, sensitive-mode
violation, style mismatch or malformed image.

QA failure returns `unavailable`, exposes no image bytes and is not cached.
There is no automatic regeneration or repair in Q08 v1.

## 5. Artifact and cache contract

The JSON-ready metadata artifact contains asset hash/ID, cluster/article
identity, dimensions/media type, public-safe alt, exact AI transparency label,
provider/requested model, returned model only when supplied, generated time,
brief/prompt/style/safety versions, representation/safety class, cache keys,
QA model/status/reasons, call/usage/cost metadata and terminal status.

`VisualResult` carries ready bytes only through an injectable in-memory boundary.
Raw prompt, credential, signed URL, repository/local path and private storage
locator are not artifact fields. An unavailable result exposes no bytes.

`visual_brief_key` hashes selected fact identity, locale and brief/safety policy.
`image_cache_key` additionally hashes provider/model, style, safety/mode,
dimensions, quality, format, compression, background and moderation. Exact image
cache lookup occurs before any paid call. Only QA-passed ready results enter the
success cache; a cache hit makes zero provider calls.

## 6. Cost and call bounds

Each uncached artifact permits at most one generation plus one semantic-QA call.
The planning estimate is USD 0.041 for the medium 1536x1024 image plus Terra QA
token usage at the owner planning rates. The pipeline fails closed if aggregate
estimated cost exceeds USD 0.08. No automatic paid regeneration is possible.

## 7. Live-image gate

The memory-only smoke runs two wholly synthetic scenarios:

1. an ordinary civic/culture story requiring `editorial_illustrative`;
2. a synthetic sensitive disaster-context story requiring
   `editorial_conceptual` and no fake-documentary framing.

Each scenario permits one generation and one QA call. Aggregate bounds are four
logical calls, two images and USD 0.15. Safe evidence is restricted to scenario,
status, mode/class, dimensions, byte count, SHA asset ID, requested/QA model,
available call/token counts, estimated cost and bounded reasons. Image bytes,
prompt, fact packet, provider response and credential remain memory-only and are
not persisted.

The gate passed with four logical provider calls and two memory-only images at
an aggregate estimated cost of USD 0.093792. Both artifacts passed local WebP
decode/hash/dimension validation at 1536x1024 and semantic QA with
`gpt-5.6-terra`; the requested generation model was
`gpt-image-2-2026-04-21`. The ordinary scenario produced an
`editorial_illustrative` artifact (111,586 bytes; generation 315 input / 1,372
output tokens; QA 2,239 input / 149 output tokens). The sensitive scenario
produced an `editorial_conceptual` artifact (283,294 bytes; generation 335 input
/ 1,372 output tokens; QA 2,253 input / 85 output tokens). Both reason-code sets
were empty. Prompt, fact packet, image bytes, raw provider responses and
credential were not persisted.

The PR remains Draft for review. Organization verification, exact-model access,
credential, moderation, budget or sensitive conceptual-QA failure remains a
fail-closed condition; model or safety policy is not weakened to obtain PASS.

## 8. Explicit exclusions

No object storage, public URL, database persistence, publisher image/body fetch,
reference image, layout, worker/mobile/schema integration, public deployment,
account/payment/analytics or commercial-rights claim is part of Q08.
