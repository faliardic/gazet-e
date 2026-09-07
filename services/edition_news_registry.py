"""Static, versioned Q06 RSS source registry."""

from __future__ import annotations

from services.edition_news_models import SourceDefinition

REGISTRY_VERSION = "gazet-e.rss-registry.v1"

RSS_REGISTRY = (
    SourceDefinition(publisher_id="ntv", source_id="ntv-turkiye", display_name="NTV Türkiye", family="NTV", section="gundem", feed_url="https://www.ntv.com.tr/turkiye.rss"),
    SourceDefinition(publisher_id="ntv", source_id="ntv-dunya", display_name="NTV Dünya", family="NTV", section="dunya", feed_url="https://www.ntv.com.tr/dunya.rss"),
    SourceDefinition(publisher_id="ntv", source_id="ntv-ekonomi", display_name="NTV Ekonomi", family="NTV", section="ekonomi", feed_url="https://www.ntv.com.tr/ekonomi.rss"),
    SourceDefinition(publisher_id="ntv", source_id="ntv-teknoloji", display_name="NTV Teknoloji", family="NTV", section="teknoloji", feed_url="https://www.ntv.com.tr/teknoloji.rss"),
    SourceDefinition(publisher_id="ntv", source_id="ntv-spor", display_name="NTV Spor", family="NTV", section="spor", feed_url="https://www.ntv.com.tr/sporskor.rss"),
    SourceDefinition(publisher_id="haberturk", source_id="haberturk-gundem", display_name="Habertürk Gündem", family="Habertürk", section="gundem", feed_url="https://www.haberturk.com/rss/kategori/gundem.xml"),
    SourceDefinition(publisher_id="haberturk", source_id="haberturk-dunya", display_name="Habertürk Dünya", family="Habertürk", section="dunya", feed_url="https://www.haberturk.com/rss/kategori/dunya.xml"),
    SourceDefinition(publisher_id="haberturk", source_id="haberturk-ekonomi", display_name="Habertürk Ekonomi", family="Habertürk", section="ekonomi", feed_url="https://www.haberturk.com/rss/ekonomi.xml"),
    SourceDefinition(publisher_id="haberturk", source_id="haberturk-spor", display_name="Habertürk Spor", family="Habertürk", section="spor", feed_url="https://www.haberturk.com/rss/spor.xml"),
    SourceDefinition(publisher_id="haberturk", source_id="haberturk-teknoloji", display_name="Habertürk Teknoloji", family="Habertürk", section="teknoloji", feed_url="https://www.haberturk.com/rss/kategori/teknoloji.xml"),
    SourceDefinition(publisher_id="sozcu", source_id="sozcu-gundem", display_name="Sözcü Gündem", family="Sözcü", section="gundem", feed_url="https://www.sozcu.com.tr/feeds-rss-category-gundem"),
    SourceDefinition(publisher_id="sozcu", source_id="sozcu-dunya", display_name="Sözcü Dünya", family="Sözcü", section="dunya", feed_url="https://www.sozcu.com.tr/feeds-rss-category-dunya"),
    SourceDefinition(publisher_id="sozcu", source_id="sozcu-ekonomi", display_name="Sözcü Ekonomi", family="Sözcü", section="ekonomi", feed_url="https://www.sozcu.com.tr/feeds-rss-category-ekonomi"),
    SourceDefinition(publisher_id="sozcu", source_id="sozcu-spor", display_name="Sözcü Spor", family="Sözcü", section="spor", feed_url="https://www.sozcu.com.tr/feeds-rss-category-spor"),
    SourceDefinition(publisher_id="sozcu", source_id="sozcu-teknoloji", display_name="Sözcü Bilim Teknoloji", family="Sözcü", section="teknoloji", feed_url="https://www.sozcu.com.tr/feeds-rss-category-bilim-teknoloji"),
    SourceDefinition(publisher_id="evrim-agaci", source_id="evrim-agaci-bilim", display_name="Evrim Ağacı", family="Evrim Ağacı", section="teknoloji", feed_url="https://evrimagaci.org/rss.xml"),
)

REGISTRY_BY_SOURCE_ID = {source.source_id: source for source in RSS_REGISTRY}
