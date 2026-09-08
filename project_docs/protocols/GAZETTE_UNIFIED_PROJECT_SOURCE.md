# Gazet+E Unified Project Source

Bu belge Gazet+E Mobile V2 için kalıcı ürün amacı, owner kararları ve değişmez ürün sınırlarının kanonik kaynağıdır. Current SHA, Issue/PR, branch veya tamamlanma durumu burada tutulmaz; bunlar GitHub'dan okunur.

## 1. Ürün amacı

Gazet+E, kullanıcının haber akışlarını tek tek takip etmesini gerektirmeden, istediği anda güncel haberlerden kişisel bir **dijital basılı gazete baskısı** üretir.

Ürünün sattığı temel değer üçüncü taraf haber metnini yeniden satmak değildir. Değer:

- toplama;
- ayıklama;
- tekrarları azaltma;
- önem sıralama;
- source-authoritative headline ve bounded feed/excerpt sunumu;
- tutarlı AI görselleştirme;
- fiziksel tam sayfa basılı gazete tasarımı;
- editoryal alanı koruyan sayfa-içi reklam yerleşimi;
- kaynak erişimi

bileşimidir.

## 2. Owner kararları — 6 Eylül 2026

### O-001 — Mobile-first V2

V2'nin ana dağıtım yüzeyi mobil uygulamadır. v1.1 desktop/PDF/static web baseline korunur fakat V2'nin ana UX'i olarak kabul edilmez.

### O-002 — On-demand edition

Kullanıcı bir eylemle o anın haberlerinden yeni edition hazırlatabilmelidir. Scheduled morning edition ileride eklenebilir; on-demand deneyimin yerine geçmez.

### O-003 — Classic newspaper presentation

Ana ekran haber feed'i veya card listesi değildir. Kullanıcı tam bir klasik gazete sayfası görür ve onu dijital bir fiziksel yüzey gibi inceler.

### O-004 — Exactly two primary reading modes

V2'de iki primary mode vardır:

1. **Gazete Modu** — tam gazete sayfası; pinch-zoom, pan/scroll, page navigation, interaktif story regions.
2. **Okuma Modu** — telefona uygun article view; source headline, varsa
   bounded source/feed excerpt, AI editorial image, publication/source ve
   source action. Okuma Modu reklam içermez.

Yeni bir primary reader mode owner kararı olmadan eklenmez. Yardımcı sheet/dialog bu iki mode dışında üçüncü ana deneyim sayılmaz.

### O-005 — Source access is mandatory

Her story original source'a bağlanabilir olmalıdır. Newspaper surface içindeki uygun source affordance veya Okuma Modu'ndaki `Kaynağa Git` eylemi source erişimini korur.

### O-006 — AI-generated editorial imagery by default

V2'de görünür haber görselleri AI tarafından oluşturulur. RSS/publisher image hotlink veya kopyalama ana görsel stratejisi değildir.

Amaç:

- tutarlı Gazet+E visual identity;
- third-party photo dependency azaltma;
- story-specific visual composition;
- cache/version control.

### O-007 — No fake documentary evidence

AI görüntüsü özellikle hassas gerçek olaylarda yaşanmış olayı fotoğrafla kanıtlıyormuş gibi davranmaz. Savaş, afet, kaza, suç, politik buluşma ve benzeri durumlarda conceptual/editorial representation kullanılır.

AI-generated nature kullanıcıdan saklanmaz.

### O-008 — v1.1 is a protected legacy baseline

Q02 architecture audit tamamlanana kadar mevcut v1.1 RSS, filtering, issue, render ve publish kodu korunur. Mobile V2 uğruna toplu rewrite/silme yapılmaz.

### O-009 — Real-device acceptance for the newspaper interaction

Pinch/pan/page navigation/article hit region ve two-mode transition davranışı gerçek mobil cihaz üzerinde owner PASS olmadan product-complete kabul edilmez.

### O-010 — Canonical public/product brand ve repository identity

6 Eylül 2026 owner kararıyla canonical public/product marka `Gazet+E`, masthead/wordmark gösterimi `GAZET+E` olarak kesinleştirildi. Eski `ChatGPT Gazette` adı aktif marka değildir.

Fatih'in 7 Eylül 2026 owner kararıyla repository rename kalıcıdır ve kanonik GitHub repository kimliği `faliardic/gazet-e`dir. Önceki `faliardic/chatgpt-haber` repository slug koruması bu kararla supersede edilmiştir. Python package/import namespace'i `chatgpt_haber` ve CLI komutu `chatgpt-haber` uyumluluk için korunmaya devam eder. Bu karar trademark, domain, store-name veya legal clearance iddiası değildir; bunlar Q13 gate'inde doğrulanır.

## 3. Owner kararları — 8 Eylül 2026

### O-011 — Product runtime'da AI text yoktur

Gazet+E V2 product runtime'ı haber özeti, dek, reading body, verifier, repair
veya başka bir text enrichment için AI/LLM çağırmaz. AI'nın tek editoryal
generation görevi haber görselidir; image safety/semantic QA bu görsel
sınırının parçasıdır. Hedef text-AI API maliyeti sıfırdır.

