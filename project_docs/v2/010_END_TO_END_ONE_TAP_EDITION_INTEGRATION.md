# GV2-011 — Q10 End-to-end One-tap Edition Integration

**Authority:** GitHub Issue #24

**Lane:** CRITICAL — durable integration, paid-dispatch fencing and asset delivery

**Exact base:** `8f55b0aee5f5e623318cdb0d9024af1ca31d5546`

**Current gate truth:** Gate A deterministic/local validation `PASS`; Gate B
independent review, Gate C separately authorized live run and Gate D exact
Android artifact/owner acceptance are `PENDING`. Q10 remains `ACTIVE`; Q11
remains `QUEUED`. No live RSS/OpenAI call, paid generation, device action,
deployment, Ready or merge was performed by Gate A.

## 1. Durable worker assembly

The existing Q05 state machine remains authoritative:

```text
requested -> collecting -> selecting -> summarizing -> illustrating
          -> laying_out -> ready | failed | cancelled
```

Q10 supplies small executors around the unchanged Q06–Q09 public APIs. Each
executor reads the immutable persisted request or the preceding PostgreSQL
manifest, does only its named stage, and returns a versioned safe manifest.
Q05 stores that manifest in the same transaction that advances the checkpoint;
the final assembly manifest is stored in the same transaction as canonical
edition publication.

Additive PostgreSQL records freeze:

- integration policy/version fingerprint per job;
- immutable stage input/output manifests;
- verified Q07/Q08 artifacts by their existing exact cache keys;
- paid-operation reservation, attempt fence, bounded usage and terminal state;
- stable assembly fingerprint, edition identity and first assembly timestamp.

Paid execution is disabled by default even if a provider credential exists. A
worker composition root requires the exact explicit `authorized` switch and the
frozen development ceiling: at most four selected clusters, two pages, 24
logical calls, 48 transport attempts, four generated images and USD 0.48
estimated cost. Reservation uses worst-case exposure before dispatch. Every
provider method is fenced again by current job lease, attempt and cancellation.
An operation left with unknown remote outcome becomes `uncertain` on recovery
and is not replayed automatically. No external exactly-once billing claim is
made.

Only normalized RSS candidates, selected identities, safe artifact metadata and
bounded reason codes are durable. Raw feeds, full publisher bodies/images,
prompts, raw provider responses, credentials and binary image bytes are absent
from JSONB/public payloads.

## 2. Partial failure and canonical Q04 publication

Assembly accepts only Q07 `ready/passed` summaries paired with identity-matching
Q08 `ready/passed` visuals. Unavailable or uncertain stories are omitted and
reported separately; no feed-text fallback, invented visual, unrelated
placeholder or unlimited backfill is used. Q09 receives the surviving bounded
projections unchanged and all layout overflow items retain their Q09 reason.
Only placed articles enter the Q04 document.

Article/source identities and attribution come from Q06/Q07 evidence; editorial
copy comes from verified Q07 output; visual provenance, cache and version fields
come from Q08. At least one complete article/page and every referenced verified
asset are required. The unchanged `CanonicalEditionValidator` and Q05 immutable
publication transaction remain the final ready boundary. The separate
integration report exposes only counts, identities and bounded skip/overflow
reasons, allowing the client to label a reduced edition truthfully.

## 3. Development object store and asset API

`DevelopmentAssetStore` requires a configured absolute root outside the
repository. It accepts only locally decoded `image/webp` bytes whose dimensions
and SHA-256 equal Q08 metadata. Writes use an atomic immutable put-if-absent
operation; later reads re-check size, format, dimensions and hash. Path
traversal, symlink escape, directory listing and arbitrary proxying are absent.

The API serves bytes only through
`/v1/editions/{edition_id}/assets/{sha256_hex}` after confirming that the asset
belongs to that ready edition. Unknown, wrong-edition, missing or tampered assets
return a bounded not-found response. Canonical Q04 JSON keeps only `asset_id`;
private locators and bytes never enter the document.

The composition root defines `127.0.0.1` as the development bind default.
Release transport remains HTTPS. Android INTERNET permission is present, while
the debug network policy permits cleartext only for loopback hosts; the Dart
client independently rejects other cleartext origins.

## 4. Mobile one-tap flow

The production entry creates a Q05 request from one `Gazetemi Hazırla` action.
The controller keeps one random idempotency key across ambiguous retries,
prevents concurrent submissions, tracks real named lifecycle states with a
bounded poll loop, sends cancellation intent and ignores stale async results.
Job/idempotency identity participates in Flutter restoration so process recovery
resumes status tracking and never automatically submits another paid request.

Ready JSON is fail-closed parsed by the existing Q04 model. Each edition-scoped
asset response is counted from consumed bytes, capped at 8 MiB, checked for
WebP media type, SHA-256 and decoded dimensions, then injected as runtime-only
bytes. Runtime bytes do not serialize. The same `EditionSession`, newspaper
canvas, gestures, source launcher and reading view remain in use. The bundled
fixture remains an explicit repository/test entry and is never substituted for
a failed live request. Live copy does not claim `OFFLINE FIXTURE`; a reduced
edition displays a short truthful notice.

The only new mobile dependency is `crypto` 3.0.7; HTTP and image decoding use
the Flutter/Dart SDK.

## 5. Gate A evidence

The T0 amendment was validated first with Windows Python 3.12.10 and exact
Flutter 3.44.6 / Dart 3.12.2. Gate A then used a task-isolated PostgreSQL 18.6
cluster on a non-default loopback port and a disposable object root; the shared
PostgreSQL service was not restarted or modified.

- full Python suite: `251 passed, 1 skipped` (one existing FastAPI/httpx warning);
- focused Q10 integration/recovery/security suite: `10 passed`;
- existing Q05 PostgreSQL lifecycle suite: `23 passed`;
- existing focused Q06–Q09 suites: `131 passed`;
- `flutter analyze`: no issues;
- full Flutter suite: `46 passed`;
- exact fake path: fake RSS transport -> real Q06 collector/ranker -> fake
  Q07/Q08 providers -> real durable worker/cache/object store -> Q09 -> unchanged
  Q04 validator/publication -> restarted API -> edition-scoped asset response;
- recovery evidence: worker/store replacement between stages, mid-two-story
  process loss, exact completed-cache reuse and no replay of the uncertain paid
  operation; cancellation/lease fences prevent later dispatch;
- integrity evidence: wrong edition, traversal, tamper, hash/dimension and
  non-ready visual paths fail closed; no empty/broken-asset ready edition;
- live publisher/provider calls and estimated paid cost: `0`.

Gate A test PASS is not independent review, live-provider proof or mobile device
acceptance. Those gates remain explicitly pending under Issue #24.
