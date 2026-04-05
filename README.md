# Card Maven

A self-hosted sports card collection manager. Track your cards, monitor market prices, and generate eBay listings — all from a local web app.

## Features

- **Collection management** — Add, edit, and delete cards with full metadata (player, year, set, variation, serial number, grade/grader, condition, purchase price)
- **Photo storage** — Upload front and back card photos; images are auto-resized to 1200px
- **Price tracking** — Fetches recently sold comps from eBay (via Finding API) and 130point.com; stores historical price records per card
- **Buy/sell/hold recommendations** — Automatically calculated from ROI and 90-day price trend
- **eBay listing generator** — Produces a ready-to-use title, HTML description, and suggested pricing based on recent comps
- **Dashboard** — Portfolio summary: total invested, estimated value, profit/loss, and sell alerts

## Requirements

- Python 3.10+
- pip

All Python dependencies are listed in `requirements.txt`.

## Getting Started

```bash
# Clone the repo
git clone https://github.com/lfoos/card-maven.git
cd card-maven

# Install dependencies
pip3 install -r requirements.txt

# Start the app
./run.sh
```

Then open [http://localhost:5050](http://localhost:5050) in your browser.

The SQLite database (`card_maven.db`) is created automatically on first run.

## Configuration

Copy or edit `config.json` to add your eBay Developer App ID:

```json
{
  "ebay_app_id": "YOUR_EBAY_APP_ID_HERE"
}
```

Without an App ID, eBay API price fetching is disabled. Price data from 130point.com still works without any credentials.

To get a free eBay App ID, register at the [eBay Developers Program](https://developer.ebay.com/).

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/dashboard` | Portfolio summary stats |
| GET | `/api/cards` | List all cards (supports `?q=`, `?sort=`, `?order=`) |
| POST | `/api/cards` | Add a new card |
| GET | `/api/cards/:id` | Get a single card |
| PUT | `/api/cards/:id` | Update a card |
| DELETE | `/api/cards/:id` | Delete a card |
| POST | `/api/cards/:id/photos` | Upload front/back photos |
| GET | `/api/cards/:id/prices` | Get price history for a card |
| POST | `/api/cards/:id/prices` | Add a manual price record |
| POST | `/api/cards/:id/refresh-prices` | Fetch latest comps from all sources |
| POST | `/api/cards/:id/generate-listing` | Generate a draft eBay listing |
| GET | `/api/listings` | List all listings (supports `?status=draft\|posted\|sold`) |
| GET | `/api/listings/:id` | Get a single listing |
| PUT | `/api/listings/:id` | Update a listing |
| DELETE | `/api/listings/:id` | Delete a listing |
| POST | `/api/refresh-all-prices` | Refresh prices for every card |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python / Flask |
| Database | SQLite via Flask-SQLAlchemy |
| Image processing | Pillow |
| Scraping | requests + BeautifulSoup4 |
| Frontend | Vanilla JS / HTML / CSS (single-page) |

## License

MIT
