# Unit Tests Design — Card Maven Backend

**Date:** 2026-04-05
**Scope:** Backend unit tests only (frontend excluded by user decision)
**Stack:** pytest + Flask test client + in-memory SQLite

---

## Approach

Use pytest with Flask's built-in test client and an in-memory SQLite database. Each test runs inside a transaction that rolls back on teardown, giving every test a clean database state without recreating the schema. External HTTP calls (eBay API, 130point scraper) are patched with `unittest.mock.patch` so tests are fully offline.

No new runtime dependencies are required — only `pytest` is added to the dev toolchain.

---

## File Structure

```
tests/
  __init__.py
  conftest.py           # app, client, db_session fixtures; make_card / make_price factories
  test_models.py        # Card._trend, Card._recommend, Card.to_dict, build_search_query
  test_api_cards.py     # Cards CRUD + search/filter routes
  test_api_prices.py    # Price history, manual price entry, refresh-prices
  test_api_listings.py  # generate-listing, listing CRUD
  test_api_dashboard.py # Dashboard aggregation
```

---

## Fixtures (`conftest.py`)

| Fixture | Scope | Purpose |
|---------|-------|---------|
| `app` | session | Flask app with `TESTING=True`, `sqlite:///:memory:`, tables created once |
| `client` | function | Flask test client |
| `db_session` | function | Wraps each test in a rolled-back transaction for isolation |
| `make_card(**kwargs)` | function | Factory: inserts a Card with defaults, returns the ORM object |
| `make_price(card, price, **kwargs)` | function | Factory: inserts a PriceRecord linked to a card |

---

## Test Coverage

### `test_models.py` — Pure logic, no HTTP

**`Card._trend(prices)`**
- Returns `"neutral"` when fewer than 3 prices
- Returns `"up"` when second-half average is >10% above first-half average
- Returns `"down"` when second-half average is >10% below first-half average
- Returns `"neutral"` when difference is ≤10%

**`Card._recommend(prices)`**
- Returns `"sell"` with reason when ROI > 100%
- Returns `"sell"` with reason when ROI > 50% and trend is `"down"` or `"neutral"`
- Returns `"hold"` with reason when trend is `"up"` and ROI < 20%
- Returns `"sell"` with reason when ROI < -30%
- Returns `"hold"` with reason when no purchase price set

**`Card.to_dict()`**
- `roi` is `None` when `purchase_price` is missing or zero
- `recent_avg` and `recent_median` only include records from the last 90 days
- `price_count` matches number of qualifying recent records

**`build_search_query(card)`**
- Includes player, year, set, variation when present
- Appends `"PSA 10"` style string when both grader and grade are set
- Omits missing optional fields without leaving extra spaces

---

### `test_api_cards.py`

| Test | Route | Assertion |
|------|-------|-----------|
| Create card | `POST /api/cards` | Returns 201, body contains all submitted fields |
| Create card missing player | `POST /api/cards` | Still creates with `"Unknown"` player |
| List all cards | `GET /api/cards` | Returns array, count matches DB |
| Search by player | `GET /api/cards?q=trout` | Only matching cards returned |
| Search by set | `GET /api/cards?q=topps` | Only matching cards returned |
| Get single card | `GET /api/cards/<id>` | Returns correct card |
| Get missing card | `GET /api/cards/9999` | Returns 404 |
| Update card | `PUT /api/cards/<id>` | Updated fields reflected in response |
| Delete card | `DELETE /api/cards/<id>` | Returns `{"deleted": true}`; subsequent GET returns 404 |
| Delete cascades prices | `DELETE /api/cards/<id>` | Associated PriceRecords removed |

---

### `test_api_prices.py`

| Test | Route | Assertion |
|------|-------|-----------|
| Get empty price history | `GET /api/cards/<id>/prices` | Returns `[]` |
| Get price history | `GET /api/cards/<id>/prices` | Returns records sorted by date desc |
| Add manual price | `POST /api/cards/<id>/prices` | Returns 201; `estimated_value` updated on card |
| Add manual price invalid | `POST /api/cards/<id>/prices` | Missing `price` key raises an exception and returns an error response |
| Refresh prices (mocked) | `POST /api/cards/<id>/refresh-prices` | Fetchers called; new records stored; `added` count correct |
| Refresh prices deduplication | `POST /api/cards/<id>/refresh-prices` | Duplicate URLs not inserted on second refresh |

---

### `test_api_listings.py`

| Test | Route | Assertion |
|------|-------|-----------|
| Generate listing | `POST /api/cards/<id>/generate-listing` | Returns 201; title ≤ 80 chars; status is `"draft"` |
| Generate listing pricing from comps | `POST /api/cards/<id>/generate-listing` | `buy_now_price` ≈ median × 0.95 when price records exist |
| Generate listing fallback pricing | `POST /api/cards/<id>/generate-listing` | Uses `estimated_value` when no price records |
| List listings | `GET /api/listings` | Returns all listings |
| Filter by status | `GET /api/listings?status=draft` | Only draft listings returned |
| Get single listing | `GET /api/listings/<id>` | Returns listing with nested card fields |
| Update listing | `PUT /api/listings/<id>` | Title, prices, status updated |
| Update listing status | `PUT /api/listings/<id>` | Status transitions (draft → posted → sold) |
| Delete listing | `DELETE /api/listings/<id>` | Returns `{"deleted": true}`; subsequent GET returns 404 |

---

### `test_api_dashboard.py`

| Test | Assertion |
|------|-----------|
| Empty collection | All totals are 0, `sell_alerts` is 0, lists are empty |
| `total_invested` | Sum of all `purchase_price` values |
| `total_value` | Sum of `estimated_value` (falls back to `purchase_price` when null) |
| `total_profit` | `total_value - total_invested` |
| `sell_alerts` count | Matches number of cards where recommendation is `"sell"` |
| `recent_cards` | Returns at most 5 cards, ordered newest first |
| `sell_alert_cards` | Returns at most 5 sell-recommended cards |

---

## Running Tests

```bash
# Install pytest (one-time)
pip3 install pytest

# Run all tests
pytest tests/ -v

# Run a single file
pytest tests/test_models.py -v
```

---

## Out of Scope

- Frontend JavaScript (excluded by design)
- eBay API live integration (patched in all tests)
- 130point.com scraper live integration (patched in all tests)
- Photo upload file I/O (routes tested with empty file payloads only)
