# Gazet+E Mobile V2 — Kanonik Ürün Yol Haritası

**Durum:** Aktif geliştirme için tek kanonik yürütme kuyruğu  
**Güncelleme:** 8 Eylül 2026<br>
**Kapsam kaynağı:** `project_docs/v2/GAZETTE_MOBILE_V2_SCOPE.md`  
**Kalıcı ürün kararları:** `project_docs/protocols/GAZETTE_UNIFIED_PROJECT_SOURCE.md`

## 1. Bu dosyanın görevi

Bu `ROADMAP.md`, Gazet+E Mobile V2 için sıradaki production işinin seçildiği tek kanonik queue'dur.

- Current SHA, Issue/PR ve branch durumu her görevde GitHub'dan okunur.
- Aynı anda açık bir production Issue/PR varsa onun required gate'leri kapanmadan sonraki Q'ya geçilmez.
- Queue sırası yalnız owner kararıyla değişir.
- `docs/` GitHub Pages output alanıdır; governance kaynağı değildir.
- v1.1 desktop/PDF/static-web sistemi legacy/reference baseline olarak korunur.

## 2. Durum etiketleri

- `ACTIVE` — current production/governance child.
- `NEXT` — active child kapanınca başlanacak ilk iş.
- `QUEUED` — sırayla bekler.
- `DECISION GATE` — implementation öncesi owner kararı gerekir.
- `RELEASE GATE` — yayın yeterliliği kapısıdır.
- `FINAL OWNER GATE` — public/store release için açık owner kararı gerekir.
- `RETIRED/SUPERSEDED` — tarihsel implementation/evidence korunur fakat aktif
  product runtime yönü daha yeni owner kararıyla değiştirilmiştir.

## 3. Kanonik queue

### Q01 — V2 project authority bootstrap

**Kaynak:** Issue #2  
**Durum:** `COMPLETE`

Bitiş tanımı:

- repository maintenance-only durumundan V2 active-development durumuna truth-sync edilir;
- `AGENTS.md`, bu roadmap, V2 scope ve unified product source oluşur;
- iki primary reading mode, on-demand edition ve AI-image policy kanonikleşir;
- generated `docs/` output alanı governance dosyalarından ayrılır;
- v1.1 implementation'a production değişikliği yapılmaz.

### Q02 — Mevcut motor audit'i + mobile/backend architecture boundary

**Durum:** `COMPLETE`

Kod yazmadan önce mevcut v1.1 sisteminin hangi parçalarının V2'de yeniden kullanılacağı belirlenir.

**Kanonik karar kaydı:** `project_docs/v2/002_V1_ENGINE_MOBILE_ARCHITECTURE_AUDIT.md`

- Mobile client: Flutter; fixed logical newspaper canvas, explicit hit regions ve iki modda shared edition session.
- Backend: Python FastAPI + PostgreSQL durable job/metadata + ayrı Python worker; immutable asset'ler object storage'da.
- Canonical sınır: versioned interactive edition document; mevcut üç sayfalı issue JSON yalnız legacy adapter girdisi.
- Sıralama gate'i: Q03 bundled fixture/local asset ile tamamen offline kanıtlanmadan live RSS, AI veya backend entegrasyonu başlamaz.

Audit en az şunları kapsar:

- RSS ingestion ve normalization;
- editorial quality/filtering;
- article identity/deduplication;
- current issue JSON contract;
- HTML/PDF layout/render code;
- image enrichment bağımlılıkları;
- timing/cache fırsatları;
- mobile client için uygun olmayan desktop/Playwright parçaları.

Architecture çıktısı en az şunları kesinleştirir:

- mobile client teknoloji seçimi ve gerekçesi;
- server/backend sınırı;
- provider secret'larının client'a girmemesi;
- edition/job lifecycle;
- canonical edition JSON/document contract;
- AI generation işlerinin güvenli backend sınırı;
- cache/identity yaklaşımı;
- v1.1 reuse vs replace matrisi.

**Stop:** audit tamamlanmadan geniş mobile/backend rewrite başlamaz.

### Q03 — Static interactive newspaper reader vertical slice

**Durum:** `COMPLETE`

Fixture/sample edition ile canlı RSS/AI olmadan çekirdek mobil deneyim kanıtlanır.

Bitiş tanımı:

