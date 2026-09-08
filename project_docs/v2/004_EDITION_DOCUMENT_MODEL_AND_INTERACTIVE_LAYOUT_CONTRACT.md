# GV2-005 — Q04 Edition Document Model and Interactive Layout Contract

**Authority:** GitHub Issue #12

**Exact base:** `8a387fe1f5801afc2345832d5dc0c8a71a1a92c2` (`main`)

**Branch:** `gv2/005-edition-contract`

**Lane:** STANDARD

**Canonical contract:** `gazet-e.edition.v1`

## Active-contract amendment — O-011/O-012/O-013

Q04 `gazet-e.edition.v1` ve aşağıdaki acceptance kanıtı tarihsel olarak
korunur. Fatih'in 8 Eylül 2026 owner kararı bu v1 contract'ın aktif Q10 için
final biçim olmadığını kesinleştirmiştir. Bu truth-sync schema veya production
modeli değiştirmez; controlled successor/version migration Q10 içinde ayrıca
uygulanacaktır.

Aktif successor contract en az şunları sağlamalıdır:

- AI-generated `dek`, `summary` veya `reading_body` zorunluluğu yoktur;
  Okuma Modu source headline, varsa bounded source/feed excerpt,
  publication/source, AI editorial visual ve source action taşır;
- page, versioned `350 mm × 500 mm` initial physical profile ile logical render
  scale'i birlikte taşır; mobile editorial reflow yapmaz;
- Gazete Modu için optional reserved ad placement/creative identity ve açık
  `REKLAM` semantics taşır; en fazla bir ad/page ve en fazla `%15` page area
  fail-closed doğrulanır;
- ad geometry editorial/source/hit geometry ile çakışmaz ve Okuma Modu'na ad
  taşımaz;
- same immutable edition aynı ad creative'i korur; geometry/creative değişimi
  layout/edition cache identity'yi değiştirir.

Existing v1 fixture, schema, parser ve tests bu adımda silinmez veya geçmişte
bu alanları taşımamış gibi yeniden yazılmaz.

## 1. Sonuç

Q04, immutable-ready Gazet+E edition belgesini backend ile mobil reader
arasındaki teknoloji-bağımsız veri sınırı olarak production-shape hale getirir.
Kanonik JSON Schema:

`schemas/gazet-e.edition.v1.schema.json`

Flutter tarafındaki eşdeğer model, fail-closed parser ve JSON-ready serializer
`mobile/lib/edition.dart` içindedir. Q03 fixture'ı aynı sözleşmeye migrate
edilmiştir; accepted Gazete Modu, Okuma Modu, gesture ve navigation davranışı
değişmemiştir.

Bu contract ready edition içindir. Job state/progress, generation request,
backend API, database, object storage ve provider execution Q04 belgesinin
parçası değildir.

## 2. Kanonik belge sınırı

Root belge tam olarak şu bölümleri taşır:

| Bölüm | Kanonik gerçek |
|---|---|
| `contract_version` | Yalnız `gazet-e.edition.v1` |
| `edition` | Immutable kimlik, `ready` state, request/generation zamanları, locale/timezone, marka ve version seti |
| `pages` | Sıralı page kimlikleri, logical canvas, template ve explicit placements/hit regions |
| `articles` | Article/cluster/content identity, Gazet+E metni, source truth, visual provenance ve cache identity |
| `cache` | Edition ve layout cache key'leri |

Schema bütün object'lerde `additionalProperties: false` kullanır. Bu tercih,
client'ın bilmediği bir alanı sessizce kabul edip farklı anlam üretmesini
engeller. Cross-object ve coordinate invariant'ları JSON Schema'nın yanında
Dart parser tarafından doğrulanır.

### 2.1 Edition metadata

- `edition.id` immutable ready-edition kimliğidir.
- `state` yalnız `ready` olabilir.
- `requested_at` ve `generated_at` explicit timezone taşıyan ISO-8601
  timestamp'lerdir; generation request'ten önce olamaz.
- `locale`, `timezone`, `title`, `Gazet+E` brand ve `GAZET+E` masthead
  zorunludur.
- `editorial_policy`, `summary_prompt`, `visual_brief`, `visual_style` ve
  `layout_engine` version'ları explicit'tir; client server gerçeğini yeniden
  hesaplamaz.

### 2.2 Page ve layout

- Page ID ve order benzersizdir; array strictly increasing order'dadır.
- Canvas width/height pozitif ve finite, unit yalnız `logical` olabilir.
- Template ID/version her page'de zorunludur.
- Placement ID, mevcut article referansı, bilinen role, in-canvas rectangle,
  non-negative `z_index` ve hit-region listesi taşır.
- Placement rolleri yalnız `hero`, `secondary`, `brief` olabilir.
- Hit action yalnız `open_reading` veya `open_source` olabilir.
- Her görünür placement bir `open_reading` ve source truth görünür olduğu için
  ayrı bir `open_source` affordance taşır.
- Flutter contract geometry'sini responsive feed/card modeline dönüştürmez.

### 2.3 Article ve source truth

- `id`, `cluster_id` ve SHA-256 `content_version` ayrı kimliklerdir.
- Headline, dek, Gazet+E summary ve structured paragraph `reading_body`
  zorunludur.
- En az bir source vardır. Source; ID, publisher ID, name, HTTPS canonical URL
  ve varsa publication timestamp taşır.
