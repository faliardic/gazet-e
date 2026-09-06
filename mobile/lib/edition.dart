import 'dart:convert';
import 'dart:ui';

const supportedContractVersion = 'gazet-e.edition.v1';

final class EditionDocument {
  EditionDocument({
    required this.contractVersion,
    required this.edition,
    required this.pages,
    required this.articles,
  });

  final String contractVersion;
  final EditionMetadata edition;
  final List<NewspaperPage> pages;
  final Map<String, Article> articles;

  Article articleById(String id) => articles[id]!;

  static EditionDocument parse(String source) {
    final Object? decoded;
    try {
      decoded = jsonDecode(source);
    } on FormatException catch (error) {
      throw FormatException(
        'Edition fixture is not valid JSON: ${error.message}',
      );
    }
    return EditionDocument.fromJson(_map(decoded, r'$'));
  }

  factory EditionDocument.fromJson(Map<String, Object?> json) {
    final contractVersion = _string(
      json['contract_version'],
      'contract_version',
    );
    if (contractVersion != supportedContractVersion) {
      throw FormatException(
        'Unsupported contract_version "$contractVersion"; expected '
        '"$supportedContractVersion".',
      );
    }

    final edition = EditionMetadata.fromJson(
      _map(json['edition'], 'edition'),
      'edition',
    );

    final articleList = _list(json['articles'], 'articles');
    if (articleList.isEmpty) {
      throw const FormatException('articles must not be empty.');
    }
    final articles = <String, Article>{};
    for (var index = 0; index < articleList.length; index++) {
      final article = Article.fromJson(
        _map(articleList[index], 'articles[$index]'),
        'articles[$index]',
      );
      if (articles.containsKey(article.id)) {
        throw FormatException('Duplicate article id "${article.id}".');
      }
      articles[article.id] = article;
    }

    final pageList = _list(json['pages'], 'pages');
    if (pageList.length < 3) {
      throw const FormatException('Q03 fixture must contain at least 3 pages.');
    }
    final pages = <NewspaperPage>[];
    final pageIds = <String>{};
    var previousOrder = 0;
    for (var index = 0; index < pageList.length; index++) {
      final page = NewspaperPage.fromJson(
        _map(pageList[index], 'pages[$index]'),
        'pages[$index]',
      );
      if (!pageIds.add(page.id)) {
        throw FormatException('Duplicate page id "${page.id}".');
      }
      if (page.order <= previousOrder) {
        throw const FormatException(
          'pages must be stored in strictly increasing order.',
        );
      }
      previousOrder = page.order;

      for (final placement in page.placements) {
        if (!articles.containsKey(placement.articleId)) {
          throw FormatException(
            'Placement "${placement.id}" references missing article '
            '"${placement.articleId}".',
          );
        }
        final actions = placement.hitRegions
            .map((region) => region.action)
            .toSet();
        if (!actions.contains(HitAction.openReading) ||
            !actions.contains(HitAction.openSource)) {
          throw FormatException(
            'Placement "${placement.id}" must define distinct open_reading '
            'and open_source hit regions.',
          );
        }
      }
      pages.add(page);
    }

    return EditionDocument(
      contractVersion: contractVersion,
      edition: edition,
      pages: List.unmodifiable(pages),
      articles: Map.unmodifiable(articles),
    );
  }
}

final class EditionMetadata {
  const EditionMetadata({
    required this.id,
    required this.title,
    required this.generatedAt,
    required this.locale,
    required this.brandName,
    required this.masthead,
  });

  final String id;
  final String title;
  final DateTime generatedAt;
  final String locale;
  final String brandName;
  final String masthead;

