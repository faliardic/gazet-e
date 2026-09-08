# GV2-009 — Q08 AI Visual Editor, Generation, Safety and Cache

**Authority:** GitHub Issue #20 and the owner OpenAI provider amendment

**Lane:** CRITICAL — external AI image provider, server-side secret and
editorial-safety boundary

**Completion gate:** `PASS`. The corrected v2 brief/QA and v3 generation-prompt
contract passed its bounded live-image gate on exact production revision
`0ca86a51bbfa328deed880a88da687930451de61`. Q08 is `COMPLETE`; Q09 later
completed and current integration work is Q10.

**Active integration amendment:** O-011 removes Q07/AI-text from product
runtime. Q08 remains the sole AI editorial generation stage: image generation
plus image safety/semantic QA. Its historical implementation/live evidence is
unchanged, but Q10 must supply Q06 fact/source identity directly and must not
invoke Q07 summary/verifier/repair. Deterministic visual-brief construction is
not a paid text-model call; target text-AI cost is `0`.

## 1. Boundary

Q08 is an isolated server-side stage:

```text
Q06 facts + source/cluster identity
  -> deterministic visual brief and safety classification
  -> exact cache lookup
  -> one OpenAI Image API generation
  -> local WebP validation
  -> one OpenAI Responses semantic visual-QA call
  -> ready memory artifact or fail-closed unavailable
```

The Q06 fact packet remains factual authority. Historical callers could supply
a Q07 artifact only for matching identity, but active product runtime does not
generate or pass AI summary prose. No text output authorizes new visual detail.
Q08 does not fetch publisher pages, bodies, images, reference photos, social
images or new sources.

Q08 does not modify the Q05 worker/store, Q06 ingestion, Q07 summary pipeline,
edition schema, mobile reader, Q09 layout or Q10 publication/storage wiring.

## 2. Deterministic visual brief and safety

Versions are fixed:

- brief: `gazet-e.visual-brief.v2`
- generation prompt: `gazet-e.image-prompt.v3`
- style: `gazet-e.editorial-visual.v1`
- safety: `gazet-e.visual-safety.v1`
- semantic QA: `gazet-e.visual-qa.v2`

The local brief preserves cluster, lead/evidence article and fact-fingerprint
identity. Supported subject/context cues come only from the supplied bounded
headlines and excerpts. The brief adds deterministic composition, forbidden
detail and public-safe alt-text instructions; there is no paid text-model brief
call.

Ordinary stories use `editorial_illustrative`. War/conflict, disaster, accident,
crime/violence, political event and death/injury categories force
`editorial_conceptual`. A caller-declared named-real-person story also forces a
non-identifying conceptual representation. Sensitive composition is restricted
to non-literal abstract geometry/forms, controlled light/material/texture and
clearly conceptual symbolic treatment. Sensitive briefs prohibit scene
reconstruction and exact faces, people, clothing, place, damage, casualties,
weapons, equipment, vehicles, weather, signage and other factual-looking event
details. If a bounded safe brief cannot be formed, generation does not run.

The runtime-private prompt is deterministic and at most 6,000 characters. It is
never part of artifact/cache metadata, logs, diagnostics or PR evidence. For
`editorial_conceptual`, the brief's exact `composition_intent` is the single
authoritative visual grammar; the renderer adds no broader object, atmosphere or
scene allowance.

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

The verifier receives only the in-memory image, bounded supported cues, the same
bounded `composition_intent` supplied to generation,
representation/safety/style versions and forbidden-detail rules. For
`editorial_conceptual`, explicitly allowed non-factual abstract geometry/forms,
light/material/texture and clearly conceptual symbolic motifs are not by
themselves unsupported visual details. Exact factual-looking people, place,
event scene, damage, casualty, equipment, vehicle, signage or other unsupported
reconstruction still fails closed. Its output is only `passed|failed` with
bounded reason codes: documentary risk, unsupported visual detail, identifiable
real person, embedded text/logo, sensitive-mode violation, style mismatch or
malformed image.

