import pytest
from datetime import datetime, timedelta
from app import Card, PriceRecord, build_search_query, db


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
        assert 'strong profit' in reason

    def test_sell_when_roi_over_50_and_trend_neutral(self):
        # ROI = (160-100)/100*100 = 60%; trend "neutral" → check 3 fires
        self.card.purchase_price = 100.0
        self.card.estimated_value = 160.0
        prices = [100, 100, 100, 100]  # no change → "neutral"
        rec, reason = self.card._recommend(prices)
        assert rec == 'sell'
        assert 'momentum' in reason

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

    def test_hold_default_when_roi_is_moderate(self):
        # ROI = (115-100)/100*100 = 15%; trend "neutral" → no branch fires → default hold
        self.card.purchase_price = 100.0
        self.card.estimated_value = 115.0
        prices = [110, 110, 110, 110]  # neutral trend
        rec, reason = self.card._recommend(prices)
        assert rec == 'hold'
        assert 'Holding at' in reason


# ── Card.to_dict ──────────────────────────────────────────────────────────────

class TestToDict:
    def test_roi_is_none_when_no_purchase_price(self, app, make_card):
        card_id = make_card(purchase_price=None)
        with app.app_context():
            d = db.session.get(Card, card_id).to_dict()
        assert d['roi'] is None

    def test_roi_is_none_when_purchase_price_is_zero(self, app, make_card):
        card_id = make_card(purchase_price=0.0)
        with app.app_context():
            d = db.session.get(Card, card_id).to_dict()
        assert d['roi'] is None

    def test_recent_prices_exclude_records_older_than_90_days(
        self, app, make_card, make_price
    ):
        card_id = make_card(purchase_price=50.0)
        old = datetime.utcnow() - timedelta(days=100)
        make_price(card_id, price=200.0, fetched_at=old)   # outside 90-day window
        make_price(card_id, price=80.0)                     # recent
        with app.app_context():
            d = db.session.get(Card, card_id).to_dict()
        assert d['price_count'] == 1
        assert d['recent_avg'] == 80.0

    def test_price_count_matches_recent_records(self, app, make_card, make_price):
        card_id = make_card()
        make_price(card_id, price=60.0)
        make_price(card_id, price=70.0)
        with app.app_context():
            d = db.session.get(Card, card_id).to_dict()
        assert d['price_count'] == 2

    def test_recent_avg_and_median_are_correct(self, app, make_card, make_price):
        card_id = make_card()
        for p in [60.0, 80.0, 100.0]:
            make_price(card_id, price=p)
        with app.app_context():
            d = db.session.get(Card, card_id).to_dict()
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
