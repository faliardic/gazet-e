import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart';

import 'edition.dart';
import 'edition_job_api_client.dart';

enum EditionGenerationState {
  idle,
  submitting,
  tracking,
  cancelling,
  ready,
  failed,
  cancelled,
}

final class EditionGenerationController extends ChangeNotifier {
  EditionGenerationController({
    required this._gateway,
    Future<void> Function(Duration)? delay,
    String Function()? idempotencyKeyFactory,
    this.maxPolls = 120,
  }) : _delay = delay ?? Future<void>.delayed,
       _idempotencyKeyFactory = idempotencyKeyFactory ?? _newKey;

  final EditionJobGateway _gateway;
  final Future<void> Function(Duration) _delay;
  final String Function() _idempotencyKeyFactory;
  final int maxPolls;

  EditionGenerationState _state = EditionGenerationState.idle;
  RemoteJobState? _remoteState;
  String? _jobId;
  String? _idempotencyKey;
  String? _failureCode;
  EditionDocument? _edition;
  bool _isReducedEdition = false;
  int _epoch = 0;
  bool _disposed = false;

  EditionGenerationState get state => _state;
  RemoteJobState? get remoteState => _remoteState;
  String? get jobId => _jobId;
  String? get idempotencyKey => _idempotencyKey;
  String? get failureCode => _failureCode;
  EditionDocument? get edition => _edition;
  bool get isReducedEdition => _isReducedEdition;
  bool get canPrepare =>
      _state == EditionGenerationState.idle ||
      _state == EditionGenerationState.ready ||
      _state == EditionGenerationState.failed ||
      _state == EditionGenerationState.cancelled;
  bool get canCancel =>
      _jobId != null &&
      (_state == EditionGenerationState.submitting ||
          _state == EditionGenerationState.tracking);

  Future<void> prepare({
    String locale = 'tr-TR',
    String timezone = 'Europe/Istanbul',
  }) async {
    if (!canPrepare) {
      return;
    }
    final epoch = ++_epoch;
    if (_state == EditionGenerationState.ready) {
      _jobId = null;
      _idempotencyKey = null;
      _remoteState = null;
    }
    _state = EditionGenerationState.submitting;
    _failureCode = null;
    if (_edition == null) {
      _isReducedEdition = false;
    }
    _idempotencyKey ??= _idempotencyKeyFactory();
    notifyListeners();
    try {
      var status = await _gateway.createJob(
        idempotencyKey: _idempotencyKey!,
        locale: locale,
        timezone: timezone,
      );
      if (!_isCurrent(epoch)) {
        return;
      }
      _jobId = status.jobId;
      notifyListeners();
      await _track(status, epoch);
    } on Object {
      _fail('edition_service_unavailable', epoch);
    }
  }

  Future<void> cancel() async {
    final jobId = _jobId;
    if (!canCancel || jobId == null) {
      return;
    }
    final epoch = ++_epoch;
    _state = EditionGenerationState.cancelling;
    notifyListeners();
    try {
      final status = await _gateway.cancelJob(jobId);
      if (!_isCurrent(epoch)) {
        return;
      }
      _remoteState = status.state;
      if (status.state == RemoteJobState.cancelled) {
        _state = EditionGenerationState.cancelled;
        notifyListeners();
      } else {
        await _track(status, epoch);
      }
    } on Object {
      _fail('cancellation_unavailable', epoch);
    }
  }

  Future<void> resume({
    required String jobId,
    required String idempotencyKey,
  }) async {
    if (_jobId != null || _state != EditionGenerationState.idle) {
      return;
    }
    final epoch = ++_epoch;
    _jobId = jobId;
    _idempotencyKey = idempotencyKey;
    _state = EditionGenerationState.tracking;
    notifyListeners();
    try {
      final status = await _gateway.getJob(jobId);
      if (!_isCurrent(epoch)) {
        return;
      }
      await _track(status, epoch);
    } on Object {
      _fail('edition_service_unavailable', epoch);
    }
  }

  void reset() {
    _epoch++;
    _state = EditionGenerationState.idle;
    _remoteState = null;
    _jobId = null;
    _idempotencyKey = null;
    _failureCode = null;
    _edition = null;
    _isReducedEdition = false;
    notifyListeners();
  }

  Future<void> _finish(RemoteJobStatus status, int epoch) async {
    if (status.state == RemoteJobState.cancelled) {
      _state = EditionGenerationState.cancelled;
      notifyListeners();
      return;
    }
    if (status.state == RemoteJobState.failed) {
      _fail(status.failureCode ?? 'edition_generation_failed', epoch);
      return;
    }
    final editionId = status.editionId;
    if (editionId == null) {
      _fail('ready_edition_missing', epoch);
      return;
    }
    final edition = await _gateway.loadReadyEdition(editionId);
    final reduced = await _gateway.isReducedEdition(status.jobId);
    if (!_isCurrent(epoch)) {
      return;
    }
    _edition = edition;
    _isReducedEdition = reduced;
    _state = EditionGenerationState.ready;
    notifyListeners();
  }

  Future<void> _track(RemoteJobStatus initial, int epoch) async {
    var status = initial;
    for (var poll = 0; poll < maxPolls; poll++) {
      _remoteState = status.state;
      if (status.terminal) {
        await _finish(status, epoch);
        return;
      }
      _state = EditionGenerationState.tracking;
      notifyListeners();
      await _delay(const Duration(seconds: 1));
      if (!_isCurrent(epoch)) {
        return;
      }
      status = await _gateway.getJob(status.jobId);
    }
    _fail('status_timeout', epoch);
  }

  bool _isCurrent(int epoch) => !_disposed && epoch == _epoch;

  void _fail(String code, int epoch) {
    if (!_isCurrent(epoch)) {
      return;
    }
    _failureCode = code;
    _state = EditionGenerationState.failed;
    notifyListeners();
  }

  static String _newKey() {
    final random = Random.secure();
    final bytes = List<int>.generate(16, (_) => random.nextInt(256));
    return 'mobile-${DateTime.now().toUtc().microsecondsSinceEpoch}-'
        '${bytes.map((value) => value.toRadixString(16).padLeft(2, '0')).join()}';
  }

  @override
  void dispose() {
    _disposed = true;
    _epoch++;
    super.dispose();
  }
}
