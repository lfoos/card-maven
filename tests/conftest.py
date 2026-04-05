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
