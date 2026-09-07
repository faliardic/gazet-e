import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:readerproof/edition.dart';
import 'package:readerproof/edition_repository.dart';
import 'package:readerproof/fixture_asset_resolver.dart';

import 'test_fixture.dart';

void main() {
  group('gazet-e.edition.v1 canonical contract', () {
    test('canonical fixture preserves production-shape fields', () async {
      final source = await loadFixtureSource();
      final document = EditionDocument.parse(
        source,
        assetResolver: const FixtureAssetResolver().resolve,
      );
      final article = document.articles['article-city-signals']!;

      expect(document.edition.state, 'ready');
      expect(document.edition.timezone, 'Europe/Istanbul');
      expect(document.edition.versions.editorialPolicy, isNotEmpty);
      expect(document.edition.versions.summaryPrompt, isNotEmpty);
      expect(document.edition.versions.visualBrief, isNotEmpty);
      expect(document.edition.versions.visualStyle, isNotEmpty);
      expect(document.edition.versions.layoutEngine, isNotEmpty);
      expect(document.pages.first.template.id, 'front');
      expect(document.pages.first.placements.first.zIndex, 1);
      expect(article.contentVersion, startsWith('sha256:'));
      expect(article.primarySource.publisherId, 'publisher-q03-fixture');
      expect(article.visual.width, 1536);
      expect(article.visual.height, 1024);
      expect(article.visual.provenance.generatedByAi, isTrue);
      expect(article.visual.provenance.provider, 'openai-imagegen');
      expect(article.visual.provenance.cacheKey, startsWith('sha256:'));
      expect(article.cache.summaryKey, startsWith('sha256:'));
      expect(article.cache.visualBriefKey, startsWith('sha256:'));
      expect(document.cache.editionKey, startsWith('sha256:'));
      expect(document.cache.layoutKey, startsWith('sha256:'));
      expect(
        () => document.pages.add(document.pages.first),
        throwsUnsupportedError,
      );
      expect(
        () => document.articles['another'] = article,
        throwsUnsupportedError,
      );
    });

    test('parse to JSON-ready serialization to parse is stable', () async {
      final first = EditionDocument.parse(await loadFixtureSource());
      final jsonReady = first.toJson();
      final serialized = jsonEncode(jsonReady);
      final second = EditionDocument.parse(serialized);

      expect(second.toJson(), equals(jsonReady));
      expect(second.pages.map((page) => page.order), [1, 2, 3]);
      expect(
        second.articles.values.first.primarySource.id,
        second.articles.values.first.primarySourceId,
      );
      expect(
        second.pages.first.placements.first.hitRegions.map(
          (region) => region.action,
        ),
        containsAll([HitAction.openReading, HitAction.openSource]),
      );
    });

    test('fixture asset resolution stays outside canonical JSON', () async {
      final source = await loadFixtureSource();
      expect(source, isNot(contains('asset_path')));
      expect(source, isNot(contains('assets/images/')));
      for (final forbiddenField in [
        'provider_secret',
        'api_key',
        'raw_prompt',
        'private_path',
        'signed_url',
        'raw_publisher_body',
        'publisher_body',
      ]) {
        expect(source, isNot(contains(forbiddenField)));
      }

      final unresolved = EditionDocument.parse(source);
      expect(
        () => unresolved.articles.values.first.visual.assetPath,
        throwsStateError,
      );

      final resolved = EditionDocument.parse(
        source,
        assetResolver: const FixtureAssetResolver().resolve,
      );
      expect(
        resolved.articles['article-city-signals']!.visual.assetPath,
        'assets/images/city-signals.png',
      );
      expect(
        () => const FixtureAssetResolver().resolve('asset_unknown'),
        throwsFormatException,
      );
    });

    test(
      'repository applies the fixture resolver at the client boundary',
      () async {
        final document = await EditionRepository().loadFixture();

        expect(
          document.articles['article-climate-city']!.visual.assetPath,
          'assets/images/climate-resilience.png',
        );
      },
    );

    test('rejects missing required edition and version fields', () async {
      await _expectRejected((json) {
        _edition(json).remove('requested_at');
      }, contains('requested_at is required'));
      await _expectRejected((json) {
        _versions(json).remove('layout_engine');
      }, contains('layout_engine is required'));
    });

    test('rejects non-ready canonical edition state', () async {
      await _expectRejected((json) {
        _edition(json)['state'] = 'generating';
      }, contains('state must be "ready"'));
    });

    test('rejects duplicate page ids and orders', () async {
      await _expectRejected((json) {
        _pages(json)[1]['id'] = _pages(json).first['id'];
      }, contains('Duplicate page id'));
      await _expectRejected((json) {
        _pages(json)[1]['order'] = _pages(json).first['order'];
      }, contains('Duplicate page order'));
    });

    test('rejects invalid and non-finite canvas values', () async {
      await _expectRejected((json) {
        _canvas(json)['width'] = 0;
      }, contains('must be positive'));
      await _expectRejected((json) {
        _canvas(json)['height'] = double.nan;
      }, contains('must be a finite number'));
    });

    test('rejects missing article reference and invalid rectangles', () async {
      await _expectRejected((json) {
        _firstPlacement(json)['article_id'] = 'article-missing';
      }, contains('references missing article'));
      await _expectRejected((json) {
        _rect(_firstPlacement(json))['x'] = 999;
      }, contains('must remain inside'));
      await _expectRejected((json) {
        _rect(_firstHit(json))['width'] = double.infinity;
      }, contains('must be a finite number'));
    });

    test('rejects duplicate placement and hit-region ids', () async {
      await _expectRejected((json) {
        final placements = _placements(json);
        placements[1]['id'] = placements.first['id'];
      }, contains('Duplicate placement id'));
      await _expectRejected((json) {
        final placements = _placements(json);
        _hits(placements[1]).first['id'] = _firstHit(json)['id'];
      }, contains('Duplicate hit region id'));
    });

    test('rejects unknown role, action and reading-body type', () async {
      await _expectRejected((json) {
        _firstPlacement(json)['role'] = 'card';
      }, contains('role "card" is unsupported'));
      await _expectRejected((json) {
        _firstHit(json)['action'] = 'open_webview';
      }, contains('action "open_webview" is unsupported'));
      await _expectRejected((json) {
        _readingBlocks(json).first['type'] = 'html';
      }, contains('type "html" is unsupported'));
    });

    test('requires distinct reading and source hit actions', () async {
      await _expectRejected((json) {
        _hits(
          _firstPlacement(json),
        ).removeWhere((hit) => hit['action'] == 'open_reading');
      }, contains('must define an open_reading'));
      await _expectRejected((json) {
        _hits(
          _firstPlacement(json),
        ).removeWhere((hit) => hit['action'] == 'open_source');
      }, contains('must define an open_source'));
    });

    test('rejects invalid article source truth', () async {
      await _expectRejected((json) {
        _firstArticle(json)['sources'] = <Object?>[];
      }, contains('sources must not be empty'));
      await _expectRejected((json) {
        _firstArticle(json)['primary_source_id'] = 'source-missing';
      }, contains('does not reference a source'));
      await _expectRejected((json) {
        _firstSource(json)['canonical_url'] = 'http://example.org/news';
      }, contains('canonical HTTPS URL'));
      await _expectRejected((json) {
        final sources = _sources(json);
        sources.add(Map<String, Object?>.from(sources.first));
      }, contains('Duplicate source id'));
    });

    test('keeps article, cluster and content identities distinct', () async {
      await _expectRejected((json) {
        final article = _firstArticle(json);
        article['cluster_id'] = article['id'];
      }, contains('must remain distinct'));
      await _expectRejected((json) {
        _firstArticle(json).remove('content_version');
      }, contains('content_version is required'));
    });

    test('requires visual metadata and provenance', () async {
      await _expectRejected((json) {
        _visual(json).remove('width');
      }, contains('width is required'));
      await _expectRejected((json) {
        _visual(json).remove('transparency_label');
      }, contains('transparency_label is required'));
      await _expectRejected((json) {
        _provenance(json).remove('model');
      }, contains('model is required'));
    });

    test('requires article and edition cache identities', () async {
      await _expectRejected((json) {
        _articleCache(json).remove('summary_key');
      }, contains('summary_key is required'));
      await _expectRejected((json) {
        _rootCache(json).remove('layout_key');
      }, contains('layout_key is required'));
      await _expectRejected((json) {
        _rootCache(json)['edition_key'] = 'not-a-hash';
      }, contains('lowercase SHA-256 identity'));
    });

    test(
      'rejects forbidden sensitive and raw-content fields anywhere',
      () async {
        for (final field in [
          'provider_secret',
          'raw_prompt',
          'private_path',
          'asset_path',
          'raw_publisher_body',
        ]) {
          await _expectRejected((json) {
            _firstArticle(json)[field] = 'must-not-cross-contract';
          }, contains('$field is forbidden'));
        }
      },
    );

    test(
      'rejects unspecified fields instead of silently accepting them',
      () async {
        await _expectRejected((json) {
          _firstArticle(json)['debug_metadata'] = true;
        }, contains('debug_metadata is unsupported'));
      },
    );
  });
}

