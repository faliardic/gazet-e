# GV2-004 — Q03 Static Interactive Newspaper Reader Vertical Slice

**Authority:** GitHub Issue #10
**Exact base:** `3404f0074b08a6630ad0e83dc9d6c7fcce503053`
**Branch:** `gv2/004-static-reader-proof`
**Lane:** STANDARD
**Ürün markası:** `Gazet+E`; masthead: `GAZET+E`

## 1. Sonuç

Q03, `mobile/` altında Android ve iOS hedefli izole bir Flutter reader proof olarak uygulandı. Proof yalnız bundled `gazet-e.edition.v1` fixture ve bundled local kavramsal görsellerle çalışır; live RSS, backend, remote edition, AI provider, account veya analytics erişimi yoktur.

Bu slice iki canonical mode'u aynı `EditionSession` üzerinde kanıtlar:

- **Gazete Modu:** fixed logical page canvas, basılı gazete hiyerarşisi, pinch zoom, zoomed pan, fit-scale page navigation ve explicit article/source hit regions.
- **Okuma Modu:** headline, local editoryal görsel, görünür AI/editoryal-placeholder etiketi, Gazet+E özeti/reading body, source/publication time ve açık `Kaynağa Git` eylemi.

Automated PASS gerçek cihaz kabulü değildir. Draft PR, Fatih'in cihazda gesture/readability PASS/FAIL kararı verilene kadar Ready veya merge edilmez.

## 2. Project ve dependency boundary

- Root: `mobile/`
- Flutter: `3.44.6`
- Dart: `3.12.2`
- Platform scaffold: yalnız `android/` ve `ios/`
- Provisional proof application ID: `com.faliardic.gazete.readerproof`
- Runtime direct dependencies: Flutter SDK, `url_launcher 6.3.2`
- Dev dependencies: `flutter_test`, `flutter_lints`

Application ID yalnız Q03 acceptance artifact'ını ayırt eder. Final package/store identity yetkisi Q15'tedir.

`url_launcher` yalnız kullanıcının explicit source action'ında fixture'daki canonical HTTPS URL'yi external system browser'a göndermek için kullanılır. Embedded WebView yoktur. App içinde HTTP client, RSS, API, provider key, database, router/state-management paketi, analytics veya code generation yoktur.

## 3. Bundled fixture

`mobile/assets/fixtures/edition.json` Q03'e özel minimal local contract örneğidir; Q04 production schema'sı değildir.

Fixture şunları taşır:

- `contract_version: gazet-e.edition.v1`;
- tek deterministic edition ve ordered üç page;
- her page için `1000 × 1414 logical` canvas;
- `hero`, `secondary`, `brief` placement rolleri;
- article ve cluster kimlikleri;
- headline, dek, Gazet+E summary ve paragraph reading body;
- primary source name, canonical HTTPS URL ve varsa publication time;
- canvas-bounded placement rectangles;
- birbirinden ayrı `open_reading` ve `open_source` hit rectangles;
- accessibility labels;
- bundled asset path, alt text, transparency label, `generated_by_ai` ve `conceptual` safety class.

Parser unsupported contract version, missing article reference, invalid/non-positive rectangle, out-of-canvas geometry, yanlış page order, geçersiz source URL ve eksik reading/source action durumlarında fail-closed davranır.

## 4. Local editorial visual evidence

Üç bundled PNG built-in image generation aracıyla üretildi:

- `mobile/assets/images/city-signals.png` — soyut şehir, gün doğumu ve bilgi akışı;
- `mobile/assets/images/civic-technology.png` — devre izleriyle birleşen insan ölçekli kamusal mimari;
- `mobile/assets/images/climate-resilience.png` — yaprak, su yolu ve yeşil şehir katmanları.

Ortak prompt sınırı: `stylized-concept`, landscape editorial illustration, screen-print/risograph, newspaper halftone/paper grain; no people, no identifiable real event, no documentary scene, no text/logo/brand/watermark. Bu yüzden asset'ler gerçek olay kanıtı gibi davranmaz. Okuma Modu her görseli “AI ile üretilmiş kavramsal editoryal placeholder • Q03 proof” etiketiyle sunar.

## 5. Interaction sözleşmesi

### 5.1 Fixed page surface

Fixture koordinatları responsive card reflow'a çevrilmez. `NewspaperViewport`, logical canvas'ı viewport'a tek fit scale ile yerleştirir; `InteractiveViewer` bu fitted surface üzerinde `1×–4×` transform uygular. Placement ve hit-region koordinatları canvas space'te sabit kalır.

