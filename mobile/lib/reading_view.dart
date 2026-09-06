import 'package:flutter/material.dart';

import 'edition.dart';
import 'newspaper_view.dart';
import 'source_launcher.dart';

class ReadingView extends StatelessWidget {
  const ReadingView({
    required this.article,
    required this.onBack,
    required this.sourceLauncher,
    super.key,
  });

  final Article article;
  final VoidCallback onBack;
  final SourceLauncher sourceLauncher;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: paperColor,
      appBar: AppBar(
        backgroundColor: paperColor,
        foregroundColor: inkColor,
        leading: IconButton(
          key: const Key('back-to-newspaper'),
          onPressed: onBack,
          tooltip: 'Gazete Modu’na dön',
          icon: const Icon(Icons.arrow_back),
        ),
        title: const Text(
          'OKUMA MODU',
          style: TextStyle(fontSize: 14, fontWeight: FontWeight.w900),
        ),
      ),
      body: SafeArea(
        top: false,
        child: SingleChildScrollView(
          key: const Key('reading-scroll-view'),
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 40),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 720),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    article.headline,
                    key: const Key('reading-headline'),
                    style: const TextStyle(
                      color: inkColor,
                      fontFamily: 'serif',
                      fontSize: 39,
                      height: 1.02,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    article.dek,
                    style: TextStyle(
                      color: inkColor.withValues(alpha: 0.76),
                      fontSize: 18,
                      height: 1.35,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 18),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(3),
                    child: Semantics(
                      image: true,
                      label: article.visual.alt,
                      child: AspectRatio(
                        aspectRatio: 3 / 2,
                        child: Image.asset(
                          article.visual.assetPath,
                          fit: BoxFit.cover,
                          excludeFromSemantics: true,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  Semantics(
                    label: 'Görsel şeffaflık bilgisi',
                    child: Container(
                      key: const Key('visual-transparency-label'),
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 9,
                      ),
                      color: const Color(0xFFE8DDC6),
                      child: Row(
                        children: [
                          const Icon(
                            Icons.auto_awesome,
                            size: 17,
                            color: coralColor,
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              article.visual.transparencyLabel,
                              style: const TextStyle(
                                color: inkColor,
                                fontSize: 12,
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 22),
                  _SourceLine(source: article.primarySource),
                  const Divider(height: 32, color: inkColor),
                  Text(
                    article.summary,
                    key: const Key('reading-summary'),
                    style: const TextStyle(
                      color: inkColor,
                      fontFamily: 'serif',
                      fontSize: 23,
                      height: 1.42,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 18),
                  for (final paragraph in article.readingBody) ...[
                    Text(
                      paragraph,
                      style: const TextStyle(
                        color: inkColor,
                        fontSize: 18,
                        height: 1.58,
                      ),
                    ),
                    const SizedBox(height: 14),
                  ],
                  const SizedBox(height: 8),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      key: const Key('reading-open-source'),
                      onPressed: () => _openSource(context),
                      icon: const Icon(Icons.open_in_new),
                      label: Text(
                        '${article.primarySource.name} • Kaynağa Git',
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _openSource(BuildContext context) async {
    final opened = await sourceLauncher.open(
      article.primarySource.canonicalUrl,
    );
    if (!opened && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Kaynak bağlantısı açılamadı.')),
      );
    }
  }
}

class _SourceLine extends StatelessWidget {
  const _SourceLine({required this.source});

  final ArticleSource source;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 4,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        const Text(
          'KAYNAK',
          style: TextStyle(
            color: coralColor,
            fontSize: 12,
            fontWeight: FontWeight.w900,
            letterSpacing: 1.2,
          ),
        ),
        Text(
          source.name,
          key: const Key('reading-source-name'),
          style: const TextStyle(fontWeight: FontWeight.w800),
        ),
        if (source.publishedAt case final publishedAt?)
          Text(
            _formatPublishedAt(publishedAt),
            key: const Key('reading-publication-time'),
            style: TextStyle(color: inkColor.withValues(alpha: 0.64)),
          ),
      ],
    );
  }

  String _formatPublishedAt(DateTime value) {
    final local = value.toLocal();
    String two(int number) => number.toString().padLeft(2, '0');
    return '${two(local.day)}.${two(local.month)}.${local.year} • '
        '${two(local.hour)}:${two(local.minute)}';
  }
}
