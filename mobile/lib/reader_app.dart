import 'dart:async';

import 'package:flutter/material.dart';

import 'edition.dart';
import 'edition_generation_controller.dart';
import 'edition_job_api_client.dart';
import 'edition_repository.dart';
import 'edition_session.dart';
import 'newspaper_view.dart';
import 'reading_view.dart';
import 'source_launcher.dart';

class ReaderProofApp extends StatefulWidget {
  const ReaderProofApp({
    super.key,
    this.edition,
    this.repository,
    this.generationController,
    this.sourceLauncher = const ExternalSourceLauncher(),
  });

  final EditionDocument? edition;
  final EditionRepository? repository;
  final EditionGenerationController? generationController;
  final SourceLauncher sourceLauncher;

  @override
  State<ReaderProofApp> createState() => _ReaderProofAppState();
}

class _ReaderProofAppState extends State<ReaderProofApp> with RestorationMixin {
  EditionSession? _session;
  Object? _loadError;
  final RestorableStringN _restoredJobId = RestorableStringN(null);
  final RestorableStringN _restoredIdempotencyKey = RestorableStringN(null);
  bool _restorationRegistered = false;

  @override
  String? get restorationId => 'gazet-e-generation';

  @override
  void restoreState(RestorationBucket? oldBucket, bool initialRestore) {
    registerForRestoration(_restoredJobId, 'job-id');
    registerForRestoration(_restoredIdempotencyKey, 'idempotency-key');
    _restorationRegistered = true;
    final controller = widget.generationController;
    final jobId = _restoredJobId.value;
    final key = _restoredIdempotencyKey.value;
    if (controller != null && jobId != null && key != null) {
      unawaited(controller.resume(jobId: jobId, idempotencyKey: key));
    }
  }

  @override
  void initState() {
    super.initState();
    final edition = widget.edition;
    if (edition != null) {
      _session = EditionSession(edition);
    } else if (widget.generationController != null) {
      widget.generationController!.addListener(_onGenerationChanged);
      _onGenerationChanged();
    } else {
      _loadFixture();
    }
  }

  void _onGenerationChanged() {
    final controller = widget.generationController;
    if (_restorationRegistered) {
      _restoredJobId.value = controller?.jobId;
      _restoredIdempotencyKey.value = controller?.idempotencyKey;
    }
    final edition = controller?.edition;
    if (edition == null || _session?.edition.edition.id == edition.edition.id) {
      return;
    }
    final previous = _session;
    _session = EditionSession(edition);
    previous?.dispose();
    if (mounted) {
      setState(() {});
    }
  }

  Future<void> _loadFixture() async {
    try {
      final edition = await (widget.repository ?? EditionRepository())
          .loadFixture();
      if (!mounted) {
        return;
      }
      setState(() => _session = EditionSession(edition));
    } on Object catch (error) {
      if (mounted) {
        setState(() => _loadError = error);
      }
    }
  }

  @override
  void dispose() {
    widget.generationController?.removeListener(_onGenerationChanged);
    _session?.dispose();
    _restoredJobId.dispose();
    _restoredIdempotencyKey.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      restorationScopeId: 'gazet-e-app',
      title: 'Gazet+E Reader Proof',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF153A52),
          brightness: Brightness.light,
        ),
        scaffoldBackgroundColor: const Color(0xFFF2EEE4),
        useMaterial3: true,
      ),
      home: _buildHome(),
    );
  }

  Widget _buildHome() {
    final session = _session;
    if (session != null) {
      return EditionReader(
        session: session,
        sourceLauncher: widget.sourceLauncher,
        reducedEdition: widget.generationController?.isReducedEdition ?? false,
      );
    }
    if (_loadError != null) {
      return Scaffold(
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Text(
              'Bundled edition açılamadı.\n$_loadError',
              key: const Key('fixture-load-error'),
              textAlign: TextAlign.center,
            ),
          ),
        ),
      );
    }
    final generation = widget.generationController;
    if (generation != null) {
      return AnimatedBuilder(
        animation: generation,
        builder: (context, _) => _GenerationHome(controller: generation),
      );
    }
    return const Scaffold(body: Center(child: CircularProgressIndicator()));
  }
}

