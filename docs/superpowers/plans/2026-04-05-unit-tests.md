# Backend Unit Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pytest test suite covering Flask API routes, SQLAlchemy model logic, and price/listing business rules using an in-memory SQLite database.

**Architecture:** A single `TEST_DATABASE_URI` environment variable set before app import points Flask-SQLAlchemy at `sqlite:///:memory:`. A session-scoped `app` fixture creates tables once; a function-scoped `clean_tables` fixture truncates all rows between tests. External HTTP calls are patched with `unittest.mock.patch`.

**Tech Stack:** Python 3.10+, pytest, Flask test client, SQLAlchemy, unittest.mock (all stdlib/already installed except pytest)

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `app.py` | Modify line 29 | Read `TEST_DATABASE_URI` env var so tests get in-memory SQLite |
| `pytest.ini` | Create | Tell pytest where tests live |
| `tests/__init__.py` | Create | Make tests a package |
| `tests/conftest.py` | Create | App/client fixtures, `clean_tables`, `make_card`, `make_price` factories |
| `tests/test_models.py` | Create | `_trend`, `_recommend`, `to_dict`, `build_search_query` |
| `tests/test_api_cards.py` | Create | Cards CRUD + search/filter routes |
| `tests/test_api_prices.py` | Create | Price history, manual price, refresh-prices |
| `tests/test_api_listings.py` | Create | generate-listing, listing CRUD |
| `tests/test_api_dashboard.py` | Create | Dashboard aggregation |

---

## Task 1: Scaffold — app.py patch, pytest.ini, conftest.py

**Files:**
- Modify: `app.py:29`
- Create: `pytest.ini`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Patch app.py to support TEST_DATABASE_URI**

In `app.py`, find line 29 (inside `app.config.update(...)`):

```python
    SQLALCHEMY_DATABASE_URI=f"sqlite:///{os.path.join(BASE_DIR, 'card_maven.db')}",
```

Replace with:

```python
    SQLALCHEMY_DATABASE_URI=os.environ.get('TEST_DATABASE_URI') or f"sqlite:///{os.path.join(BASE_DIR, 'card_maven.db')}",
```

This lets conftest.py set `TEST_DATABASE_URI=sqlite:///:memory:` before importing app, so the very first engine Flask-SQLAlchemy creates points at in-memory SQLite — no file created, no cache to clear.

- [ ] **Step 2: Create pytest.ini**

```ini
[pytest]
testpaths = tests
```

- [ ] **Step 3: Create tests/__init__.py**

Empty file — just needs to exist.

```python
```

- [ ] **Step 4: Create tests/conftest.py**

```python
import os
import pytest
from datetime import datetime

# Must be set BEFORE app is imported so Flask-SQLAlchemy creates the engine
# pointing at in-memory SQLite rather than card_maven.db.
os.environ.setdefault('TEST_DATABASE_URI', 'sqlite:///:memory:')

from app import app as flask_app, db as _db, Card, PriceRecord, EbayListing  # noqa: E402


@pytest.fixture(scope='session')
def app():
    flask_app.config.update({'TESTING': True})
    with flask_app.app_context():
        _db.create_all()
    yield flask_app
    with flask_app.app_context():
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def clean_tables(app):
    """Truncate every table after each test so tests are fully isolated."""
    yield
    with app.app_context():
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()


@pytest.fixture
def make_card(app):
    """
    Factory that inserts a Card and returns its integer ID.

    Usage:
        card_id = make_card(player='Mike Trout', purchase_price=50.0)
        card_id = make_card()  # uses defaults
    """
    def _factory(
        player='Test Player',
        year='2020',
        card_set='Topps',
        purchase_price=50.0,
        **kwargs,
    ):
        with app.app_context():
            card = Card(
                player=player,
                year=year,
                card_set=card_set,
                purchase_price=purchase_price,
                **kwargs,
            )
            _db.session.add(card)
            _db.session.commit()
            return card.id

    return _factory


@pytest.fixture
def make_price(app):
    """
    Factory that inserts a PriceRecord and returns its integer ID.

    Usage:
        make_price(card_id, price=80.0)
        make_price(card_id, price=80.0, fetched_at=datetime(2023, 1, 1))
        make_price(card_id, price=80.0, listing_url='http://ebay.com/1')
    """
    def _factory(card_id, price, source='manual', fetched_at=None,
                 listing_url=None, **kwargs):
        with app.app_context():
            pr = PriceRecord(
                card_id=card_id,
                source=source,
                price=price,
                fetched_at=fetched_at or datetime.utcnow(),
                listing_url=listing_url,
                **kwargs,
            )
            _db.session.add(pr)
            _db.session.commit()
            return pr.id

    return _factory
```

