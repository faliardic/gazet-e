# GV2-006 — Q05 On-Demand Edition Job Service

**Durum:** Q05 implementation contract

**Lane:** STANDARD

**Kapsam:** FastAPI + direct psycopg + PostgreSQL durable job metadata + ayrı
Python worker

## 1. Amaç ve sınır

Bu slice, `Gazetemi Hazırla` isteğinin kaybolmayan ve gözlemlenebilir server
lifecycle'ını kurar. API yalnız istek, durum, cancellation ve hazır canonical
edition kaynaklarını sunar. Ayrı worker, PostgreSQL lease'i altında yalnız
inject edilmiş stage executor'larını çağırır.

Q05 stage içeriklerini üretmez. Production/default kodda canlı RSS, gerçek
dedupe/ranking, AI summary, AI image ve layout engine yoktur. Deterministik
canonical Q04 fixture'ı yalnız test executor'ı çıktısıdır.

## 2. HTTP sözleşmesi

### `POST /v1/edition-jobs`

- Zorunlu, görünür ASCII ve en fazla 128 karakter `Idempotency-Key` alır.
- Body yalnız `request_version`, `locale` ve `timezone` alanlarını kabul eder.
- Desteklenen request version `gazet-e.edition-request.v1`dir.
- Yeni logical job için `202`; aynı key + aynı normalize request için aynı job
  ve yine `202` döner.
- Aynı key + farklı request `409`; eksik/geçersiz header veya body `422` olur.
- Ham idempotency key saklanmaz ve dönülmez; SHA-256 identity ile request
  fingerprint saklanır.

### `GET /v1/edition-jobs/{job_id}`

Durable `state`, `stage`, `attempt`, oluşturma/güncelleme/checkpoint zamanları,
varsa cancellation veya güvenli failure bilgisi ve yalnız `ready` sonrasında
`edition_id` döner. Tahminî yüzde/progress üretilmez. Bilinmeyen job `404`tür.

### `POST /v1/edition-jobs/{job_id}/cancel`

İdempotenttir. `requested` doğrudan `cancelled` olur. Aktif stage cancellation
intent'i kaydeder; worker güvenli checkpoint'e gelince `cancelled` terminal
durumu ve effective timestamp atomik kaydedilir. `ready`, `failed` ve
`cancelled` yeniden sınıflandırılmaz.

### `GET /v1/editions/{edition_id}`

Yalnız server-side schema + cross-invariant doğrulamasından geçmiş immutable
`gazet-e.edition.v1` document döner. Bilinmeyen edition `404`tür; job status
ayrı kaynak kalır.

## 3. Durable lifecycle

Normal sıra tam olarak şöyledir:

```text
requested -> collecting -> selecting -> summarizing
          -> illustrating -> laying_out -> ready
```

Terminal olmayan her durum güvenli kurallarla `failed` veya `cancelled`
olabilir. Skipped/backward transition fail-closed olur. Retryable failure
yalnız internal, explicit requeue helper ile ve varsayılan üç attempt sınırı
içinde `requested` durumuna dönebilir. Public retry endpoint yoktur;
non-retryable veya attempt sınırındaki failure terminaldir.

Cancellation failure değildir. `cancellation_requested_at` intent'i,
`cancellation_effective_at` ise checkpoint'te tamamlanan terminal gerçeği
ifade eder.

## 4. PostgreSQL concurrency ve recovery

Store doğrudan psycopg ve explicit SQL kullanır. İki idempotent,
non-destructive tablo oluşturur:

- `edition_jobs`: request identity/body, lifecycle, attempt, checkpoint,
  lease/heartbeat, cancellation, safe failure ve sonuç edition kimliği;
- `editions`: edition kimliği, contract version, canonical JSONB, canonical
  SHA-256 ve publication timestamp.

