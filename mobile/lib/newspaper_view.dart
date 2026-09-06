import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'edition.dart';
import 'edition_session.dart';
import 'source_launcher.dart';

const paperColor = Color(0xFFF7F0DE);
const inkColor = Color(0xFF17232A);
const navyColor = Color(0xFF153A52);
const coralColor = Color(0xFFCC5A45);

class NewspaperView extends StatelessWidget {
  const NewspaperView({
    required this.session,
    required this.sourceLauncher,
    super.key,
  });

  final EditionSession session;
  final SourceLauncher sourceLauncher;

  @override
  Widget build(BuildContext context) {
    final page = session.currentPage;
    final controller = session.controllerFor(page.id);
    final scale = controller.value.getMaxScaleOnAxis();
    final isAtFit = session.isAtFitScale(page.id);

    return Scaffold(
      backgroundColor: const Color(0xFF102532),
      appBar: AppBar(
        backgroundColor: const Color(0xFF102532),
        foregroundColor: Colors.white,
        titleSpacing: 20,
        title: const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'GAZETE MODU',
              style: TextStyle(fontSize: 13, fontWeight: FontWeight.w800),
            ),
            Text(
              'Offline reader proof',
              style: TextStyle(fontSize: 11, color: Color(0xFFB8CEDA)),
            ),
          ],
        ),
        actions: [
          Semantics(
            label: 'Yakınlaştırmayı sıfırla',
            button: true,
            child: IconButton(
              key: const Key('reset-zoom'),
              onPressed: isAtFit ? null : session.resetCurrentTransform,
              icon: const Icon(Icons.fit_screen),
              tooltip: 'Sayfayı sığdır',
            ),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: SafeArea(
        top: false,
        child: Column(
          children: [
            Expanded(
              child: NewspaperViewport(
                page: page,
                edition: session.edition,
                controller: controller,
                onOpenArticle: session.openArticle,
                onOpenSource: (article) => _openSource(context, article),
              ),
            ),
            _NavigationBar(session: session, scale: scale, isAtFit: isAtFit),
          ],
        ),
      ),
    );
  }

  Future<void> _openSource(BuildContext context, Article article) async {
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

class _NavigationBar extends StatelessWidget {
  const _NavigationBar({
    required this.session,
    required this.scale,
    required this.isAtFit,
  });

  final EditionSession session;
  final double scale;
  final bool isAtFit;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: const Color(0xFF0B1C26),
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 10),
      child: Row(
        children: [
          IconButton.filledTonal(
            key: const Key('previous-page'),
            onPressed: session.canGoBack ? session.previousPage : null,
            color: Colors.white,
            disabledColor: const Color(0xFF55707D),
            tooltip: 'Önceki sayfa',
            icon: const Icon(Icons.arrow_back),
          ),
          Expanded(
            child: Semantics(
              liveRegion: true,
              label:
                  'Sayfa ${session.pageIndex + 1}, toplam ${session.edition.pages.length}',
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    'SAYFA ${session.pageIndex + 1} / ${session.edition.pages.length}',
                    key: const Key('page-indicator'),
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w900,
                      letterSpacing: 1.4,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    isAtFit
                        ? '${(scale * 100).round()}% • Sayfa geçişi açık'
                        : '${(scale * 100).round()}% • Geçiş için sayfayı sığdır',
                    key: const Key('zoom-navigation-status'),
                    style: const TextStyle(
                      color: Color(0xFFB8CEDA),
                      fontSize: 11,
                    ),
                  ),
                ],
              ),
            ),
          ),
          IconButton.filled(
            key: const Key('next-page'),
            onPressed: session.canGoForward ? session.nextPage : null,
            tooltip: 'Sonraki sayfa',
            icon: const Icon(Icons.arrow_forward),
          ),
        ],
      ),
    );
  }
}