- `Gazete Modu` gerçek basılı gazete hissi veren tam sayfa sunar;
- pinch-zoom ve zoomed pan çalışır;
- page navigation gesture conflict yaratmaz;
- newspaper article regions tıklanabilir;
- article tap `Okuma Modu` açar;
- Okuma Modu mobil-okunur source headline, fixture dönemine ait örnek metin,
  AI/editorial image placeholder, kaynak ve `Kaynağa Git` sunar;
- paper üzerindeki source affordance gerekirse doğrudan kaynağı açabilir;
- Okuma Modu'ndan geri dönüş aynı edition/page bağlamını korur;
- Fatih gerçek cihazda gesture/readability PASS verir.

Bu Q, product-market riski yüksek temel etkileşimi backend yatırımından önce kanıtlar.
Q03 fixture'daki tarihsel örnek summary içeriği active product text contract'ı
değildir; O-011 ile Q10 Okuma Modu source excerpt sınırına geçer.

### Q04 — Edition document model + interactive layout contract

**Durum:** `COMPLETE` — historical `gazet-e.edition.v1`; Q10 revision active

- edition ID/timestamp;
- page identity/order;
- article identity;
- newspaper rectangle/hit-region coordinates;
- source headline/bounded source excerpt/source/source URL;
- AI visual metadata;
- layout template/version;
- reading-mode content;
- provenance/cache fields

JSON-ready canonical contract olarak tanımlanır ve fixture/regression testleri eklenir.
O-011/O-012/O-013; active successor contract'ın AI text zorunluluğunu
kaldırmasını, physical page profile ve in-page ad geometry/identity taşımasını
gerektirir. Q04 v1 evidence korunur; controlled version migration Q10'a aittir.

### Q05 — On-demand edition job service

**Durum:** `COMPLETE`

`Gazetemi Hazırla` eylemi için bounded job lifecycle kurulur:

Historical Q05 v1 sırası `summarizing` stage'ini içeriyordu. O-011 ile aktif
production target lifecycle şöyledir:

`requested -> collecting -> selecting -> illustrating -> laying_out -> ready | failed | cancelled`

Q05'in tarihsel durability/lease/idempotency kanıtı korunur; stage-model ve
recovery migration'ı current Q10 revision içinde kontrollü yapılır.

- progress truthful olur;
- duplicate request storm engellenir;
- cancellation/retry semantics açık olur;
- client provider secrets taşımaz.

### Q06 — Live news ingestion + dedupe + ranking + attribution

**Durum:** `COMPLETE`

Mevcut RSS kabiliyetleri V2 service contract'a taşınır veya dar uyarlamayla yeniden kullanılır.

- kaynak kimliği ve URL zorunlu;
- duplicate stories kümelenir;
- aynı olayın gereksiz tekrarları azaltılır;
- recency + importance ranking deterministik/izlenebilir sinyaller taşır;
- full publisher article yeniden yayınlama varsayılmaz.

### Q07 — AI editorial summary pipeline

**Durum:** `RETIRED/SUPERSEDED`

- haber gerçeğine sadık kısa Gazet+E özeti;
- unsupported detail/hallucination kontrolü;
- source attribution;
- versioned prompt/model metadata;
- cache;
- failure fallback

kurulur.

Bu implementation, testler ve live-gate kanıtı tarihsel olarak geçerlidir;
O-011 sonrasında product runtime Q07 generation/verifier/repair/cache yolunu
çağırmaz ve text-AI maliyeti sıfırdır. Bu durum tarihsel dosyaları silmez.

### Q08 — AI visual editor + generation + safety + cache

**Durum:** `COMPLETE`

Her story için pipeline:

`article facts -> visual brief -> editorial safety classification -> AI generation -> visual QA -> cache`

Bitiş tanımı:

- visible editorial story images AI-generated by default;
- publisher/RSS image dependency yok;
- sensitive real events fake documentary evidence gibi resmedilmez;
- style guide bütün edition boyunca tutarlı;
- image provenance/model/brief/style version izlenebilir;
- aynı article/style revision gereksiz yeniden üretilmez;
- Reading Mode'da AI editorial image transparency görünürdür.

### Q09 — Newspaper layout engine V2

**Durum:** `COMPLETE` — historical logical-canvas engine

Ranked article set'i basılı gazete estetiğine dönüştüren versioned layout engine kurulur.

- hero/secondary/brief story hierarchy;
- dengeli görsel-metinsel yoğunluk;
- bounded template set;
- interactive hit-region output;
- mobile zoom'da okunabilir tipografi;
- page count/overflow deterministic davranış.

