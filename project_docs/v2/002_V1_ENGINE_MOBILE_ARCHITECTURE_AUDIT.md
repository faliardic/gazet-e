# GV2-002 — v1.1 Engine Audit ve Mobile/Backend Architecture Boundary

**Karar durumu:** Q02 için kanonik teknik karar<br>
**Authority:** GitHub Issue #4<br>
**Audit tabanı:** `d89289626b7057923a12414df257ad3b1d708c34` (`main`)<br>
**Marka:** `Gazet+E`; masthead: `GAZET+E`
**Kapsam:** read-only source audit + documentation-only architecture kararı

## 1. Yönetici kararı

Gazet+E Mobile V2 için seçilen sınır şudur:

- **Mobil istemci:** Flutter. Gazete yüzeyi fixed logical canvas üzerinde `InteractiveViewer` + `CustomPainter`/`Stack` bileşimiyle kurulur. `Gazete Modu` ve `Okuma Modu` aynı edition session state'ini paylaşır.
- **Backend:** Python FastAPI API + PostgreSQL'de kalıcı job/edition metadata + ayrı Python worker. Haber ve edition asset'leri object storage'da tutulur. İlk sürümde Redis/Celery eklenmez.
- **İş bölümü:** RSS toplama, normalizasyon, seçim, Gazet+E özeti, AI görsel üretimi, layout ve cache server tarafında; gesture, sayfa sunumu, okuma görünümü ve source action mobilde çalışır.
- **Contract:** mobil ile backend arasındaki tek source of truth, versioned ve immutable-ready canonical edition document'tır. Mevcut v1.1 üç sayfalı issue JSON'u bu contract değildir; yalnız legacy import/fixture girdisi olabilir.
- **İlk implementation sırası:** Q03, backend ve canlı RSS/AI olmadan bundled fixture + local asset'lerle reader interaction riskini kanıtlar. Bu gate geçmeden Q04/Q05 veya live entegrasyon başlatılmaz.

Bu karar v1.1'i kaldırmaz. Legacy CLI, HTML/PDF ve GitHub Pages hattı bakım uyumluluğu için yerinde kalır; Mobile V2 runtime'ına taşınmaz.

## 2. Audit yöntemi ve source haritası

Audit, production kodunu çalıştırmadan ve değiştirmeden exact base üzerindeki gerçek çağrı zincirini izledi:

```text
CLI / one-click
  -> issue_from_rss
      -> RSS + ANKA collect
      -> quality gate + scoring + fuzzy duplicate suppression
      -> fixed front/inside/technology page assembly
  -> detail + image enrichment
  -> current issue validation / JSON write
  -> Jinja HTML -> Playwright PDF
  -> archive / Desktop / GitHub Pages outputs
```

Başlıca kanıt noktaları:

- [`builder.py`](../../chatgpt_haber/builder.py#L11-L53): synchronous collect/select, fixed üç sayfa ve enrichment çağrısı.
- [`cli.py`](../../chatgpt_haber/cli.py#L117-L220): cleanup'tan archive/desktop çıktısına kadar process-local orchestration.
- [`sources.py`](../../chatgpt_haber/sources.py#L20-L38): feed listesi ve ANKA HTML kaynağı.
- [`issue.py`](../../chatgpt_haber/issue.py#L18-L21): sabit page count, template ve paper-size varsayımları.
- [`render.py`](../../chatgpt_haber/render.py#L85-L154): Jinja/file-system HTML üretimi ve detail page bağları.
- [`pages_publish.py`](../../chatgpt_haber/pages_publish.py#L32-L113): build sonrası generated `docs/` publication hattı.

## 3. v1.1 source audit bulguları

### 3.1 RSS/source ingestion ve normalization

`sources.py` dört RSS ailesi ile ANKA ana sayfasını topluyor. RSS media/enclosure alanlarından görsel adayı çıkarıyor; ANKA için HTML link parsing yapıyor. Feed item'ları ortak article sözlüğüne çevrilse de network policy ortak değil: ANKA `requests` timeout kullanırken `feedparser.parse` çağrıları açık timeout/retry/conditional-fetch contract'ı taşımıyor. Source adapter, clock ve HTTP client dependency olarak enjekte edilmiyor.

Mevcut normalizasyon yararlı alanları ortaya çıkarıyor fakat identity'yi taşıyamıyor: feed içindeki sentetik ID source adı + sıra numarasına dayanıyor; sıra değişince identity değişebilir. Aynı çalıştırmada exact link ve fuzzy benzerlik azaltması var, fakat redirect/canonical URL, tracking parametreleri ve cross-run identity için kalıcı bir model yok.

**Karar:** parser ve field-normalization bilgisi server-side adapter arkasında yeniden kullanılır. Her adapter bounded timeout, retry/backoff, source ID, canonical URL ve gözlemlenebilir fetch sonucu üretir. Raw network erişimi mobil istemciye taşınmaz.

### 3.2 Editorial filtering, quality ve source validation

[`news_quality_filters.py`](../../services/news_quality_filters.py#L157-L240) boş/generic/clickbait benzeri girdiler ve deprem haberleri için doğrulanabilir hard-reject kuralları sağlıyor. `sources.py` source, section, keyword, recency, image ve local user-profile sinyallerini birleştiren scoring uyguluyor; sonra quality gate'i tekrar çalıştırıyor.

Güçlü taraf, kuralların büyük bölümünün saf metin girdileriyle test edilebilir olmasıdır. Sınırlar ise şunlardır:

- politika ve ağırlıklar versioned bir artifact değildir;
- recency ve AppData profil state'i process/environment bağımlıdır;
- source validation çoğunlukla feed konfigurasyonu ve URL varlığı düzeyindedir;
- deprem odaklı özel kurallar genel editorial safety modelinin yerine geçemez;
- `print` tabanlı raporlama distributed job gözlemlenebilirliği sağlamaz.

**Karar:** hard filters ve ranking sinyalleri pure, versioned server policy modülüne adapter ile taşınır. Her seçimin `policy_version`, signal breakdown ve reject reason kaydı tutulur. Publisher metninin yeniden yayınlanabilir olduğu varsayılmaz.

### 3.3 Article identity, duplicate suppression ve event clustering

Mevcut fuzzy duplicate yaklaşımı normalize başlık token overlap'ı ve section'a göre eşik kullanıyor. Bu, aynı run içinde tekrar azaltmaya yarar; identity değildir. [`random_news_service.py`](../../services/random_news_service.py#L292-L294) URL/source/title/published hash'i üretse de bu yalnız random-news alt sistemi içindir ve canonical pipeline tarafından kullanılmaz.

V2 üç ayrı kavramı ayırır:

1. **Article identity:** belirli publisher item'ının stabil kimliği.
2. **Content version:** aynı item'ın kaynak içeriğindeki anlamlı revizyon.
3. **Story cluster:** farklı publisher item'larının aynı olaya ilişkin olduğu versioned ilişki.

Canonical URL, host/source kimliği, redirect ve tracking normalizasyonundan sonra article ID'nin temelidir. Fuzzy başlık benzerliği yalnız cluster candidate signal olabilir; iki article'ı sessizce aynı identity yapamaz.

### 3.4 Current issue JSON/data model

[`issue.py`](../../chatgpt_haber/issue.py#L128-L161) modern girdiyi normalize ediyor; [`looks_like_modern_issue`](../../chatgpt_haber/issue.py#L164-L170) tam üç sayfa ve sınırlı template seti bekliyor. Legacy conversion eksik içerikleri clone ederek fixed story count'a dolduruyor. [`validate_issue_data`](../../chatgpt_haber/issue.py#L221-L255) temel headline/body/layout/image kontrolleri yapıyor. [`issue.schema.json`](../../schemas/issue.schema.json) aynı fixed print modelini tarif ediyor.

Model headline, body, source bundle ve `layout_hint` taşıdığı için migration girdisi olarak değerlidir. Ancak aşağıdakiler yoktur:

- contract/policy/model/layout version'ları;
- stabil article, cluster, page ve placement semantiği;
- logical canvas koordinatları ve hit regions;
- source provenance ve birden fazla source ilişkisi;
- AI görsel provenance/transparency/safety metadata'sı;
- content-addressed asset ve cache keys;
- job/edition lifecycle ayrımı.

**Karar:** mevcut schema Mobile V2'de authoritative hale getirilmez. Q03 fixture'ı aşağıdaki canonical contract'ın local örneğini kullanır; legacy JSON gerekiyorsa açık bir import adapter'ı ile çevrilir.

### 3.5 Render/layout ve Playwright/PDF ayrımı

Jinja partial'ları hero/secondary/brief gibi faydalı editorial hierarchy kavramları taşıyor. `render.py` ise issue nesnesine presentation linkleri ekliyor, filesystem yollarını URI/base64'e çeviriyor, detail HTML dosyaları yazıyor ve Playwright Chromium ile print PDF alıyor. CSS A3/A4 baskı ölçülerine ve browser pagination'a bağlı. `layout_issue.py` içindeki eski layout blocks de interactive geometry üretmiyor.

**Karar:** hierarchy, role ve template vocabulary mimari girdidir; Python/Jinja/CSS/Playwright runtime kodu mobile layout engine değildir. V2 layout worker, fixed logical canvas üzerinde explicit placement/hit-region contract üretir. Flutter yalnız bu contract'ı deterministik çizer; client'ta editorial reflow yapmaz.

### 3.6 Image enrichment ve third-party bağımlılıkları

[`sources.py`](../../chatgpt_haber/sources.py#L545-L704) RSS image URL, page OG/Twitter meta scraping, download, Pillow dimension/fallback ve local-file attachment zinciri kullanıyor. Detail enrichment aynı publisher sayfasından JSON-LD/semantic selector/body veya description toplamaya çalışıyor. Cache yalnız aynı process içindeki URL map'idir. Bu zincir publisher görselini V2 visible image olarak sürdürürse ürünün “AI-generated by default” kararıyla ve commercial rights gate'iyle çelişir.

**Karar:** publisher image scraping/downloading V2 visible asset pipeline'ında kullanılmaz. Source sayfasından permissible facts/excerpt toplama ayrı Q13 terms/legal gate'ine bağlıdır. Production visual worker, versioned brief + safety class + provider/model/style metadata ile AI asset üretir. Q03 yalnız repository içindeki açıkça AI/editorial placeholder olarak etiketli local fixture asset kullanır.

### 3.7 Timing, cache ve cleanup

[`build_timing.py`](../../chatgpt_haber/build_timing.py#L10-L53) `perf_counter` ile process-local stage sürelerini kaydediyor; stage isimleri backend telemetry vocabulary'sine başlangıç olabilir. CLI cleanup bilinen output dosyalarını hedefli biçimde siliyor ve symlink/junction içine inmiyor. Bu güvenli legacy davranıştır, ancak job retry/cache değildir.

`requests-cache` ve `tenacity` dependency olarak tanımlı olsa da production Python akışında kullanılmıyor. Kalıcı conditional feed cache, content cache, lease, retry checkpoint veya idempotency store yok.

**Karar:** V2 cache her artifact için explicit content/version key kullanır; job stage'leri PostgreSQL transaction'larıyla checkpoint edilir. Cleanup yerine immutable/content-addressed asset + retention policy uygulanır. Stage duration, attempt ve failure reason structured telemetry olur.

### 3.8 Windows-only ve Gazet+E Studio legacy

`apps/gazette_studio.py`, `apps/random_news_app.py` ve `one_click.py` Tkinter, Desktop/AppData, local subprocess/thread ve system browser varsayımlarına bağlıdır. PowerShell/PyInstaller build script'leri Windows fontları, local Chromium kurulumu ve `.exe` paketleme kullanır. `user_profile.py` ve random-news state'i AppData'da process-local JSON tutar.

**Karar:** bunların tamamı legacy-only'dir. Mobile client'a subprocess, filesystem path, AppData veya embedded Python taşınmaz. İlerideki personalization ayrı server/account kararıdır; Q03'e dahil değildir.

### 3.9 GitHub Pages publication boundary

`pages_publish.py` tam legacy build'i staging'de çalıştırıp index, PDF, JSON ve dated archive kopyalarını generated `docs/` altına yazar. Bu statik publication channel'dır; authenticated API, durable job store veya Mobile V2 asset origin değildir.

**Karar:** `docs/` yalnız v1.1 GitHub Pages publication output olarak kalır. Governance `project_docs/` altında, Mobile V2 API/edition/object assets ayrı service boundary'de kalır. Q03 `docs/` yazmaz.

### 3.10 Tests ve fixtures

`examples/issue.sample.json` ile issue/filter/render/technology/builder/pages testleri mevcut davranış için iyi regression kanıtıdır. Fakat sample fixed üç sayfa, print template ve eksik interactive geometry taşır. Render testleri HTML/PDF link ve detail-page davranışını kanıtlar; mobile gesture davranışını kanıtlamaz.

**Karar:** Q03 yeni canonical fixture ve local assets kullanır. v1.1 fixture'ı yalnız adapter input örneği olabilir. Q03 acceptance, parser/unit/widget kanıtına ek olarak gerçek cihaz pinch/pan/page-conflict/hit-region/readability owner PASS ister.

## 4. Mobile framework karşılaştırması

| Seçenek | Gazete coordinate surface | Gesture/hit region | İki mod + state | Repo/team maliyeti | Karar |
|---|---|---|---|---|---|
| **Flutter** | `CustomPainter`, `Stack` ve tek render pipeline ile fixed logical canvas doğal | First-party `InteractiveViewer`, gesture arena, hit test ve semantics primitive'leri var | Navigator + shared view model/repository sınırı açık | Yeni Dart toolchain; buna karşılık tek UI implementation | **SEÇİLDİ** |
| React Native | Absolute layout/transform mümkün | Core responder ve `Pressable` var; yüksek kaliteli composed pinch/pan için ek gesture/render koordinasyonu gerekir | JS state ekosistemi güçlü | JS/native dependency matrisi ve custom surface glue artar | Seçilmedi |
| Compose Multiplatform | Custom drawing ve shared UI güçlü | Multiplatform input destekli, fakat platform-specific davranış ve giriş noktaları yönetilir | Kotlin state yaklaşımı güçlü | Mevcut Python repo için Kotlin/Gradle/Xcode öğrenme ve entegrasyon maliyeti daha yüksek | Seçilmedi |
| Ayrı SwiftUI + Jetpack Compose | Her platformda native kontrol | En güçlü platform uyumu | İki implementation'da state/contract parity gerekir | MVP ekibi için en yüksek çift geliştirme ve test maliyeti | Seçilmedi |

Flutter seçiminin belirleyici nedeni “cross-platform” etiketi değil, bu ürünün riskli çekirdeği olan tek bir zoomable coordinate surface'i, explicit hit testing'i ve accessibility semantics'i aynı render modelinde sınayabilmesidir. Flutter'ın resmi dokümantasyonu `InteractiveViewer` için pan/zoom, `CustomPainter` için paint/hitTest/semantics ve gesture arena için conflict çözüm primitive'lerini doğrudan tanımlar.

### 4.1 Newspaper surface sözleşmesi

- Her page kendi `canvas.width`, `canvas.height` ve `unit: logical` değerini taşır; örnek aspect `1000 × 1414` olabilir, fakat ölçü contract alanıdır.
- Flutter surface, canvas'ı viewport'a minimum scale ile sığdırır. Placement'lar `Stack`/paint katmanında contract koordinatlarıyla çizilir.
- `InteractiveViewer` + `TransformationController` her page için scale/translation state'ini tutar.
- Article ve source actions explicit `hit_regions` ile çalışır. Görünmez erişilebilir target'lar placement üstünde konumlanır; custom-painted öğeler semantics label üretir.
- Horizontal page swipe yalnız scale minimuma yakınken ve active pan yokken page turn yapar. Zoomed durumda yatay gesture canvas pan'ıdır; page navigation düğme/indicator ile de erişilebilir kalır.
- Reading view açıldığında `selected_article_id`, page ID/order ve page transform kaybolmaz. Back aynı `EditionSession` üzerinden önceki page/viewport'a döner.
- Source action OS browser'a yalnız explicit user action ile HTTPS canonical source URL açar.

### 4.2 Client state sınırı

Tek `EditionSession` şu state'i sahiplenir: `edition_id`, ordered page IDs, current page, page başına transform, selected article, active mode ve downloaded asset availability. Repository contract'ı load/validate/cache eder; view model navigation/gesture intent'ini yönetir; view yalnız render eder. Gazete ve Okuma modları ayrı veri kopyaları üretmez.

## 5. Backend/service karşılaştırması ve karar

| Seçenek | Python reuse | Durable long job | Operasyon yükü | Karar |
|---|---:|---:|---:|---|
| Mevcut local CLI/desktop | Yüksek | Yok | Tek makineye bağlı | Legacy-only |
| FastAPI + in-process `BackgroundTasks` | Yüksek | Process kaybında garanti yok | Düşük | Ağır edition job için reddedildi |
| **FastAPI + PostgreSQL durable job + ayrı Python worker** | **Yüksek** | **Lease/checkpoint/idempotency ile var** | **MVP için bounded** | **SEÇİLDİ** |
| FastAPI + Celery + Redis | Yüksek | Var | Ek broker, worker semantics ve operasyon | Trafik kanıtı sonrası defer |
| Node/TypeScript service | Düşük; ingestion/filtering rewrite gerekir | Queue seçimine bağlı | İkinci dilde backend rewrite | Seçilmedi |
| Serverless function zinciri | Orta | Provider workflow/state ürününe bağlı | Timeout, orchestration ve lock-in | Seçilmedi |

FastAPI'nin kendi resmi rehberi ağır background computation için ayrı process/queue yaklaşımını önerir; bu nedenle request process içindeki `BackgroundTasks` durable pipeline olarak kullanılmaz. PostgreSQL unique constraint idempotency'yi, row lease ise MVP worker coordination'ını sağlar. `FOR UPDATE SKIP LOCKED` queue-like access için uygundur; edition hacmi kanıtlanırsa broker eklemek contract'ı değiştirmeden mümkündür.

### 5.1 Service bileşenleri

```text
Flutter app
  -> FastAPI: request/status/edition access
       -> PostgreSQL: request keys, jobs, checkpoints, editions, provenance
       -> Object storage: immutable image/edition assets
  -> Python worker: collect -> select -> summarize -> illustrate -> layout
       -> RSS/publisher adapters
       -> AI providers (server-side secrets only)
```

- API kısa request/response doğrulaması yapar; pipeline'ı request process içinde yürütmez.
- Worker job row'unu bounded lease ile alır, heartbeat yazar ve her stage sonunda transaction checkpoint'i bırakır.
- Worker crash olursa lease expiry sonrası aynı stage deterministic input/cache keys ile yeniden denenir.
- Provider secrets yalnız server secret manager/environment'ta bulunur; mobile bundle, edition JSON, logs ve error payload'larına girmez.
- Object URLs kısa süreli/signed veya public-safe immutable asset policy'sine göre verilir; provider URL/key'leri contract'a sızmaz.

### 5.2 API ve truthful lifecycle

Minimum service contract:

- `POST /v1/edition-jobs` — `Idempotency-Key` ve versioned request body alır; `202` ile mevcut/yeni `job_id` döner.
- `GET /v1/edition-jobs/{job_id}` — durable state, current stage, attempt, son checkpoint zamanı ve safe failure döner.
- `POST /v1/edition-jobs/{job_id}/cancel` — non-terminal job için idempotent cancellation intent kaydeder; effective terminal state'i döner.
- `GET /v1/editions/{edition_id}` — yalnız validation PASS etmiş canonical edition document döner.

State machine sabittir:

```text
requested -> collecting -> selecting -> summarizing -> illustrating -> laying_out -> ready
any non-terminal -----------------------------------------------------> failed
any non-terminal ---------------------------------------------------> cancelled
```

Stage adı gerçek durable checkpoint'i gösterir; uydurma yüzde ilerleme gösterilmez. Bilinen toplam varsa item counts ayrıca sunulabilir. Retry yalnız `failed` state'indeki `retryable=true` failure veya expired lease için bounded attempt/backoff ile yapılır; failure payload'ı `code`, `retryable`, `attempt` ve safe diagnostic taşır. Kullanıcı aynı idempotency key ile retry storm yaratamaz.

`cancelled`, intentional user/system cancellation için ayrı terminal state'tir; `failed` değildir ve `retryable` failure payload'ı taşımaz. Cancel endpoint aynı job için tekrar çağrıldığında aynı sonucu döndürür. Job `cancellation.requested_at`, `effective_at` ve safe actor/reason metadata'sını saklar; başlamamış işi hemen, aktif işi ise provider çağrısından sonraki güvenli checkpoint'te durdurur ve sonraki artifact'ı publish etmez. Cancelled job'ı yeniden üretmek bilinçli yeni request/idempotency key gerektirir. Ready ve failed terminal job'lar cancel ile yeniden sınıflandırılmaz. Ready edition immutable'dır; farklı policy/request yeni edition/job identity üretir.

## 6. Canonical interactive edition contract

Bu document backend → mobile sınırının tek kanonik ürün contract'ıdır. Job status ayrı resource'dur. Ready document immutable ve schema-validated olur.

```json
{
  "contract_version": "gazet-e.edition.v1",
  "edition": {
    "id": "ed_01J...",
    "state": "ready",
    "requested_at": "2026-09-07T08:00:00Z",
    "generated_at": "2026-09-07T08:02:21Z",
    "locale": "tr-TR",
    "timezone": "Europe/Istanbul",
    "brand": { "name": "Gazet+E", "masthead": "GAZET+E" },
    "versions": {
      "editorial_policy": "editorial.tr.v1",
      "summary_prompt": "summary.tr.v1",
      "visual_brief": "visual-brief.v1",
      "visual_style": "gazet-e-editorial.v1",
      "layout_engine": "layout.v1"
    }
  },
  "pages": [
    {
      "id": "pg_front",
      "order": 1,
      "canvas": { "width": 1000, "height": 1414, "unit": "logical" },
      "template": { "id": "front", "version": "1" },
      "placements": [
        {
          "id": "pl_hero",
          "article_id": "art_7a...",
          "role": "hero",
          "rect": { "x": 40, "y": 180, "width": 920, "height": 520 },
          "z_index": 1,
          "hit_regions": [
            {
              "id": "hit_read_hero",
              "action": "open_reading",
              "rect": { "x": 40, "y": 180, "width": 920, "height": 520 },
              "accessibility_label": "Haberi okuma modunda aç"
            },
            {
              "id": "hit_source_hero",
              "action": "open_source",
              "rect": { "x": 790, "y": 650, "width": 170, "height": 50 },
              "accessibility_label": "Kaynağa git"
            }
          ]
        }
      ]
    }
  ],
  "articles": [
    {
      "id": "art_7a...",
      "cluster_id": "cluster_19...",
      "content_version": "sha256:...",
      "headline": "Örnek başlık",
      "dek": "Kısa sunuş",
      "summary": "Gazet+E tarafından kaynak gerçeklerine sadık hazırlanmış özet.",
      "reading_body": [
        { "type": "paragraph", "text": "Okuma modu için kısa editoryal metin." }
      ],
      "primary_source_id": "src_item_1",
      "sources": [
        {
          "id": "src_item_1",
          "publisher_id": "publisher_1",
          "name": "Örnek Kaynak",
          "canonical_url": "https://example.org/news/example",
          "published_at": "2026-09-07T07:30:00Z"
        }
      ],
      "visual": {
        "asset_id": "asset_sha256_...",
        "url": "https://assets.example/sha256/...",
        "content_hash": "sha256:...",
        "width": 1536,
        "height": 1024,
        "alt": "Kavramsal editoryal görsel açıklaması",
        "transparency_label": "AI-generated editorial image",
        "provenance": {
          "generated_by_ai": true,
          "provider": "server-provider-id",
          "model": "model-version",
          "generated_at": "2026-09-07T08:01:30Z",
          "brief_version": "visual-brief.v1",
          "style_version": "gazet-e-editorial.v1",
          "safety_class": "conceptual",
          "cache_key": "sha256:..."
        }
      },
      "cache": {
        "summary_key": "sha256:...",
        "visual_brief_key": "sha256:..."
      }
    }
  ],
  "cache": {
    "edition_key": "sha256:...",
    "layout_key": "sha256:..."
  }
}
```

### 6.1 Contract invariant'ları

- `contract_version`, edition ID/state/timestamps, locale/timezone, marka ve tüm policy/model/layout version'ları zorunludur.
- Page ID/order benzersizdir; canvas ölçüleri pozitif ve sonludur.
- Placement mevcut article'a referans verir; rectangle sonlu, non-negative ve canvas sınırları içindedir.
- Her görünür article için `open_reading`; source sunulan her article için güvenilir `open_source` hit region vardır. Hit region coordinate space page canvas ile aynıdır.
- Article ID, cluster ID ve content version birbirinin yerine kullanılmaz.
- En az bir source, primary source ve HTTPS canonical URL zorunludur. Full publisher body contract'a varsayılan olarak girmez.
- AI visual için alt text, transparency label, content hash, dimensions, provider/model, generation time, brief/style version, safety class ve cache key zorunludur.
- Client, provider prompt/key, raw scrape veya private storage path görmez.
- Unknown action/type/version fail-open çizilmez; parser anlaşılır unsupported-contract hatası verir.
- Ready edition mutation görmez. Düzeltme gerekiyorsa yeni edition/content version üretilir.

## 7. Identity, cache, cost ve security sınırları

### 7.1 Identity keys

- `article_id = SHA-256("article-id.v1" + publisher_id + canonical_url)`; URL yoksa açıkça işaretlenmiş fallback, normalized headline + source-published time bucket kullanır.
- `content_version = SHA-256(article_id + normalized permissible source facts hash)`.
- `cluster_id`, versioned cluster algorithm'ının entity/event/time signals sonucudur; algorithm version değişimi cluster identity alanına yansır.
- Client `request_id` + `Idempotency-Key` PostgreSQL unique constraint ile tek logical job'a bağlanır.
- Server `generation_key`, canonical request + freshness bucket + locale + editorial policy version birleşimidir. Aynı key için active/ready job yeniden kullanılır.

### 7.2 Artifact cache keys

- Summary: content/cluster fingerprint + locale + prompt/policy/model version.
- Visual brief: selected facts fingerprint + brief/safety policy version.
- Image: visual brief hash + style + safety class + provider/model + aspect/dimensions.
- Layout: ordered article IDs/content versions + page canvas + template/layout-engine version.
- Edition: generation key + ordered content/layout artifact hashes.

Cache yalnız exact key match'te reuse eder. Asset'ler content-addressed ve immutable olur. Failure/unsafe output başarılı cache girdisi sayılmaz. Retention ve deletion account/legal policy geldiğinde ayrıca versioned olur.

### 7.3 Cost ve security

- Early identity/cluster/cache lookup gereksiz summary/image çağrısından önce çalışır.
- Provider concurrency, timeout, attempt ve edition başına maliyet budget'ı server tarafında bounded olur.
- Loglar provider key, full request prompt, private source body veya signed URL içermez; correlation/job/artifact ID kullanır.
- Mobile yalnız scoped API erişimi görür. Auth, personal data ve abuse policy Q03 kapsamına alınmaz; production öncesi ayrı security gate zorunludur.
- RSS/source terms, excerpt/summary policy ve AI visual rights Q13 geçmeden commercial kullanım varsayılmaz.

## 8. v1.1 reuse / replace matrisi

| Alan / source | Sınıf | Gerekçe ve V2 sınırı |
|---|---|---|
| `sources.py` feed listesi, RSS parse ve ortak field extraction | **REUSE WITH ADAPTER** | Server-side source adapters; injected HTTP/clock, timeout/retry, canonical URL ve source ID zorunlu |
| ANKA HTML collector | **DEFER / UNKNOWN** | Kırılgan scraping ve terms doğrulaması gerekir; Q13 öncesi production varsayımı yok |
| `news_quality_filters.py` hard-reject kuralları | **REUSE WITH ADAPTER** | Pure/versioned policy ve structured reason haline getirilir |
| `sources.py` ranking signals | **REUSE WITH ADAPTER** | Deterministic inputs, versioned weights ve explainability eklenir; AppData state çıkarılır |
| Başlık-token fuzzy duplicate kontrolü | **REUSE WITH ADAPTER** | Yalnız cluster candidate signal; canonical identity olamaz |
| Feed sıra numaralı ID ve current dedupe identity | **REPLACE IN V2** | Cross-run stabil değil; canonical URL/content/cluster ayrımı gerekir |
| `builder.py` synchronous orchestration | **REPLACE IN V2** | Fixed üç sayfa ve process-local failure yerine durable stage worker gerekir |
| `issue.py` legacy/modern normalization | **REUSE WITH ADAPTER** | Yalnız explicit legacy import ve test-fixture migration sınırında |
| Current `issue.schema.json` authoritative contract | **REPLACE IN V2** | Interactive geometry, provenance, versions ve identity eksik |
| `technology_page.py` taxonomy/classifier | **REUSE WITH ADAPTER** | Editorial taxonomy signal olarak; ayrı/fixed page zorunluluğu olmadan |
| `technology_page.py` clone/fixed third-page assembly | **LEGACY ONLY** | Duplicate içerik ve sabit print page varsayımı |
| Publisher detail/body scraping | **DEFER / UNKNOWN** | Terms, content rights, selector reliability ve facts-only sınırı Q13'e bağlı |
| Publisher image scrape/download ve Pillow fallback zinciri | **REPLACE IN V2** | Visible V2 visual AI-generated-by-default pipeline'dan gelir; Q03 local fixture kullanır |
| `render.py`, Jinja templates ve print CSS | **LEGACY ONLY** | HTML/PDF/file URI/print browser runtime; hierarchy vocabulary contract tasarımına bilgi verir |
| Playwright PDF üretimi | **LEGACY ONLY** | Mobil runtime ve canonical layout engine değildir |
| `layout_issue.py` eski layout blocks | **LEGACY ONLY** | Coordinate/hit-region contract üretmez |
| `build_timing.py` stage duration vocabulary | **REUSE WITH ADAPTER** | Backend structured metrics/tracing'e çevrilir; process-local JSON kanonik değildir |
| CLI cleanup/archive/Desktop akışı | **LEGACY ONLY** | Local filesystem ve tek makine publication davranışı |
| `gazette_reports.py` quality/source signal hesapları | **REUSE WITH ADAPTER** | Structured server telemetry/audit row olarak; HTML/file reports legacy kalır |
| `user_profile.py` AppData persistence | **LEGACY ONLY** | Mobil/server account personalization Q11'de ayrı tasarlanır |
| Random news service/app | **LEGACY ONLY** | Ayrı local UX/cache/identity; canonical edition yolu değildir |
| Gazette Studio, one-click, PowerShell/PyInstaller `.exe` | **LEGACY ONLY** | Windows/Tkinter/subprocess boundary mobile'a taşınmaz |
| `pages_publish.py` ve generated `docs/` | **LEGACY ONLY** | GitHub Pages statik v1.1 publication; API/object store değildir |
| Existing filter/issue test cases | **REUSE WITH ADAPTER** | Pure policy ve legacy-import regression'larına dönüştürülebilir |
| Existing render/pages/Windows tests | **LEGACY ONLY** | v1.1 regression'ı korur; mobile acceptance yerine geçmez |
| `examples/issue.sample.json` | **REUSE WITH ADAPTER** | İçerik seed'i olabilir; Q03 için canonical geometry/provenance/local asset ile dönüştürülür |
| Teknik `chatgpt_haber` package/import ve `chatgpt-haber` CLI | **REUSE AS-IS** | v1.1 compatibility namespace; public marka contract'ı değildir |

## 9. Q03 fixture-only reader proof gate

Q03'ün amacı framework seçimini ve gazete etkileşimini en ucuz noktada yanlışlayabilmektir. Bu nedenle slice şu sınırı ihlal edemez:

### Dahil

- bundled, schema-valid `gazet-e.edition.v1` fixture;
- en az üç page, birden fazla placement role ve local AI/editorial placeholder asset;
- Gazete Modu fixed canvas render;
- pinch zoom, zoomed pan ve minimum-scale page navigation conflict kuralı;
- reading/source hit regions ve accessibility semantics;
- Okuma Modu ve aynı page/transform'a geri dönüş;
- parser/invariant unit testleri, widget/gesture testleri ve deterministic golden/screenshot kanıtı;
- Android/iOS hedeflerinden en az bir gerçek cihazda Fatih gesture/readability PASS; diğer hedef gate'i implementation planında açık tutulur.

### Hariç / stop

- live RSS/ANKA/publisher HTTP;
- FastAPI, PostgreSQL, object storage veya remote edition fetch;
- AI summary/image provider çağrısı veya provider key;
- production auth, personalization, archive/offline sync;
- Jinja/Playwright/PDF entegrasyonu;
- mevcut v1.1 production source/test/dependency/generated output değişikliği.

Q03 PASS kanıtı: app ağ kapalıyken aynı fixture'ı açar; paper geometry contract'a uyar; zoom/pan/page-turn conflict deterministik davranır; article/source targets güvenilir ve erişilebilirdir; reading/back state korunur; gerçek cihazda okunabilirlik kabul edilir. Ancak bu gate sonrası Q04 contract implementation ve Q05 backend başlanabilir.

## 10. Uygulama sırası ve karar kapıları

1. **Q03:** yalnız Flutter reader + canonical local fixture; interaction riski.
2. **Q04:** edition schema, validators ve interactive layout contract'ı repository'de productionlaştır.
3. **Q05:** FastAPI/PostgreSQL worker skeleton, idempotent request ve truthful progress.
4. **Q06–Q09:** source adapters, summary, AI visual ve layout worker stage'lerini sırayla bağla.
5. **Q10+:** end-to-end, personalization, history/offline; Q13 legal/security gates olmadan commercial varsayım yapma.

Bu audit yeni dependency veya production implementation yetkisi vermez. Q03 için ayrı GitHub Issue, Issue #4 merge edildikten sonra bu contract ve fixture-only stop koşullarıyla açılmalıdır.

## 11. Resmi teknik referanslar

- Flutter gestures ve gesture arena: <https://docs.flutter.dev/ui/interactivity/gestures>
- Flutter `InteractiveViewer`: <https://api.flutter.dev/flutter/widgets/InteractiveViewer-class.html>
- Flutter `CustomPainter` hit test/semantics: <https://api.flutter.dev/flutter/rendering/CustomPainter-class.html>
- Flutter app architecture: <https://docs.flutter.dev/app-architecture/guide>
- React Native `Pressable` hit rectangles: <https://reactnative.dev/docs/pressable>
- React Native gesture responder: <https://reactnative.dev/docs/gesture-responder-system.html>
- Compose Multiplatform overview/platform specifics: <https://kotlinlang.org/compose-multiplatform/> ve <https://kotlinlang.org/docs/multiplatform/compose-platform-specifics.html>
- FastAPI heavy background work sınırı: <https://fastapi.tiangolo.com/tutorial/background-tasks/>
- PostgreSQL unique constraints: <https://www.postgresql.org/docs/16/ddl-constraints.html>
- PostgreSQL `SKIP LOCKED`: <https://www.postgresql.org/docs/15/sql-select.html>

## 12. Q02 acceptance kaydı

- [x] Exact base ve GitHub Issue authority doğrulandı.
- [x] RSS, filtering, identity/dedupe, issue contract, render/layout, image, timing/cache, Windows ve Pages sınırları gerçek source üzerinden audit edildi.
- [x] Mobile seçenekleri karşılaştırıldı; Flutter tek net seçim olarak kaydedildi.
- [x] Backend seçenekleri karşılaştırıldı; FastAPI + PostgreSQL durable worker tek net seçim olarak kaydedildi.
- [x] Canonical interactive edition contract ve invariant'ları tanımlandı.
- [x] v1.1 reuse/replace matrisi izinli sınıflarla tamamlandı.
- [x] Q03 fixture-only proof, live RSS/AI öncesi zorunlu gate olarak korundu.
- [x] Production source, test, dependency, `docs/` ve generated output değişikliği yapılmadı.