- [ ] **Step 5: Install pytest and verify the scaffold imports cleanly**

```bash
cd "/Users/lfoos/Documents/Claude/Projects/Card Maven"
pip3 install pytest --break-system-packages --quiet
pytest tests/ --collect-only
```

Expected: pytest discovers zero tests (no test files yet) with no import errors.

- [ ] **Step 6: Commit**

```bash
git add app.py pytest.ini tests/
git commit -m "test: scaffold pytest suite with conftest, fixtures, and in-memory SQLite"
```

---

## Task 2: test_models.py — Pure logic, no HTTP

**Files:**
- Create: `tests/test_models.py`

- [ ] **Step 1: Create tests/test_models.py**

```python
import pytest
from datetime import datetime, timedelta
from app import Card, PriceRecord, build_search_query


# ── Card._trend ───────────────────────────────────────────────────────────────

class TestTrend:
    """
    _trend(prices) splits the list in half and compares averages.
    >10% increase → "up", >10% decrease → "down", otherwise "neutral".
    Requires at least 3 prices; fewer returns "neutral".
    """

    def setup_method(self):
        self.card = Card(player='Test', purchase_price=100.0)

    def test_empty_list_is_neutral(self):
        assert self.card._trend([]) == 'neutral'

    def test_one_price_is_neutral(self):
        assert self.card._trend([50]) == 'neutral'

    def test_two_prices_is_neutral(self):
        assert self.card._trend([50, 60]) == 'neutral'

    def test_up_when_second_half_over_10_pct_higher(self):
        # first-half avg=10, second-half avg=12 → +20% → "up"
        assert self.card._trend([10, 10, 12, 12]) == 'up'

    def test_down_when_second_half_over_10_pct_lower(self):
        # first-half avg=10, second-half avg=8 → -20% → "down"
        assert self.card._trend([10, 10, 8, 8]) == 'down'

    def test_neutral_when_change_within_10_pct(self):
        # first-half avg=10, second-half avg=10.5 → +5% → "neutral"
        assert self.card._trend([10, 10, 10.5, 10.5]) == 'neutral'

    def test_exactly_10_pct_is_neutral(self):
        # +10% is not > 10, so "neutral"
        assert self.card._trend([10, 10, 11, 11]) == 'neutral'


# ── Card._recommend ───────────────────────────────────────────────────────────

class TestRecommend:
    """
    _recommend(prices) returns (action, reason).
    Requires both prices and purchase_price to produce a non-trivial result.
    ROI is computed from estimated_value (or median of prices if no estimated_value).
    """

    def setup_method(self):
        self.card = Card(player='Test')

    def test_hold_when_no_prices(self):
        rec, reason = self.card._recommend([])
        assert rec == 'hold'
        assert reason == 'Not enough data yet'

    def test_hold_when_no_purchase_price(self):
        self.card.purchase_price = None
        rec, reason = self.card._recommend([100])
        assert rec == 'hold'
        assert reason == 'Not enough data yet'

    def test_sell_when_roi_over_100_and_trend_up(self):
        # ROI = (110-50)/50*100 = 120%; trend "up" bypasses check 3, hits check 4
        self.card.purchase_price = 50.0
        self.card.estimated_value = 110.0
        prices = [50, 50, 100, 100]   # second half avg 100 > first half avg 50 → "up"
        rec, reason = self.card._recommend(prices)
        assert rec == 'sell'
        assert '120' in reason

    def test_sell_when_roi_over_50_and_trend_neutral(self):
        # ROI = (160-100)/100*100 = 60%; trend "neutral" → check 3 fires
        self.card.purchase_price = 100.0
        self.card.estimated_value = 160.0
        prices = [100, 100, 100, 100]  # no change → "neutral"
        rec, reason = self.card._recommend(prices)
        assert rec == 'sell'

    def test_hold_when_trend_up_and_roi_under_20(self):
        # ROI = (110-100)/100*100 = 10%; trend "up" and roi < 20 → "hold" (check 7)
        self.card.purchase_price = 100.0
        self.card.estimated_value = 110.0
        prices = [80, 80, 100, 100]   # second half > first half by 25% → "up"
        rec, reason = self.card._recommend(prices)
        assert rec == 'hold'

    def test_sell_when_roi_under_negative_30(self):
        # ROI = (60-100)/100*100 = -40%; trend "down" → check 6 fires
        self.card.purchase_price = 100.0
        self.card.estimated_value = 60.0
        prices = [80, 80, 60, 60]     # second half < first half by 25% → "down"
        rec, reason = self.card._recommend(prices)
        assert rec == 'sell'

    def test_hold_when_losing_but_trend_recovering(self):
        # ROI = (85-100)/100*100 = -15%; trend "up" and roi between -20 and 0 → default hold
        self.card.purchase_price = 100.0
        self.card.estimated_value = 85.0
        prices = [70, 70, 90, 90]     # "up"
        rec, _ = self.card._recommend(prices)
        assert rec == 'hold'


# ── Card.to_dict ──────────────────────────────────────────────────────────────

class TestToDict:
    def test_roi_is_none_when_no_purchase_price(self, app, make_card):
        card_id = make_card(purchase_price=None)
        with app.app_context():
            d = Card.query.get(card_id).to_dict()
        assert d['roi'] is None

    def test_roi_is_none_when_purchase_price_is_zero(self, app, make_card):
        card_id = make_card(purchase_price=0.0)
        with app.app_context():
            d = Card.query.get(card_id).to_dict()
        assert d['roi'] is None

    def test_recent_prices_exclude_records_older_than_90_days(
        self, app, make_card, make_price
    ):
        card_id = make_card(purchase_price=50.0)
        old = datetime.utcnow() - timedelta(days=100)
        make_price(card_id, price=200.0, fetched_at=old)   # outside 90-day window
        make_price(card_id, price=80.0)                     # recent
        with app.app_context():
            d = Card.query.get(card_id).to_dict()
        assert d['price_count'] == 1
        assert d['recent_avg'] == 80.0

    def test_price_count_matches_recent_records(self, app, make_card, make_price):
        card_id = make_card()
        make_price(card_id, price=60.0)
        make_price(card_id, price=70.0)
        with app.app_context():
            d = Card.query.get(card_id).to_dict()
        assert d['price_count'] == 2

    def test_recent_avg_and_median_are_correct(self, app, make_card, make_price):
        card_id = make_card()
        for p in [60.0, 80.0, 100.0]:
            make_price(card_id, price=p)
        with app.app_context():
            d = Card.query.get(card_id).to_dict()
        assert d['recent_avg'] == 80.0
        assert d['recent_median'] == 80.0


# ── build_search_query ────────────────────────────────────────────────────────

class TestBuildSearchQuery:
    def test_includes_player(self):
        card = Card(player='Mike Trout')
        assert 'Mike Trout' in build_search_query(card)

    def test_includes_year_and_set(self):
        card = Card(player='Mike Trout', year='2011', card_set='Topps Update')
        q = build_search_query(card)
        assert '2011' in q
        assert 'Topps Update' in q

    def test_includes_grader_and_grade_as_pair(self):
        card = Card(player='Mike Trout', grader='PSA', grade='10')
        assert 'PSA 10' in build_search_query(card)

    def test_includes_variation(self):
        card = Card(player='Mike Trout', variation='Gold Refractor')
        assert 'Gold Refractor' in build_search_query(card)

    def test_omits_missing_fields_without_extra_spaces(self):
        card = Card(player='Mike Trout')   # no year, set, variation, grader, grade
        q = build_search_query(card)
        assert '  ' not in q              # no double spaces
        assert q == q.strip()             # no leading/trailing whitespace

    def test_only_grade_no_grader_uses_grade_alone(self):
        card = Card(player='Mike Trout', grade='10')  # grade but no grader
        q = build_search_query(card)
        assert '10' in q
```