- `primary_source_id` aynı article içindeki bir source'a çözülür.
- Full publisher body, raw scrape body veya private source content contract'a
  girmez.

### 2.4 Visual provenance ve asset identity

Visual şu kanonik alanları taşır:

- `asset_id`, SHA-256 content hash, pixel width/height;
- kullanıcıya açık alt text ve transparency label;
- `generated_by_ai`, public-safe provider identifier, model version,
  generation time, brief/style version, safety class ve cache key.

`asset_id` content'in kanonik referansıdır; repository-local path veya remote
fetch locator değildir. Provider key/secret, raw prompt, signed URL, private
storage path ve local path edition JSON'a yazılmaz.

Q03 offline proof için `mobile/lib/fixture_asset_resolver.dart`, üç bilinen
`asset_id` değerini bundled PNG path'lerine client-local olarak çözer. Bu map
serialize edilmez ve canonical fixture içinde yer almaz. Bilinmeyen fixture
asset ID fail-closed olur. Production asset transport/resolution Q04'te
uydurulmaz; ilgili service boundary sonraki yetkili işte tanımlanır.

### 2.5 Cache identity

- Her article `summary_key` ve `visual_brief_key` taşır.
- Visual provenance kendi generation/cache key'ini taşır.
- Root `edition_key` ve `layout_key` taşır.
- Bütün key'ler lowercase `sha256:<64 hex>` formatındadır.
- Mobile bu key'leri üretmez veya provider truth'u yeniden türetmez.

## 3. Fail-closed invariant matrisi

| # | İhlal | Sonuç |
|---:|---|---|
| 1 | Unsupported contract version | Reject |
| 2 | Eksik edition veya version alanı | Reject |
| 3 | `ready` dışında canonical state | Reject |
| 4 | Duplicate page ID/order veya unordered array | Reject |
| 5 | Invalid, non-positive veya non-finite canvas | Reject |
| 6 | Missing article placement reference | Reject |
| 7 | Invalid/non-finite/out-of-canvas placement veya hit rectangle | Reject |
| 8 | Page scope'ta duplicate placement/hit ID | Reject |
| 9 | Unknown placement role, hit action veya reading-body type | Reject |
| 10 | Visible placement'ta `open_reading` yok | Reject |
| 11 | Paper source affordance için `open_source` yok | Reject |
| 12 | Source yok, primary reference bozuk veya canonical URL HTTPS değil | Reject |
| 13 | Article/cluster/content identity eksik veya collapsed | Reject |
| 14 | Visual dimension/hash/alt/transparency/provenance eksik | Reject |
| 15 | Cache key veya edition version eksik/geçersiz | Reject |
| 16 | Secret/raw prompt/private path/raw publisher field | Reject |

Parser ayrıca duplicate article/source kimliklerini ve schema'da tanımlanmayan
alanları reddeder. URL user-info kabul edilmez. Timestamp'ler explicit timezone
taşır.

## 4. Serialization sözleşmesi

`EditionDocument.toJson()` yalnız JSON-ready map/list/string/number/bool/null
değerleri üretir. Runtime-only bundled asset çözümü serialize edilmez.

Regression şu zinciri doğrular:

`parse -> toJson -> jsonEncode -> parse -> toJson`

İkinci JSON-ready çıktı ilk canonical model çıktısıyla deep-equal olmalıdır.
Page array/order, article/source references, structured reading body, versions,
visual provenance ve cache key'leri round-trip boyunca korunur. Timestamp'ler
aynı anı koruyacak biçimde UTC ISO-8601'e normalize edilebilir.

Model alanları final, collection'lar unmodifiable'dır. Ready document üzerinde
client mutation API'si yoktur.

## 5. Q03 reader compatibility

Q04 migration'ı yalnız data boundary'yi değiştirir:

- mevcut üç page ve bütün logical rectangle değerleri korunur;
- headline/dek/summary/reading text/source ve visual content korunur;
- local images aynı PNG asset'lerine resolver üzerinden bağlanır;
- `newspaper_view.dart`, `reading_view.dart`, `edition_session.dart` ve
  `source_launcher.dart` değişmez;
- existing gesture, reader-flow ve golden regressions aynı davranışı kanıtlar;
- network client, remote asset fetch veya dependency eklenmez.

Bu nedenle Q03'ün Fatih tarafından verilmiş cihaz acceptance'ı yeniden açılmaz.

## 6. Test ve validation kanıtı

Focused Q04 testleri şunları kapsar:

- production-shape fixture parse;
- JSON-ready round-trip;
- edition/page/article/source/visual/cache/version preservation;
- 16 fail-closed invariant;
- identity/reference uniqueness;
- deterministic page order;
- primary source ve action ayrımı;
- visual provenance/transparency;
- canonical JSON dışında fixture asset resolution;
- forbidden ve unknown field rejection.

Milestone validation: `flutter analyze`, full `flutter test`, JSON parse,
`git diff --check`, exact allowlist ve protected-drift kontrolüdür. Native,
platform config veya user-visible UI değişmediği için Android/iOS build ve yeni
device rituali gerekmez.

## 7. Explicit exclusions

Q04 şunları başlatmaz:

- FastAPI/PostgreSQL/job lifecycle veya Q05 implementation;
- live RSS/publisher/asset network erişimi;
- AI provider çağrısı, prompt veya secret yönetimi;
- auth, account, analytics, payment, personalization veya archive/sync;
- legacy Python/issue schema/generated docs değişikliği;
- permanent application ID veya release/signing kararı.
