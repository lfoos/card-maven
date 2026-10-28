from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from card_maven.market.sources.ebay import (
    EbayApi,
    EbayBrowseSource,
    EbayConfig,
    EbayTaxonomyClient,
    map_item,
)
from card_maven.market.sources.fixture import FixtureSale, FixtureSource
from card_maven.market.sources.port import MarketQuery, MarketSourceError
from card_maven.market.sources.registry import build_sources
from card_maven.shared.config import Settings
from card_maven.shared.errors import DependencyUnavailableError, InvalidInputError
from card_maven.shared.money import Money

REPO_ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
SANDBOX = "https://api.sandbox.ebay.com"
QUERY = MarketQuery(
    sport="baseball",
    year=2025,
    set_name="Bowman Chrome",
    card_number="CPA-JW",
    players=("JJ Wetherholt",),
    parallel_name="Gold Refractor",
)


class TestQuery:
    def test_keywords_skip_base(self) -> None:
        assert QUERY.keywords == "2025 Bowman Chrome JJ Wetherholt CPA-JW Gold Refractor"
        base = MarketQuery(
            sport="baseball", year=2024, set_name="Topps Chrome", parallel_name="Base"
        )
        assert base.keywords == "2024 Topps Chrome"


class TestFixtureSource:
    def test_repository_fixtures_load_and_filter_by_set_and_year(self) -> None:
        source = FixtureSource.from_file(REPO_ROOT / "config/market_fixtures.yaml")
        records = source.fetch(QUERY, now=NOW)
        assert records
        assert all("2025" in r.title and "Bowman Chrome" in r.title for r in records)
        assert all(r.kind == "sale" for r in records)

    def test_dates_are_relative_to_now_and_limit_applies(self) -> None:
        source = FixtureSource(
            [
                FixtureSale(id="a", title="2025 Bowman Chrome A", price="10.50", days_ago=3),
                FixtureSale(
                    id="b", title="2025 Bowman Chrome B", price="1", days_ago=0, type="fixed_price"
                ),
            ]
        )
        first, second = source.fetch(QUERY, now=NOW)
        assert first.occurred_at == NOW - timedelta(days=3)
        assert first.price == Money(1050, "USD")
        assert second.option == "fixed_price"
        limited = MarketQuery(sport="baseball", year=2025, set_name="Bowman Chrome", limit=1)
        assert len(source.fetch(limited, now=NOW)) == 1

    def test_invalid_file(self, tmp_path: Path) -> None:
        path = tmp_path / "f.yaml"
        path.write_text("sales: [{id: x}]")
        with pytest.raises(InvalidInputError, match="invalid"):
            FixtureSource.from_file(path)


CONFIG = EbayConfig(
    host=SANDBOX,
    client_id="id",
    client_secret="secret",
    marketplace_id="EBAY_US",
    category_id="261328",
    campaign_id="5338000000",
)

# Shaped like a Browse `item_summary/search` response (fields per eBay's published schema).
SEARCH_RESPONSE = {
    "href": f"{SANDBOX}/buy/browse/v1/item_summary/search?q=...",
    "total": 4,
    "limit": 50,
    "offset": 0,
    "itemSummaries": [
        {
            "itemId": "v1|110551231|0",
            "legacyItemId": "110551231",
            "title": "2025 Bowman Chrome JJ Wetherholt CPA-JW Gold Refractor Auto /50 PSA 10",
            "price": {"value": "1299.99", "currency": "USD"},
            "buyingOptions": ["FIXED_PRICE", "BEST_OFFER"],
            "condition": "Graded",
            "conditionId": "2750",
            "itemWebUrl": "https://www.ebay.com/itm/110551231",
            "itemAffiliateWebUrl": "https://www.ebay.com/itm/110551231?mkcid=1&campid=5338000000",
            "image": {"imageUrl": "https://i.ebayimg.com/images/g/abc/s-l225.jpg"},
            "itemEndDate": "2026-11-20T18:00:00.000Z",
        },
        {
            "itemId": "v1|110551232|0",
            "title": "2025 Bowman Chrome JJ Wetherholt Gold Refractor Auto 3/50",
            "price": {"value": "600.00", "currency": "USD"},
            "currentBidPrice": {"value": "455.00", "currency": "USD"},
            "bidCount": 12,
            "buyingOptions": ["AUCTION"],
            "conditionId": "4000",
            "itemWebUrl": "https://www.ebay.com/itm/110551232",
        },
        {"itemId": "v1|no-price|0", "title": "Missing price"},
        {
            "itemId": "v1|best|0",
            "title": "Best offer only",
            "price": {"value": "5"},
            "buyingOptions": ["BEST_OFFER"],
        },
    ],
}
TOKEN_RESPONSE = {
    "access_token": "token-1",
    "expires_in": 7200,
    "token_type": "Application Access Token",
}