- [ ] **Step 2: Run models tests**

```bash
pytest tests/test_models.py -v
```

Expected: all tests pass (green). If `test_sell_when_roi_over_100_and_trend_up` fails, recheck that `purchase_price=50, estimated_value=110` gives ROI=120 and the prices `[50,50,100,100]` produce trend "up".

- [ ] **Step 3: Commit**

```bash
git add tests/test_models.py
git commit -m "test: add model unit tests for _trend, _recommend, to_dict, build_search_query"
```

---

## Task 3: test_api_cards.py — CRUD + search

**Files:**
- Create: `tests/test_api_cards.py`

- [ ] **Step 1: Create tests/test_api_cards.py**

```python
import pytest
from app import PriceRecord


class TestCreateCard:
    def test_returns_201(self, client):
        resp = client.post('/api/cards', json={'player': 'Mike Trout'})
        assert resp.status_code == 201

    def test_returns_submitted_fields(self, client):
        resp = client.post('/api/cards', json={
            'player': 'Mike Trout',
            'year': '2011',
            'card_set': 'Topps Update',
        })
        data = resp.get_json()
        assert data['player'] == 'Mike Trout'
        assert data['year'] == '2011'
        assert data['card_set'] == 'Topps Update'

    def test_missing_player_defaults_to_unknown(self, client):
        resp = client.post('/api/cards', json={})
        assert resp.status_code == 201
        assert resp.get_json()['player'] == 'Unknown'


class TestListCards:
    def test_returns_all_cards(self, client, make_card):
        make_card(player='Mike Trout')
        make_card(player='Derek Jeter')
        resp = client.get('/api/cards')
        assert resp.status_code == 200
        assert len(resp.get_json()) == 2

    def test_empty_collection_returns_empty_list(self, client):
        resp = client.get('/api/cards')
        assert resp.get_json() == []

    def test_search_by_player(self, client, make_card):
        make_card(player='Mike Trout')
        make_card(player='Derek Jeter')
        cards = client.get('/api/cards?q=trout').get_json()
        assert len(cards) == 1
        assert cards[0]['player'] == 'Mike Trout'

    def test_search_by_set(self, client, make_card):
        make_card(player='Mike Trout', card_set='Topps Update')
        make_card(player='Derek Jeter', card_set='Bowman')
        cards = client.get('/api/cards?q=topps').get_json()
        assert len(cards) == 1
        assert cards[0]['card_set'] == 'Topps Update'

    def test_search_is_case_insensitive(self, client, make_card):
        make_card(player='Mike Trout')
        cards = client.get('/api/cards?q=TROUT').get_json()
        assert len(cards) == 1

    def test_search_returns_empty_when_no_match(self, client, make_card):
        make_card(player='Mike Trout')
        cards = client.get('/api/cards?q=zzznomatch').get_json()
        assert cards == []


class TestGetCard:
    def test_returns_correct_card(self, client, make_card):
        card_id = make_card(player='Mike Trout')
        data = client.get(f'/api/cards/{card_id}').get_json()
        assert data['player'] == 'Mike Trout'
        assert data['id'] == card_id

    def test_missing_card_returns_404(self, client):
        resp = client.get('/api/cards/9999')
        assert resp.status_code == 404


class TestUpdateCard:
    def test_updates_player_name(self, client, make_card):
        card_id = make_card(player='Mike Trout')
        resp = client.put(f'/api/cards/{card_id}', json={'player': 'Ken Griffey Jr'})
        assert resp.status_code == 200
        assert resp.get_json()['player'] == 'Ken Griffey Jr'

    def test_updates_multiple_fields(self, client, make_card):
        card_id = make_card()
        resp = client.put(f'/api/cards/{card_id}', json={
            'year': '1999',
            'card_set': 'Bowman Chrome',
            'grade': '9',
        })
        data = resp.get_json()
        assert data['year'] == '1999'
        assert data['card_set'] == 'Bowman Chrome'
        assert data['grade'] == '9'

    def test_update_missing_card_returns_404(self, client):
        resp = client.put('/api/cards/9999', json={'player': 'Nobody'})
        assert resp.status_code == 404


class TestDeleteCard:
    def test_returns_deleted_true(self, client, make_card):
        card_id = make_card()
        resp = client.delete(f'/api/cards/{card_id}')
        assert resp.status_code == 200
        assert resp.get_json() == {'deleted': True}

    def test_deleted_card_returns_404_on_get(self, client, make_card):
        card_id = make_card()
        client.delete(f'/api/cards/{card_id}')
        assert client.get(f'/api/cards/{card_id}').status_code == 404

    def test_delete_cascades_price_records(self, client, app, make_card, make_price):
        card_id = make_card()
        make_price(card_id, price=75.0)
        client.delete(f'/api/cards/{card_id}')
        with app.app_context():
            assert PriceRecord.query.filter_by(card_id=card_id).count() == 0

    def test_delete_missing_card_returns_404(self, client):
        resp = client.delete('/api/cards/9999')
        assert resp.status_code == 404
```

