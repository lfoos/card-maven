"""Build the configured market sources."""

from __future__ import annotations

from card_maven.market.sources.ebay import EbayApi, EbayBrowseSource, EbayConfig
from card_maven.market.sources.fixture import FixtureSource
from card_maven.market.sources.port import MarketDataSource
from card_maven.shared.config import Settings
from card_maven.shared.logging import get_logger

log = get_logger(__name__)


def build_sources(settings: Settings) -> dict[str, MarketDataSource]:
    sources: dict[str, MarketDataSource] = {}
    for code in settings.market_sources:
        if code == "fixture":
            sources[code] = FixtureSource.from_file(settings.market_fixtures_path)
        elif code == "ebay_browse":
            if not settings.ebay_configured:
                log.warning("market_source_skipped", source=code, reason="eBay keys not set")
                continue
            sources[code] = EbayBrowseSource(EbayApi(EbayConfig.from_settings(settings)))
        else:
            log.warning("market_source_skipped", source=code, reason="unknown source")
    return sources
