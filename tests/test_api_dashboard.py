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
