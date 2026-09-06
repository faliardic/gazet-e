import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:readerproof/edition.dart';

Future<String> loadFixtureSource() async {
  TestWidgetsFlutterBinding.ensureInitialized();
  return rootBundle.loadString('assets/fixtures/edition.json');
}

Future<EditionDocument> loadTestEdition() async {
  return EditionDocument.parse(await loadFixtureSource());
}
