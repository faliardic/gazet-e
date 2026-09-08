import 'package:flutter/material.dart';

import 'edition.dart';

class EditionAssetImage extends StatelessWidget {
  const EditionAssetImage({
    required this.visual,
    required this.fit,
    this.excludeFromSemantics = false,
    super.key,
  });

  final EditorialVisual visual;
  final BoxFit fit;
  final bool excludeFromSemantics;

  @override
  Widget build(BuildContext context) {
    final bytes = visual.assetBytes;
    if (bytes != null) {
      return Image.memory(
        bytes,
        fit: fit,
        excludeFromSemantics: excludeFromSemantics,
        gaplessPlayback: true,
      );
    }
    return Image.asset(
      visual.assetPath,
      fit: fit,
      excludeFromSemantics: excludeFromSemantics,
    );
  }
}