class NewspaperViewport extends StatelessWidget {
  const NewspaperViewport({
    required this.page,
    required this.edition,
    required this.controller,
    required this.onOpenArticle,
    required this.onOpenSource,
    super.key,
  });

  final NewspaperPage page;
  final EditionDocument edition;
  final TransformationController controller;
  final ValueChanged<String> onOpenArticle;
  final ValueChanged<Article> onOpenSource;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final fit = math.min(
          constraints.maxWidth / page.canvas.width,
          constraints.maxHeight / page.canvas.height,
        );
        final fittedWidth = page.canvas.width * fit;
        final fittedHeight = page.canvas.height * fit;

        return Center(
          child: SizedBox(
            width: fittedWidth,
            height: fittedHeight,
            child: InteractiveViewer(
              key: Key('interactive-page-${page.id}'),
              transformationController: controller,
              minScale: 1,
              maxScale: 4,
              panEnabled: true,
              scaleEnabled: true,
              boundaryMargin: const EdgeInsets.all(36),
              clipBehavior: Clip.hardEdge,
              child: SizedBox(
                width: fittedWidth,
                height: fittedHeight,
                child: FittedBox(
                  fit: BoxFit.fill,
                  child: SizedBox(
                    width: page.canvas.width,
                    height: page.canvas.height,
                    child: NewspaperCanvas(
                      page: page,
                      edition: edition,
                      onOpenArticle: onOpenArticle,
                      onOpenSource: onOpenSource,
                    ),
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

class NewspaperCanvas extends StatelessWidget {
  const NewspaperCanvas({
    required this.page,
    required this.edition,
    required this.onOpenArticle,
    required this.onOpenSource,
    super.key,
  });

  final NewspaperPage page;
  final EditionDocument edition;
  final ValueChanged<String> onOpenArticle;
  final ValueChanged<Article> onOpenSource;

  @override
  Widget build(BuildContext context) {
    return RepaintBoundary(
      key: Key('newspaper-canvas-${page.id}'),
      child: ColoredBox(
        color: paperColor,
        child: Stack(
          clipBehavior: Clip.hardEdge,
          children: [
            const Positioned.fill(child: _PaperTexture()),
            _Masthead(page: page, edition: edition.edition),
            for (final placement in page.placements)
              Positioned.fromRect(
                rect: placement.rect.rect,
                child: _StoryBlock(
                  role: placement.role,
                  article: edition.articleById(placement.articleId),
                ),
              ),
            for (final placement in page.placements)
              for (final region in placement.hitRegions)
                Positioned.fromRect(
                  rect: region.rect.rect,
                  child: _HitTarget(
                    pageId: page.id,
                    placementId: placement.id,
                    region: region,
                    onTap: () {
                      final article = edition.articleById(placement.articleId);
                      switch (region.action) {
                        case HitAction.openReading:
                          onOpenArticle(article.id);
                        case HitAction.openSource:
                          onOpenSource(article);
                      }
                    },
                  ),
                ),
          ],
        ),
      ),
    );
  }
}

class _PaperTexture extends StatelessWidget {
  const _PaperTexture();

  @override
  Widget build(BuildContext context) {
    return CustomPaint(painter: _PaperTexturePainter());
  }
}

class _PaperTexturePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final linePaint = Paint()
      ..color = inkColor.withValues(alpha: 0.035)
      ..strokeWidth = 1;
    for (double y = 0; y < size.height; y += 17) {
      canvas.drawLine(
        Offset.zero.translate(0, y),
        Offset(size.width, y),
        linePaint,
      );
    }
    final dotPaint = Paint()..color = navyColor.withValues(alpha: 0.035);
    for (double x = 11; x < size.width; x += 29) {
      for (double y = 9; y < size.height; y += 31) {
        canvas.drawCircle(Offset(x, y), 1.1, dotPaint);
      }
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _Masthead extends StatelessWidget {
  const _Masthead({required this.page, required this.edition});

  final NewspaperPage page;
  final EditionMetadata edition;

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: 40,
      top: 24,
      right: 40,
      height: 132,
      child: Column(
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: Text(
                  edition.masthead,
                  key: const Key('masthead'),
                  style: const TextStyle(
                    color: inkColor,
                    fontFamily: 'serif',
                    fontSize: 76,
                    height: 0.92,
                    fontWeight: FontWeight.w900,
                    letterSpacing: -4,
                  ),
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    page.label.toUpperCase(),
                    key: Key('page-label-${page.id}'),
                    style: const TextStyle(
                      color: coralColor,
                      fontSize: 17,
                      fontWeight: FontWeight.w900,
                      letterSpacing: 1.4,
                    ),
                  ),
                  Text(
                    page.section.toUpperCase(),
                    style: const TextStyle(
                      color: inkColor,
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 10),
          Container(height: 5, color: inkColor),
          const SizedBox(height: 5),
          Row(
            children: [
              Text(
                edition.title,
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const Spacer(),
              const Text(
                'KAVRAMSAL GÖRSELLER • OFFLINE FIXTURE',
                style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _StoryBlock extends StatelessWidget {
  const _StoryBlock({required this.role, required this.article});

  final PlacementRole role;
  final Article article;

  @override
  Widget build(BuildContext context) {
    final isHero = role == PlacementRole.hero;
    final isBrief = role == PlacementRole.brief;
    final headlineSize = isHero ? 38.0 : (isBrief ? 24.0 : 29.0);

    return DecoratedBox(
      decoration: BoxDecoration(
        color: paperColor.withValues(alpha: 0.94),
        border: Border.all(color: inkColor, width: isHero ? 3 : 2),
      ),
      child: Padding(
        padding: EdgeInsets.all(isHero ? 16 : 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (!isBrief) ...[
              Expanded(
                flex: isHero ? 6 : 5,
                child: ClipRect(
                  child: SizedBox.expand(
                    child: Image.asset(
                      article.visual.assetPath,
                      fit: BoxFit.cover,
                      excludeFromSemantics: true,
                    ),
                  ),
                ),
              ),
              SizedBox(height: isHero ? 13 : 9),
            ],
            Text(
              article.headline,
              maxLines: isBrief ? 4 : 3,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: inkColor,
                fontFamily: 'serif',
                fontSize: headlineSize,
                height: 0.98,
                fontWeight: FontWeight.w900,
              ),
            ),
            const SizedBox(height: 8),
            Expanded(
              flex: isBrief ? 1 : 2,
              child: Text(
                article.dek,
                maxLines: isBrief ? 5 : 3,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: inkColor.withValues(alpha: 0.82),
                  fontSize: isHero ? 17 : 15,
                  height: 1.18,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.only(top: 7),
              decoration: const BoxDecoration(
                border: Border(top: BorderSide(color: coralColor, width: 2)),
              ),
              child: Text(
                '${article.primarySource.name.toUpperCase()}  ↗',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: coralColor,
                  fontSize: 12,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 0.8,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _HitTarget extends StatelessWidget {
  const _HitTarget({
    required this.pageId,
    required this.placementId,
    required this.region,
    required this.onTap,
  });

  final String pageId;
  final String placementId;
  final HitRegion region;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final actionName = switch (region.action) {
      HitAction.openReading => 'open_reading',
      HitAction.openSource => 'open_source',
    };
    return Semantics(
      container: true,
      button: true,
      label: region.accessibilityLabel,
      child: GestureDetector(
        key: Key('hit-$pageId-$placementId-$actionName'),
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: region.action == HitAction.openSource
                ? coralColor.withValues(alpha: 0.035)
                : Colors.transparent,
            border: region.action == HitAction.openSource
                ? Border.all(color: coralColor.withValues(alpha: 0.22))
                : null,
          ),
        ),
      ),
    );
  }
}
