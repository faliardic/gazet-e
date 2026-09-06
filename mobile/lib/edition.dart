import 'dart:convert';
import 'dart:ui';

const supportedContractVersion = 'gazet-e.edition.v1';

typedef EditionAssetPathResolver = String? Function(String assetId);

final class EditionDocument {
  EditionDocument({
    required this.contractVersion,
    required this.edition,
    required this.pages,
    required this.articles,
    required this.cache,
  });

  final String contractVersion;
  final EditionMetadata edition;
  final List<NewspaperPage> pages;
  final Map<String, Article> articles;
  final EditionCache cache;

  Article articleById(String id) => articles[id]!;

  static EditionDocument parse(
    String source, {
    EditionAssetPathResolver? assetResolver,
  }) {
    final Object? decoded;
    try {
      decoded = jsonDecode(source);
    } on FormatException catch (error) {
      throw FormatException(
        'Edition document is not valid JSON: ${error.message}',
      );
    }
    return EditionDocument.fromJson(
      _map(decoded, r'$'),
      assetResolver: assetResolver,
    );
  }

  factory EditionDocument.fromJson(
    Map<String, Object?> json, {
    EditionAssetPathResolver? assetResolver,
  }) {
    _rejectForbiddenFields(json, r'$');
    _expectKeys(json, r'$', {
      'contract_version',
      'edition',
      'pages',
      'articles',
      'cache',
    });

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
        assetResolver: assetResolver,
      );
      if (articles.containsKey(article.id)) {
        throw FormatException('Duplicate article id "${article.id}".');
      }
      articles[article.id] = article;
    }

    final pageList = _list(json['pages'], 'pages');
    if (pageList.isEmpty) {
      throw const FormatException('pages must not be empty.');
    }
    final pages = <NewspaperPage>[];
    final pageIds = <String>{};
    final pageOrders = <int>{};
    var previousOrder = 0;
    for (var index = 0; index < pageList.length; index++) {
      final page = NewspaperPage.fromJson(
        _map(pageList[index], 'pages[$index]'),
        'pages[$index]',
      );
      if (!pageIds.add(page.id)) {
        throw FormatException('Duplicate page id "${page.id}".');
      }
      if (!pageOrders.add(page.order)) {
        throw FormatException('Duplicate page order "${page.order}".');
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
        if (!actions.contains(HitAction.openReading)) {
          throw FormatException(
            'Placement "${placement.id}" must define an open_reading '
            'hit region.',
          );
        }
        if (!actions.contains(HitAction.openSource)) {
          throw FormatException(
            'Placement "${placement.id}" exposes source truth and must '
            'define an open_source hit region.',
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
      cache: EditionCache.fromJson(_map(json['cache'], 'cache'), 'cache'),
    );
  }

  Map<String, Object?> toJson() => {
    'contract_version': contractVersion,
    'edition': edition.toJson(),
    'pages': pages.map((page) => page.toJson()).toList(growable: false),
    'articles': articles.values
        .map((article) => article.toJson())
        .toList(growable: false),
    'cache': cache.toJson(),
  };
}

final class EditionMetadata {
  const EditionMetadata({
    required this.id,
    required this.state,
    required this.title,
    required this.requestedAt,
    required this.generatedAt,
    required this.locale,
    required this.timezone,
    required this.brandName,
    required this.masthead,
    required this.versions,
  });

  final String id;
  final String state;
  final String title;
  final DateTime requestedAt;
  final DateTime generatedAt;
  final String locale;
  final String timezone;
  final String brandName;
  final String masthead;
  final EditionVersions versions;

  factory EditionMetadata.fromJson(Map<String, Object?> json, String path) {
    _expectKeys(json, path, {
      'id',
      'state',
      'title',
      'requested_at',
      'generated_at',
      'locale',
      'timezone',
      'brand',
      'versions',
    });
    final state = _string(json['state'], '$path.state');
    if (state != 'ready') {
      throw FormatException('$path.state must be "ready".');
    }
    final brand = _map(json['brand'], '$path.brand');
    _expectKeys(brand, '$path.brand', {'name', 'masthead'});
    final brandName = _string(brand['name'], '$path.brand.name');
    final masthead = _string(brand['masthead'], '$path.brand.masthead');
    if (brandName != 'Gazet+E' || masthead != 'GAZET+E') {
      throw FormatException('$path.brand must identify Gazet+E / GAZET+E.');
    }
    final requestedAt = _timestamp(json['requested_at'], '$path.requested_at');
    final generatedAt = _timestamp(json['generated_at'], '$path.generated_at');
    if (generatedAt.isBefore(requestedAt)) {
      throw FormatException(
        '$path.generated_at must not precede requested_at.',
      );
    }
    return EditionMetadata(
      id: _string(json['id'], '$path.id'),
      state: state,
      title: _string(json['title'], '$path.title'),
      requestedAt: requestedAt,
      generatedAt: generatedAt,
      locale: _string(json['locale'], '$path.locale'),
      timezone: _string(json['timezone'], '$path.timezone'),
      brandName: brandName,
      masthead: masthead,
      versions: EditionVersions.fromJson(
        _map(json['versions'], '$path.versions'),
        '$path.versions',
      ),
    );
  }

  Map<String, Object?> toJson() => {
    'id': id,
    'state': state,
    'title': title,
    'requested_at': _timestampJson(requestedAt),
    'generated_at': _timestampJson(generatedAt),
    'locale': locale,
    'timezone': timezone,
    'brand': {'name': brandName, 'masthead': masthead},
    'versions': versions.toJson(),
  };
}

final class EditionVersions {
  const EditionVersions({
    required this.editorialPolicy,
    required this.summaryPrompt,
    required this.visualBrief,
    required this.visualStyle,
    required this.layoutEngine,
  });

  final String editorialPolicy;
  final String summaryPrompt;
  final String visualBrief;
  final String visualStyle;
  final String layoutEngine;

  factory EditionVersions.fromJson(Map<String, Object?> json, String path) {
    _expectKeys(json, path, {
      'editorial_policy',
      'summary_prompt',
      'visual_brief',
      'visual_style',
      'layout_engine',
    });
    return EditionVersions(
      editorialPolicy: _string(
        json['editorial_policy'],
        '$path.editorial_policy',
      ),
      summaryPrompt: _string(json['summary_prompt'], '$path.summary_prompt'),
      visualBrief: _string(json['visual_brief'], '$path.visual_brief'),
      visualStyle: _string(json['visual_style'], '$path.visual_style'),
      layoutEngine: _string(json['layout_engine'], '$path.layout_engine'),
    );
  }

  Map<String, Object?> toJson() => {
    'editorial_policy': editorialPolicy,
    'summary_prompt': summaryPrompt,
    'visual_brief': visualBrief,
    'visual_style': visualStyle,
    'layout_engine': layoutEngine,
  };
}

final class NewspaperPage {
  const NewspaperPage({
    required this.id,
    required this.order,
    required this.label,
    required this.section,
    required this.canvas,
    required this.template,
    required this.placements,
  });

  final String id;
  final int order;
  final String label;
  final String section;
  final CanvasSpec canvas;
  final TemplateSpec template;
  final List<Placement> placements;

  factory NewspaperPage.fromJson(Map<String, Object?> json, String path) {
    _expectKeys(json, path, {
      'id',
      'order',
      'label',
      'section',
      'canvas',
      'template',
      'placements',
    });
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
    final hitIds = <String>{};
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
      for (final hit in placement.hitRegions) {
        if (!hitIds.add(hit.id)) {
          throw FormatException('Duplicate hit region id "${hit.id}".');
        }
      }
      placements.add(placement);
    }
    return NewspaperPage(
      id: _string(json['id'], '$path.id'),
      order: _positiveInt(json['order'], '$path.order'),
      label: _string(json['label'], '$path.label'),
      section: _string(json['section'], '$path.section'),
      canvas: canvas,
      template: TemplateSpec.fromJson(
        _map(json['template'], '$path.template'),
        '$path.template',
      ),
      placements: List.unmodifiable(placements),
    );
  }

  Map<String, Object?> toJson() => {
    'id': id,
    'order': order,
    'label': label,
    'section': section,
    'canvas': canvas.toJson(),
    'template': template.toJson(),
    'placements': placements
        .map((placement) => placement.toJson())
        .toList(growable: false),
  };
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
    _expectKeys(json, path, {'width', 'height', 'unit'});
    final width = _positiveNumber(json['width'], '$path.width');
    final height = _positiveNumber(json['height'], '$path.height');
    final unit = _string(json['unit'], '$path.unit');
    if (unit != 'logical') {
      throw FormatException('$path.unit must be "logical".');
    }
    return CanvasSpec(width: width, height: height, unit: unit);
  }

  Map<String, Object?> toJson() => {
    'width': width,
    'height': height,
    'unit': unit,
  };
}

