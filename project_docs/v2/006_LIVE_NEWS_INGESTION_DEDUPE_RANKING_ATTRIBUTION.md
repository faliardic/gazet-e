# GV2-007 — Q06 Live News Ingestion, Dedupe, Ranking and Attribution

**Durum:** Q06 implementation contract

**Lane:** STANDARD

**Kapsam:** Static HTTPS RSS registry, bounded collection, stable identity,
structured quality, deterministic clustering/ranking ve source attribution

## 1. Sonuç ve sınır

Q06, dört RSS publisher family'den gelen feed item'larını daha sonraki
Q07–Q10 stage'leri için immutable, açıklanabilir ve duplicate-reduced ranked
collection'a dönüştürür. Yeni runtime sınırı yalnız
`services/edition_news_*.py` modülleridir; legacy `sources.py` V2 adapter'ı
değildir.

Bu katman Q04 edition document üretmez ve Q05 worker/store/API'ye bağlanmaz.
Publisher article page/body/image scraping, ANKA HTML, AI/LLM, AI image,
layout, mobile, personalization ve commercial-rights iddiası yoktur.

## 2. Versioned static registry

Registry version `gazet-e.rss-registry.v1`dir. Her kayıt stable publisher/source
ID, display name, family, section ve explicit HTTPS feed URL taşır.

- NTV: Türkiye, Dünya, Ekonomi, Teknoloji, Spor
- Habertürk: Gündem, Dünya, Ekonomi, Spor, Teknoloji
- Sözcü: Gündem, Dünya, Ekonomi, Spor, Bilim Teknoloji
- Evrim Ağacı: Bilim/Teknoloji

Registry dışında user-supplied URL alan collection API'si yoktur. ANKA veya
publisher page URL'si registry'ye girmez.

## 3. Bounded RSS network contract

Production collector:

- identifiable `Gazet+E/2.0` user-agent kullanır;
- connect/read timeout'u sırasıyla 3/7 saniyeyle sınırlar;
- transient network, 429 ve 5xx için en fazla iki attempt ve bounded backoff
  uygular;
- redirect sayısını beşle sınırlar ve bütün redirect/final URL'lerde HTTPS
  ister;
- response'u streaming olarak en fazla 2 MiB okur;
- feed başına en fazla 30 item normalize eder;
- `feedparser.parse()` fonksiyonuna URL değil fetched bytes verir;
- bir feed failure'ını safe status/diagnostic olarak kaydeder ve diğer feed'lere
  devam eder.

Fetch result source ID, publisher ID, fetch time, success/status, HTTP status,
candidate/rejected-item count ve bounded diagnostic taşır. Raw exception,
credential, raw feed veya full publisher body saklanmaz.

## 4. Candidate ve attribution contract'ı

Her candidate:

- `article_id` ve `content_version`;
- normalized canonical HTTPS article URL;
- en çok 300 karakter feed headline;
- en çok 1200 karakter internal feed excerpt;
- varsa timezone-aware publication timestamp;
- collection timestamp;
- publisher/source/display/section/feed attribution;
- versioned structured quality ve ranking breakdown

taşır. Feed excerpt Q07 input adayıdır; user-facing full publisher-body
republication değildir. Image URL, local asset path, body, prompt veya provider
alanı modelde yoktur.

## 5. URL, article ve content identity

Canonical URL normalization:

- yalnız HTTPS kabul eder;
- hostname'i lowercase yapar ve default `:443` portunu kaldırır;
- fragment'i siler;
- `utm_*`, `fbclid`, `gclid`, `dclid`, `msclkid`, `igshid` ve bilinen campaign
  parametrelerini çıkarır;
- meaningful query parametrelerini key/value sırasıyla deterministik korur;
- malformed, credential-bearing veya non-HTTPS URL'yi fail-closed reddeder.

Article identity exact owner formülüdür:

```text
SHA-256("article-id.v1" + publisher_id + normalized_canonical_url)
```

Content version, version tag'i + article ID + normalized headline + bounded
excerpt + publication timestamp birleşiminin SHA-256 değeridir. Feed fact
değişikliği content version'ı değiştirir; article ID'yi değiştirmez.

## 6. Quality ve exact dedupe

Quality policy `gazet-e.quality.v1`dir. Mevcut pure hard-reject bilgisi kopya
candidate view üzerinde uygulanır ve mutation/print yerine immutable
`accepted + reason_codes` contract'ına çevrilir. Rejected candidate audit için
çıktıda kalır fakat ranked article veya cluster'a giremez.

Aynı publisher + aynı normalized URL tek article identity'dir. Birden fazla
content version görüldüğünde publication time ve content hash ile deterministik
latest version seçilir. Başlık benzerliği exact dedupe veya identity merge
sebebi değildir.

## 7. Cross-source clustering

Cluster policy `gazet-e.story-cluster.v1`dir. Yalnız farklı publisher
article'ları şu conservative sinyallerle aynı story cluster'a alınabilir:

- aynı section;
- publication time varsa en fazla 36 saat uzaklık;
- stop-word çıkarılmış headline token'larında en az üç meaningful ortak token;
- minimum 0.60 containment ve 0.40 Jaccard similarity.

Generic title'lar minimum meaningful-token şartını geçmeden birleşmez. Article
identity'ler cluster içinde ayrı kalır. Cluster ID, policy version + sıralı
member article ID'lerinin SHA-256 değeridir. Member/cluster sırası ve lead
seçimi score, publication time ve article-ID tie-break'leriyle deterministiktir.

## 8. Deterministic ranking

Ranking policy `gazet-e.news-ranking.v1`dir. Yalnız şu bounded sinyaller vardır:

- base;
- injected clock'a göre recency bucket;
- publisher baseline;
- section importance;
- bounded headline/topic signal;
- cluster seviyesinde source-diversity evidence.

Her article `base`, `recency`, `publisher`, `section`, `headline_topic` ve
`total` breakdown'ı taşır. Her cluster lead score, diversity bonus ve total
taşır. User profile/AppData, image availability, AI scoring, layout rolü veya
network sırası ranking'i etkilemez.

## 9. Validation ve live gate

Deterministik test matrisi registry/network bounds, isolated feed failure,
attribution, URL failure/normalization, article/content identity, exact dedupe,
cross-source/generic clustering, deterministic cluster/lead, structured reject,
ranking/recency breakdown, forbidden signals/fields ve Q05/AI/scraping
izolasyonunu kapsar.

Live gate production adapter'ı yalnız static registry üzerinde çalıştırır ve
raw feed/body artifact yazmaz. Gate'in kapanması için aynı run'da en az iki
publisher family parseable candidate üretmeli; aksi durumda Q06 PENDING kalır.

Q07 summary, Q08 image, Q09 layout ve Q10 job/mobile wiring ayrı authority
kapsamlarıdır.