Worker claim transaction'ı runnable satırları sıraya koyar ve
`FOR UPDATE SKIP LOCKED` kullanır. Canlı lease ikinci worker'a verilmez.
Heartbeat yalnız aynı worker'ın canlı lease'ini uzatır. Worker, executor
çalıştığı sürece lease süresinin üçte biri ve en fazla beş saniyelik aralıkla
ayrı bağlantı üzerinden heartbeat gönderir. Executor bittiğinde keepalive
thread'i deterministik olarak durdurulup join edilir. Ownership kaybı veya
heartbeat hatasında eski worker checkpoint, failure ya da publication mutation
yapmadan fail-closed durur. Lease süresi gerçekten dolunca başka worker aynı
logical job ve son durable stage/checkpoint'i artan attempt ile devralabilir;
yeni job yaratılmaz.

Stage tamamlanması, sonraki stage'e geçiş ve lease yenileme tek DB transaction
içindedir. Cancellation intent'i varsa aynı checkpoint işlemi ilerlemek yerine
terminal cancellation kaydeder. Process kaybı halinde son commit edilmiş stage
yeniden çalışabilir; bu nedenle gelecekteki Q06–Q09 executor'ları job/stage
kimliğiyle idempotent tasarlanmalıdır.

## 5. Worker/executor sınırı

`EditionJobWorker.run_one()` en eski runnable job'ı claim eder ve o job'ı
terminal sonuca kadar sürer. Her stage çağrısından önce lease heartbeat yapılır.
Executor mapping constructor ile zorunlu olarak inject edilir; eksik executor
safe non-retryable failure üretir.

Stage exception'larının ham metni response, durable diagnostic veya log
contract'ına taşınmaz. Tanımlı stage failure yalnız bounded code, retryable
truth ve güvenli diagnostic taşır. Failure transaction'ı aynı row lock altında
cancellation intent'ini önce kontrol eder; intent varsa declared veya unexpected
executor failure yerine `cancelled` checkpoint'i commit edilir. Son
`laying_out` executor'ı JSON object döndürmelidir; production kod fixture veya
edition uydurmaz.

## 6. Canonical edition publication

Publication öncesinde mevcut Draft 2020-12 schema format checking ile çalışır.
Ek validation şunları fail-closed uygular:

- edition time sırası ve canonical JSON/finite-number yeterliliği;
- unique article/page/order/placement/hit/source kimlikleri;
- article, primary source ve placement referential integrity;
- safe canonical HTTPS source URL;
- deterministic page order ve canvas içinde rectangles;
- her placement için ayrı `open_reading` ve `open_source` action;
- secret, raw prompt/body ve private/local asset locator yasağı.

Invalid document onarılmaz veya enrich edilmez; job güvenli biçimde fail olur.
Doğrulama, immutable edition insert ve job'ın `ready` olması aynı transaction
içindedir. Aynı `edition_id` ile farklı canonical content yayınlamak reddedilir.

## 7. Güvenlik ve operasyon sınırı

Q05 auth, account, payment, CORS, public deployment, object storage veya
production database kararı vermez. Provider secret/API key client'a, request'e,
DB diagnostic'e veya response'a girmez. DSN yalnız process environment'tan
alınır; `.env.example` gerçek credential içermez.

Local integration gate için kullanılan database disposable ve local-only
olmalıdır. Test suite `GAZETE_TEST_POSTGRES_DSN` yoksa veya beklenen dedicated
`gazete_q05_test` database/role ve loopback server identity doğrulanmazsa skip
etmez, fail olur.

## 8. Q05 doğrulama kanıtı

Focused matris request/version validation, idempotency reuse/conflict,
durability, lifecycle whitelist, truthful status, cancellation checkpoint,
terminal stability, live lease ownership, heartbeat, iki-worker
`SKIP LOCKED`, expired lease recovery, bounded retry, safe diagnostic,
injected stage sırası, canonical publication/fetch, invalid publication ve
edition immutability davranışlarını gerçek PostgreSQL üzerinde kapsar.

Q06–Q09 execution'ı, mobil client bağlantısı ve production deployment sonraki
ayrı authority kapsamlarıdır.