final class TemplateSpec {
  const TemplateSpec({required this.id, required this.version});

  final String id;
  final String version;

  factory TemplateSpec.fromJson(Map<String, Object?> json, String path) {
    _expectKeys(json, path, {'id', 'version'});
    return TemplateSpec(
      id: _string(json['id'], '$path.id'),
      version: _string(json['version'], '$path.version'),
    );
  }

  Map<String, Object?> toJson() => {'id': id, 'version': version};
}

enum PlacementRole { hero, secondary, brief }

enum HitAction { openReading, openSource }

final class Placement {
  const Placement({
    required this.id,
    required this.articleId,
    required this.role,
    required this.rect,
    required this.zIndex,
    required this.hitRegions,
  });

  final String id;
  final String articleId;
  final PlacementRole role;
  final RectSpec rect;
  final int zIndex;
  final List<HitRegion> hitRegions;

  factory Placement.fromJson(
    Map<String, Object?> json,
    String path,
    CanvasSpec canvas,
  ) {
    _expectKeys(json, path, {
      'id',
      'article_id',
      'role',
      'rect',
      'z_index',
      'hit_regions',
    });
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
      zIndex: _nonNegativeInt(json['z_index'], '$path.z_index'),
      hitRegions: List.unmodifiable(regions),
    );
  }

  Map<String, Object?> toJson() => {
    'id': id,
    'article_id': articleId,
    'role': role.wireName,
    'rect': rect.toJson(),
    'z_index': zIndex,
    'hit_regions': hitRegions
        .map((region) => region.toJson())
        .toList(growable: false),
  };
}

