# Gazette Mobile V2 — Product Scope

## 1. Product statement

Gazette Mobile V2, kullanıcının istediği anda güncel haberleri derleyip yapay zekâ ile seçen, özetleyen ve görselleştiren; sonucu klasik basılı gazete estetiğinde interaktif bir mobil baskı olarak sunan kişisel gazete uygulamasıdır.

Ana değer önerisi haberleri kopyalamak değil, **bilgi gürültüsünü kullanıcının okuyabileceği tek bir editoryal baskıya dönüştürmektir**.

## 2. Ana kullanıcı hareketi — On-demand edition

Uygulamanın merkezinde tek bir güçlü eylem vardır:

`Gazetemi Hazırla`

Bu eylem current edition üretim zincirini başlatır:

`collect -> normalize -> dedupe -> rank -> summarize -> visual brief -> AI image -> layout -> ready edition`

Kullanıcı teknik pipeline ayrıntısıyla uğraşmaz. İlerleme durumu yalnız truthful ve anlaşılır aşamalarla gösterilir.

Her baskı oluşturulduğu zamana göre bir `edition` kimliği ve zaman damgası taşır. Aynı haber tekrar görüldüğünde AI summary/image maliyeti gereksiz yere yeniden harcanmaz; identity/version-aware cache kullanılır.

## 3. Primary reading modes

V2'nin tam olarak iki primary reading mode'u vardır.

### 3.1 Gazete Modu

Default ana deneyimdir.

- Ekranda gerçek bir basılı gazete sayfası kompozisyonu görünür.
- Telefon sayfayı responsive feed'e dönüştürmez; gazete sayfası kendi koordinat sistemini korur.
- Kullanıcı pinch ile zoom yapar.
- Zoomed durumda pan/scroll ile sayfanın farklı bölgelerine gider.
- Sayfalar arasında swipe/page navigation vardır.
- Gesture priority, zoomed pan sırasında istemsiz sayfa değişimini engellemelidir.
- Haber alanları interaktif hit-region'dır.
- Haber başlığı/görseli/alanına tap varsayılan olarak Okuma Modu'nu açar.
- Kaynak etiketi veya uygun küçük source affordance doğrudan original source'a gidebilir.
- Page transition hafif ve hızlıdır; günlük kullanımı yavaşlatan ağır 3D page-curl zorunlu değildir.

### 3.2 Okuma Modu

Gazete deneyimini tamamlayan mobil-okunur article view'dır.

Minimum içerik:

- headline;
- AI-generated editorial image;
- image transparency/provenance indicator;
- Gazette kısa özeti;
- source/publication adı;
- yayın zamanı mevcutsa;
- `Kaynağa Git` eylemi;
- Gazete Modu'na dönüş.

Geri dönüş mümkün olduğunca aynı edition, page ve önceki navigation bağlamını korur.

Okuma Modu publisher'ın tam makalesinin kopyası değildir; kullanıcı orijinal içeriğe source link ile gider.

## 4. Newspaper visual system

Gazete ekranı klasik basılı gazete dilini korur:

- güçlü masthead;
- edition tarih/saat bilgisi;
- hero/manşet hiyerarşisi;
- sütunlar;
- secondary stories;
- kısa haber blokları;
- dengeli görsel/metin yoğunluğu;
- versioned template sistemi.

Ama sayfa statik PDF bitmap'i olmak zorunda değildir. V2'nin canonical edition modeli semantik/interaktif öğeler taşımalıdır:

- article blocks;
- text regions;
- image regions;
- source links;
- hit rectangles;
- page coordinates;
- reading-mode target.

PDF export ileride secondary capability olabilir; mobil ana reader gerçek PDF viewer'a bağımlı tasarlanmaz.

## 5. AI editorial images

V2 görünür story imagery'sinin varsayılan kaynağı AI generation'dır.

Pipeline:

1. article facts çıkarılır;
2. model bir visual brief üretir;
3. editorial safety class belirlenir;
4. image model görsel üretir;
5. visual QA kontrolü yapılır;
6. kabul edilen asset cache'e alınır.

### 5.1 Stil

Bütün edition boyunca tutarlı premium editorial visual language kullanılır. Rastgele stil karışımı yapılmaz.

### 5.2 Hassas gerçek olaylar

