# GV2-010 — Q09 Newspaper Layout Engine V2

**Authority:** GitHub Issue #22

**Lane:** STANDARD — deterministic server-side layout planning

**Exact base:** `30e22738040268ea8a8db7f16c83dee4b60dcfa2`

**Deterministic acceptance:** `PASS` — corrected focused Q09 suite `33 passed`,
including the unchanged Q04 `CanonicalEditionValidator` projection path. The
pre-correction relevant non-PostgreSQL baseline was `210 passed, 1 skipped`.
Independent corrected-head review passed for `129c070ef3e93aa6bcd65c495e04215d3c56ec2a`;
PR #23 was merged as `8f55b0aee5f5e623318cdb0d9024af1ca31d5546`.
Q09 is therefore `COMPLETE`; Q10 owns the now-active assembly/asset integration.

**Active layout amendment:** Q09's `1000×1414 logical` engine, tests and merge
evidence remain historical `COMPLETE`. O-012/O-013 now require the current Q10
revision to establish a versioned `350 mm × 500 mm` physical full-page profile,
fixed logical render scale and optional reserved in-page advertising geometry.
Q09 history is not rewritten and its production core is not changed by this
authority sync.

The Q10 revision must reserve ad geometry before article packing, allow at most
one ad/page and `%15` page area, require `REKLAM`, forbid overlap with
editorial/source/hit regions, and preserve page gestures outside the bounded ad
tap region. No suitable slot means no ad. Ad slot/creative identity participates
in layout/edition identity; same immutable edition reopening retains the same
creative. Only local/synthetic inventory belongs to Q10; real ad serving stays
Q14.

## 1. Boundary

Q09 is a pure Python planning stage:

```text
bounded layout-ready story projections
  -> canonical rank/tie-break order
  -> bounded static template packing
  -> fixed logical-canvas pages, placements and hit regions
  -> structured overflow + deterministic layout key
```

It does not join Q06/Q07/Q08 production modules, create a final ready edition,
resolve public assets, fetch publisher data, call an AI provider, render HTML or
PDF, run a browser, or change mobile behavior. Q10 owns pipeline assembly and
publication wiring.

## 2. Versions and public-safe input

Versions are fixed:

- layout engine: `gazet-e.layout-engine.v2`;
- layout policy: `gazet-e.layout-policy.v1`;
- template registry: `gazet-e.layout-templates.v2` (`front` and `inside`
  definitions version `3`).

`LayoutStory` is an immutable, extra-forbid projection containing only:

- article, cluster and content-version identity;
- explicit non-negative rank, deterministic tie-break key and section;
- bounded headline, dek and source display name;
- QA-passed visual availability plus dimensions and SHA identity when present.

No URL, publisher body/image, provider metadata, prompt, credential, local/private
path, browser state or user profile is accepted. Stories are canonicalized by
`(rank, tie_break_key, article_id)`; caller iteration order is irrelevant.
Duplicate article IDs fail closed.

`LayoutPolicy` carries only a bounded `max_pages` value from 1 through 20. Q09
does not define free/premium edition length or personalization policy.

## 3. Q03/Q04 canvas and template compatibility

Every page uses the accepted Q03/Q04 canvas:

```text
width=1000, height=1414, unit=logical
```

The bounded registry has two static versioned templates using the accepted
`front` and `inside` vocabulary. Both reserve the Q03 masthead/top margin and
40-unit paper margins. `front` contains one visual-required hero, one
visual-required secondary and two brief slots. `inside` contains one
visual-required hero, one visual-required secondary and one brief slot. Geometry
is finite, positive, non-overlapping and inside the canvas. The registry and
each template contain no more than eight entries/slots.

Hero and secondary match the accepted renderer's image-bearing roles and are
eligible only when the caller reports a QA-passed visual. Brief is the sole
text-only role. A missing visual is routed to an eligible brief or truthful
structured overflow; it never triggers a fetch or generation and never invents
an asset. Q10 still owns final edition/visual fallback assembly.

Each slot defines conservative headline/dek character capacity. Content that
does not fit any eligible slot is not clipped into a neighboring rectangle; it
returns as structured `content_exceeds_capacity` overflow.

## 4. Deterministic hierarchy and packing

