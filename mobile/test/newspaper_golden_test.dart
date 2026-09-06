import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:readerproof/newspaper_view.dart';

import 'test_fixture.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('front page composition matches deterministic golden', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(540, 760));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final edition = await loadTestEdition();
    final page = edition.pages.first;

    await tester.pumpWidget(
      MaterialApp(
        debugShowCheckedModeBanner: false,
        home: ColoredBox(
          color: const Color(0xFF102532),
          child: Center(
            child: RepaintBoundary(
              key: const Key('golden-front-page'),
              child: SizedBox(
                width: 500,
                height: 707,
                child: FittedBox(
                  fit: BoxFit.fill,
                  child: SizedBox(
                    width: page.canvas.width,
                    height: page.canvas.height,
                    child: NewspaperCanvas(
                      page: page,
                      edition: edition,
                      onOpenArticle: (_) {},
                      onOpenSource: (_) {},
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await expectLater(
      find.byKey(const Key('golden-front-page')),
      matchesGoldenFile('goldens/newspaper_front_page.png'),
    );
  });
}
