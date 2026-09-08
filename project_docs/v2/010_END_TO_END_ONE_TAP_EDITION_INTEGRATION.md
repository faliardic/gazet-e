# GV2-011 — Q10 End-to-end One-tap Edition Integration

**Authority:** GitHub Issue #24, including owner reset O-011/O-012/O-013

**Lane:** CRITICAL — durable image-only integration, physical page contract,
asset delivery and in-page advertising boundary

**Exact base:** `8f55b0aee5f5e623318cdb0d9024af1ca31d5546`

**Current truth:** Q10 remains `ACTIVE`; Q11 remains `QUEUED`. The first Gate A
implementation at `39de1ae44784b77fca821fe9b161d5a188c35096` is superseded as
a product direction because it wires Q07 AI-summary output into runtime. Its
T0/test evidence and the subsequent Gate B G1–G10 review remain historical and
are not deleted. This authority-sync step changes no production/test code and
does not claim a corrected Gate A/B PASS. Gate C live and Gate D device/release
actions remain pending and unauthorized.

## 1. Revised production lifecycle and AI boundary

The active lifecycle is exactly:

```text
requested -> collecting -> selecting -> illustrating
          -> laying_out -> ready | failed | cancelled
```

Q10 will retain Q05 idempotency, lease/attempt fencing, heartbeat,
cancellation, durable checkpoint recovery and immutable publication, while
removing the `summarizing` product stage through a controlled versioned
migration. Q07 production files and historical evidence are not deleted, but
the active worker must not invoke Q07 generation, verifier, repair, prompt or
summary cache paths.

AI is used only for Q08 editorial image generation and image safety/semantic
QA. Visual brief construction remains bounded and deterministic. Text-AI calls
and estimated product-runtime text-AI cost are exactly zero. Paid image work
must keep durable authorization, per-job/per-run bounds, unknown-exposure
accounting, cancellation/lease fencing and completed-work reuse.

The collection snapshot and deterministic selection remain Q06-authoritative.
No publisher page/body/image fetch, AI text enrichment or missing-excerpt fill
is added.

## 2. Reading truth and canonical edition revision

Okuma Modu contains only:

- source-authoritative headline;
- bounded source/feed description or excerpt when it exists;
- publication/source and publication time when supplied;
- QA-passed AI editorial visual with transparency/provenance;
- explicit `Kaynağa Git` action;
- return to the same Gazete Modu edition/page context.

Missing excerpt remains missing; no AI summary/dek/reading body is generated.
Okuma Modu is ad-free. Full publisher text is not scraped or republished.

The historical `gazet-e.edition.v1` contract requires fields that no longer
match this active text/page/ad direction. A versioned successor must be created
rather than silently overloading v1. It must preserve source/visual identity,
fail-closed parsing, explicit actions and immutable ready publication while
adding physical page and ad semantics described below. Existing v1 schema,
fixture and tests remain historical compatibility evidence until an explicit
migration authority permits their controlled successor work.

## 3. Physical full-page newspaper contract

Gazete Modu uses a versioned initial physical profile:

```text
width_mm=350, height_mm=500, fixed logical render scale
```

This is a broadsheet-style reference profile, not a printer/store vendor
standard. Physical dimensions, margins, gutters, columns, typography, image
slots and ad slots are part of layout identity. The phone fits, pinch-zooms,
pans and navigates this fixed page; editorial blocks never mobile-reflow.
Accepted Q03 gesture/session behavior remains protected.

Q09's merged `1000×1414 logical` engine and acceptance evidence remain
historical. The new physical/ad layout work belongs to the current Q10 revision
without changing Q09 history or silently mutating its accepted contract.

## 4. In-page ad contract

Q10 may use only bounded local/synthetic inventory. Layout reserves optional ad
geometry before article packing and enforces:

- Gazete Modu only; Okuma Modu never renders ads;
- at most one ad slot per page and at most `%15` of physical page area;
- explicit visible and semantic `REKLAM` label;
- no overlap with masthead/hero/editorial text/image/source/action/hit regions;
- no overlay, interstitial, popup, modal, sticky, fullscreen, autoplay or
  forced-wait format;
- no gesture interception outside an explicit isolated ad tap region;
- no suitable slot means no ad;
- ad slot/creative identity participates in layout and edition identity;
- creative may change for a deliberately new edition, but reopening the same
  immutable edition preserves the same creative.

No ad network, SDK, external creative transport, targeting, tracking,
telemetry, advertiser account, auction or billing belongs to Q10. Those remain
Q14 implementation concerns after Q13 commercial/privacy/legal gates.

## 5. Asset, API and mobile boundaries retained

The development object store remains edition-scoped, immutable and
content-addressed. Only Q08 QA-passed WebP bytes with matching SHA-256,
dimensions and media type may be committed or served. Image bytes and private
locators remain outside canonical JSON. Runtime transport remains same-origin,
bounded and production-HTTPS/debug-loopback-only.

