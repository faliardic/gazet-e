import 'package:flutter/widgets.dart';

import 'edition.dart';

final class EditionSession extends ChangeNotifier {
  EditionSession(this.edition)
    : _controllers = {
        for (final page in edition.pages) page.id: TransformationController(),
      } {
    for (final controller in _controllers.values) {
      controller.addListener(_onTransformChanged);
    }
  }

  static const fitScaleTolerance = 0.01;

  final EditionDocument edition;
  final Map<String, TransformationController> _controllers;

  int _pageIndex = 0;
  String? _selectedArticleId;

  int get pageIndex => _pageIndex;
  NewspaperPage get currentPage => edition.pages[_pageIndex];
  String? get selectedArticleId => _selectedArticleId;
  Article? get selectedArticle => _selectedArticleId == null
      ? null
      : edition.articleById(_selectedArticleId!);

  TransformationController controllerFor(String pageId) =>
      _controllers[pageId]!;

  bool isAtFitScale(String pageId) {
    final scale = controllerFor(pageId).value.getMaxScaleOnAxis();
    return scale <= 1 + fitScaleTolerance;
  }

  bool get canGoBack => _pageIndex > 0 && isAtFitScale(currentPage.id);
  bool get canGoForward =>
      _pageIndex < edition.pages.length - 1 && isAtFitScale(currentPage.id);

  bool goToPage(int index) {
    if (!isAtFitScale(currentPage.id) ||
        index < 0 ||
        index >= edition.pages.length ||
        index == _pageIndex) {
      return false;
    }
    _pageIndex = index;
    notifyListeners();
    return true;
  }

  bool previousPage() => goToPage(_pageIndex - 1);
  bool nextPage() => goToPage(_pageIndex + 1);

  void openArticle(String articleId) {
    if (!edition.articles.containsKey(articleId)) {
      throw ArgumentError.value(articleId, 'articleId', 'Unknown article');
    }
    _selectedArticleId = articleId;
    notifyListeners();
  }

  void closeArticle() {
    if (_selectedArticleId == null) {
      return;
    }
    _selectedArticleId = null;
    notifyListeners();
  }

  void resetCurrentTransform() {
    controllerFor(currentPage.id).value = Matrix4.identity();
  }

  void _onTransformChanged() {
    notifyListeners();
  }

  @override
  void dispose() {
    for (final controller in _controllers.values) {
      controller.removeListener(_onTransformChanged);
      controller.dispose();
    }
    super.dispose();
  }
}
