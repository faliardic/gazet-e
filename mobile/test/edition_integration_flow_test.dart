import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:readerproof/edition.dart';
import 'package:readerproof/edition_generation_controller.dart';
import 'package:readerproof/edition_job_api_client.dart';

void main() {
  test(
    'one request tracks the real lifecycle and opens the ready edition',
    () async {
      final edition = await _fixture();
      final gateway = _FakeGateway(
        statuses: [
          _status(RemoteJobState.requested),
          _status(RemoteJobState.summarizing),
          _status(RemoteJobState.ready, editionId: edition.edition.id),
        ],
        edition: edition,
      );
      final controller = EditionGenerationController(
        gateway: gateway,
        delay: (_) async {},
        idempotencyKeyFactory: () => 'stable-mobile-key',
      );

      await controller.prepare();

      expect(controller.state, EditionGenerationState.ready);
      expect(controller.edition, same(edition));
      expect(gateway.createCalls, 1);
      expect(gateway.keys, ['stable-mobile-key']);
      expect(gateway.getCalls, 2);
      expect(gateway.loadCalls, 1);
      expect(gateway.reportCalls, 1);
    },
  );

  test('concurrent taps cannot create duplicate jobs', () async {
    final edition = await _fixture();
    final pending = Completer<RemoteJobStatus>();
    final gateway = _FakeGateway(
      statuses: [],
      edition: edition,
      pendingCreate: pending,
    );
    final controller = EditionGenerationController(
      gateway: gateway,
      delay: (_) async {},
      idempotencyKeyFactory: () => 'one-key',
    );
    addTearDown(controller.dispose);

    final first = controller.prepare();
    final second = controller.prepare();
    expect(gateway.createCalls, 1);
    pending.complete(
      _status(RemoteJobState.ready, editionId: edition.edition.id),
    );
    await Future.wait([first, second]);

    expect(gateway.createCalls, 1);
    expect(controller.state, EditionGenerationState.ready);
  });

  test('ambiguous create retry reuses the original idempotency key', () async {
    final edition = await _fixture();
    final gateway = _FakeGateway(
      statuses: [_status(RemoteJobState.ready, editionId: edition.edition.id)],
      edition: edition,
      createFailures: 1,
    );
    final controller = EditionGenerationController(
      gateway: gateway,
      delay: (_) async {},
      idempotencyKeyFactory: () => 'ambiguous-key',
    );

    await controller.prepare();
    expect(controller.state, EditionGenerationState.failed);
    await controller.prepare();

    expect(controller.state, EditionGenerationState.ready);
    expect(gateway.keys, ['ambiguous-key', 'ambiguous-key']);
  });

  test(
    'cancellation invalidates stale polling and reaches cancelled',
    () async {
      final edition = await _fixture();
      final pollingDelay = Completer<void>();
      final gateway = _FakeGateway(
        statuses: [_status(RemoteJobState.requested)],
        edition: edition,
        cancelStatus: _status(RemoteJobState.cancelled),
      );
      final controller = EditionGenerationController(
        gateway: gateway,
        delay: (_) => pollingDelay.future,
        idempotencyKeyFactory: () => 'cancel-key',
      );

      final preparing = controller.prepare();
      await Future<void>.delayed(Duration.zero);
      expect(controller.state, EditionGenerationState.tracking);
      await controller.cancel();
      expect(controller.state, EditionGenerationState.cancelled);
      pollingDelay.complete();
      await preparing;

      expect(gateway.cancelCalls, 1);
      expect(gateway.getCalls, 0);
      expect(controller.edition, isNull);
    },
  );

  test(
    'restored job identity resumes without creating a new request',
    () async {
      final edition = await _fixture();
      final gateway = _FakeGateway(
        statuses: [
          _status(RemoteJobState.layingOut),
          _status(RemoteJobState.ready, editionId: edition.edition.id),
        ],
        edition: edition,
      );
      final controller = EditionGenerationController(
        gateway: gateway,
        delay: (_) async {},
      );

      await controller.resume(jobId: 'job-1', idempotencyKey: 'restored-key');

      expect(controller.state, EditionGenerationState.ready);
      expect(controller.idempotencyKey, 'restored-key');
      expect(gateway.createCalls, 0);
      expect(gateway.getCalls, 2);
    },
  );

  test(
    'HTTP asset path verifies SHA, dimensions, and keeps bytes out of JSON',
    () async {
      final webp = base64Decode(
        'UklGRiQAAABXRUJQVlA4IBgAAAAwAQCdASoCAAIAAUAmJaQAA3AA/v0gUAA=',
      );
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      addTearDown(server.close);
      final fixture =
          jsonDecode(await File('assets/fixtures/edition.json').readAsString())
              as Map<String, Object?>;
      const hash =
          'sha256:c5e8a8c2bb2f1d7b845abcbd3b215589114f636d8eaf3b4261213d8951c4fdf4';
      final servedAsset = List<int>.of(webp);
      for (final article in fixture['articles']! as List<Object?>) {
        final visual =
            (article! as Map<String, Object?>)['visual']!
                as Map<String, Object?>;
        visual['asset_id'] = hash;
        visual['content_hash'] = hash;
        visual['width'] = 2;
        visual['height'] = 2;
      }
      server.listen((request) async {
        if (request.uri.path.contains('/assets/')) {
          request.response.headers.contentType = ContentType('image', 'webp');
          request.response.add(servedAsset);
        } else {
          request.response.headers.contentType = ContentType.json;
          request.response.write(jsonEncode(fixture));
        }
        await request.response.close();
      });
      final gateway = HttpEditionJobGateway(
        origin: Uri.parse('http://127.0.0.1:${server.port}'),
        allowDebugLoopback: true,
      );

      final document = await gateway.loadReadyEdition('edition-id');

      expect(document.articles.values.first.visual.assetBytes, webp);
      expect(jsonEncode(document.toJson()), isNot(contains('image_bytes')));
      expect(
        jsonEncode(document.toJson()),
        isNot(contains(base64Encode(webp))),
      );
      servedAsset[servedAsset.length - 1] ^= 1;
      await expectLater(
        gateway.loadReadyEdition('edition-id'),
        throwsFormatException,
      );
    },
  );

  test('HTTP origin rejects public cleartext and user-info', () {
    expect(
      () => HttpEditionJobGateway(origin: Uri.parse('http://example.test')),
      throwsArgumentError,
    );
    expect(
      () =>
          HttpEditionJobGateway(origin: Uri.parse('https://user@example.test')),
      throwsArgumentError,
    );
  });
}