- [ ] **Step 2: Run card API tests**

```bash
pytest tests/test_api_cards.py -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_api_cards.py
git commit -m "test: add API tests for cards CRUD and search"
```

---

## Task 4: test_api_prices.py — Price history, manual entry, refresh

**Files:**
- Create: `tests/test_api_prices.py`

- [ ] **Step 1: Create tests/test_api_prices.py**

```python
import pytest
from unittest.mock import patch


class TestGetPriceHistory:
    def test_empty_history_returns_empty_list(self, client, make_card):
        card_id = make_card()
        resp = client.get(f'/api/cards/{card_id}/prices')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_returns_all_price_records(self, client, make_card, make_price):
        card_id = make_card()
        make_price(card_id, price=50.0)
        make_price(card_id, price=60.0)
        records = client.get(f'/api/cards/{card_id}/prices').get_json()
        assert len(records) == 2

    def test_returns_prices_for_correct_card_only(self, client, make_card, make_price):
        card_a = make_card(player='A')
        card_b = make_card(player='B')
        make_price(card_a, price=50.0)
        make_price(card_b, price=999.0)
        records = client.get(f'/api/cards/{card_a}/prices').get_json()
        assert len(records) == 1
        assert records[0]['price'] == 50.0


class TestAddManualPrice:
    def test_returns_201(self, client, make_card):
        card_id = make_card()
        resp = client.post(f'/api/cards/{card_id}/prices', json={'price': 75.0})
        assert resp.status_code == 201

    def test_price_appears_in_history(self, client, make_card):
        card_id = make_card()
        client.post(f'/api/cards/{card_id}/prices', json={'price': 75.0})
        records = client.get(f'/api/cards/{card_id}/prices').get_json()
        assert any(r['price'] == 75.0 for r in records)

    def test_estimated_value_updated_to_single_price(self, client, make_card):
        card_id = make_card()
        client.post(f'/api/cards/{card_id}/prices', json={'price': 80.0})
        data = client.get(f'/api/cards/{card_id}').get_json()
        assert data['estimated_value'] == 80.0

    def test_estimated_value_is_median_of_multiple_prices(self, client, make_card):
        card_id = make_card()
        for p in [60.0, 80.0, 100.0]:
            client.post(f'/api/cards/{card_id}/prices', json={'price': p})
        data = client.get(f'/api/cards/{card_id}').get_json()
        assert data['estimated_value'] == 80.0   # median of [60, 80, 100]

    def test_source_defaults_to_manual(self, client, make_card):
        card_id = make_card()
        client.post(f'/api/cards/{card_id}/prices', json={'price': 75.0})
        records = client.get(f'/api/cards/{card_id}/prices').get_json()
        assert records[0]['source'] == 'manual'


class TestRefreshPrices:
    def test_stores_new_records_and_returns_added_count(self, client, make_card):
        card_id = make_card(player='Mike Trout', year='2011', card_set='Topps')
        mock_records = [
            {'price': 100.0, 'sale_date': '2024-01-01',
             'url': 'http://ebay.com/1', 'title': 'Mike Trout PSA 10'},
        ]
        with patch('app.fetch_ebay_sold', return_value=mock_records), \
             patch('app.fetch_130point', return_value=[]):
            resp = client.post(f'/api/cards/{card_id}/refresh-prices')
        assert resp.status_code == 200
        assert resp.get_json()['added'] == 1

    def test_deduplicates_by_url_on_second_refresh(self, client, make_card):
        card_id = make_card(player='Mike Trout', year='2011', card_set='Topps')
        mock_records = [
            {'price': 100.0, 'sale_date': '2024-01-01',
             'url': 'http://ebay.com/1', 'title': 'Mike Trout PSA 10'},
        ]
        with patch('app.fetch_ebay_sold', return_value=mock_records), \
             patch('app.fetch_130point', return_value=[]):
            client.post(f'/api/cards/{card_id}/refresh-prices')
            resp = client.post(f'/api/cards/{card_id}/refresh-prices')
        assert resp.get_json()['added'] == 0

    def test_estimated_value_updated_after_refresh(self, client, make_card):
        card_id = make_card(player='Mike Trout', year='2011', card_set='Topps')
        mock_records = [
            {'price': 120.0, 'sale_date': '2024-01-01',
             'url': 'http://ebay.com/2', 'title': 'Mike Trout'},
        ]
        with patch('app.fetch_ebay_sold', return_value=mock_records), \
             patch('app.fetch_130point', return_value=[]):
            client.post(f'/api/cards/{card_id}/refresh-prices')
        data = client.get(f'/api/cards/{card_id}').get_json()
        assert data['estimated_value'] == 120.0

    def test_both_sources_combined(self, client, make_card):
        card_id = make_card(player='Mike Trout', year='2011', card_set='Topps')
        ebay_records = [
            {'price': 100.0, 'url': 'http://ebay.com/1', 'sale_date': '', 'title': ''},
        ]
        point_records = [
            {'price': 90.0, 'url': 'http://130point.com/1', 'sale_date': '', 'title': ''},
        ]
        with patch('app.fetch_ebay_sold', return_value=ebay_records), \
             patch('app.fetch_130point', return_value=point_records):
            resp = client.post(f'/api/cards/{card_id}/refresh-prices')
        assert resp.get_json()['added'] == 2
```