QA failure returns `unavailable`, exposes no image bytes and is not cached.
There is no automatic regeneration or repair in the Q08 contract.

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
`image_cache_key` additionally hashes the brief, generation-prompt and semantic
QA versions plus provider/model, style, safety/mode, dimensions, quality, format,
compression, background and moderation. The v2 contract therefore cannot reuse
v1 success-cache entries. Exact image cache lookup occurs before any paid call.
Only QA-passed ready results enter the success cache; a cache hit makes zero
provider calls.

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

The earlier gate passed on revision
`ead5f5d69eeb89785dcd82af2838ee933a5d4b88`, before the sensitive-event
classification boundary changed, and is not closure authority for the current
production revision. The initial gate on
`21075735c5a8e765b398ea00fc68a93db75fd45c` stopped after the ordinary scenario
failed semantic QA with `unsupported_visual_detail`; the pipeline returned
`unavailable` and exposed no image bytes.

The owner-authorized final validation-only retry on the same production
revision did not fully pass and will not be repeated. The ordinary scenario was
`ready` / `editorial_illustrative` / `ordinary`: 1536x1024 WebP, 159,858 bytes,
asset `sha256:bda85d8549ba1ef58089844bf3c3aab255fbd2fbb0b725f725a1131d9992fee4`,
two calls, generation usage 315 input / 1,372 output tokens, QA usage 2,239 input
/ 21 output tokens, and estimated cost USD 0.045730. The sensitive scenario was
`unavailable` / `editorial_conceptual` / `sensitive_real_event` after semantic
QA returned `unsupported_visual_detail`; its terminal artifact exposed no image
bytes. It used two calls, generation usage 335 input / 1,372 output tokens, QA
usage 2,253 input / 150 output tokens, and estimated cost USD 0.047306. Aggregate
evidence was four logical calls, two generation attempts and estimated cost USD
0.093036. Requested models remained `gpt-image-2-2026-04-21` and
`gpt-5.6-terra`. Prompt, fact packet, image bytes, raw provider responses and
credential were not persisted.

The one-time corrected-revision gate on
`0ca86a51bbfa328deed880a88da687930451de61` fully passed. The ordinary scenario
was `ready` / `editorial_illustrative` / `ordinary`: 1536x1024 WebP, 154,248
bytes, asset
`sha256:cf08e3b6c801541744109894492c81d93da8e3a5bf4ee2f42a8d5d84a0040a7d`,
two calls, generation usage 345 input / 1,372 output tokens, QA usage 2,360 input
/ 21 output tokens, and estimated cost USD 0.045972. The sensitive scenario was
`ready` / `editorial_conceptual` / `sensitive_real_event`: 1536x1024 WebP,
279,902 bytes, asset
`sha256:b4588b1cfcd1c10c2646e211835b7d6430d3aad3e531ba4661b89ffdc63da98a`,
two calls, generation usage 405 input / 1,372 output tokens, QA usage 2,423 input
/ 71 output tokens, and estimated cost USD 0.046698. Both reason-code sets were
empty. Aggregate evidence was four logical calls, two images and estimated cost
USD 0.092670. Requested models were `gpt-image-2-2026-04-21` and
`gpt-5.6-terra`. Local WebP decode, exact dimensions and SHA identity passed;
prompt, fact packet, image bytes, raw provider responses, credential and private
locators were not persisted.

The PR remains Draft for review. Organization verification, exact-model access,
credential, moderation, budget or sensitive conceptual-QA failure remains a
fail-closed condition; model or safety policy is not weakened to obtain PASS.

## 8. Explicit exclusions

No object storage, public URL, database persistence, publisher image/body fetch,
reference image, layout, worker/mobile/schema integration, public deployment,
account/payment/analytics or commercial-rights claim is part of Q08.