extension on PlacementRole {
  String get wireName => switch (this) {
    PlacementRole.hero => 'hero',
    PlacementRole.secondary => 'secondary',
    PlacementRole.brief => 'brief',
  };
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
    _expectKeys(json, path, {'id', 'action', 'rect', 'accessibility_label'});
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

  Map<String, Object?> toJson() => {
    'id': id,
    'action': action.wireName,
    'rect': rect.toJson(),
    'accessibility_label': accessibilityLabel,
  };
}

extension on HitAction {
  String get wireName => switch (this) {
    HitAction.openReading => 'open_reading',
    HitAction.openSource => 'open_source',
  };
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
    _expectKeys(json, path, {'x', 'y', 'width', 'height'});
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

  Map<String, Object?> toJson() => {
    'x': x,
    'y': y,
    'width': width,
    'height': height,
  };
}

final class Article {
  const Article({
    required this.id,
    required this.clusterId,
    required this.contentVersion,
    required this.headline,
    required this.dek,
    required this.summary,
    required this.readingBlocks,
    required this.primarySourceId,
    required this.sources,
    required this.visual,
    required this.cache,
  });

  final String id;
  final String clusterId;
  final String contentVersion;
  final String headline;
  final String dek;
  final String summary;
  final List<ReadingBlock> readingBlocks;
  final String primarySourceId;
  final List<ArticleSource> sources;
  final EditorialVisual visual;
  final ArticleCache cache;

  List<String> get readingBody =>
      List.unmodifiable(readingBlocks.map((block) => block.text));

  ArticleSource get primarySource =>
      sources.firstWhere((source) => source.id == primarySourceId);