Page one uses `front`; later pages use `inside`. Within each template, slots are
visited in fixed editorial-priority order. The first canonically ranked eligible
story receives each slot. This gives higher-ranked eligible stories hero,
secondary and brief priority before lower-ranked eligible stories, with at most
one hero per page.

Page IDs (`page-001`, …), contiguous one-based order, placement IDs, z-index and
hit IDs are derived solely from page/slot order. Page section is the first placed
story's caller-supplied section. Stories are never duplicated.

Each placement contains exactly two distinct, non-overlapping regions inside
the placement rectangle:

- `open_reading` for the article surface;
- `open_source` for a fixed-height visible source affordance.

Both carry deterministic accessibility labels. Page, template, placement,
rectangle, role, z-index and hit-region field names map directly to the existing
Q04 `gazet-e.edition.v1` schema; no schema or mobile transformation is needed.

## 5. Overflow and identity

When `max_pages` is genuinely exhausted, every remaining continuation-eligible
story is returned once as `page_limit_exhausted`. A story that fits a front slot
but no inside continuation slot is returned as
`continuation_capacity_exhausted`; increasing `max_pages` cannot falsely appear
to resolve that condition. A story too large for every eligible registry slot
is returned once as `content_exceeds_capacity`. `LayoutOverflow` reports
terminal status, ordered items, total input count, placed count and page limit;
counts must preserve unique input identities.

`layout_key` is SHA-256 over canonical JSON containing:

- ordered complete layout-story projections;
- layout-engine and layout-policy versions;
- policy values;
- template-registry version;
- template IDs/versions, canvas, slot geometry, roles, capacity and visual rules.

It therefore changes for content/version, rank/tie-break, headline/dek/source,
section, visual availability/identity/dimensions, policy, engine or template
changes, while remaining stable for irrelevant caller iteration order. Secrets,
prompts and private locators cannot enter the key.

## 6. Immutable output contract

`LayoutPlan` is immutable and JSON-ready. It contains the engine, policy and
template-registry versions; deterministic `layout_key`; ordered pages; and
structured overflow. Cross-model validation enforces:

- contiguous unique page IDs/orders;
- unique placement and hit IDs;
- at most one hero per page;
- positive in-canvas placement and hit rectangles;
- no placement collision;
- exactly one reading and one source action per placement;
- no duplicated or simultaneously placed/overflowed article;
- unique overflow article identities;
- emitted page count no greater than the declared page limit;
- exact input/placed/overflow counts.

Q09 does not create article/source/visual objects or root edition metadata. A
focused projection test combines its page output with synthetic Q04 article
objects and passes the existing `CanonicalEditionValidator` unchanged.

## 7. Deterministic acceptance

The focused suite covers all Issue #22 requirements:

1. repeatable JSON-equivalent plans and keys;
2. shuffled-input canonicalization;
3. rank/tie/article ordering;
4. stable front hierarchy;
5. one-hero maximum;
6. long-copy capacity and collision safety;
7. positive in-canvas geometry;
8. reading/source hit regions;
9. deterministic unique placement/hit IDs;
10. deterministic unique page IDs/orders;
11. bounded versioned registry;
12. visual availability without external calls;
13. distinct continuation-capacity and genuine page-limit overflow without
    loss/duplication, including the two-story 150/360-character counterexample;
14. content/policy/template cache-key invalidation;
15. iteration-order-stable keys;
16. unchanged Q04 schema validation;
17. protected-path isolation;
18. absence of network/provider/browser/PDF/Playwright paths.

The corrected matrix additionally covers all-no-visual and mixed visual
availability across multiple pages, shuffled continuation input, validated
duplicate-overflow/page-limit rejection, and a positive JSON round trip with
identity/count conservation.

Synthetic/local fixtures are used exclusively. No mobile/device gate is opened
because Q09 preserves the accepted fixed-canvas rendering language. Integrated
visual/device acceptance returns in Q10.

## 8. Explicit exclusions

No Q05 job wiring, Q06 ingestion, Q07 summary, Q08 image pipeline, mobile,
schema, legacy runtime, dependency/configuration, object storage/public URL,
personalization, payment, analytics, Q10 integration or deployment change is
part of Q09.
