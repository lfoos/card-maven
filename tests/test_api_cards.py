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
        # Verify persisted
        fetched = client.get(f'/api/cards/{card_id}').get_json()
        assert fetched['player'] == 'Ken Griffey Jr'

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
        # Verify persisted
        fetched = client.get(f'/api/cards/{card_id}').get_json()
        assert fetched['year'] == '1999'
        assert fetched['card_set'] == 'Bowman Chrome'
        assert fetched['grade'] == '9'

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
