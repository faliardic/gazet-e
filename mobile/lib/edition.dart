import 'dart:convert';
import 'dart:typed_data';
import 'dart:ui';

const supportedContractVersion = 'gazet-e.edition.v1';
const activeContractVersion = 'gazet-e.edition.v2';
const legacyContractVersion = supportedContractVersion;

typedef EditionAssetPathResolver = String? Function(String assetId);
typedef EditionAssetBytesResolver = Uint8List? Function(String assetId);

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
    EditionAssetBytesResolver? assetBytesResolver,
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
      assetBytesResolver: assetBytesResolver,
    );
  }

  factory EditionDocument.fromJson(
    Map<String, Object?> json, {
    EditionAssetPathResolver? assetResolver,
    EditionAssetBytesResolver? assetBytesResolver,
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
    if (contractVersion != activeContractVersion &&
        contractVersion != legacyContractVersion) {
      throw FormatException(
        'Unsupported contract_version "$contractVersion"; expected '
        '"$activeContractVersion" or "$legacyContractVersion".',
      );
    }
    final isV2 = contractVersion == activeContractVersion;

    final edition = EditionMetadata.fromJson(
      _map(json['edition'], 'edition'),
      'edition',
      isV2: isV2,
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
        assetBytesResolver: assetBytesResolver,
        isV2: isV2,
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
        isV2: isV2,
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

    if (isV2) {
      final placed = pages
          .expand((page) => page.placements)
          .map((placement) => placement.articleId)
          .toList(growable: false);
      if (placed.length != placed.toSet().length ||
          placed.toSet().difference(articles.keys.toSet()).isNotEmpty ||
          articles.keys.toSet().difference(placed.toSet()).isNotEmpty) {
        throw const FormatException(
          'v2 articles must each have exactly one editorial placement.',
        );
      }
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

  factory EditionMetadata.fromJson(
    Map<String, Object?> json,
    String path, {
    required bool isV2,
  }) {
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
        isV2: isV2,
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
    this.editorialPolicy,
    this.summaryPrompt,
    required this.visualBrief,
    required this.visualStyle,
    required this.layoutEngine,
    this.physicalLayout,
    this.adPolicy,
  });

  final String? editorialPolicy;
  final String? summaryPrompt;
  final String visualBrief;
  final String visualStyle;
  final String layoutEngine;
  final String? physicalLayout;
  final String? adPolicy;

  factory EditionVersions.fromJson(
    Map<String, Object?> json,
    String path, {
    required bool isV2,
  }) {
    _expectKeys(
      json,
      path,
      isV2
          ? {
              'visual_brief',
              'visual_style',
              'layout_engine',
              'physical_layout',
              'ad_policy',
            }
          : {
              'editorial_policy',
              'summary_prompt',
              'visual_brief',
              'visual_style',
              'layout_engine',
            },
    );
    return EditionVersions(
      editorialPolicy: isV2
          ? null
          : _string(json['editorial_policy'], '$path.editorial_policy'),
      summaryPrompt: isV2
          ? null
          : _string(json['summary_prompt'], '$path.summary_prompt'),
      visualBrief: _string(json['visual_brief'], '$path.visual_brief'),
      visualStyle: _string(json['visual_style'], '$path.visual_style'),
      layoutEngine: _string(json['layout_engine'], '$path.layout_engine'),
      physicalLayout: isV2
          ? _string(json['physical_layout'], '$path.physical_layout')
          : null,
      adPolicy: isV2 ? _string(json['ad_policy'], '$path.ad_policy') : null,
    );
  }

  Map<String, Object?> toJson() => {
    if (editorialPolicy != null) 'editorial_policy': editorialPolicy,
    if (summaryPrompt != null) 'summary_prompt': summaryPrompt,
    'visual_brief': visualBrief,
    'visual_style': visualStyle,
    'layout_engine': layoutEngine,
    if (physicalLayout != null) 'physical_layout': physicalLayout,
    if (adPolicy != null) 'ad_policy': adPolicy,
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
    this.physicalProfile,
    this.ads = const [],
  });

  final String id;
  final int order;
  final String label;
  final String section;
  final CanvasSpec canvas;
  final TemplateSpec template;
  final List<Placement> placements;
  final PhysicalProfile? physicalProfile;
  final List<PageAd> ads;

  factory NewspaperPage.fromJson(
    Map<String, Object?> json,
    String path, {
    required bool isV2,
  }) {
    _expectKeys(json, path, {
      'id',
      'order',
      'label',
      'section',
      'canvas',
      'template',
      'placements',
      if (isV2) 'physical_profile',
      if (isV2) 'ads',
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
      if (isV2 && !placement.rect.containsEvery(placement.hitRegions)) {
        throw FormatException(
          '$placementPath hit regions must remain inside the placement.',
        );
      }
      if (isV2 &&
          placements.any((item) => item.rect.overlaps(placement.rect))) {
        throw FormatException('$path editorial placements must not overlap.');
      }
      placements.add(placement);
    }
    final physicalProfile = isV2
        ? PhysicalProfile.fromJson(
            _map(json['physical_profile'], '$path.physical_profile'),
            '$path.physical_profile',
          )
        : null;
    if (isV2 && (canvas.width != 700 || canvas.height != 1000)) {
      throw FormatException(
        '$path v2 canvas must be exactly 700×1000 logical.',
      );
    }
    final ads = <PageAd>[];
    if (isV2) {
      final rawAds = _list(json['ads'], '$path.ads');
      if (rawAds.length > 1) {
        throw FormatException('$path.ads allows at most one display-only ad.');
      }
      for (var index = 0; index < rawAds.length; index++) {
        final ad = PageAd.fromJson(
          _map(rawAds[index], '$path.ads[$index]'),
          '$path.ads[$index]',
          canvas,
        );
        if (ad.rect.area > canvas.width * canvas.height * 0.15) {
          throw FormatException('$path.ads[$index] exceeds 15% page area.');
        }
        if (placements.any((item) => item.rect.overlaps(ad.rect)) ||
            placements.any(
              (item) => item.hitRegions.any(
                (region) => region.rect.overlaps(ad.rect),
              ),
            )) {
          throw FormatException(
            '$path.ads[$index] overlaps editorial content.',
          );
        }
        ads.add(ad);
      }
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
      physicalProfile: physicalProfile,
      ads: List.unmodifiable(ads),
    );
  }

  Map<String, Object?> toJson() => {
    'id': id,
    'order': order,
    'label': label,
    'section': section,
    if (physicalProfile != null) 'physical_profile': physicalProfile!.toJson(),
    'canvas': canvas.toJson(),
    'template': template.toJson(),
    'placements': placements
        .map((placement) => placement.toJson())
        .toList(growable: false),
    if (physicalProfile != null)
      'ads': ads.map((ad) => ad.toJson()).toList(growable: false),
  };
}

final class PhysicalProfile {
  const PhysicalProfile({
    required this.version,
    required this.widthMm,
    required this.heightMm,
    required this.logicalUnitsPerMm,
  });

  final String version;
  final double widthMm;
  final double heightMm;
  final double logicalUnitsPerMm;

  factory PhysicalProfile.fromJson(Map<String, Object?> json, String path) {
    _expectKeys(json, path, {
      'version',
      'width_mm',
      'height_mm',
      'logical_units_per_mm',
    });
    final profile = PhysicalProfile(
      version: _string(json['version'], '$path.version'),
      widthMm: _positiveNumber(json['width_mm'], '$path.width_mm'),
      heightMm: _positiveNumber(json['height_mm'], '$path.height_mm'),
      logicalUnitsPerMm: _positiveNumber(
        json['logical_units_per_mm'],
        '$path.logical_units_per_mm',
      ),
    );
    if (profile.version != 'gazet-e.physical-profile.350x500.v1' ||
        profile.widthMm != 350 ||
        profile.heightMm != 500 ||
        profile.logicalUnitsPerMm != 2) {
      throw FormatException('$path must identify the 350×500 mm v1 profile.');
    }
    return profile;
  }

  Map<String, Object?> toJson() => {
    'version': version,
    'width_mm': widthMm,
    'height_mm': heightMm,
    'logical_units_per_mm': logicalUnitsPerMm,
  };
}

final class PageAd {
  const PageAd({
    required this.id,
    required this.creativeId,
    required this.label,
    required this.headline,
    required this.body,
    required this.rect,
  });

  final String id;
  final String creativeId;
  final String label;
  final String headline;
  final String body;
  final RectSpec rect;

  factory PageAd.fromJson(
    Map<String, Object?> json,
    String path,
    CanvasSpec canvas,
  ) {
    _expectKeys(json, path, {
      'id',
      'creative_id',
      'label',
      'headline',
      'body',
      'rect',
    });
    final label = _string(json['label'], '$path.label');
    if (label != 'REKLAM') {
      throw FormatException('$path.label must be "REKLAM".');
    }
    final rect = RectSpec.fromJson(
      _map(json['rect'], '$path.rect'),
      '$path.rect',
    );
    rect.validateInside(canvas, '$path.rect');
    return PageAd(
      id: _string(json['id'], '$path.id'),
      creativeId: _string(json['creative_id'], '$path.creative_id'),
      label: label,
      headline: _string(json['headline'], '$path.headline'),
      body: _string(json['body'], '$path.body'),
      rect: rect,
    );
  }

  Map<String, Object?> toJson() => {
    'id': id,
    'creative_id': creativeId,
    'label': label,
    'headline': headline,
    'body': body,
    'rect': rect.toJson(),
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
  double get area => width * height;

  bool overlaps(RectSpec other) =>
      x < other.x + other.width &&
      other.x < x + width &&
      y < other.y + other.height &&
      other.y < y + height;

  bool containsEvery(List<HitRegion> regions) => regions.every(
    (region) =>
        region.rect.x >= x &&
        region.rect.y >= y &&
        region.rect.x + region.rect.width <= x + width &&
        region.rect.y + region.rect.height <= y + height,
  );

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
    this.feedExcerpt,
    this.sourceOnly = false,
  });

  final String id;
  final String clusterId;
  final String contentVersion;
  final String headline;
  final String dek;
  final String summary;
  final List<ReadingBlock> readingBlocks;
  final String? feedExcerpt;
  final bool sourceOnly;
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
    EditionAssetBytesResolver? assetBytesResolver,
    required bool isV2,
  }) {
    _expectKeys(
      json,
      path,
      isV2
          ? {
              'id',
              'cluster_id',
              'content_version',
              'headline',
              'primary_source_id',
              'sources',
              'visual',
              'cache',
            }
          : {
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
            },
      optional: isV2 ? {'feed_excerpt'} : const {},
    );
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

    final rawBody = isV2
        ? const <Object?>[]
        : _list(json['reading_body'], '$path.reading_body');
    if (!isV2 && rawBody.isEmpty) {
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

    final rawExcerpt = json['feed_excerpt'];
    if (isV2 && rawExcerpt != null && rawExcerpt is! String) {
      throw FormatException('$path.feed_excerpt must be a string.');
    }
    final feedExcerpt = rawExcerpt as String?;
    if (feedExcerpt != null && feedExcerpt.length > 1200) {
      throw FormatException('$path.feed_excerpt exceeds 1200 characters.');
    }
    return Article(
      id: id,
      clusterId: clusterId,
      contentVersion: contentVersion,
      headline: _string(json['headline'], '$path.headline'),
      dek: isV2 ? (feedExcerpt ?? '') : _string(json['dek'], '$path.dek'),
      summary: isV2 ? '' : _string(json['summary'], '$path.summary'),
      readingBlocks: List.unmodifiable(readingBlocks),
      feedExcerpt: feedExcerpt,
      sourceOnly: isV2,
      primarySourceId: primarySourceId,
      sources: List.unmodifiable(sources),
      visual: EditorialVisual.fromJson(
        _map(json['visual'], '$path.visual'),
        '$path.visual',
        assetResolver: assetResolver,
        assetBytesResolver: assetBytesResolver,
      ),
      cache: ArticleCache.fromJson(
        _map(json['cache'], '$path.cache'),
        '$path.cache',
        isV2: isV2,
      ),
    );
  }

  Map<String, Object?> toJson() => {
    'id': id,
    'cluster_id': clusterId,
    'content_version': contentVersion,
    'headline': headline,
    if (sourceOnly && feedExcerpt != null) 'feed_excerpt': feedExcerpt,
    if (!sourceOnly) 'dek': dek,
    if (!sourceOnly) 'summary': summary,
    if (!sourceOnly)
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
    required this._resolvedAssetBytes,
  });

  final String assetId;
  final String contentHash;
  final int width;
  final int height;
  final String alt;
  final String transparencyLabel;
  final VisualProvenance provenance;
  final String? _resolvedAssetPath;
  final Uint8List? _resolvedAssetBytes;

  bool get generatedByAi => provenance.generatedByAi;
  String get safetyClass => provenance.safetyClass;
  Uint8List? get assetBytes => _resolvedAssetBytes;

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
    EditionAssetBytesResolver? assetBytesResolver,
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
      resolvedAssetBytes: assetBytesResolver?.call(assetId),
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
  const ArticleCache({this.summaryKey, required this.visualBriefKey});

  final String? summaryKey;
  final String visualBriefKey;

  factory ArticleCache.fromJson(
    Map<String, Object?> json,
    String path, {
    required bool isV2,
  }) {
    _expectKeys(
      json,
      path,
      isV2 ? {'visual_brief_key'} : {'summary_key', 'visual_brief_key'},
    );
    return ArticleCache(
      summaryKey: isV2
          ? null
          : _sha256(json['summary_key'], '$path.summary_key'),
      visualBriefKey: _sha256(
        json['visual_brief_key'],
        '$path.visual_brief_key',
      ),
    );
  }

  Map<String, Object?> toJson() => {
    if (summaryKey != null) 'summary_key': summaryKey,
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
