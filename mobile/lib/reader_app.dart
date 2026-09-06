import 'package:flutter/material.dart';

import 'edition.dart';
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
    this.sourceLauncher = const ExternalSourceLauncher(),
  });

  final EditionDocument? edition;
  final EditionRepository? repository;
  final SourceLauncher sourceLauncher;

  @override
  State<ReaderProofApp> createState() => _ReaderProofAppState();
}

class _ReaderProofAppState extends State<ReaderProofApp> {
  EditionSession? _session;
  Object? _loadError;

  @override
  void initState() {
    super.initState();
    final edition = widget.edition;
    if (edition != null) {
      _session = EditionSession(edition);
    } else {
      _loadFixture();
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
    _session?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
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
    return const Scaffold(body: Center(child: CircularProgressIndicator()));
  }
}

class EditionReader extends StatelessWidget {
  const EditionReader({
    required this.session,
    required this.sourceLauncher,
    super.key,
  });

  final EditionSession session;
  final SourceLauncher sourceLauncher;

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
        );
      },
    );
  }
}
