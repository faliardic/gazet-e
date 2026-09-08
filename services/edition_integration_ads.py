"""Deterministic display-only synthetic advertising for the Q10 proof."""

from __future__ import annotations

import hashlib

AD_POLICY_VERSION = "gazet-e.synthetic-ad-policy.v1"
AD_LABEL = "REKLAM"
MAX_ADS_PER_PAGE = 1
MAX_AD_AREA_RATIO = 0.15

_SYNTHETIC_CREATIVES = (
    ("synthetic-culture-v1", "KÜLTÜR DOSYASI", "Yerel kültür etkinlikleri için örnek ilan."),
    ("synthetic-books-v1", "KİTAP GÜNLERİ", "Bağımsız yayınlar için sentetik tanıtım alanı."),
    ("synthetic-coffee-v1", "GÜNÜN MOLASI", "Gerçek marka içermeyen yerel örnek yaratıcı."),
)


def reserve_synthetic_ad(
    edition_seed: str,
    page_order: int,
    *,
    suitable: bool = True,
) -> dict[str, object] | None:
    """Reserve one bounded footer slot before physical editorial projection."""

    if not suitable:
        return None
    digest = hashlib.sha256(
        f"{AD_POLICY_VERSION}:{edition_seed}:{page_order}".encode("utf-8")
    ).digest()
    creative_id, headline, body = _SYNTHETIC_CREATIVES[
        int.from_bytes(digest[:4], "big") % len(_SYNTHETIC_CREATIVES)
    ]
    return {
        "id": f"ad-page-{page_order}",
        "creative_id": creative_id,
        "label": AD_LABEL,
        "headline": headline,
        "body": body,
        "rect": {"x": 70, "y": 900, "width": 560, "height": 80},
    }