Okuma Modu source-authoritative headline, varsa kaynağın sağladığı bounded
feed/description excerpt, publication/source, AI editorial visual ve açık
`Kaynağa Git` eylemini sunar. Excerpt yoksa AI ile tamamlanmaz. Full publisher
body scrape veya varsayılan yeniden yayınlama yapılmaz.

Q07 implementation/test/live-gate kanıtı tarihsel olarak korunur fakat aktif
ürün yönünde `RETIRED/SUPERSEDED` durumundadır. Bu karar tek başına tarihsel
dosyaları silme yetkisi değildir.

### O-012 — Kanonik yüzey fiziksel tam gazete sayfasıdır

Gazete Modu'nun kanonik referans profili versioned **350 mm × 500 mm**
broadsheet-style tam sayfadır. Contract fiziksel width/height ile logical render
scale'i birlikte taşır. Telefon bu sabit sayfayı yalnız fit eder, zoomlar, pan
eder ve sayfalar arasında gezinir; editoryal blokları mobil genişliğe göre
reflow etmez. Bu ilk profil bir matbaa/store standardı iddiası değildir ve
ileride versioned yeni profil ile değiştirilebilir.

### O-013 — Reklam yalnız ayrılmış gazete sayfası slotundadır

- Reklam yalnız Gazete Modu'nun önceden ayrılmış layout slotunda bulunabilir.
- Sayfa başına en fazla bir slot ve toplam sayfa alanının en fazla `%15`i
  kullanılabilir; uygun slot yoksa reklam gösterilmez.
- Her reklam açıkça `REKLAM` olarak etiketlenir; editoryal haber veya AI haber
  görseli gibi davranmaz.
- Reklam editorial/source/hit region ile örtüşmez, render sonrasında sayfayı
  yeniden boyutlandırmaz ve bounded reklam tap alanı dışında pinch/pan/page
  navigation gesture'larını engellemez.
- Overlay, interstitial, popup, modal, sticky, fullscreen, autoplay ve forced
  wait reklam biçimleri yoktur. Okuma Modu reklam içermez.
- Yeni edition farklı synthetic/local creative seçebilir; aynı immutable
  edition yeniden açıldığında creative kimliği ve görünümü değişmez. Geometry
  veya içerik etkiliyorsa ad-slot/creative identity layout/edition identity'ye
  katılır.
- Q10 yalnız bounded local/synthetic inventory ile layout ve interaction
  sözleşmesini kanıtlar. Gerçek ad network, targeting, tracking, telemetry,
  auction, advertiser account ve billing/SDK entegrasyonu Q14 ve ilgili Q13
  commercial/privacy gate'lerine aittir.

## 4. Editorial truth principles

- Product runtime AI-generated summary/dek/reading body üretmez.
- Source/feed excerpt yalnız bounded source verisi olarak gösterilir; eksik
  excerpt AI ile uydurulmaz.
- Source name ve canonical URL edition contract'ta korunur.
- AI editorial image ile source fact veya documentary evidence birbirine
  karıştırılmaz.
- Aynı olayın farklı kaynakları duplicate cluster olarak ele alınabilir; kaynak izi kaybolmaz.
- Publisher full article metninin product content'i olarak yeniden yayınlanacağı varsayılmaz.
- Üçüncü taraf RSS veya feed'in ücretsiz erişilebilir olması commercial republication license varsayımı değildir.

## 5. AI visual principles

Her AI visual en az şu metadata ile izlenebilir olmalıdır:

- article/cluster identity;
- visual brief version;
- style version;
- generation provider/model;
- generation timestamp;
- safety/editorial class;
- asset identity/cache key.

Visual brief article facts'tan türetilir. Modelin rahatça görsel üretebilmesi için unsupported factual details uydurulmaz.

## 6. Interaction principles

- Gazete Modu ürünün karakteridir; Okuma Modu accessibility/readability tamamlayıcısıdır.
- Zoomed pan ile page swipe çakışmamalıdır.
- Article tap kolay ve predictable olmalıdır.
- Kullanıcı accidental browser redirect yaşamamalıdır; source action açıkça anlaşılır olmalıdır.
- Okuma Modu'ndan geri dönünce edition bağlamı kaybolmamalıdır.
- Ağır page-curl veya dekoratif animasyon, kullanım hızından daha önemli değildir.
- Reklam tap alanı dışındaki reader gesture'ları reklam tarafından yakalanmaz.

## 7. Cost and cache principles

AI maliyeti edition başına kontrolsüz büyütülmez.

- text-AI runtime çağrısı ve maliyeti sıfırdır;
- aynı story + aynı relevant version için cached verified image tercih edilir;
- only-new/changed work yeniden üretilir;
- generation concurrency/rate limit bounded olur;
- failure fallback edition'ı mümkün olduğunca kullanılabilir bırakır;
- cost instrumentation monetization kararından önce görünür hale gelir.

## 8. Security principles

- Provider secrets mobile client'a gömülmez.
- Payment/account/privacy değişiklikleri CRITICAL lane'dir.
- Production data migration veya destructive cleanup explicit authority olmadan yapılmaz.
- Store/release signing ve public production action ayrı release gate'tir.

## 9. Governance

Execution sırası `ROADMAP.md`'den okunur. Bir owner kararı bu belgeyle çelişen yeni bir ürün yönü getirirse önce bu source ve gerekirse scope/roadmap truth-sync edilir, sonra production implementation başlar.
