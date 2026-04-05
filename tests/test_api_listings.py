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
        # Verify persisted
        fetched = client.get(f'/api/listings/{listing_id}').get_json()
        assert fetched['title'] == 'Updated Title'

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
