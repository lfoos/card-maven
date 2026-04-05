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
