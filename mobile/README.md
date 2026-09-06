# Gazet+E static reader proof

Bu Flutter uygulaması Issue #10 / Q03 için izole edilmiş offline reader kanıtıdır. Final store uygulaması veya production contract değildir.

## Sınır

- Platformlar: Android ve iOS.
- Provisional application ID: `com.faliardic.gazete.readerproof`.
- Runtime dependencies: Flutter SDK ve `url_launcher`.
- Edition: `assets/fixtures/edition.json` içindeki bundled `gazet-e.edition.v1` fixture.
- Görseller: bundled kavramsal/editoryal placeholder PNG'leri.
- Network/news/backend/AI provider, database, analytics, auth ve embedded WebView yoktur.

`url_launcher` yalnız açık `Kaynağa Git` eyleminde fixture'daki canonical HTTPS URL'yi sistem tarayıcısına göndermek için kullanılır. Normal article tap yalnız Okuma Modu'nu açar.

## Doğrulama

```powershell
flutter analyze
flutter test
flutter build apk --debug
```

Golden kanıtı `test/goldens/newspaper_front_page.png` dosyasıdır. Golden yalnız kasıtlı görsel değişiklikte şu focused komutla yeniden üretilir:

```powershell
flutter test --update-goldens test/newspaper_golden_test.dart
```

Automated PASS gerçek cihaz gesture/readability kabulü değildir. Q03 merge öncesi Fatih'in pinch, zoomed pan, page navigation, hit target, Okuma Modu ve context restoration için manuel PASS vermesi gerekir.
