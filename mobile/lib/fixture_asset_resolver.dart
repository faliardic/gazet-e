final class FixtureAssetResolver {
  const FixtureAssetResolver();

  static const _bundledAssets = {
    'asset_city_signals': 'assets/images/city-signals.png',
    'asset_climate_resilience': 'assets/images/climate-resilience.png',
    'asset_civic_technology': 'assets/images/civic-technology.png',
  };

  String resolve(String assetId) {
    final path = _bundledAssets[assetId];
    if (path == null) {
      throw FormatException(
        'Fixture asset_id "$assetId" has no bundled proof asset.',
      );
    }
    return path;
  }
}