Future<void> _expectRejected(
  void Function(Map<String, Object?> json) mutate,
  Matcher messageMatcher,
) async {
  final json = await _fixtureJson();
  mutate(json);
  expect(
    () => EditionDocument.fromJson(json),
    throwsA(
      isA<FormatException>().having(
        (error) => error.message,
        'message',
        messageMatcher,
      ),
    ),
  );
}

Future<Map<String, Object?>> _fixtureJson() async =>
    jsonDecode(await loadFixtureSource()) as Map<String, Object?>;

Map<String, Object?> _edition(Map<String, Object?> json) =>
    json['edition']! as Map<String, Object?>;

Map<String, Object?> _versions(Map<String, Object?> json) =>
    _edition(json)['versions']! as Map<String, Object?>;

List<Map<String, Object?>> _pages(Map<String, Object?> json) =>
    (json['pages']! as List<Object?>).cast<Map<String, Object?>>();

Map<String, Object?> _canvas(Map<String, Object?> json) =>
    _pages(json).first['canvas']! as Map<String, Object?>;

List<Map<String, Object?>> _placements(Map<String, Object?> json) =>
    (_pages(json).first['placements']! as List<Object?>)
        .cast<Map<String, Object?>>();

Map<String, Object?> _firstPlacement(Map<String, Object?> json) =>
    _placements(json).first;