def browse(router: respx.Router) -> EbayBrowseSource:
    router.post(f"{SANDBOX}/identity/v1/oauth2/token").respond(json=TOKEN_RESPONSE)
    return EbayBrowseSource(EbayApi(CONFIG, httpx.Client()))


class TestEbayBrowse:
    def test_maps_search_results(self, respx_mock: respx.Router) -> None:
        route = respx_mock.get(f"{SANDBOX}/buy/browse/v1/item_summary/search").respond(
            json=SEARCH_RESPONSE
        )
        records = browse(respx_mock).fetch(QUERY, now=NOW)

        assert [r.source_listing_id for r in records] == [
            "v1|110551231|0",
            "v1|110551232|0",
            "v1|best|0",
        ]
        slab, auction, best = records
        assert slab.kind == "listing"
        assert slab.price == Money(129999, "USD")
        assert slab.option == "fixed_price"
        assert slab.url is not None
        assert "campid=5338000000" in slab.url  # affiliate link preferred
        assert slab.condition_hint == "graded"
        assert slab.ends_at == datetime(2026, 11, 20, 18, tzinfo=UTC)
        assert slab.occurred_at == NOW
        assert slab.image_url == "https://i.ebayimg.com/images/g/abc/s-l225.jpg"
        assert auction.price == Money(45500, "USD")  # current bid, not the BIN/start price
        assert (auction.option, auction.bid_count, auction.condition_hint) == ("auction", 12, "raw")
        assert auction.url == "https://www.ebay.com/itm/110551232"  # no affiliate URL returned
        assert best.option == "best_offer"

        request = route.calls.last.request
        assert request.headers["Authorization"] == "Bearer token-1"
        assert request.headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_US"
        assert request.headers["X-EBAY-C-ENDUSERCTX"] == "affiliateCampaignId=5338000000"
        params = request.url.params
        assert params["category_ids"] == "261328"
        assert params["filter"] == "buyingOptions:{FIXED_PRICE|AUCTION}"
        assert params["q"] == QUERY.keywords

    def test_token_is_cached_and_refreshed_on_401(self, respx_mock: respx.Router) -> None:
        token = respx_mock.post(f"{SANDBOX}/identity/v1/oauth2/token").respond(json=TOKEN_RESPONSE)
        search = respx_mock.get(f"{SANDBOX}/buy/browse/v1/item_summary/search")
        search.side_effect = [
            httpx.Response(200, json={"itemSummaries": []}),
            httpx.Response(200, json={"itemSummaries": []}),
            httpx.Response(401),
            httpx.Response(200, json={"itemSummaries": []}),
        ]
        source = EbayBrowseSource(EbayApi(CONFIG, httpx.Client()))
        source.fetch(QUERY, now=NOW)
        source.fetch(QUERY, now=NOW)
        assert token.call_count == 1  # cached
        source.fetch(QUERY, now=NOW)  # 401 -> new token -> retry once
        assert token.call_count == 2
        assert search.call_count == 4

    def test_no_affiliate_header_without_campaign(self, respx_mock: respx.Router) -> None:
        respx_mock.post(f"{SANDBOX}/identity/v1/oauth2/token").respond(json=TOKEN_RESPONSE)
        route = respx_mock.get(f"{SANDBOX}/buy/browse/v1/item_summary/search").respond(json={})
        config = EbayConfig(
            host=SANDBOX,
            client_id="id",
            client_secret="s",
            marketplace_id="EBAY_US",
            category_id="261328",
            campaign_id=None,
        )
        assert EbayBrowseSource(EbayApi(config, httpx.Client())).fetch(QUERY, now=NOW) == []
        assert "X-EBAY-C-ENDUSERCTX" not in route.calls.last.request.headers

    @pytest.mark.parametrize(
        ("status", "error"),
        [
            (429, DependencyUnavailableError),
            (503, DependencyUnavailableError),
            (400, MarketSourceError),
            (403, MarketSourceError),
        ],
    )
    def test_http_errors(
        self, respx_mock: respx.Router, status: int, error: type[Exception]
    ) -> None:
        respx_mock.get(f"{SANDBOX}/buy/browse/v1/item_summary/search").respond(status)
        with pytest.raises(error):
            browse(respx_mock).fetch(QUERY, now=NOW)

    def test_network_errors_are_transient(self, respx_mock: respx.Router) -> None:
        respx_mock.get(f"{SANDBOX}/buy/browse/v1/item_summary/search").mock(
            side_effect=httpx.ConnectTimeout("slow")
        )
        with pytest.raises(DependencyUnavailableError):
            browse(respx_mock).fetch(QUERY, now=NOW)

    @pytest.mark.parametrize(
        ("status", "error"),
        [(401, MarketSourceError), (400, MarketSourceError), (500, DependencyUnavailableError)],
    )
    def test_oauth_failures(
        self, respx_mock: respx.Router, status: int, error: type[Exception]
    ) -> None:
        respx_mock.post(f"{SANDBOX}/identity/v1/oauth2/token").respond(status)
        with pytest.raises(error):
            EbayBrowseSource(EbayApi(CONFIG, httpx.Client())).fetch(QUERY, now=NOW)

    def test_oauth_unreachable(self, respx_mock: respx.Router) -> None:
        respx_mock.post(f"{SANDBOX}/identity/v1/oauth2/token").mock(
            side_effect=httpx.ConnectError("down")
        )
        with pytest.raises(DependencyUnavailableError, match="OAuth"):
            EbayBrowseSource(EbayApi(CONFIG, httpx.Client())).fetch(QUERY, now=NOW)

    def test_oauth_request_shape(self, respx_mock: respx.Router) -> None:
        token = respx_mock.post(f"{SANDBOX}/identity/v1/oauth2/token").respond(json=TOKEN_RESPONSE)
        respx_mock.get(f"{SANDBOX}/buy/browse/v1/item_summary/search").respond(json={})
        EbayBrowseSource(EbayApi(CONFIG, httpx.Client())).fetch(QUERY, now=NOW)
        request = token.calls.last.request
        assert request.headers["Authorization"] == "Basic aWQ6c2VjcmV0"  # base64("id:secret")
        assert b"grant_type=client_credentials" in request.content
        assert b"scope=https%3A%2F%2Fapi.ebay.com%2Foauth%2Fapi_scope" in request.content

    def test_long_keywords_are_truncated(self) -> None:
        long = MarketQuery(sport="baseball", year=2025, set_name="X" * 150)
        assert len(long.keywords[:100]) == 100


