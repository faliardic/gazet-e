# Changelog

## Unreleased — Mobile V2 bootstrap

- 8 Eylül 2026 owner product reset'i O-011/O-012/O-013 olarak truth-sync edildi. Product runtime'dan AI summary/verifier/repair/dek/reading-body kaldırılacak; text-AI çağrısı ve maliyeti sıfır olacak, AI yalnız editorial image generation ile image safety/QA için kullanılacak. Okuma Modu source headline, varsa bounded source/feed excerpt, publication/source, AI visual ve `Kaynağa Git` sunacak; eksik excerpt üretilmeyecek ve bu mod reklam içermeyecek. Gazete Modu versioned `350 mm × 500 mm` fixed physical page kullanacak; Q10 yalnız local/synthetic inventory ile sayfa başına en fazla bir, alanın en fazla `%15`ini kullanan, açık `REKLAM` etiketli ve editorial/hit/gesture alanlarından ayrılmış reklam slotunu kanıtlayacak. Gerçek ad serving/targeting/tracking/billing Q14 ve Q13 gate'lerinde kalıyor.
- Q10'un `39de1ae44784b77fca821fe9b161d5a188c35096` head'indeki ilk Gate A implementation'ı ve izole PostgreSQL/fake-provider test kanıtı tarihseldir; Q07 AI-summary runtime bağlantısı nedeniyle yeni owner direction tarafından supersede edilmiştir. Production/test kodu bu truth-sync'te değiştirilmedi; controlled lifecycle/schema/physical-page/ad revision'ı ve bağımsız review yeniden gereklidir. Q10 `ACTIVE`, Q11 `QUEUED` kalır.
- Q09 pure Python newspaper layout engine tarihsel olarak versioned `1000×1414 logical` canvas/templates, deterministic rank/tie packing, visual-required hero/secondary ve text-only brief hierarchy, explicit reading/source hit regions, continuation capacity ile gerçek page-limit'i ayıran structured overflow, fail-closed plan identity/page-limit validation, Q04-compatible page projection ve exact layout cache identity ile tamamlandı. `350×500 mm` physical page ve ad-slot gereksinimleri Q09 geçmişini yeniden yazmadan current Q10 revision'ına taşındı.
- Q08 AI visual editor pipeline; deterministic fact-grounded brief/safety classification, exact OpenAI Image API generation contract, local WebP/hash validation, bounded Terra semantic QA, fail-closed in-memory artifact ve exact-key success cache ile tamamlandı ve aktif product runtime'ın tek AI generation/QA hattı olarak kaldı. Türkçe sensitive-event classifier sınırı konservatif çekim eşleşmeleriyle güçlendirildi; sensitive v2 brief/QA ve v3 generation-prompt sözleşmesi aynı bounded conceptual intent ve versioned cache identity üzerinde hizalandı. Exact production revision `0ca86a51bbfa328deed880a88da687930451de61` iki senaryolu live gate'i 4 çağrı, 2 WebP görsel ve tahmini USD 0.092670 ile PASS verdi.
- Q07 source-grounded OpenAI editorial-summary pipeline tarihsel olarak bounded Q06 fact packet, strict structured generation/verifier contracts, local validation, exact-key cache, one-repair ceiling ve safe unavailable fallback ile tamamlandı. Gerçek OpenAI live-provider gate `gpt-5.6-terra` ile 2 çağrı, 1.076 input token, 194 output token ve tahmini USD 0.00448 maliyetle `ready` / `passed` sonucu verdi. O-011 sonrasında Q07 `RETIRED/SUPERSEDED` durumundadır; implementation/test/live evidence silinmez fakat product runtime bu yolu çağırmaz.
- Q06 live-news katmanı; dört publisher family için bounded static-HTTPS RSS adapter'ı, stable article/content identity, structured quality reasons, exact dedupe, conservative cross-source clustering ve versioned deterministic ranking ile tamamlandı.
- Q05 on-demand edition job service; FastAPI API, direct psycopg PostgreSQL persistence, idempotency, lease/heartbeat/checkpoint recovery, bounded retry, safe cancellation, injected worker stages ve immutable validated edition publication ile tamamlandı.
- `gazet-e.edition.v1` backend→mobile contract'ı technology-neutral JSON Schema, fail-closed Dart parser/serializer, production-shape fixture, external fixture asset resolver ve regression matrisiyle kanonikleştirildi.
- Q03 Flutter reader proof; üç sayfalı bundled fixture, fixed newspaper canvas, pinch/pan, fit-scale navigation, explicit article/source hit regions, Okuma Modu ve deterministic golden ile offline olarak tamamlandı.
- GitHub repository'si 7 Eylül 2026 owner kararıyla kalıcı olarak `faliardic/gazet-e` adına taşındı; `chatgpt_haber` namespace'i ve `chatgpt-haber` CLI uyumluluk adları değişmeden korundu.
- v1.1 RSS, filtering, identity/dedupe, issue, render/layout, image, timing/cache, Windows ve GitHub Pages sınırları read-only source audit ile sınıflandırıldı.
- Mobile V2 için Flutter client ile Python FastAPI + PostgreSQL durable worker sınırı seçildi; versioned interactive edition contract ve reuse/replace matrisi kanonikleştirildi.
- Q03 reader proof'ünün live RSS/AI/backend öncesinde bundled fixture ve local asset'lerle offline kalması zorunlu gate olarak korundu.
- Canonical public/product marka `Gazet+E`, masthead/wordmark gösterimi `GAZET+E` olarak kesinleştirildi.
- Aktif v1.1 UI, render, prompt ve sample defaults yeni markaya truth-sync edildi; package/CLI uyumluluk adları ile tarihsel yayın kanıtları korundu.
- Repository, v1.1 legacy baseline korunarak Mobile V2 aktif geliştirmesine yeniden açıldı.
- CSE tarzı GitHub-first çalışma otoritesi için `AGENTS.md` ve kanonik `ROADMAP.md` eklendi.
- V2 ürün kapsamı ve kalıcı owner kararları `project_docs/` altında kanonikleştirildi.
- V2'nin ana hareketi on-demand `Gazetemi Hazırla` edition üretimi olarak belirlendi.
- İki primary reading mode donduruldu: `Gazete Modu` ve `Okuma Modu`.
- Klasik basılı gazete sayfası, pinch-zoom/pan/page navigation ve interaktif story regions ürün çekirdeği olarak kaydedildi.
- Görünür V2 haber görsellerinin AI-generated by default olması kararlaştırıldı; hassas gerçek olaylarda fake documentary evidence üretilmemesi product boundary olarak eklendi.
- Original source erişimi ve attribution zorunlu edition contract alanı olarak belirlendi.
- `docs/` klasörünün GitHub Pages publication output olduğu netleştirildi; governance dokümantasyonu `project_docs/` altına ayrıldı.
- İlk teknik adım olarak mevcut v1.1 motorunun reuse/replace ve mobile/backend boundary audit'i sıraya alındı.
- Bu bootstrap'ta production source, test, dependency, generated newspaper output veya release artifact değiştirilmedi.