AI görsel sistemi şu tür haberlerde gerçekte çekilmiş kanıt fotoğrafı izlenimi üretmemelidir:

- savaş/çatışma;
- terör/saldırı;
- afet;
- kaza;
- politik/diplomatik buluşma;
- suç;
- belirli gerçek kişiye atfedilen tartışmalı davranış.

Bu durumlarda editorial/conceptual representation tercih edilir. Örneğin bayraklar, kurum binası, harita, sembolik ortam, veri/konsept illüstrasyonu veya non-documentary visual language kullanılabilir.

### 5.3 Transparency

Kullanıcıya bunun AI-generated editorial image olduğu saklanmaz. Reading Mode'da açık bir gösterge; Newspaper Mode'da ise tasarımı bozmayan tutarlı bir işaret/legend kullanılabilir.

## 6. Source and editorial truth

Her article için zorunlu minimum source truth:

- source name;
- canonical/original URL;
- publication time/date mevcutsa;
- source article identity veya normalized identity;
- Gazette summary ile source content ayrımı.

Gazette'in summary'si kaynak haberi desteklemeyen yeni facts eklememelidir. Full publisher article metni V2 product content'i olarak varsayılan şekilde yeniden yayımlanmaz.

## 7. Mobile/backend boundary principles

Q02 architecture audit kesin teknoloji kararını verir; ancak şu güvenlik ilkeleri şimdiden bağlayıcıdır:

- AI provider secret/API key mobile binary içine gömülmez;
- untrusted client generation quota'yı doğrudan sınırsız tüketemez;
- edition generation resumable/observable bir service boundary'ye sahip olmalıdır;
- client yalnız presentation ve kullanıcı interaction için gereken data'yı almalıdır;
- generation/cache/provenance server-side veya eşdeğer güvenli boundary'de tutulmalıdır.

## 8. v1.1 reuse principle

Mevcut v1.1 sisteminde değerli olabilecek parçalar vardır:

- RSS collection;
- normalization;
- editorial filtering;
- issue JSON fikri;
- layout logic;
- source validation;
- timing/build pipeline.

Ancak HTML/PDF/Playwright/desktop parçalarının mobile runtime'a doğrudan taşınacağı varsayılmaz. Q02 audit reuse/replace kararını modül bazında verir.

## 9. Performance product target

On-demand edition bekleme süresi ürünün temel riskidir.

Bu nedenle:

- cached article summary/image yeniden kullanılmalı;
- yalnız yeni/değişmiş article AI işine girmeli;
- progress UI truthful olmalı;
- image generation paralellik/rate limit sınırları kontrollü olmalı;
- partial asset failure için fallback bulunmalı;
- ready edition yeniden açılırken generation tekrarlanmamalıdır.

Kesin süre hedefleri gerçek prototype ölçümü sonrası belirlenir; bootstrap aşamasında hayali SLA yazılmaz.

## 10. Initial commercial direction

V2'nin ilk ürün hipotezi kişisel premium gazete deneyimidir. Monetization çekirdek reader/generation UX'i kanıtlanmadan önce implementation önceliği değildir.

Muhtemel premium değer alanları:

- daha sık on-demand edition;
- daha uzun edition;
- gelişmiş personalization;
- tracked topics/companies/people;
- archive/offline;
- premium generation quota.

Gerçek fiyat ve quota AI maliyet ölçümü, source/legal review ve kullanıcı testi sonrasında belirlenir.

## 11. Explicit non-goals for initial V2

İlk V2 çekirdeğinin parçası değildir:

- sosyal medya feed'i;
- comments/community;
- publisher CMS;
- reklam ağı;
- video-first experience;
- desktop uygulamasını yeniden yazmak;
- web publication sistemini V2 reader'a dönüştürmek;
- ekip/organization admin sistemi.

## 12. Product acceptance principle

V2'nin başarısı yalnız build/test PASS değildir. Çekirdek gazete reader slice'ı gerçek mobil cihazda Fatih tarafından en az şu açılardan kabul edilmelidir:

- gazete hissi;
- zoom/pan rahatlığı;
- page navigation;
- article tap accuracy;
- Okuma Modu readability;
- source access;
- geri dönüş bağlamı;
- görsel kalitesi.
