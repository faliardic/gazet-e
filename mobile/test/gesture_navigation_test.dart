import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:readerproof/edition_session.dart';
import 'package:readerproof/reader_app.dart';
import 'package:readerproof/source_launcher.dart';

import 'test_fixture.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('fit-scale left swipe turns exactly one page forward', (
    tester,
  ) async {
    final session = await _pumpReader(tester);

    await tester.drag(_viewport('front'), const Offset(-180, 4));
    await tester.pumpAndSettle();

    expect(session.pageIndex, 1);
  });

  testWidgets('fit-scale right swipe returns to the previous page', (
    tester,
  ) async {
    final session = await _pumpReader(tester);
    await tester.drag(_viewport('front'), const Offset(-180, 4));
    await tester.pumpAndSettle();

    await tester.drag(_viewport('climate'), const Offset(180, -3));
    await tester.pumpAndSettle();

    expect(session.pageIndex, 0);
  });

  testWidgets('one long swipe cannot skip multiple pages', (tester) async {
    final session = await _pumpReader(tester);

    await tester.drag(_viewport('front'), const Offset(-500, 0));
    await tester.pumpAndSettle();

    expect(session.pageIndex, 1);
  });

  testWidgets('outward swipes at edition boundaries fail safely', (
    tester,
  ) async {
    final session = await _pumpReader(tester);

    await tester.drag(_viewport('front'), const Offset(180, 0));
    await tester.pumpAndSettle();
    expect(session.pageIndex, 0);

    await tester.drag(_viewport('front'), const Offset(-180, 0));
    await tester.pumpAndSettle();
    await tester.drag(_viewport('climate'), const Offset(-180, 0));
    await tester.pumpAndSettle();
    expect(session.pageIndex, 2);

    await tester.drag(_viewport('technology'), const Offset(-180, 0));
    await tester.pumpAndSettle();
    expect(session.pageIndex, 2);
  });

  testWidgets('sub-threshold horizontal drag does not turn the page', (
    tester,
  ) async {
    final session = await _pumpReader(tester);

    await tester.drag(_viewport('front'), const Offset(-48, 2));
    await tester.pumpAndSettle();

    expect(session.pageIndex, 0);
  });

  testWidgets('mostly vertical drag does not turn the page', (tester) async {
    final session = await _pumpReader(tester);

    await tester.drag(_viewport('front'), const Offset(-100, 190));
    await tester.pumpAndSettle();

    expect(session.pageIndex, 0);
  });

  testWidgets('pinch gesture does not turn the page', (tester) async {
    final session = await _pumpReader(tester);

    await _pinchToZoom(tester, _viewport('front'));

    expect(
      session.controllerFor('front').value.getMaxScaleOnAxis(),
      greaterThan(1.2),
    );
    expect(session.pageIndex, 0);
  });

  testWidgets('zoomed horizontal drag pans without turning the page', (
    tester,
  ) async {
    final session = await _pumpReader(tester);
    final viewport = _viewport('front');
    await _pinchToZoom(tester, viewport);
    final controller = session.controllerFor('front');
    final beforePan = controller.value.clone();

    await tester.drag(viewport, const Offset(70, 4));
    await tester.pumpAndSettle();

    expect(controller.value.storage, isNot(equals(beforePan.storage)));
    expect(session.pageIndex, 0);
  });

  testWidgets('zoomed state disables button and programmatic navigation', (
    tester,
  ) async {
    final session = await _pumpReader(tester);
    await _pinchToZoom(tester, _viewport('front'));

    final next = tester.widget<IconButton>(find.byKey(const Key('next-page')));
    expect(next.onPressed, isNull);
    expect(session.nextPage(), isFalse);
    expect(session.pageIndex, 0);
  });
}

Finder _viewport(String pageId) => find.byKey(Key('interactive-page-$pageId'));

Future<EditionSession> _pumpReader(WidgetTester tester) async {
  await tester.binding.setSurfaceSize(const Size(430, 900));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  final session = EditionSession(await loadTestEdition());
  addTearDown(session.dispose);
  await tester.pumpWidget(
    MaterialApp(
      home: EditionReader(
        session: session,
        sourceLauncher: const _NoopSourceLauncher(),
      ),
    ),
  );
  await tester.pumpAndSettle();
  return session;
}

Future<void> _pinchToZoom(WidgetTester tester, Finder viewport) async {
  final center = tester.getCenter(viewport);
  final first = await tester.createGesture(pointer: 1);
  final second = await tester.createGesture(pointer: 2);
  await first.down(center - const Offset(35, 0));
  await second.down(center + const Offset(35, 0));
  await tester.pump();
  await first.moveTo(center - const Offset(95, 0));
  await second.moveTo(center + const Offset(95, 0));
  await tester.pump(const Duration(milliseconds: 100));
  await first.up();
  await second.up();
  await tester.pumpAndSettle();
}

final class _NoopSourceLauncher implements SourceLauncher {
  const _NoopSourceLauncher();

  @override
  Future<bool> open(Uri uri) async => true;
}