## 1.1.0 - 2026-07-12

- Gazetenin görünür adı ChatGPT Gazette olarak güncellendi.
- Üst bant mavi, beyaz ve kırmızı renk geçişleriyle yeniden tasarlandı.
- Güvenilir, Hızlı, Tarafsız sloganı ve eski dekoratif bant unsurları kaldırıldı.
- Haber görselleri başlıklarla aynı bağlantıya bağlandı.
- Haber detay çıkarma sistemi güçlendirildi.
- Sağ haber listesi internal detay sayfalarına bağlandı.
- Haber kartları ve detay sayfalarındaki alt kaynak yazıları kaldırıldı.
- Kaynak erişimi detay üstündeki KAYNAĞI AÇ bağlantısında korundu.
- Windows tek-tıklama OptionInfo hatası düzeltildi.

## 1.0.0 - 2026-07-12

- Üç sayfalık Türkçe gazete tamamlandı.
- Manşet, gündem-ekonomi ve teknoloji sayfaları son hâline getirildi.
- RSS toplama ve editoryal filtreleme akışı tamamlandı.
- Fast/full build modları eklendi ve doğrulandı.
- PDF içi haber detayları ve `GAZETEYE DÖNÜŞ` bağlantıları korundu.
- Statik web gazetesi üretimi eklendi.
- PDF indirme ve tarih arşivi eklendi.
- Windows Gazette Studio doğrulandı.
- Timing ölçümleri eklendi.
- Hedef odaklı hızlı cleanup tamamlandı.
- Proje bakım moduna alındı.