The mobile one-tap flow retains one idempotency identity across ambiguous
transport retry, truthful status/cancellation/recovery, explicit new-edition
intent and the current edition until a replacement is fully ready. Gazete and
Okuma modes continue sharing one protected session. Ads are rendered only as
page geometry and cannot introduce a third reader mode or client-side editorial
reflow.

## 6. Historical evidence and supersession

Before O-011/O-012/O-013, T0 used Windows Python 3.12.10, Flutter 3.44.6 /
Dart 3.12.2 and an isolated PostgreSQL 18.6 loopback cluster. The old Gate A
reported `10 passed` focused Q10 tests, `251 passed, 1 skipped` full Python,
`flutter analyze` clean and `46 passed` Flutter tests with fake providers and no
live cost. These numbers apply only to the superseded head and are not evidence
for the revised implementation.

The independent review at that head recorded Gate B `FAIL` findings G1–G10.
G1 database-target safety remains a prerequisite before any destructive test.
G4/G5/G6/G7/G8/G10 remain applicable where they cross the revised architecture;
G2/G3 must be re-derived for image-only policy, physical/ad identity and image
spending. Summary-specific correction work is intentionally stopped.

No live RSS/OpenAI request, image generation, APK/build/install, device,
deployment, Ready or merge is authorized by this document.

## 7. Proposed revised production write-set

Paths already inside Issue #24's current implementation allowlist:

- `services/edition_integration_*.py`, `services/edition_asset_*.py`;
- `services/edition_job_api.py`, `services/edition_job_store.py`,
  `services/edition_job_worker.py`;
- `tests/test_edition_integration_*.py`, `tests/test_edition_asset_*.py`;
- `mobile/lib/edition_job_*.dart`, `mobile/lib/edition_api_*.dart`,
  `mobile/lib/edition_asset_*.dart`, `mobile/lib/edition_generation_*.dart`;
- `mobile/lib/main.dart`, `mobile/lib/reader_app.dart`,
  `mobile/lib/newspaper_view.dart`, `mobile/lib/reading_view.dart`;
- matching `mobile/test/edition_integration_*_test.dart`, job and asset tests;
- Android debug-loopback manifests/config, safe environment/docs truth files.

The owner reset makes the following previously protected paths/purposes
genuinely necessary, but they require explicit next-step allowlist authority
before any production/test edit:

- `services/edition_job_models.py` and `tests/test_edition_job_service.py` —
  remove `summarizing` from the active lifecycle while preserving durable
  compatibility and fail-closed transition tests;
- a new versioned Q04 schema under `schemas/`, plus
  `services/edition_job_validation.py` and `mobile/lib/edition.dart` contract
  updates — source-excerpt/no-AI-text, physical dimensions and ad identity /
  geometry without rewriting `gazet-e.edition.v1` history;
- Q04 backend/mobile contract tests for the new version;
- `mobile/lib/newspaper_view.dart` purpose expansion for bounded in-page ad
  rendering/hit semantics while preserving protected gestures/session.

No Q06/Q07/Q08/Q09 core, legacy, provider/model, dependency, ad SDK, Q11 or
external monetization path is proposed. Implementation must not resume until
ChatGPT reviews this authority sync and grants the exact protected-path
expansion or selects a narrower compatible contract path.

## 8. Historical Gate A record — superseded product direction

The following record applies only to exact head
`39de1ae44784b77fca821fe9b161d5a188c35096`. It is preserved as historical
implementation and validation evidence, not as the active product contract and
not as proof for a future corrected revision.

### 8.1 Durable worker assembly at that head

The Q05 state machine then used was:

```text
requested -> collecting -> selecting -> summarizing -> illustrating
          -> laying_out -> ready | failed | cancelled
```

Q10 supplied executors around the then-current Q06–Q09 public APIs. Each
executor read the immutable persisted request or preceding PostgreSQL manifest,
performed its named stage and returned a versioned safe manifest. Q05 stored
that manifest in the same transaction that advanced the checkpoint; the final
assembly manifest was stored in the same transaction as canonical edition
publication.

The additive PostgreSQL records froze:

- integration policy/version fingerprint per job;
- immutable stage input/output manifests;
- verified Q07/Q08 artifacts by their existing exact cache keys;
- paid-operation reservation, attempt fence, bounded usage and terminal state;
- stable assembly fingerprint, edition identity and first assembly timestamp.

Paid execution was disabled by default even if a provider credential existed.
The composition root required an explicit `authorized` switch and froze a
development ceiling of at most four selected clusters, two pages, 24 logical
calls, 48 transport attempts, four generated images and USD 0.48 estimated
cost. Reservation used worst-case exposure before dispatch. Provider methods
were fenced by current job lease, attempt and cancellation. An operation left
with unknown remote outcome became `uncertain` on recovery and was not replayed
automatically. No external exactly-once billing claim was made.