  factory EditionMetadata.fromJson(Map<String, Object?> json, String path) {
    final generatedAtText = _string(json['generated_at'], '$path.generated_at');
    final generatedAt = DateTime.tryParse(generatedAtText);
    if (generatedAt == null) {
      throw FormatException(
        '$path.generated_at must be an ISO-8601 timestamp.',
      );
    }
    final brand = _map(json['brand'], '$path.brand');
    final brandName = _string(brand['name'], '$path.brand.name');
    final masthead = _string(brand['masthead'], '$path.brand.masthead');
    if (brandName != 'Gazet+E' || masthead != 'GAZET+E') {
      throw FormatException('$path.brand must identify Gazet+E / GAZET+E.');
    }
    return EditionMetadata(
      id: _string(json['id'], '$path.id'),
      title: _string(json['title'], '$path.title'),
      generatedAt: generatedAt,
      locale: _string(json['locale'], '$path.locale'),
      brandName: brandName,
      masthead: masthead,
    );
  }
}

final class NewspaperPage {
  const NewspaperPage({
    required this.id,
    required this.order,
    required this.label,
    required this.section,
    required this.canvas,
    required this.placements,
  });

  final String id;
  final int order;
  final String label;
  final String section;
  final CanvasSpec canvas;
  final List<Placement> placements;

  factory NewspaperPage.fromJson(Map<String, Object?> json, String path) {
    final canvas = CanvasSpec.fromJson(
      _map(json['canvas'], '$path.canvas'),
      '$path.canvas',
    );
    final rawPlacements = _list(json['placements'], '$path.placements');
    if (rawPlacements.isEmpty) {
      throw FormatException('$path.placements must not be empty.');
    }
    final placements = <Placement>[];
    final placementIds = <String>{};
    for (var index = 0; index < rawPlacements.length; index++) {
      final placementPath = '$path.placements[$index]';
      final placement = Placement.fromJson(
        _map(rawPlacements[index], placementPath),
        placementPath,
        canvas,
      );
      if (!placementIds.add(placement.id)) {
        throw FormatException('Duplicate placement id "${placement.id}".');
      }
      placements.add(placement);
    }
    return NewspaperPage(
      id: _string(json['id'], '$path.id'),
      order: _positiveInt(json['order'], '$path.order'),
      label: _string(json['label'], '$path.label'),
      section: _string(json['section'], '$path.section'),
      canvas: canvas,
      placements: List.unmodifiable(placements),
    );
  }
}

final class CanvasSpec {
  const CanvasSpec({
    required this.width,
    required this.height,
    required this.unit,
  });

  final double width;
  final double height;
  final String unit;

  factory CanvasSpec.fromJson(Map<String, Object?> json, String path) {
    final width = _positiveNumber(json['width'], '$path.width');
    final height = _positiveNumber(json['height'], '$path.height');
    final unit = _string(json['unit'], '$path.unit');
    if (unit != 'logical') {
      throw FormatException('$path.unit must be "logical".');
    }
    return CanvasSpec(width: width, height: height, unit: unit);
  }
}

enum PlacementRole { hero, secondary, brief }

enum HitAction { openReading, openSource }

final class Placement {
  const Placement({
    required this.id,
    required this.articleId,
    required this.role,
    required this.rect,
    required this.hitRegions,
  });

  final String id;
  final String articleId;
  final PlacementRole role;
  final RectSpec rect;
  final List<HitRegion> hitRegions;

  factory Placement.fromJson(
    Map<String, Object?> json,
    String path,
    CanvasSpec canvas,
  ) {
    final roleText = _string(json['role'], '$path.role');
    final role = switch (roleText) {
      'hero' => PlacementRole.hero,
      'secondary' => PlacementRole.secondary,
      'brief' => PlacementRole.brief,
      _ => throw FormatException('$path.role "$roleText" is unsupported.'),
    };
    final rect = RectSpec.fromJson(
      _map(json['rect'], '$path.rect'),
      '$path.rect',
    );
    rect.validateInside(canvas, '$path.rect');

    final rawRegions = _list(json['hit_regions'], '$path.hit_regions');
    if (rawRegions.isEmpty) {
      throw FormatException('$path.hit_regions must not be empty.');
    }
    final regions = <HitRegion>[];
    for (var index = 0; index < rawRegions.length; index++) {
      final regionPath = '$path.hit_regions[$index]';
      final region = HitRegion.fromJson(
        _map(rawRegions[index], regionPath),
        regionPath,
      );
      region.rect.validateInside(canvas, '$regionPath.rect');
      regions.add(region);
    }
    return Placement(
      id: _string(json['id'], '$path.id'),
      articleId: _string(json['article_id'], '$path.article_id'),
      role: role,
      rect: rect,
      hitRegions: List.unmodifiable(regions),
    );
  }
}