  factory Article.fromJson(
    Map<String, Object?> json,
    String path, {
    EditionAssetPathResolver? assetResolver,
  }) {
    _expectKeys(json, path, {
      'id',
      'cluster_id',
      'content_version',
      'headline',
      'dek',
      'summary',
      'reading_body',
      'primary_source_id',
      'sources',
      'visual',
      'cache',
    });
    final id = _string(json['id'], '$path.id');
    final clusterId = _string(json['cluster_id'], '$path.cluster_id');
    final contentVersion = _sha256(
      json['content_version'],
      '$path.content_version',
    );
    if (id == clusterId ||
        id == contentVersion ||
        clusterId == contentVersion) {
      throw FormatException(
        '$path id, cluster_id and content_version must remain distinct.',
      );
    }

    final rawSources = _list(json['sources'], '$path.sources');
    if (rawSources.isEmpty) {
      throw FormatException('$path.sources must not be empty.');
    }
    final sources = <ArticleSource>[];
    final sourceIds = <String>{};
    for (var index = 0; index < rawSources.length; index++) {
      final source = ArticleSource.fromJson(
        _map(rawSources[index], '$path.sources[$index]'),
        '$path.sources[$index]',
      );
      if (!sourceIds.add(source.id)) {
        throw FormatException('Duplicate source id "${source.id}" in $path.');
      }
      sources.add(source);
    }
    final primarySourceId = _string(
      json['primary_source_id'],
      '$path.primary_source_id',
    );
    if (!sourceIds.contains(primarySourceId)) {
      throw FormatException(
        '$path.primary_source_id "$primarySourceId" does not reference a '
        'source.',
      );
    }

    final rawBody = _list(json['reading_body'], '$path.reading_body');
    if (rawBody.isEmpty) {
      throw FormatException('$path.reading_body must not be empty.');
    }
    final readingBlocks = <ReadingBlock>[];
    for (var index = 0; index < rawBody.length; index++) {
      readingBlocks.add(
        ReadingBlock.fromJson(
          _map(rawBody[index], '$path.reading_body[$index]'),
          '$path.reading_body[$index]',
        ),
      );
    }

    return Article(
      id: id,
      clusterId: clusterId,
      contentVersion: contentVersion,
      headline: _string(json['headline'], '$path.headline'),
      dek: _string(json['dek'], '$path.dek'),
      summary: _string(json['summary'], '$path.summary'),
      readingBlocks: List.unmodifiable(readingBlocks),
      primarySourceId: primarySourceId,
      sources: List.unmodifiable(sources),
      visual: EditorialVisual.fromJson(
        _map(json['visual'], '$path.visual'),
        '$path.visual',
        assetResolver: assetResolver,
      ),
      cache: ArticleCache.fromJson(
        _map(json['cache'], '$path.cache'),
        '$path.cache',
      ),
    );
  }

  Map<String, Object?> toJson() => {
    'id': id,
    'cluster_id': clusterId,
    'content_version': contentVersion,
    'headline': headline,
    'dek': dek,
    'summary': summary,
    'reading_body': readingBlocks
        .map((block) => block.toJson())
        .toList(growable: false),
    'primary_source_id': primarySourceId,
    'sources': sources.map((source) => source.toJson()).toList(growable: false),
    'visual': visual.toJson(),
    'cache': cache.toJson(),
  };
}

final class ReadingBlock {
  const ReadingBlock({required this.type, required this.text});

  final String type;
  final String text;

  factory ReadingBlock.fromJson(Map<String, Object?> json, String path) {
    _expectKeys(json, path, {'type', 'text'});
    final type = _string(json['type'], '$path.type');
    if (type != 'paragraph') {
      throw FormatException('$path.type "$type" is unsupported.');
    }
    return ReadingBlock(type: type, text: _string(json['text'], '$path.text'));
  }

  Map<String, Object?> toJson() => {'type': type, 'text': text};
}

final class ArticleSource {
  const ArticleSource({
    required this.id,
    required this.publisherId,
    required this.name,
    required this.canonicalUrl,
    required this.publishedAt,
  });

  final String id;
  final String publisherId;
  final String name;
  final Uri canonicalUrl;
  final DateTime? publishedAt;

