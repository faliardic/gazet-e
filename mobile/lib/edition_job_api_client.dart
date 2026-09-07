import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:crypto/crypto.dart';

import 'edition.dart';

const _maxJsonBytes = 2 * 1024 * 1024;
const _maxAssetBytes = 8 * 1024 * 1024;

enum RemoteJobState {
  requested,
  collecting,
  selecting,
  summarizing,
  illustrating,
  layingOut,
  ready,
  failed,
  cancelled,
}

final class RemoteJobStatus {
  const RemoteJobStatus({
    required this.jobId,
    required this.state,
    required this.editionId,
    required this.failureCode,
  });

  final String jobId;
  final RemoteJobState state;
  final String? editionId;
  final String? failureCode;

  bool get terminal => switch (state) {
    RemoteJobState.ready ||
    RemoteJobState.failed ||
    RemoteJobState.cancelled => true,
    _ => false,
  };

  factory RemoteJobStatus.fromJson(Map<String, Object?> json) {
    final stateText = json['state'];
    final jobId = json['job_id'];
    if (stateText is! String || jobId is! String || jobId.isEmpty) {
      throw const FormatException('Edition job response is malformed.');
    }
    final state = switch (stateText) {
      'requested' => RemoteJobState.requested,
      'collecting' => RemoteJobState.collecting,
      'selecting' => RemoteJobState.selecting,
      'summarizing' => RemoteJobState.summarizing,
      'illustrating' => RemoteJobState.illustrating,
      'laying_out' => RemoteJobState.layingOut,
      'ready' => RemoteJobState.ready,
      'failed' => RemoteJobState.failed,
      'cancelled' => RemoteJobState.cancelled,
      _ => throw const FormatException('Edition job state is unsupported.'),
    };
    final editionId = json['edition_id'];
    final failure = json['failure'];
    String? failureCode;
    if (failure is Map<String, Object?>) {
      final value = failure['code'];
      failureCode = value is String ? value : null;
    }
    if (state == RemoteJobState.ready && editionId is! String) {
      throw const FormatException('Ready job lacks an edition identity.');
    }
    return RemoteJobStatus(
      jobId: jobId,
      state: state,
      editionId: editionId is String ? editionId : null,
      failureCode: failureCode,
    );
  }
}

abstract interface class EditionJobGateway {
  Future<RemoteJobStatus> createJob({
    required String idempotencyKey,
    required String locale,
    required String timezone,
  });

  Future<RemoteJobStatus> getJob(String jobId);
  Future<RemoteJobStatus> cancelJob(String jobId);
  Future<EditionDocument> loadReadyEdition(String editionId);
  Future<bool> isReducedEdition(String jobId);
}

final class HttpEditionJobGateway implements EditionJobGateway {
  HttpEditionJobGateway({
    required Uri origin,
    bool allowDebugLoopback = false,
    HttpClient? client,
  }) : _origin = _validateOrigin(origin, allowDebugLoopback),
       _client = client ?? HttpClient();

  final Uri _origin;
  final HttpClient _client;

  @override
  Future<RemoteJobStatus> createJob({
    required String idempotencyKey,
    required String locale,
    required String timezone,
  }) async {
    final response = await _json(
      'POST',
      '/v1/edition-jobs',
      expectedStatuses: const {202},
      headers: {'Idempotency-Key': idempotencyKey},
      body: {
        'request_version': 'gazet-e.edition-request.v1',
        'locale': locale,
        'timezone': timezone,
      },
    );
    return RemoteJobStatus.fromJson(response);
  }

  @override
  Future<RemoteJobStatus> getJob(String jobId) async =>
      RemoteJobStatus.fromJson(
        await _json(
          'GET',
          '/v1/edition-jobs/${Uri.encodeComponent(jobId)}',
          expectedStatuses: const {200},
        ),
      );

  @override
  Future<RemoteJobStatus> cancelJob(String jobId) async =>
      RemoteJobStatus.fromJson(
        await _json(
          'POST',
          '/v1/edition-jobs/${Uri.encodeComponent(jobId)}/cancel',
          expectedStatuses: const {200},
        ),
      );

  @override
  Future<bool> isReducedEdition(String jobId) async {
    final report = await _json(
      'GET',
      '/v1/edition-jobs/${Uri.encodeComponent(jobId)}/integration',
      expectedStatuses: const {200},
    );
    final selected = report['selected_story_count'];
    final placed = report['placed_story_count'];
    if (selected is! int || placed is! int || selected < placed) {
      throw const FormatException('Integration report counts are malformed.');
    }
    return placed < selected;
  }