final class HitRegion {
  const HitRegion({
    required this.id,
    required this.action,
    required this.rect,
    required this.accessibilityLabel,
  });

  final String id;
  final HitAction action;
  final RectSpec rect;
  final String accessibilityLabel;

  factory HitRegion.fromJson(Map<String, Object?> json, String path) {
    final actionText = _string(json['action'], '$path.action');
    final action = switch (actionText) {
      'open_reading' => HitAction.openReading,
      'open_source' => HitAction.openSource,
      _ => throw FormatException('$path.action "$actionText" is unsupported.'),
    };
    return HitRegion(
      id: _string(json['id'], '$path.id'),
      action: action,
      rect: RectSpec.fromJson(_map(json['rect'], '$path.rect'), '$path.rect'),
      accessibilityLabel: _string(
        json['accessibility_label'],
        '$path.accessibility_label',
      ),
    );
  }
}

final class RectSpec {
  const RectSpec({
    required this.x,
    required this.y,
    required this.width,
    required this.height,
  });

  final double x;
  final double y;
  final double width;
  final double height;

  Rect get rect => Rect.fromLTWH(x, y, width, height);

  factory RectSpec.fromJson(Map<String, Object?> json, String path) {
    return RectSpec(
      x: _nonNegativeNumber(json['x'], '$path.x'),
      y: _nonNegativeNumber(json['y'], '$path.y'),
      width: _positiveNumber(json['width'], '$path.width'),
      height: _positiveNumber(json['height'], '$path.height'),
    );
  }

  void validateInside(CanvasSpec canvas, String path) {
    if (x + width > canvas.width || y + height > canvas.height) {
      throw FormatException(
        '$path must remain inside ${canvas.width}×${canvas.height} canvas.',
      );
    }
  }
}

final class Article {
  const Article({
    required this.id,
    required this.clusterId,
    required this.headline,
    required this.dek,
    required this.summary,
    required this.readingBody,
    required this.primarySource,
    required this.visual,
  });

  final String id;
  final String clusterId;
  final String headline;
  final String dek;
  final String summary;
  final List<String> readingBody;
  final ArticleSource primarySource;
  final EditorialVisual visual;

  factory Article.fromJson(Map<String, Object?> json, String path) {
    final rawSources = _list(json['sources'], '$path.sources');
    if (rawSources.isEmpty) {
      throw FormatException('$path.sources must not be empty.');
    }
    final sources = <ArticleSource>[];
    for (var index = 0; index < rawSources.length; index++) {
      sources.add(
        ArticleSource.fromJson(
          _map(rawSources[index], '$path.sources[$index]'),
          '$path.sources[$index]',
        ),
      );
    }
    final primarySourceId = _string(
      json['primary_source_id'],
      '$path.primary_source_id',
    );
    ArticleSource? primarySource;
    for (final source in sources) {
      if (source.id == primarySourceId) {
        primarySource = source;
        break;
      }
    }
    if (primarySource == null) {
      throw FormatException(
        '$path.primary_source_id "$primarySourceId" does not reference a source.',
      );
    }

    final rawBody = _list(json['reading_body'], '$path.reading_body');
    if (rawBody.isEmpty) {
      throw FormatException('$path.reading_body must not be empty.');
    }
    final body = <String>[];
    for (var index = 0; index < rawBody.length; index++) {
      final paragraph = _map(rawBody[index], '$path.reading_body[$index]');
      if (_string(paragraph['type'], '$path.reading_body[$index].type') !=
          'paragraph') {
        throw FormatException(
          '$path.reading_body[$index].type is unsupported.',
        );
      }
      body.add(_string(paragraph['text'], '$path.reading_body[$index].text'));
    }

    return Article(
      id: _string(json['id'], '$path.id'),
      clusterId: _string(json['cluster_id'], '$path.cluster_id'),
      headline: _string(json['headline'], '$path.headline'),
      dek: _string(json['dek'], '$path.dek'),
      summary: _string(json['summary'], '$path.summary'),
      readingBody: List.unmodifiable(body),
      primarySource: primarySource,
      visual: EditorialVisual.fromJson(
        _map(json['visual'], '$path.visual'),
        '$path.visual',
      ),
    );
  }
}