- [ ] **Step 2: Run price API tests**

```bash
pytest tests/test_api_prices.py -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_api_prices.py
git commit -m "test: add API tests for price history, manual entry, and refresh-prices"
```

---

## Task 5: test_api_listings.py — generate-listing + CRUD

**Files:**
- Create: `tests/test_api_listings.py`

- [ ] **Step 1: Create tests/test_api_listings.py**

```python
import pytest
import statistics


class TestGenerateListing:
    def test_returns_201_with_draft_status(self, client, make_card):
        card_id = make_card(player='Mike Trout', year='2011', card_set='Topps Update')
        resp = client.post(f'/api/cards/{card_id}/generate-listing')
        assert resp.status_code == 201
        assert resp.get_json()['status'] == 'draft'

    def test_title_is_at_most_80_chars(self, client, make_card):
        card_id = make_card(
            player='A Very Long Player Name That Is Definitely Over Eighty Characters Long',
            year='2011',
            card_set='Topps Update Series',
            variation='Gold Refractor Prizm',
        )
        title = client.post(f'/api/cards/{card_id}/generate-listing').get_json()['title']
        assert len(title) <= 80

    def test_title_contains_player_name(self, client, make_card):
        card_id = make_card(player='Mike Trout', year='2011')
        title = client.post(f'/api/cards/{card_id}/generate-listing').get_json()['title']
        assert 'Mike Trout' in title

    def test_pricing_from_comps(self, client, make_card, make_price):
        card_id = make_card(player='Mike Trout')
        make_price(card_id, price=100.0)
        make_price(card_id, price=120.0)
        data = client.post(f'/api/cards/{card_id}/generate-listing').get_json()
        expected_buy_now = round(statistics.median([100.0, 120.0]) * 0.95, 2)
        assert data['buy_now_price'] == expected_buy_now

    def test_pricing_fallback_to_estimated_value(self, client, make_card):
        card_id = make_card(player='Mike Trout', estimated_value=200.0)
        data = client.post(f'/api/cards/{card_id}/generate-listing').get_json()
        assert data['buy_now_price'] == round(200.0 * 0.95, 2)

    def test_pricing_is_none_when_no_comps_or_value(self, client, make_card):
        card_id = make_card(player='Mike Trout', estimated_value=None)
        data = client.post(f'/api/cards/{card_id}/generate-listing').get_json()
        assert data['buy_now_price'] is None

    def test_generate_for_missing_card_returns_404(self, client):
        resp = client.post('/api/cards/9999/generate-listing')
        assert resp.status_code == 404


class TestListListings:
    def test_returns_all_listings(self, client, make_card):
        card_id = make_card()
        client.post(f'/api/cards/{card_id}/generate-listing')
        client.post(f'/api/cards/{card_id}/generate-listing')
        listings = client.get('/api/listings').get_json()
        assert len(listings) == 2

    def test_empty_returns_empty_list(self, client):
        assert client.get('/api/listings').get_json() == []

    def test_filter_by_draft_status(self, client, make_card):
        card_id = make_card()
        # Create two listings; mark one as posted
        listing_id = client.post(
            f'/api/cards/{card_id}/generate-listing'
        ).get_json()['id']
        client.post(f'/api/cards/{card_id}/generate-listing')
        client.put(f'/api/listings/{listing_id}', json={'status': 'posted'})

        drafts = client.get('/api/listings?status=draft').get_json()
        assert len(drafts) == 1
        assert drafts[0]['status'] == 'draft'

    def test_filter_by_posted_status(self, client, make_card):
        card_id = make_card()
        listing_id = client.post(
            f'/api/cards/{card_id}/generate-listing'
        ).get_json()['id']
        client.put(f'/api/listings/{listing_id}', json={'status': 'posted'})

        posted = client.get('/api/listings?status=posted').get_json()
        assert len(posted) == 1
        assert posted[0]['status'] == 'posted'


class TestGetListing:
    def test_returns_correct_listing(self, client, make_card):
        card_id = make_card(player='Mike Trout')
        listing_id = client.post(
            f'/api/cards/{card_id}/generate-listing'
        ).get_json()['id']
        data = client.get(f'/api/listings/{listing_id}').get_json()
        assert data['id'] == listing_id

    def test_includes_nested_card_fields(self, client, make_card):
        card_id = make_card(player='Mike Trout')
        listing_id = client.post(
            f'/api/cards/{card_id}/generate-listing'
        ).get_json()['id']
        data = client.get(f'/api/listings/{listing_id}').get_json()
        assert data['card']['player'] == 'Mike Trout'

    def test_missing_listing_returns_404(self, client):
        assert client.get('/api/listings/9999').status_code == 404


class TestUpdateListing:
    def test_updates_title_and_price(self, client, make_card):
        card_id = make_card()
        listing_id = client.post(
            f'/api/cards/{card_id}/generate-listing'
        ).get_json()['id']
        resp = client.put(f'/api/listings/{listing_id}', json={
            'title': 'Updated Title',
            'buy_now_price': 99.99,
        })
        data = resp.get_json()
        assert data['title'] == 'Updated Title'
        assert data['buy_now_price'] == 99.99

    def test_status_transition_draft_to_posted(self, client, make_card):
        card_id = make_card()
        listing_id = client.post(
            f'/api/cards/{card_id}/generate-listing'
        ).get_json()['id']
        data = client.put(
            f'/api/listings/{listing_id}', json={'status': 'posted'}
        ).get_json()
        assert data['status'] == 'posted'

    def test_status_transition_to_sold(self, client, make_card):
        card_id = make_card()
        listing_id = client.post(
            f'/api/cards/{card_id}/generate-listing'
        ).get_json()['id']
        data = client.put(
            f'/api/listings/{listing_id}', json={'status': 'sold'}
        ).get_json()
        assert data['status'] == 'sold'


class TestDeleteListing:
    def test_returns_deleted_true(self, client, make_card):
        card_id = make_card()
        listing_id = client.post(
            f'/api/cards/{card_id}/generate-listing'
        ).get_json()['id']
        resp = client.delete(f'/api/listings/{listing_id}')
        assert resp.get_json() == {'deleted': True}

    def test_deleted_listing_returns_404(self, client, make_card):
        card_id = make_card()
        listing_id = client.post(
            f'/api/cards/{card_id}/generate-listing'
        ).get_json()['id']
        client.delete(f'/api/listings/{listing_id}')
        assert client.get(f'/api/listings/{listing_id}').status_code == 404
```