### 5.2 Zoom, pan ve page navigation

- Fit/minimum scale `1×` relative transform'dur.
- Pinch zoom ve zoomed pan `InteractiveViewer` tarafından uygulanır.
- `EditionSession.fitScaleTolerance = 0.01`; current page transform bunun üstündeyken previous/next action disable edilir.
- Görünür `SAYFA n / total` indicator, zoom yüzdesi, navigation availability ve `Sayfayı sığdır` action'ı vardır.
- Her page kendi `TransformationController` nesnesini edition session boyunca korur.

### 5.3 Article ve source actions

- Ordinary article rectangle yalnız `openArticle` ile Okuma Modu'nu açar.
- Source rectangle ayrı, görünür ve accessibility label taşıyan `open_source` target'tır.
- Source launch yalnız explicit target veya Okuma Modu `Kaynağa Git` düğmesinden yapılır.
- Parser yalnız HTTPS canonical source URL kabul eder; embedded browser yoktur.

### 5.4 Shared context

Gazete ve Okuma modları aynı `EditionSession` nesnesini kullanır. Selected article dışında edition ID, current page index ve page controller matrix değişmez. Back action selected article'ı kapatır ve aynı page/viewport'u yeniden gösterir.

## 6. Focused test matrisi

| Issue #10 kanıtı | Test |
|---|---|
| Fixture parse + üç ordered page | `edition_parser_test.dart` |
| Unsupported contract version | `edition_parser_test.dart` |
| Broken article reference | `edition_parser_test.dart` |
| Invalid/out-of-canvas rectangle | `edition_parser_test.dart` |
| Page 1 → 2 → 3 fixture order render | `reader_flow_test.dart` |
| Article hit → Okuma Modu, browser yok | `reader_flow_test.dart` |
| Explicit source action ayrı | `reader_flow_test.dart` |
| Back aynı page/transform | `reader_flow_test.dart` |
| Fit scale navigation enabled | `reader_flow_test.dart` |
| Zoomed navigation disabled | `reader_flow_test.dart` |
| İki pointer pinch + zoomed pan regression | `gesture_navigation_test.dart` |
| Article/source accessibility labels | `reader_flow_test.dart` |
| Deterministic front-page composition | `newspaper_golden_test.dart` + `test/goldens/newspaper_front_page.png` |

Flutter widget golden ortamındaki deterministic Ahem font glyph'leri text geometry'sini blok olarak gösterir. Golden composition/layout regression kanıtıdır; gerçek tipografi/readability kanıtı değildir. Gerçek tipografi cihaz artifact'ında ve owner gate'inde değerlendirilir.

## 7. Offline ve protected boundary kanıtı

- Edition `rootBundle.loadString` ile local JSON'dan yüklenir.
- Görseller yalnız `Image.asset` ile bundled path'lerden yüklenir.
- App source'unda network client, remote fixture, RSS, API, AI provider veya key yoktur.
- External browser yalnız explicit source action sonucu çalışır; core reader source launch olmadan tamamen kullanılabilir.
- Existing Python production source, tests, dependencies, `docs/**`, `archive/**` ve generated legacy output değişmez.
- Q04 production contract/backend işi bu branch'e alınmaz.

## 8. Automated validation ve device gate

Required validation seti:

```text
flutter analyze
flutter test
flutter build apk --debug
git diff --check
```

Windows workspace ve pub cache farklı drive'larda olduğu için Kotlin incremental compiler relative-path cache hatası verdi. `mobile/android/gradle.properties` içinde `kotlin.incremental=false` ile mobile-only deterministic build workaround uygulandı; yeni dependency veya legacy change eklenmedi.

Android acceptance artifact, final PR head'ten tekrar üretilir ve APK SHA-256 ile package/device provenance PR kaydına yazılır. Önceden yetkilendirilmiş cihaz varsa yalnız `com.faliardic.gazete.readerproof` paketi non-destructive update/install ile açılır.

## 9. Fatih real-device acceptance — PENDING

Fatih aşağıdakiler için açık PASS/FAIL vermelidir:

- printed-newspaper feel;
- text ve image readability;
- pinch zoom kararlılığı;
- zoomed pan rahatlığı;
- zoomed durumda accidental page turn olmaması;
- fit scale page navigation;
- article tap doğruluğu;
- source action açıklığı;
- Okuma Modu okunabilirliği;
- back sonrası page/viewport restoration.

Automated ve device-install kanıtı bu kararı infer etmez. Owner acceptance PENDING veya FAIL iken PR Draft kalır.
