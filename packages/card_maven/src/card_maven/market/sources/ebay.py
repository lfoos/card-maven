"""eBay adapters: OAuth (client credentials), Browse search, Taxonomy aspects.

Browse data is *display-only* (ADR-0009): it becomes current asks, never comps
or estimates. Sandbox and production differ only in host.
"""

from __future__ import annotations

import base64
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx

from card_maven.market.sources.port import MarketQuery, MarketRecord, MarketSourceError, Option
from card_maven.shared.clock import utcnow
from card_maven.shared.config import Settings
from card_maven.shared.errors import DependencyUnavailableError
from card_maven.shared.money import Money

HOSTS = {"sandbox": "https://api.sandbox.ebay.com", "production": "https://api.ebay.com"}
SCOPE = "https://api.ebay.com/oauth/api_scope"
GRADED_CONDITION_ID = "2750"
UNGRADED_CONDITION_ID = "4000"
MAX_KEYWORDS = 100  # eBay truncates longer `q` values
TOKEN_EARLY_REFRESH = timedelta(seconds=60)
# Item specifics the title parser can use. Others are ignored.
TAXONOMY_ASPECTS = frozenset({"Parallel/Variety", "Professional Grader", "Grade", "Manufacturer"})


def _raise_for(response: httpx.Response, what: str) -> None:
    if response.status_code == 429 or response.status_code >= 500:
        raise DependencyUnavailableError(f"eBay {what} unavailable (HTTP {response.status_code})")
    if response.status_code >= 400:
        raise MarketSourceError(f"eBay {what} rejected the request (HTTP {response.status_code})")


class EbayAuth:
    """Application access tokens, cached until shortly before they expire."""

    def __init__(self, client: httpx.Client, host: str, client_id: str, client_secret: str) -> None:
        self._client = client
        self._url = f"{host}/identity/v1/oauth2/token"
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        self._authorization = f"Basic {basic}"
        self._token: str | None = None
        self._expires_at = datetime.min.replace(tzinfo=utcnow().tzinfo)
        self._lock = threading.Lock()

    def token(self) -> str:
        with self._lock:
            if self._token is None or utcnow() >= self._expires_at - TOKEN_EARLY_REFRESH:
                self._refresh()
            assert self._token is not None
            return self._token

    def invalidate(self) -> None:
        with self._lock:
            self._token = None

    def _refresh(self) -> None:
        try:
            response = self._client.post(
                self._url,
                headers={
                    "Authorization": self._authorization,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"grant_type": "client_credentials", "scope": SCOPE},
            )
        except httpx.HTTPError as exc:
            raise DependencyUnavailableError("eBay OAuth is unreachable") from exc
        if response.status_code in (400, 401):
            raise MarketSourceError("eBay rejected the client credentials; check CARD_MAVEN_EBAY_*")
        _raise_for(response, "OAuth")
        body = response.json()
        self._token = body["access_token"]
        self._expires_at = utcnow() + timedelta(seconds=int(body.get("expires_in", 7200)))


def _option(buying_options: Sequence[str]) -> Option:
    if "AUCTION" in buying_options:
        return "auction"
    if "FIXED_PRICE" in buying_options:
        return "fixed_price"
    if "BEST_OFFER" in buying_options:
        return "best_offer"
    return "other"


def _money(amount: dict[str, Any] | None) -> Money | None:
    if not amount or "value" not in amount:
        return None
    return Money.from_decimal(str(amount["value"]), str(amount.get("currency", "USD")))


def _timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def map_item(item: dict[str, Any], *, observed_at: datetime) -> MarketRecord | None:
    """Translate one ``itemSummaries[]`` entry. Returns ``None`` if it has no usable price."""
    option = _option(item.get("buyingOptions") or [])
    price = _money(item.get("currentBidPrice")) if option == "auction" else None
    price = price or _money(item.get("price"))
    if price is None or not item.get("itemId") or not item.get("title"):
        return None
    condition_id = str(item.get("conditionId") or "")
    hint = {GRADED_CONDITION_ID: "graded", UNGRADED_CONDITION_ID: "raw"}.get(condition_id)
    return MarketRecord(
        kind="listing",
        source_listing_id=str(item["itemId"]),
        title=str(item["title"]),
        price=price,
        occurred_at=observed_at,
        option=option,
        bid_count=item.get("bidCount"),
        # Prefer the affiliate (EPN) link when eBay returns one.
        url=item.get("itemAffiliateWebUrl") or item.get("itemWebUrl"),
        image_url=(item.get("image") or {}).get("imageUrl"),
        ends_at=_timestamp(item.get("itemEndDate")),
        condition_hint=hint,  # type: ignore[arg-type]
        payload={
            k: item[k]
            for k in ("itemId", "legacyItemId", "condition", "conditionId", "buyingOptions")
            if k in item
        },
    )


