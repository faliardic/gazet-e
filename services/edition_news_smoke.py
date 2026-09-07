"""Bounded live-RSS gate for Q06; emits counts only, never raw feed content."""

from __future__ import annotations

import json

from services.edition_news_fetch import EditionNewsCollector
from services.edition_news_registry import REGISTRY_BY_SOURCE_ID, REGISTRY_VERSION


def run_live_smoke() -> dict[str, object]:
    collection = EditionNewsCollector().collect()
    families: dict[str, int] = {}
    feeds: list[dict[str, object]] = []
    for result in collection.fetch_results:
        source = REGISTRY_BY_SOURCE_ID[result.source_id]
        feeds.append(
            {
                "source_id": result.source_id,
                "family": source.family,
                "success": result.success,
                "status": result.status,
                "http_status": result.http_status,
                "candidate_count": result.item_count,
                "rejected_item_count": result.rejected_item_count,
            }
        )
        if result.success and result.item_count:
            families[source.family] = families.get(source.family, 0) + result.item_count

    candidates = collection.candidates
    valid_attribution = all(
        candidate.attribution.source_id in REGISTRY_BY_SOURCE_ID
        and candidate.canonical_url.startswith("https://")
        and bool(candidate.article_id)
        and bool(candidate.content_version)
        for candidate in candidates
    )
    publication_metadata_count = sum(
        candidate.published_at is not None for candidate in candidates
    )
    passed = len(families) >= 2 and valid_attribution
    return {
        "registry_version": REGISTRY_VERSION,
        "passed": passed,
        "publisher_family_count": len(families),
        "publisher_family_candidates": dict(sorted(families.items())),
        "candidate_count": len(candidates),
        "publication_metadata_count": publication_metadata_count,
        "attribution_and_identity_valid": valid_attribution,
        "feeds": feeds,
    }


def main() -> int:
    result = run_live_smoke()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