List<Map<String, Object?>> _hits(Map<String, Object?> placement) =>
    (placement['hit_regions']! as List<Object?>).cast<Map<String, Object?>>();

Map<String, Object?> _firstHit(Map<String, Object?> json) =>
    _hits(_firstPlacement(json)).first;

Map<String, Object?> _rect(Map<String, Object?> owner) =>
    owner['rect']! as Map<String, Object?>;

List<Map<String, Object?>> _articles(Map<String, Object?> json) =>
    (json['articles']! as List<Object?>).cast<Map<String, Object?>>();

Map<String, Object?> _firstArticle(Map<String, Object?> json) =>
    _articles(json).first;

List<Map<String, Object?>> _readingBlocks(Map<String, Object?> json) =>
    (_firstArticle(json)['reading_body']! as List<Object?>)
        .cast<Map<String, Object?>>();

List<Map<String, Object?>> _sources(Map<String, Object?> json) =>
    (_firstArticle(json)['sources']! as List<Object?>)
        .cast<Map<String, Object?>>();

Map<String, Object?> _firstSource(Map<String, Object?> json) =>
    _sources(json).first;

Map<String, Object?> _visual(Map<String, Object?> json) =>
    _firstArticle(json)['visual']! as Map<String, Object?>;

Map<String, Object?> _provenance(Map<String, Object?> json) =>
    _visual(json)['provenance']! as Map<String, Object?>;

Map<String, Object?> _articleCache(Map<String, Object?> json) =>
    _firstArticle(json)['cache']! as Map<String, Object?>;

Map<String, Object?> _rootCache(Map<String, Object?> json) =>
    json['cache']! as Map<String, Object?>;