final class ArticleSource {
  const ArticleSource({
    required this.id,
    required this.name,
    required this.canonicalUrl,
    required this.publishedAt,
  });

  final String id;
  final String name;
  final Uri canonicalUrl;
  final DateTime? publishedAt;

  factory ArticleSource.fromJson(Map<String, Object?> json, String path) {
    final rawUrl = _string(json['canonical_url'], '$path.canonical_url');
    final url = Uri.tryParse(rawUrl);
    if (url == null || url.scheme != 'https' || url.host.isEmpty) {
      throw FormatException(
        '$path.canonical_url must be a canonical HTTPS URL.',
      );
    }
    final rawPublishedAt = json['published_at'];
    DateTime? publishedAt;
    if (rawPublishedAt != null) {
      final text = _string(rawPublishedAt, '$path.published_at');
      publishedAt = DateTime.tryParse(text);
      if (publishedAt == null) {
        throw FormatException(
          '$path.published_at must be an ISO-8601 timestamp.',
        );
      }
    }
    return ArticleSource(
      id: _string(json['id'], '$path.id'),
      name: _string(json['name'], '$path.name'),
      canonicalUrl: url,
      publishedAt: publishedAt,
    );
  }
}

final class EditorialVisual {
  const EditorialVisual({
    required this.assetPath,
    required this.alt,
    required this.transparencyLabel,
    required this.generatedByAi,
    required this.safetyClass,
  });

  final String assetPath;
  final String alt;
  final String transparencyLabel;
  final bool generatedByAi;
  final String safetyClass;

  factory EditorialVisual.fromJson(Map<String, Object?> json, String path) {
    final assetPath = _string(json['asset_path'], '$path.asset_path');
    if (!assetPath.startsWith('assets/images/')) {
      throw FormatException('$path.asset_path must reference a bundled image.');
    }
    final generatedByAi = json['generated_by_ai'];
    if (generatedByAi is! bool) {
      throw FormatException('$path.generated_by_ai must be a boolean.');
    }
    return EditorialVisual(
      assetPath: assetPath,
      alt: _string(json['alt'], '$path.alt'),
      transparencyLabel: _string(
        json['transparency_label'],
        '$path.transparency_label',
      ),
      generatedByAi: generatedByAi,
      safetyClass: _string(json['safety_class'], '$path.safety_class'),
    );
  }
}

Map<String, Object?> _map(Object? value, String path) {
  if (value is! Map<String, Object?>) {
    throw FormatException('$path must be an object.');
  }
  return value;
}

List<Object?> _list(Object? value, String path) {
  if (value is! List<Object?>) {
    throw FormatException('$path must be an array.');
  }
  return value;
}

String _string(Object? value, String path) {
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$path must be a non-empty string.');
  }
  return value;
}

double _number(Object? value, String path) {
  if (value is! num || !value.isFinite) {
    throw FormatException('$path must be a finite number.');
  }
  return value.toDouble();
}

double _positiveNumber(Object? value, String path) {
  final number = _number(value, path);
  if (number <= 0) {
    throw FormatException('$path must be positive.');
  }
  return number;
}

double _nonNegativeNumber(Object? value, String path) {
  final number = _number(value, path);
  if (number < 0) {
    throw FormatException('$path must be non-negative.');
  }
  return number;
}

int _positiveInt(Object? value, String path) {
  if (value is! int || value <= 0) {
    throw FormatException('$path must be a positive integer.');
  }
  return value;
}
