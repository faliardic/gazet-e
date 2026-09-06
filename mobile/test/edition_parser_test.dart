import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:readerproof/edition.dart';

import 'test_fixture.dart';

void main() {
  group('Q03 edition fixture parser', () {
    test('parses bundled fixture with three ordered pages', () async {
      final edition = await loadTestEdition();

      expect(edition.contractVersion, supportedContractVersion);
      expect(edition.edition.masthead, 'GAZET+E');
      expect(edition.pages.map((page) => page.order), [1, 2, 3]);
      expect(edition.pages.map((page) => page.id), [
        'front',
        'climate',
        'technology',
      ]);
      expect(
        edition.pages
            .expand((page) => page.placements)
            .map((item) => item.role),
        containsAll(PlacementRole.values),
      );
    });

    test('rejects unsupported contract version clearly', () async {
      final json = await _fixtureJson();
      json['contract_version'] = 'gazet-e.edition.v99';

      expect(
        () => EditionDocument.fromJson(json),
        throwsA(
          isA<FormatException>().having(
            (error) => error.message,
            'message',
            contains('Unsupported contract_version'),
          ),
        ),
      );
    });

    test('rejects placement with broken article reference', () async {
      final json = await _fixtureJson();
      final pages = json['pages']! as List<Object?>;
      final firstPage = pages.first! as Map<String, Object?>;
      final placements = firstPage['placements']! as List<Object?>;
      final firstPlacement = placements.first! as Map<String, Object?>;
      firstPlacement['article_id'] = 'missing-article';

      expect(
        () => EditionDocument.fromJson(json),
        throwsA(
          isA<FormatException>().having(
            (error) => error.message,
            'message',
            contains('references missing article'),
          ),
        ),
      );
    });

    test('rejects out-of-canvas placement rectangle', () async {
      final json = await _fixtureJson();
      final pages = json['pages']! as List<Object?>;
      final firstPage = pages.first! as Map<String, Object?>;
      final placements = firstPage['placements']! as List<Object?>;
      final firstPlacement = placements.first! as Map<String, Object?>;
      final rect = firstPlacement['rect']! as Map<String, Object?>;
      rect['x'] = 950;

      expect(
        () => EditionDocument.fromJson(json),
        throwsA(
          isA<FormatException>().having(
            (error) => error.message,
            'message',
            contains('must remain inside'),
          ),
        ),
      );
    });

    test('rejects invalid negative hit rectangle', () async {
      final json = await _fixtureJson();
      final pages = json['pages']! as List<Object?>;
      final firstPage = pages.first! as Map<String, Object?>;
      final placements = firstPage['placements']! as List<Object?>;
      final firstPlacement = placements.first! as Map<String, Object?>;
      final regions = firstPlacement['hit_regions']! as List<Object?>;
      final firstRegion = regions.first! as Map<String, Object?>;
      final rect = firstRegion['rect']! as Map<String, Object?>;
      rect['y'] = -1;

      expect(
        () => EditionDocument.fromJson(json),
        throwsA(
          isA<FormatException>().having(
            (error) => error.message,
            'message',
            contains('must be non-negative'),
          ),
        ),
      );
    });
  });
}

Future<Map<String, Object?>> _fixtureJson() async {
  return jsonDecode(await loadFixtureSource()) as Map<String, Object?>;
}
