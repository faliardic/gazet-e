import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:readerproof/edition_session.dart';
import 'package:readerproof/reader_app.dart';
import 'package:readerproof/source_launcher.dart';

import 'test_fixture.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('renders three pages in fixture order', (tester) async {
    final harness = await _pumpReader(tester);
    addTearDown(harness.dispose);

    expect(find.text('SAYFA 1 / 3'), findsOneWidget);
    expect(find.byKey(const Key('page-label-front')), findsOneWidget);

    await tester.tap(find.byKey(const Key('next-page')));
    await tester.pump();
    expect(find.text('SAYFA 2 / 3'), findsOneWidget);
    expect(find.byKey(const Key('page-label-climate')), findsOneWidget);

    await tester.tap(find.byKey(const Key('next-page')));
    await tester.pump();
    expect(find.text('SAYFA 3 / 3'), findsOneWidget);
    expect(find.byKey(const Key('page-label-technology')), findsOneWidget);
  });

  testWidgets('article hit opens Okuma Modu without launching source', (
    tester,
  ) async {
    final harness = await _pumpReader(tester);
    addTearDown(harness.dispose);

    await tester.tap(
      find.byKey(const Key('hit-front-front-hero-open_reading')),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('reading-mode')), findsOneWidget);
    expect(find.byKey(const Key('reading-headline')), findsOneWidget);
    expect(find.byKey(const Key('visual-transparency-label')), findsOneWidget);
    expect(find.byKey(const Key('reading-source-name')), findsOneWidget);
    expect(find.byKey(const Key('reading-publication-time')), findsOneWidget);
    expect(harness.launcher.opened, isEmpty);
  });

  testWidgets('source hit is distinct and only explicit action launches it', (
    tester,
  ) async {
    final harness = await _pumpReader(tester);
    addTearDown(harness.dispose);

    await tester.tap(find.byKey(const Key('hit-front-front-hero-open_source')));
    await tester.pump();

    expect(harness.launcher.opened, hasLength(1));
    expect(harness.launcher.opened.single.scheme, 'https');
    expect(find.byKey(const Key('newspaper-mode')), findsOneWidget);
    expect(find.byKey(const Key('reading-mode')), findsNothing);
  });

  testWidgets('back restores the same page and transform context', (
    tester,
  ) async {
    final harness = await _pumpReader(tester);
    addTearDown(harness.dispose);
    expect(harness.session.nextPage(), isTrue);
    final controller = harness.session.controllerFor('climate');
    controller.value = Matrix4.identity()
      ..setEntry(0, 0, 1.6)
      ..setEntry(1, 1, 1.6)
      ..setEntry(0, 3, -42)
      ..setEntry(1, 3, -28);
    final expectedTransform = controller.value.clone();
    harness.session.openArticle('article-climate-city');
    await tester.pump();

    await tester.tap(find.byKey(const Key('back-to-newspaper')));
    await tester.pumpAndSettle();

    expect(harness.session.pageIndex, 1);
    expect(controller.value.storage, expectedTransform.storage);
    expect(find.byKey(const Key('interactive-page-climate')), findsOneWidget);
  });

  testWidgets('page navigation is enabled at fit scale and disabled zoomed', (
    tester,
  ) async {
    final harness = await _pumpReader(tester);
    addTearDown(harness.dispose);

    var next = tester.widget<IconButton>(find.byKey(const Key('next-page')));
    expect(next.onPressed, isNotNull);

    final controller = harness.session.controllerFor('front');
    controller.value = Matrix4.identity()
      ..setEntry(0, 0, 2)
      ..setEntry(1, 1, 2);
    await tester.pump();

    next = tester.widget<IconButton>(find.byKey(const Key('next-page')));
    expect(next.onPressed, isNull);
    expect(harness.session.nextPage(), isFalse);
    expect(harness.session.pageIndex, 0);
    expect(find.textContaining('Geçiş için sayfayı sığdır'), findsOneWidget);
  });

  testWidgets('interactive regions expose accessibility semantics', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    final harness = await _pumpReader(tester);
    addTearDown(harness.dispose);

    expect(
      find.bySemanticsLabel(
        'Kentler yeni güne ortak veriyle hazırlanıyor haberini oku',
      ),
      findsOneWidget,
    );
    expect(
      find.bySemanticsLabel('Kentler haberinin açık fixture kaynağına git'),
      findsOneWidget,
    );
    semantics.dispose();
  });
}

Future<_ReaderHarness> _pumpReader(WidgetTester tester) async {
  await tester.binding.setSurfaceSize(const Size(430, 900));
  final edition = await loadTestEdition();
  final session = EditionSession(edition);
  final launcher = _FakeSourceLauncher();
  await tester.pumpWidget(
    MaterialApp(
      theme: ThemeData(useMaterial3: true),
      home: EditionReader(session: session, sourceLauncher: launcher),
    ),
  );
  await tester.pumpAndSettle();
  return _ReaderHarness(session: session, launcher: launcher, tester: tester);
}

final class _ReaderHarness {
  _ReaderHarness({
    required this.session,
    required this.launcher,
    required this.tester,
  });

  final EditionSession session;
  final _FakeSourceLauncher launcher;
  final WidgetTester tester;

  void dispose() {
    session.dispose();
    tester.binding.setSurfaceSize(null);
  }
}

final class _FakeSourceLauncher implements SourceLauncher {
  final List<Uri> opened = [];

  @override
  Future<bool> open(Uri uri) async {
    opened.add(uri);
    return true;
  }
}
