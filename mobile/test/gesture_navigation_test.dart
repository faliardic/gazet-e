import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:readerproof/edition_session.dart';
import 'package:readerproof/reader_app.dart';
import 'package:readerproof/source_launcher.dart';

import 'test_fixture.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('pinch zoom and pan never turn the page while zoomed', (
    tester,
  ) async {
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

    final viewport = find.byKey(const Key('interactive-page-front'));
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

    final controller = session.controllerFor('front');
    expect(controller.value.getMaxScaleOnAxis(), greaterThan(1.2));
    expect(session.pageIndex, 0);
    expect(session.nextPage(), isFalse);

    final beforePan = controller.value.clone();
    await tester.drag(viewport, const Offset(45, 32));
    await tester.pumpAndSettle();

    expect(controller.value.storage, isNot(equals(beforePan.storage)));
    expect(session.pageIndex, 0);
    final next = tester.widget<IconButton>(find.byKey(const Key('next-page')));
    expect(next.onPressed, isNull);
  });
}

final class _NoopSourceLauncher implements SourceLauncher {
  const _NoopSourceLauncher();

  @override
  Future<bool> open(Uri uri) async => true;
}