class _GenerationHome extends StatelessWidget {
  const _GenerationHome({required this.controller});

  final EditionGenerationController controller;

  @override
  Widget build(BuildContext context) {
    final active =
        !controller.canPrepare &&
        controller.state != EditionGenerationState.ready;
    final status = switch (controller.state) {
      EditionGenerationState.idle => 'Yeni baskın hazır.',
      EditionGenerationState.submitting => 'Baskı isteği gönderiliyor…',
      EditionGenerationState.tracking => _remoteLabel(controller.remoteState),
      EditionGenerationState.cancelling => 'İptal isteği işleniyor…',
      EditionGenerationState.ready => 'Gazeten hazır.',
      EditionGenerationState.failed =>
        'Baskı hazırlanamadı (${controller.failureCode ?? 'unknown'}).',
      EditionGenerationState.cancelled => 'Baskı hazırlama iptal edildi.',
    };
    return Scaffold(
      appBar: AppBar(title: const Text('GAZET+E')),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.newspaper, size: 72),
              const SizedBox(height: 20),
              Text(status, key: const Key('generation-status')),
              const SizedBox(height: 24),
              FilledButton.icon(
                key: const Key('prepare-edition'),
                onPressed: controller.canPrepare ? controller.prepare : null,
                icon: const Icon(Icons.auto_awesome),
                label: const Text('Gazetemi Hazırla'),
              ),
              if (controller.canCancel || active) ...[
                const SizedBox(height: 12),
                TextButton(
                  key: const Key('cancel-generation'),
                  onPressed: controller.canCancel ? controller.cancel : null,
                  child: const Text('İptal Et'),
                ),
              ],
              if (controller.state == EditionGenerationState.failed ||
                  controller.state == EditionGenerationState.cancelled) ...[
                const SizedBox(height: 8),
                TextButton(
                  key: const Key('reset-generation'),
                  onPressed: controller.reset,
                  child: const Text('Yeni istek'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  static String _remoteLabel(RemoteJobState? state) => switch (state) {
    RemoteJobState.requested => 'Baskı sırası oluşturuldu…',
    RemoteJobState.collecting => 'Haberler toplanıyor…',
    RemoteJobState.selecting => 'Haberler seçiliyor…',
    RemoteJobState.summarizing => 'Editoryal özetler hazırlanıyor…',
    RemoteJobState.illustrating => 'Editoryal görseller hazırlanıyor…',
    RemoteJobState.layingOut => 'Gazete sayfaları yerleştiriliyor…',
    _ => 'Baskı durumu doğrulanıyor…',
  };
}

class EditionReader extends StatelessWidget {
  const EditionReader({
    required this.session,
    required this.sourceLauncher,
    this.reducedEdition = false,
    super.key,
  });

  final EditionSession session;
  final SourceLauncher sourceLauncher;
  final bool reducedEdition;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: session,
      builder: (context, _) {
        final article = session.selectedArticle;
        return PopScope(
          canPop: article == null,
          onPopInvokedWithResult: (didPop, result) {
            if (!didPop && article != null) {
              session.closeArticle();
            }
          },
          child: Column(
            children: [
              if (reducedEdition)
                const MaterialBanner(
                  content: Text(
                    'Bazı haberler doğrulanmış içerik veya görsel bulunamadığı '
                    'için bu baskıya alınmadı.',
                  ),
                  actions: [SizedBox.shrink()],
                ),
              Expanded(
                child: article == null
                    ? NewspaperView(
                        key: const Key('newspaper-mode'),
                        session: session,
                        sourceLauncher: sourceLauncher,
                      )
                    : ReadingView(
                        key: const Key('reading-mode'),
                        article: article,
                        onBack: session.closeArticle,
                        sourceLauncher: sourceLauncher,
                      ),
              ),
            ],
          ),
        );
      },
    );
  }
}
