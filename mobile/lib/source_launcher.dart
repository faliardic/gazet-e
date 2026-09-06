import 'package:url_launcher/url_launcher.dart';

abstract interface class SourceLauncher {
  Future<bool> open(Uri uri);
}

final class ExternalSourceLauncher implements SourceLauncher {
  const ExternalSourceLauncher();

  @override
  Future<bool> open(Uri uri) {
    if (uri.scheme != 'https' || uri.host.isEmpty) {
      return Future.value(false);
    }
    return launchUrl(uri, mode: LaunchMode.externalApplication);
  }
}