  @override
  Future<EditionDocument> loadReadyEdition(String editionId) async {
    final document = await _json(
      'GET',
      '/v1/editions/${Uri.encodeComponent(editionId)}',
      expectedStatuses: const {200},
    );
    final articleList = document['articles'];
    if (articleList is! List<Object?> || articleList.isEmpty) {
      throw const FormatException('Ready edition articles are unavailable.');
    }
    final resolved = <String, Uint8List>{};
    for (final rawArticle in articleList) {
      if (rawArticle is! Map<String, Object?>) {
        throw const FormatException('Ready edition article is malformed.');
      }
      final visual = rawArticle['visual'];
      if (visual is! Map<String, Object?>) {
        throw const FormatException('Ready edition visual is malformed.');
      }
      final assetId = visual['asset_id'];
      final contentHash = visual['content_hash'];
      final width = visual['width'];
      final height = visual['height'];
      if (assetId is! String ||
          contentHash != assetId ||
          !RegExp(r'^sha256:[0-9a-f]{64}$').hasMatch(assetId) ||
          width is! int ||
          height is! int) {
        throw const FormatException('Ready edition asset metadata is invalid.');
      }
      if (resolved.containsKey(assetId)) {
        continue;
      }
      resolved[assetId] = await _asset(
        editionId: editionId,
        assetId: assetId,
        width: width,
        height: height,
      );
    }
    return EditionDocument.fromJson(
      document,
      assetBytesResolver: resolved.__lookup,
    );
  }

  Future<Map<String, Object?>> _json(
    String method,
    String path, {
    required Set<int> expectedStatuses,
    Map<String, String> headers = const {},
    Map<String, Object?>? body,
  }) async {
    final request = await _client.openUrl(method, _resolve(path));
    request.headers.set(HttpHeaders.acceptHeader, 'application/json');
    headers.forEach(request.headers.set);
    if (body != null) {
      request.headers.contentType = ContentType.json;
      request.write(jsonEncode(body));
    }
    final response = await request.close();
    final bytes = await _readBounded(response, _maxJsonBytes);
    if (!expectedStatuses.contains(response.statusCode)) {
      throw HttpException('Edition service returned a bounded error status.');
    }
    final decoded = jsonDecode(utf8.decode(bytes));
    if (decoded is! Map<String, Object?>) {
      throw const FormatException('Edition service JSON is malformed.');
    }
    return decoded;
  }

  Future<Uint8List> _asset({
    required String editionId,
    required String assetId,
    required int width,
    required int height,
  }) async {
    final assetHex = assetId.substring('sha256:'.length);
    final request = await _client.getUrl(
      _resolve(
        '/v1/editions/${Uri.encodeComponent(editionId)}/assets/$assetHex',
      ),
    );
    request.headers.set(HttpHeaders.acceptHeader, 'image/webp');
    final response = await request.close();
    final bytes = await _readBounded(response, _maxAssetBytes);
    if (response.statusCode != 200 ||
        response.headers.contentType?.mimeType != 'image/webp') {
      throw HttpException('Edition asset is unavailable.');
    }
    if ('sha256:${sha256.convert(bytes)}' != assetId) {
      throw const FormatException('Edition asset integrity check failed.');
    }
    final codec = await ui.instantiateImageCodec(bytes);
    try {
      final frame = await codec.getNextFrame();
      try {
        if (frame.image.width != width || frame.image.height != height) {
          throw const FormatException('Edition asset dimensions are invalid.');
        }
      } finally {
        frame.image.dispose();
      }
    } finally {
      codec.dispose();
    }
    return bytes;
  }

  Uri _resolve(String path) => _origin.resolve(path);
}

extension on Map<String, Uint8List> {
  Uint8List? __lookup(String key) => this[key];
}

Future<Uint8List> _readBounded(HttpClientResponse response, int maximum) async {
  final builder = BytesBuilder(copy: false);
  var total = 0;
  await for (final chunk in response) {
    total += chunk.length;
    if (total > maximum) {
      throw const FormatException('Edition response exceeds its size bound.');
    }
    builder.add(chunk);
  }
  return builder.takeBytes();
}

Uri _validateOrigin(Uri origin, bool allowDebugLoopback) {
  final standardHttps =
      origin.scheme == 'https' &&
      origin.host.isNotEmpty &&
      origin.userInfo.isEmpty &&
      !origin.hasQuery &&
      !origin.hasFragment;
  final debugLoopback =
      allowDebugLoopback &&
      origin.scheme == 'http' &&
      {'127.0.0.1', 'localhost', '10.0.2.2'}.contains(origin.host) &&
      origin.userInfo.isEmpty &&
      !origin.hasQuery &&
      !origin.hasFragment;
  if (!standardHttps && !debugLoopback) {
    throw ArgumentError('Edition API origin must be HTTPS or debug loopback.');
  }
  return origin.replace(
    path: origin.path.endsWith('/') ? origin.path : '${origin.path}/',
  );
}
