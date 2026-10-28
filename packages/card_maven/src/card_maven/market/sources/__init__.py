"""Market data sources (the ``MarketDataSource`` port and its adapters).

Adapters: :mod:`.fixture` (dev/test sample data), :mod:`.ebay` (eBay Browse,
display-only). Manual comps don't come through a source; collectors post them
through the API.
"""

from card_maven.market.sources.port import (
    MarketDataSource,
    MarketQuery,
    MarketRecord,
    MarketSourceError,
)

__all__ = ["MarketDataSource", "MarketQuery", "MarketRecord", "MarketSourceError"]
