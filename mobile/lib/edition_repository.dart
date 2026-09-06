import 'package:flutter/services.dart';

import 'edition.dart';

final class EditionRepository {
  EditionRepository({AssetBundle? bundle}) : bundle = bundle ?? rootBundle;

  final AssetBundle bundle;

  Future<EditionDocument> loadFixture() async {
    final source = await bundle.loadString('assets/fixtures/edition.json');
    return EditionDocument.parse(source);
  }
}
