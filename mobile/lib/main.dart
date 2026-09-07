import 'package:flutter/material.dart';

import 'edition_generation_controller.dart';
import 'edition_job_api_client.dart';
import 'reader_app.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  const origin = String.fromEnvironment(
    'GAZETE_API_ORIGIN',
    defaultValue: 'https://api.invalid.example',
  );
  const allowDebugLoopback = bool.fromEnvironment(
    'GAZETE_ALLOW_DEBUG_LOOPBACK',
  );
  runApp(
    ReaderProofApp(
      generationController: EditionGenerationController(
        gateway: HttpEditionJobGateway(
          origin: Uri.parse(origin),
          allowDebugLoopback: allowDebugLoopback,
        ),
      ),
    ),
  );
}