- [ ] **Step 2: Run listing API tests**

```bash
pytest tests/test_api_listings.py -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_api_listings.py
git commit -m "test: add API tests for listing generation and CRUD"
```

---

## Task 6: test_api_dashboard.py — Aggregation

**Files:**
- Create: `tests/test_api_dashboard.py`

- [ ] **Step 1: Create tests/test_api_dashboard.py**

```python
import pytest
from datetime import datetime


class TestDashboardEmpty:
    def test_empty_collection_returns_all_zeros_and_empty_lists(self, client):
        data = client.get('/api/dashboard').get_json()
        assert data['total_cards'] == 0
        assert data['total_invested'] == 0
        assert data['total_value'] == 0
        assert data['total_profit'] == 0
        assert data['sell_alerts'] == 0
        assert data['recent_cards'] == []
        assert data['sell_alert_cards'] == []


class TestDashboardTotals:
    def test_total_invested_sums_purchase_prices(self, client, make_card):
        make_card(purchase_price=100.0)
        make_card(purchase_price=200.0)
        data = client.get('/api/dashboard').get_json()
        assert data['total_invested'] == 300.0

    def test_total_cards_count(self, client, make_card):
        make_card()
        make_card()
        make_card()
        data = client.get('/api/dashboard').get_json()
        assert data['total_cards'] == 3

    def test_total_value_uses_estimated_value_when_set(self, client, make_card):
        make_card(purchase_price=100.0, estimated_value=150.0)
        data = client.get('/api/dashboard').get_json()
        assert data['total_value'] == 150.0

    def test_total_value_falls_back_to_purchase_price_when_no_estimate(
        self, client, make_card
    ):
        make_card(purchase_price=100.0)   # no estimated_value
        data = client.get('/api/dashboard').get_json()
        assert data['total_value'] == 100.0

    def test_total_profit_is_value_minus_invested(self, client, make_card):
        make_card(purchase_price=100.0, estimated_value=130.0)
        data = client.get('/api/dashboard').get_json()
        assert data['total_profit'] == 30.0

    def test_total_profit_is_negative_when_underwater(self, client, make_card):
        make_card(purchase_price=100.0, estimated_value=80.0)
        data = client.get('/api/dashboard').get_json()
        assert data['total_profit'] == -20.0


class TestDashboardAlerts:
    def test_sell_alerts_count_matches_sell_recommended_cards(
        self, client, make_card, make_price
    ):
        # ROI = (160-100)/100 = 60%, one price record, neutral trend → check 3 fires → "sell"
        card_id = make_card(purchase_price=100.0, estimated_value=160.0)
        make_price(card_id, price=150.0)
        data = client.get('/api/dashboard').get_json()
        assert data['sell_alerts'] == 1

    def test_sell_alerts_zero_when_no_qualifying_cards(self, client, make_card):
        make_card(purchase_price=100.0, estimated_value=110.0)  # ROI=10%, hold
        data = client.get('/api/dashboard').get_json()
        assert data['sell_alerts'] == 0

    def test_sell_alert_cards_returns_at_most_5(self, client, make_card, make_price):
        for _ in range(7):
            card_id = make_card(purchase_price=100.0, estimated_value=160.0)
            make_price(card_id, price=150.0)
        data = client.get('/api/dashboard').get_json()
        assert len(data['sell_alert_cards']) == 5


class TestDashboardRecentCards:
    def test_recent_cards_returns_at_most_5(self, client, make_card):
        for i in range(7):
            make_card(player=f'Player {i}')
        data = client.get('/api/dashboard').get_json()
        assert len(data['recent_cards']) == 5

    def test_recent_cards_ordered_newest_first(self, client, make_card):
        make_card(player='First',  created_at=datetime(2024, 1, 1))
        make_card(player='Second', created_at=datetime(2024, 1, 2))
        make_card(player='Third',  created_at=datetime(2024, 1, 3))
        data = client.get('/api/dashboard').get_json()
        assert data['recent_cards'][0]['player'] == 'Third'

    def test_recent_cards_includes_player_and_value(self, client, make_card):
        make_card(player='Mike Trout', purchase_price=100.0, estimated_value=150.0)
        card = client.get('/api/dashboard').get_json()['recent_cards'][0]
        assert card['player'] == 'Mike Trout'
        assert card['estimated_value'] == 150.0
```

- [ ] **Step 2: Run dashboard tests**

```bash
pytest tests/test_api_dashboard.py -v
```

Expected: all tests pass.

- [ ] **Step 3: Run the full suite to confirm nothing regressed**

```bash
pytest tests/ -v
```

Expected: all tests across all files pass.

- [ ] **Step 4: Commit and push**

```bash
git add tests/test_api_dashboard.py
git commit -m "test: add dashboard aggregation tests"
git push
```

---

## Running Tests

```bash
# Install pytest once
pip3 install pytest --break-system-packages

# Run everything
pytest tests/ -v

# Run a single module
pytest tests/test_models.py -v

# Run a single test
pytest tests/test_models.py::TestTrend::test_up_when_second_half_over_10_pct_higher -v
```