final class _FakeGateway implements EditionJobGateway {
  _FakeGateway({
    required List<RemoteJobStatus> statuses,
    required this.edition,
    this.pendingCreate,
    this.createFailures = 0,
    RemoteJobStatus? cancelStatus,
  }) : statuses = List.of(statuses),
       cancelStatus = cancelStatus ?? _status(RemoteJobState.cancelled);

  final List<RemoteJobStatus> statuses;
  final EditionDocument edition;
  final Completer<RemoteJobStatus>? pendingCreate;
  final RemoteJobStatus cancelStatus;
  int createFailures;
  int createCalls = 0;
  int getCalls = 0;
  int cancelCalls = 0;
  int loadCalls = 0;
  int reportCalls = 0;
  final List<String> keys = [];

  @override
  Future<RemoteJobStatus> createJob({
    required String idempotencyKey,
    required String locale,
    required String timezone,
  }) async {
    createCalls++;
    keys.add(idempotencyKey);
    if (createFailures > 0) {
      createFailures--;
      throw const HttpException('ambiguous transport failure');
    }
    final pending = pendingCreate;
    if (pending != null) {
      return pending.future;
    }
    return statuses.removeAt(0);
  }

  @override
  Future<RemoteJobStatus> getJob(String jobId) async {
    getCalls++;
    return statuses.removeAt(0);
  }

  @override
  Future<RemoteJobStatus> cancelJob(String jobId) async {
    cancelCalls++;
    return cancelStatus;
  }

  @override
  Future<EditionDocument> loadReadyEdition(String editionId) async {
    loadCalls++;
    return edition;
  }

  @override
  Future<bool> isReducedEdition(String jobId) async {
    reportCalls++;
    return false;
  }
}

RemoteJobStatus _status(RemoteJobState state, {String? editionId}) =>
    RemoteJobStatus(
      jobId: 'job-1',
      state: state,
      editionId: editionId,
      failureCode: null,
    );

Future<EditionDocument> _fixture() async => EditionDocument.parse(
  await File('assets/fixtures/edition.json').readAsString(),
  assetResolver: (assetId) => switch (assetId) {
    'asset_city_signals' => 'assets/images/city-signals.png',
    'asset_climate_resilience' => 'assets/images/climate-resilience.png',
    'asset_civic_technology' => 'assets/images/civic-technology.png',
    _ => null,
  },
);
