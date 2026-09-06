# Yaşam Döngüsü ve Bakım Politikası

## v1.1 legacy

`v1.1.0` mevcut Python/PDF/static-web Gazette sisteminin tamamlanmış ve stabil legacy baseline'ıdır.

Legacy v1.1 için kabul edilen değişiklikler:

- kritik bug düzeltmeleri;
- bozuk RSS kaynağı düzeltmeleri;
- güvenlik sorunları;
- işletim sistemi veya bağımlılık uyumluluk hataları;
- GitHub Pages yayın hataları;
- V2 architecture audit'inin açıkça yetkilendirdiği dar compatibility/reuse değişiklikleri.

Legacy v1.1, Mobile V2 başlatıldı diye toplu olarak silinmez veya yeniden yazılmaz.

## Mobile V2 aktif geliştirme

6 Eylül 2026 owner kararıyla repository yeniden aktif ürün geliştirmesine alınmıştır.

Mobile V2 çalışmaları:

- `AGENTS.md` çalışma kurallarına;
- `ROADMAP.md` kanonik queue'suna;
- `project_docs/v2/GAZETTE_MOBILE_V2_SCOPE.md` ürün kapsamına;
- `project_docs/protocols/GAZETTE_UNIFIED_PROJECT_SOURCE.md` kalıcı owner kararlarına

uyar.

V2 için yeni mobile client, backend/service, AI summary/image pipeline, interactive layout, personalization ve commercial/release işleri yalnız ilgili roadmap Issue/gate kapsamında yapılır.

## Generated docs sınırı

Repository kökündeki `docs/` klasörü GitHub Pages publication output alanıdır. Governance/protocol dokümanları burada tutulmaz; `project_docs/` kullanılır.

## Koruma ilkesi

Bir V2 işi legacy v1.1 behavior'ı değiştirmeyi gerektiriyorsa değişiklik issue scope'unda açıkça belirtilir, minimum compatibility doğrulaması yapılır ve sessiz regression kabul edilmez.