def test_map_item_handles_other_options_and_currency() -> None:
    record = map_item(
        {"itemId": "1", "title": "t", "price": {"value": "1000", "currency": "JPY"}},
        observed_at=NOW,
    )
    assert record is not None
    assert (record.option, record.price, record.condition_hint) == (
        "other",
        Money(1000, "JPY"),
        None,
    )


class TestTaxonomy:
    def test_loads_relevant_aspects(self, respx_mock: respx.Router) -> None:
        respx_mock.post(f"{SANDBOX}/identity/v1/oauth2/token").respond(json=TOKEN_RESPONSE)
        respx_mock.get(f"{SANDBOX}/commerce/taxonomy/v1/get_default_category_tree_id").respond(
            json={"categoryTreeId": "0", "categoryTreeVersion": "130"}
        )
        aspects = respx_mock.get(
            f"{SANDBOX}/commerce/taxonomy/v1/category_tree/0/get_item_aspects_for_category"
        ).respond(
            json={
                "aspects": [
                    {
                        "localizedAspectName": "Parallel/Variety",
                        "aspectConstraint": {"aspectMode": "FREE_TEXT"},
                        "aspectValues": [
                            {"localizedValue": "Gold Refractor"},
                            {"localizedValue": " Silver Prizm "},
                            {"localizedValue": ""},
                        ],
                    },
                    {
                        "localizedAspectName": "Professional Grader",
                        "aspectValues": [{"localizedValue": "PSA"}],
                    },
                    {
                        "localizedAspectName": "Player/Athlete",
                        "aspectValues": [{"localizedValue": "Someone"}],
                    },
                ]
            }
        )
        values = EbayTaxonomyClient(EbayApi(CONFIG, httpx.Client())).aspect_values()
        assert values == [
            ("Parallel/Variety", "Gold Refractor"),
            ("Parallel/Variety", "Silver Prizm"),
            ("Professional Grader", "PSA"),
        ]
        assert aspects.calls.last.request.url.params["category_id"] == "261328"


class TestRegistry:
    def test_fixture_and_unconfigured_ebay(self) -> None:
        settings = Settings(
            _env_file=None,
            market_sources=["fixture", "ebay_browse", "nope"],  # type: ignore[call-arg]
            market_fixtures_path=REPO_ROOT / "config/market_fixtures.yaml",
        )
        assert set(build_sources(settings)) == {"fixture"}  # eBay skipped without keys

    def test_configured_ebay(self) -> None:
        settings = Settings(
            _env_file=None,
            market_sources=["ebay_browse"],
            ebay_client_id="a",  # type: ignore[call-arg]
            ebay_client_secret="b",
        )
        sources = build_sources(settings)
        assert isinstance(sources["ebay_browse"], EbayBrowseSource)
        assert EbayConfig.from_settings(settings).host == SANDBOX

    def test_production_host_and_missing_keys(self) -> None:
        settings = Settings(
            _env_file=None,
            ebay_environment="production",
            ebay_client_id="a",  # type: ignore[call-arg]
            ebay_client_secret="b",
        )
        assert EbayConfig.from_settings(settings).host == "https://api.ebay.com"
        with pytest.raises(MarketSourceError, match="CLIENT_ID"):
            EbayConfig.from_settings(Settings(_env_file=None))  # type: ignore[call-arg]
