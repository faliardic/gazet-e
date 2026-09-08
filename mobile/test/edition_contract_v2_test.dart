import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:readerproof/edition.dart';
import 'package:readerproof/newspaper_view.dart';
import 'package:readerproof/reader_app.dart';
import 'package:readerproof/source_launcher.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late String v2Source;

  setUpAll(() async {
    v2Source = await File('assets/fixtures/edition.v2.json').readAsString();
  });

  test('v2 parses the fixed physical source-only contract', () async {
    final document = EditionDocument.parse(v2Source);

    expect(document.contractVersion, activeContractVersion);
    expect(document.edition.versions.summaryPrompt, isNull);
    expect(document.edition.versions.editorialPolicy, isNull);
    expect(document.edition.versions.physicalLayout, isNotEmpty);
    expect(document.pages.single.canvas.width, 700);
    expect(document.pages.single.canvas.height, 1000);
    expect(document.pages.single.physicalProfile?.widthMm, 350);
    expect(document.pages.single.physicalProfile?.heightMm, 500);
    expect(document.pages.single.ads.single.label, 'REKLAM');
    final article = document.articles.values.single;
    expect(article.sourceOnly, isTrue);
    expect(article.feedExcerpt, isNotEmpty);
    expect(article.summary, isEmpty);
    expect(article.readingBody, isEmpty);
    expect(article.cache.summaryKey, isNull);

    final roundTrip = jsonEncode(document.toJson());
    expect(roundTrip, isNot(contains('summary_prompt')));
    expect(roundTrip, isNot(contains('reading_body')));
    expect(roundTrip, isNot(contains('summary_key')));
    expect(roundTrip, isNot(contains('"dek"')));
  });

  test('v2 rejects AI text and interactive ad fields', () async {
    final original = jsonDecode(v2Source) as Map<String, Object?>;
    final article =
        (original['articles']! as List<Object?>).single!
            as Map<String, Object?>;
    article['summary'] = 'forbidden';
    expect(() => EditionDocument.fromJson(original), throwsFormatException);

    final withUrl = jsonDecode(v2Source) as Map<String, Object?>;
    final page =
        (withUrl['pages']! as List<Object?>).single! as Map<String, Object?>;
    final ad = (page['ads']! as List<Object?>).single! as Map<String, Object?>;
    ad['url'] = 'https://example.org/track';
    expect(() => EditionDocument.fromJson(withUrl), throwsFormatException);
  });

  test('v2 keeps fixed-page geometry when the local ad is omitted', () async {
    final raw = jsonDecode(v2Source) as Map<String, Object?>;
    final page =
        (raw['pages']! as List<Object?>).single! as Map<String, Object?>;
    final placement =
        (page['placements']! as List<Object?>).single! as Map<String, Object?>;
    placement['role'] = 'brief';
    page['ads'] = <Object?>[];
    final document = EditionDocument.fromJson(raw);
    expect(document.pages.single.canvas.width, 700);
  });

  testWidgets('Gazete Modu ad is visibly labelled and has no tap action', (
    tester,
  ) async {
    final document = EditionDocument.parse(v2Source);
    await tester.pumpWidget(
      MaterialApp(
        home: SizedBox(
          width: 560,
          height: 80,
          child: PageAdView(ad: document.pages.single.ads.single),
        ),
      ),
    );
    expect(find.text('REKLAM'), findsOneWidget);
    expect(find.byType(GestureDetector), findsNothing);
  });

  testWidgets('actual app tree renders v2 modes and restores safely', (
    tester,
  ) async {
    final document = EditionDocument.parse(
      v2Source,
      assetResolver: (_) => 'assets/images/city-signals.png',
    );
    await tester.pumpWidget(
      ReaderProofApp(edition: document, sourceLauncher: _NoopLauncher()),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.byKey(const Key('page-ad-ad-page-1')), findsOneWidget);
    expect(find.text('350 × 500 mm sabit baskı'), findsOneWidget);

    await tester.tap(
      find.byKey(const Key('hit-page-1-page-1-hero-open_reading')),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.byKey(const Key('reading-feed-excerpt')), findsOneWidget);
    expect(find.byKey(const Key('reading-summary')), findsNothing);
    expect(find.text('REKLAM'), findsNothing);

    await tester.restartAndRestore();
    await tester.pump();
    expect(find.byKey(const Key('newspaper-mode')), findsOneWidget);
  });
}

final class _NoopLauncher implements SourceLauncher {
  @override
  Future<bool> open(Uri uri) async => true;
}