  factory ArticleSource.fromJson(Map<String, Object?> json, String path) {
    _expectKeys(
      json,
      path,
      {'id', 'publisher_id', 'name', 'canonical_url'},
      optional: {'published_at'},
    );
    final rawUrl = _string(json['canonical_url'], '$path.canonical_url');
    final url = Uri.tryParse(rawUrl);
    if (url == null ||
        url.scheme != 'https' ||
        url.host.isEmpty ||
        url.userInfo.isNotEmpty) {
      throw FormatException(
        '$path.canonical_url must be a canonical HTTPS URL without user info.',
      );
    }
    final rawPublishedAt = json['published_at'];
    return ArticleSource(
      id: _string(json['id'], '$path.id'),
      publisherId: _string(json['publisher_id'], '$path.publisher_id'),
      name: _string(json['name'], '$path.name'),
      canonicalUrl: url,
      publishedAt: rawPublishedAt == null
          ? null
          : _timestamp(rawPublishedAt, '$path.published_at'),
    );
  }

  Map<String, Object?> toJson() => {
    'id': id,
    'publisher_id': publisherId,
    'name': name,
    'canonical_url': canonicalUrl.toString(),
    if (publishedAt != null) 'published_at': _timestampJson(publishedAt!),
  };
}

final class EditorialVisual {
  const EditorialVisual({
    required this.assetId,
    required this.contentHash,
    required this.width,
    required this.height,
    required this.alt,
    required this.transparencyLabel,
    required this.provenance,
    required this._resolvedAssetPath,
  });

  final String assetId;
  final String contentHash;
  final int width;
  final int height;
  final String alt;
  final String transparencyLabel;
  final VisualProvenance provenance;
  final String? _resolvedAssetPath;

  bool get generatedByAi => provenance.generatedByAi;
  String get safetyClass => provenance.safetyClass;

  String get assetPath {
    final value = _resolvedAssetPath;
    if (value == null) {
      throw StateError(
        'Asset "$assetId" has no client-local resolution for this document.',
      );
    }
    return value;
  }

  factory EditorialVisual.fromJson(
    Map<String, Object?> json,
    String path, {
    EditionAssetPathResolver? assetResolver,
  }) {
    _expectKeys(json, path, {
      'asset_id',
      'content_hash',
      'width',
      'height',
      'alt',
      'transparency_label',
      'provenance',
    });
    final assetId = _string(json['asset_id'], '$path.asset_id');
    return EditorialVisual(
      assetId: assetId,
      contentHash: _sha256(json['content_hash'], '$path.content_hash'),
      width: _positiveInt(json['width'], '$path.width'),
      height: _positiveInt(json['height'], '$path.height'),
      alt: _string(json['alt'], '$path.alt'),
      transparencyLabel: _string(
        json['transparency_label'],
        '$path.transparency_label',
      ),
      provenance: VisualProvenance.fromJson(
        _map(json['provenance'], '$path.provenance'),
        '$path.provenance',
      ),
      resolvedAssetPath: assetResolver?.call(assetId),
    );
  }

  Map<String, Object?> toJson() => {
    'asset_id': assetId,
    'content_hash': contentHash,
    'width': width,
    'height': height,
    'alt': alt,
    'transparency_label': transparencyLabel,
    'provenance': provenance.toJson(),
  };
}

final class VisualProvenance {
  const VisualProvenance({
    required this.generatedByAi,
    required this.provider,
    required this.model,
    required this.generatedAt,
    required this.briefVersion,
    required this.styleVersion,
    required this.safetyClass,
    required this.cacheKey,
  });

  final bool generatedByAi;
  final String provider;
  final String model;
  final DateTime generatedAt;
  final String briefVersion;
  final String styleVersion;
  final String safetyClass;
  final String cacheKey;

  factory VisualProvenance.fromJson(Map<String, Object?> json, String path) {
    _expectKeys(json, path, {
      'generated_by_ai',
      'provider',
      'model',
      'generated_at',
      'brief_version',
      'style_version',
      'safety_class',
      'cache_key',
    });
    final generatedByAi = json['generated_by_ai'];
    if (generatedByAi is! bool) {
      throw FormatException('$path.generated_by_ai must be a boolean.');
    }
    return VisualProvenance(
      generatedByAi: generatedByAi,
      provider: _string(json['provider'], '$path.provider'),
      model: _string(json['model'], '$path.model'),
      generatedAt: _timestamp(json['generated_at'], '$path.generated_at'),
      briefVersion: _string(json['brief_version'], '$path.brief_version'),
      styleVersion: _string(json['style_version'], '$path.style_version'),
      safetyClass: _string(json['safety_class'], '$path.safety_class'),
      cacheKey: _sha256(json['cache_key'], '$path.cache_key'),
    );
  }