Q09'un `1000×1414 logical` acceptance kanıtı tarihseldir. O-012/O-013 ile
gereken versioned `350×500 mm` physical page profile ve reserved in-page ad
contract'ı, Q09 geçmişini yeniden yazmadan current Q10 revision'ında uygulanır.

### Q10 — End-to-end one-tap edition integration

**Durum:** `ACTIVE`

`Gazetemi Hazırla` → live news → selection → AI editorial image + image QA →
`350×500 mm` physical newspaper layout + bounded in-page ads → interactive
mobile edition zinciri tamamlanır. AI text generation/verifier/repair yoktur.

Acceptance:

- active request/edition contracts are `gazet-e.edition-request.v2` and
  `gazet-e.edition.v2`; new jobs never enter historical `summarizing`;
- kullanıcı manuel teknik adım yapmaz;
- progress anlaşılırdır;
- partial failure edition'ı bütünüyle gereksiz bozmaz;
- ready edition iki modda açılır;
- Okuma Modu source headline, varsa bounded feed excerpt, publication/source,
  AI editorial visual ve `Kaynağa Git` sunar; excerpt uydurulmaz ve reklam yoktur;
- Gazete Modu fixed physical page'i fit/zoom/pan/page navigation ile korur;
- synthetic/local reklam sayfa başına en fazla bir, alanın en fazla `%15`i,
  açık `REKLAM` label'ı ve editorial/hit/gesture ayrımıyla yerleşir; uygun slot
  yoksa reklam yoktur;
- aynı immutable edition aynı ad creative'i korur; yeni edition creative'i
  değiştirebilir;
- source links çalışır;
- real-device end-to-end PASS gerekir.

### Q11 — Personalization

**Durum:** `QUEUED`

- ilgi alanları;
- kategori/source ağırlıkları;
- takip edilen kişi/şirket/konu;
- görmek istemediği konu sınırlamaları;
- edition uzunluğu

minimum sürtünmeyle eklenir. Personalization source truth'u bozmaz.

### Q12 — Edition archive + offline/cache + performance

**Durum:** `QUEUED`

- son baskılar;
- aynı edition'ın yeniden açılması;
- generated image/content cache;
- bounded local storage;
- offline reading of downloaded edition;
- cache invalidation/versioning;
- düşük ağ kalitesinde graceful behavior.

### Q13 — Commercial/legal/privacy/brand readiness

**Durum:** `DECISION GATE`

Ücretli/public ürün öncesi:

- `Gazet+E` trademark/legal clearance;
- `Gazet+E` domain ve store-name availability;
- third-party trademark exposure kontrolü;
- RSS/source terms audit;
- summary/excerpt policy;
- AI image/provider commercial terms;
- privacy policy/data disclosure;
- telemetry/account behavior;
- external-browser/source attribution policy;
- AI image transparency wording

owner review ile kapanır.

### Q14 — Monetization architecture

**Durum:** `QUEUED`

Q13 gate sonrası free/premium sınırları, gerçek image-generation/QA maliyeti ve
monetization mimarisi belirlenir. Gerçek ad serving/network, targeting,
tracking, auction ve advertiser/billing entegrasyonu bu Q'ya aittir; Q10 yalnız
synthetic/local ad-layout kanıtını taşır.

Candidate ürün ayrımı:

- Free: bounded edition frequency/length;
- Premium: daha sık on-demand edition, personalization, archive/offline ve daha geniş takip.

Ödeme/account implementation bu Q'dan önce ürünün çekirdek UX'ini bloke etmez.

### Q15 — Release readiness + store package

**Durum:** `RELEASE GATE`

- focused + integrated automated validation;
- gesture/performance device matrix;
- failure/offline behavior;
- privacy/permission truth;
- production API/security configuration;
- crash/telemetry decision;
- store metadata/screenshots;
- exact release artifact provenance.

### Q16 — Public mobile release

**Durum:** `FINAL OWNER GATE`

Store/public release ancak bütün required gates PASS ve Fatih açık release kararı verdikten sonra yapılır.

## 4. Şimdilik kapsam dışı

Aşağıdakiler çekirdek iki-mod on-demand newspaper deneyimi kanıtlanmadan production queue'ya alınmaz:

- social network/feed;
- user comments;
- publisher CMS;
- ad network;
- complex organization/team admin;
- desktop V2 rewrite;
- auto-play video/audio news;
- public web reader rewrite;
- speculative blockchain/NFT/content ownership features.