Only normalized RSS candidates, selected identities, safe artifact metadata
and bounded reason codes were durable. Raw feeds, full publisher bodies/images,
prompts, raw provider responses, credentials and binary image bytes were absent
from JSONB/public payloads.

### 8.2 Partial-failure and Q04 publication behavior at that head

Assembly accepted only Q07 `ready/passed` summaries paired with
identity-matching Q08 `ready/passed` visuals. Unavailable or uncertain stories
were omitted and reported separately; no feed-text fallback, invented visual,
unrelated placeholder or unlimited backfill was used. Q09 received surviving
bounded projections and retained structured overflow reasons. Only placed
articles entered the Q04 document.

Article/source identities and attribution came from Q06/Q07 evidence;
editorial copy came from verified Q07 output; visual provenance, cache and
version fields came from Q08. At least one complete article/page and every
referenced verified asset were required. The unchanged
`CanonicalEditionValidator` and Q05 immutable publication transaction were the
final ready boundary. A separate integration report exposed only counts,
identities and bounded skip/overflow reasons.

### 8.3 Development object store and asset API at that head

`DevelopmentAssetStore` required a configured absolute root outside the
repository. It accepted only locally decoded `image/webp` bytes whose
dimensions and SHA-256 matched Q08 metadata. Writes used an atomic immutable
put-if-absent operation; later reads re-checked size, format, dimensions and
hash. Path traversal, symlink escape, directory listing and arbitrary proxying
were absent.

The API served bytes only through
`/v1/editions/{edition_id}/assets/{sha256_hex}` after confirming the asset
belonged to that ready edition. Unknown, wrong-edition, missing or tampered
assets returned a bounded not-found response. Canonical Q04 JSON kept only
`asset_id`; private locators and bytes never entered the document.

The composition root defined `127.0.0.1` as the development bind default.
Release transport remained HTTPS. Android INTERNET permission was present,
while the debug network policy permitted cleartext only for loopback hosts; the
Dart client independently rejected other cleartext origins.

### 8.4 Mobile one-tap behavior at that head

The production entry created a Q05 request from one `Gazetemi Hazırla` action.
The controller kept one random idempotency key across ambiguous retries,
prevented concurrent submissions, tracked real named lifecycle states with a
bounded poll loop, sent cancellation intent and ignored stale async results.
Job/idempotency identity participated in Flutter restoration so process
recovery resumed status tracking and never automatically submitted another paid
request.

Ready JSON was fail-closed parsed by the existing Q04 model. Each
edition-scoped asset response was counted from consumed bytes, capped at 8 MiB,
checked for WebP media type, SHA-256 and decoded dimensions, then injected as
runtime-only bytes. Runtime bytes did not serialize. The same `EditionSession`,
newspaper canvas, gestures, source launcher and reading view remained in use.
The bundled fixture remained an explicit repository/test entry and was never
substituted for a failed live request. Live copy did not claim `OFFLINE
FIXTURE`; a reduced edition displayed a short truthful notice.

The only new mobile dependency at that head was `crypto` 3.0.7; HTTP and image
decoding used the Flutter/Dart SDK.

### 8.5 Exact historical Gate A evidence

The T0 amendment was validated first with Windows Python 3.12.10 and exact
Flutter 3.44.6 / Dart 3.12.2. Gate A then used a task-isolated PostgreSQL 18.6
cluster on a non-default loopback port and a disposable object root; the shared
PostgreSQL service was not restarted or modified.

- full Python suite: `251 passed, 1 skipped` (one existing FastAPI/httpx
  warning);
- focused Q10 integration/recovery/security suite: `10 passed`;
- existing Q05 PostgreSQL lifecycle suite: `23 passed`;
- existing focused Q06–Q09 suites: `131 passed`;
- `flutter analyze`: no issues;
- full Flutter suite: `46 passed`;
- exact fake path: fake RSS transport -> real Q06 collector/ranker -> fake
  Q07/Q08 providers -> real durable worker/cache/object store -> Q09 ->
  unchanged Q04 validator/publication -> restarted API -> edition-scoped asset
  response;
- recovery evidence: worker/store replacement between stages, mid-two-story
  process loss, exact completed-cache reuse and no replay of the uncertain paid
  operation; cancellation/lease fences prevented later dispatch;
- integrity evidence: wrong edition, traversal, tamper, hash/dimension and
  non-ready visual paths failed closed; no empty/broken-asset ready edition;
- live publisher/provider calls and estimated paid cost: `0`.

That Gate A test PASS was not independent review, live-provider proof or mobile
device acceptance. The subsequent independent review recorded Gate B `FAIL`
findings G1–G10. Owner reset O-011/O-012/O-013 supersedes the product direction
of this head without erasing the record.