  Map<String, Object?> toJson() => {
    'generated_by_ai': generatedByAi,
    'provider': provider,
    'model': model,
    'generated_at': _timestampJson(generatedAt),
    'brief_version': briefVersion,
    'style_version': styleVersion,
    'safety_class': safetyClass,
    'cache_key': cacheKey,
  };
}

final class ArticleCache {
  const ArticleCache({required this.summaryKey, required this.visualBriefKey});

  final String summaryKey;
  final String visualBriefKey;

  factory ArticleCache.fromJson(Map<String, Object?> json, String path) {
    _expectKeys(json, path, {'summary_key', 'visual_brief_key'});
    return ArticleCache(
      summaryKey: _sha256(json['summary_key'], '$path.summary_key'),
      visualBriefKey: _sha256(
        json['visual_brief_key'],
        '$path.visual_brief_key',
      ),
    );
  }

  Map<String, Object?> toJson() => {
    'summary_key': summaryKey,
    'visual_brief_key': visualBriefKey,
  };
}

final class EditionCache {
  const EditionCache({required this.editionKey, required this.layoutKey});

  final String editionKey;
  final String layoutKey;

  factory EditionCache.fromJson(Map<String, Object?> json, String path) {
    _expectKeys(json, path, {'edition_key', 'layout_key'});
    return EditionCache(
      editionKey: _sha256(json['edition_key'], '$path.edition_key'),
      layoutKey: _sha256(json['layout_key'], '$path.layout_key'),
    );
  }

  Map<String, Object?> toJson() => {
    'edition_key': editionKey,
    'layout_key': layoutKey,
  };
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

DateTime _timestamp(Object? value, String path) {
  final text = _string(value, path);
  final parsed = DateTime.tryParse(text);
  final hasTimezone = RegExp(r'(?:Z|[+-]\d{2}:\d{2})$').hasMatch(text);
  if (parsed == null || !text.contains('T') || !hasTimezone) {
    throw FormatException(
      '$path must be an ISO-8601 timestamp with an explicit timezone.',
    );
  }
  return parsed;
}

String _timestampJson(DateTime value) => value.toUtc().toIso8601String();

String _sha256(Object? value, String path) {
  final text = _string(value, path);
  if (!RegExp(r'^sha256:[0-9a-f]{64}$').hasMatch(text)) {
    throw FormatException('$path must be a lowercase SHA-256 identity.');
  }
  return text;
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

int _nonNegativeInt(Object? value, String path) {
  if (value is! int || value < 0) {
    throw FormatException('$path must be a non-negative integer.');
  }
  return value;
}

void _expectKeys(
  Map<String, Object?> json,
  String path,
  Set<String> required, {
  Set<String> optional = const {},
}) {
  for (final key in required) {
    if (!json.containsKey(key)) {
      throw FormatException('$path.$key is required.');
    }
  }
  final allowed = {...required, ...optional};
  for (final key in json.keys) {
    if (!allowed.contains(key)) {
      throw FormatException('$path.$key is unsupported.');
    }
  }
}

const _forbiddenFieldNames = {
  'api_key',
  'provider_api_key',
  'provider_secret',
  'access_token',
  'refresh_token',
  'raw_prompt',
  'prompt',
  'asset_path',
  'local_path',
  'private_path',
  'storage_path',
  'signed_url',
  'raw_body',
  'raw_content',
  'raw_publisher_body',
  'publisher_body',
  'full_publisher_body',
  'scrape_body',
  'source_body',
};

void _rejectForbiddenFields(Object? value, String path) {
  if (value is Map<String, Object?>) {
    for (final entry in value.entries) {
      final key = entry.key.toLowerCase();
      if (_forbiddenFieldNames.contains(key) || key.contains('secret')) {
        throw FormatException('$path.${entry.key} is forbidden.');
      }
      _rejectForbiddenFields(entry.value, '$path.${entry.key}');
    }
  } else if (value is List<Object?>) {
    for (var index = 0; index < value.length; index++) {
      _rejectForbiddenFields(value[index], '$path[$index]');
    }
  }
}
