import 'package:flutter/services.dart';

import 'edition.dart';
import 'fixture_asset_resolver.dart';

final class EditionRepository {
  EditionRepository({
    AssetBundle? bundle,
    this.fixtureAssetResolver = const FixtureAssetResolver(),
  }) : bundle = bundle ?? rootBundle;

  final AssetBundle bundle;
  final FixtureAssetResolver fixtureAssetResolver;

  Future<EditionDocument> loadFixture() async {
    final source = await bundle.loadString('assets/fixtures/edition.json');
    return EditionDocument.parse(
      source,
      assetResolver: fixtureAssetResolver.resolve,
    );
  }
}