@dataclass(frozen=True, slots=True)
class EbayConfig:
    host: str
    client_id: str
    client_secret: str
    marketplace_id: str
    category_id: str
    campaign_id: str | None

    @classmethod
    def from_settings(cls, settings: Settings) -> EbayConfig:
        if settings.ebay_client_id is None or settings.ebay_client_secret is None:
            raise MarketSourceError(
                "eBay is enabled but CARD_MAVEN_EBAY_CLIENT_ID/SECRET are unset"
            )
        return cls(
            host=HOSTS[settings.ebay_environment],
            client_id=settings.ebay_client_id.get_secret_value(),
            client_secret=settings.ebay_client_secret.get_secret_value(),
            marketplace_id=settings.ebay_marketplace_id,
            category_id=settings.ebay_category_id,
            campaign_id=settings.ebay_campaign_id,
        )


class EbayApi:
    """Authenticated GETs against one eBay environment, shared by Browse and Taxonomy."""

    def __init__(self, config: EbayConfig, client: httpx.Client | None = None) -> None:
        self.config = config
        self._client = client or httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0))
        self._auth = EbayAuth(self._client, config.host, config.client_id, config.client_secret)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._auth.token()}",
            "X-EBAY-C-MARKETPLACE-ID": self.config.marketplace_id,
        }
        if self.config.campaign_id:
            headers["X-EBAY-C-ENDUSERCTX"] = f"affiliateCampaignId={self.config.campaign_id}"
        return headers

    def get(self, path: str, params: dict[str, Any], *, what: str) -> dict[str, Any]:
        url = f"{self.config.host}{path}"
        try:
            response = self._client.get(url, params=params, headers=self._headers())
            if response.status_code == 401:  # token revoked or expired early: one retry
                self._auth.invalidate()
                response = self._client.get(url, params=params, headers=self._headers())
        except httpx.HTTPError as exc:
            raise DependencyUnavailableError(f"eBay {what} is unreachable") from exc
        _raise_for(response, what)
        body: dict[str, Any] = response.json()
        return body


class EbayBrowseSource:
    code = "ebay_browse"

    def __init__(self, api: EbayApi) -> None:
        self._api = api

    def fetch(self, query: MarketQuery, *, now: datetime) -> Sequence[MarketRecord]:
        body = self._api.get(
            "/buy/browse/v1/item_summary/search",
            {
                "q": query.keywords[:MAX_KEYWORDS],
                "category_ids": self._api.config.category_id,
                "filter": "buyingOptions:{FIXED_PRICE|AUCTION}",
                "limit": str(min(query.limit, 200)),
            },
            what="Browse search",
        )
        items = body.get("itemSummaries") or []
        return [r for item in items if (r := map_item(item, observed_at=now)) is not None]


class EbayTaxonomyClient:
    """Item-specific vocabulary (parallels, graders, grades) for a category."""

    def __init__(self, api: EbayApi) -> None:
        self._api = api

    def aspect_values(self) -> list[tuple[str, str]]:
        config = self._api.config
        tree = self._api.get(
            "/commerce/taxonomy/v1/get_default_category_tree_id",
            {"marketplace_id": config.marketplace_id},
            what="Taxonomy",
        )
        body = self._api.get(
            f"/commerce/taxonomy/v1/category_tree/{tree['categoryTreeId']}/get_item_aspects_for_category",
            {"category_id": config.category_id},
            what="Taxonomy",
        )
        pairs: set[tuple[str, str]] = set()
        for aspect in body.get("aspects") or []:
            name = aspect.get("localizedAspectName")
            if name not in TAXONOMY_ASPECTS:
                continue
            for value in aspect.get("aspectValues") or []:
                text = str(value.get("localizedValue", "")).strip()
                if text:
                    pairs.add((name, text[:200]))
        return sorted(pairs)
