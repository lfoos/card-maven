"""
Card Maven - Sports Card Collection Manager
Flask backend: card CRUD, photo storage, price tracking, eBay listing generation
"""

import os
import json
import re
import statistics
import time
import urllib.parse
from datetime import datetime, timedelta
from io import BytesIO

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from PIL import Image
from werkzeug.utils import secure_filename

# ── App setup ────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.config.update(
    SQLALCHEMY_DATABASE_URI=f"sqlite:///{os.path.join(BASE_DIR, 'card_maven.db')}",
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=32 * 1024 * 1024,  # 32 MB
)

db = SQLAlchemy(app)

# ── Load config (API keys, etc.) ─────────────────────────────────────────────
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH) as f:
        CONFIG = json.load(f)
else:
    CONFIG = {}

EBAY_APP_ID = CONFIG.get("ebay_app_id", "")


# ── Database Models ───────────────────────────────────────────────────────────
class Card(db.Model):
    __tablename__ = "cards"

    id              = db.Column(db.Integer, primary_key=True)
    player          = db.Column(db.String(200), nullable=False)
    year            = db.Column(db.String(10))
    card_set        = db.Column(db.String(200))
    variation       = db.Column(db.String(200))
    serial_number   = db.Column(db.String(50))
    grade           = db.Column(db.String(20))    # e.g. "10", "9.5"
    grader          = db.Column(db.String(20))    # PSA, BGS, SGC, Raw
    condition_raw   = db.Column(db.String(50))    # NM-MT, EX, Poor …
    purchase_price  = db.Column(db.Float)
    purchase_date   = db.Column(db.String(20))
    front_photo     = db.Column(db.String(500))
    back_photo      = db.Column(db.String(500))
    notes           = db.Column(db.Text)
    estimated_value = db.Column(db.Float)
    last_price_upd  = db.Column(db.DateTime)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    price_records = db.relationship(
        "PriceRecord", backref="card", lazy=True, cascade="all, delete-orphan"
    )
    listings = db.relationship(
        "EbayListing", backref="card", lazy=True, cascade="all, delete-orphan"
    )

    def to_dict(self):
        records = sorted(self.price_records, key=lambda r: r.fetched_at)
        recent = [r for r in records if r.fetched_at > datetime.utcnow() - timedelta(days=90)]
        prices = [r.price for r in recent if r.price]

        recommendation, rec_reason = self._recommend(prices)
        trend = self._trend(prices)

        return {
            "id":             self.id,
            "player":         self.player,
            "year":           self.year,
            "card_set":       self.card_set,
            "variation":      self.variation,
            "serial_number":  self.serial_number,
            "grade":          self.grade,
            "grader":         self.grader,
            "condition_raw":  self.condition_raw,
            "purchase_price": self.purchase_price,
            "purchase_date":  self.purchase_date,
            "front_photo":    self.front_photo,
            "back_photo":     self.back_photo,
            "notes":          self.notes,
            "estimated_value": self.estimated_value,
            "last_price_upd": self.last_price_upd.isoformat() if self.last_price_upd else None,
            "created_at":     self.created_at.isoformat(),
            "recent_avg":     round(statistics.mean(prices), 2) if prices else None,
            "recent_median":  round(statistics.median(prices), 2) if prices else None,
            "recommendation": recommendation,
            "rec_reason":     rec_reason,
            "trend":          trend,
            "price_count":    len(prices),
            "roi":            round((self.estimated_value - self.purchase_price) / self.purchase_price * 100, 1)
                              if self.estimated_value and self.purchase_price and self.purchase_price > 0 else None,
        }

    def _trend(self, prices):
        if len(prices) < 3:
            return "neutral"
        mid = len(prices) // 2
        first_half = statistics.mean(prices[:mid])
        second_half = statistics.mean(prices[mid:])
        pct = (second_half - first_half) / first_half * 100 if first_half else 0
        if pct > 10:
            return "up"
        if pct < -10:
            return "down"
        return "neutral"

    def _recommend(self, prices):
        if not prices or not self.purchase_price:
            return "hold", "Not enough data yet"
        current = self.estimated_value or (statistics.median(prices) if prices else None)
        if not current:
            return "hold", "Waiting for price data"
        roi = (current - self.purchase_price) / self.purchase_price * 100
        trend = self._trend(prices)
        if roi > 50 and trend in ("down", "neutral"):
            return "sell", f"Up {roi:.0f}% from purchase; momentum fading"
        if roi > 100:
            return "sell", f"Up {roi:.0f}% — strong profit to lock in"
        if roi < -20 and trend == "up":
            return "hold", f"Down {abs(roi):.0f}% but price recovering — hold"
        if roi < -30:
            return "sell", f"Down {abs(roi):.0f}% — consider cutting losses"
        if trend == "up" and roi < 20:
            return "hold", "Price trending up — wait for higher"
        return "hold", f"Holding at {roi:+.0f}% from purchase"


class PriceRecord(db.Model):
    __tablename__ = "price_records"

    id          = db.Column(db.Integer, primary_key=True)
    card_id     = db.Column(db.Integer, db.ForeignKey("cards.id"), nullable=False)
    source      = db.Column(db.String(50))   # ebay_sold, 130point, manual
    price       = db.Column(db.Float)
    sale_date   = db.Column(db.String(30))
    listing_url = db.Column(db.String(800))
    title       = db.Column(db.String(500))
    fetched_at  = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id":          self.id,
            "source":      self.source,
            "price":       self.price,
            "sale_date":   self.sale_date,
            "listing_url": self.listing_url,
            "title":       self.title,
            "fetched_at":  self.fetched_at.isoformat(),
        }


class EbayListing(db.Model):
    __tablename__ = "ebay_listings"

    id              = db.Column(db.Integer, primary_key=True)
    card_id         = db.Column(db.Integer, db.ForeignKey("cards.id"), nullable=False)
    title           = db.Column(db.String(80))
    description     = db.Column(db.Text)
    starting_price  = db.Column(db.Float)
    buy_now_price   = db.Column(db.Float)
    condition_code  = db.Column(db.String(50))
    status          = db.Column(db.String(20), default="draft")  # draft/posted/sold
    ebay_item_id    = db.Column(db.String(100))
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id":             self.id,
            "card_id":        self.card_id,
            "title":          self.title,
            "description":    self.description,
            "starting_price": self.starting_price,
            "buy_now_price":  self.buy_now_price,
            "condition_code": self.condition_code,
            "status":         self.status,
            "ebay_item_id":   self.ebay_item_id,
            "created_at":     self.created_at.isoformat(),
            "card":           {
                "player":    self.card.player,
                "year":      self.card.year,
                "card_set":  self.card.card_set,
                "grade":     self.card.grade,
                "grader":    self.card.grader,
                "front_photo": self.card.front_photo,
            },
        }


# ── Price Tracking ────────────────────────────────────────────────────────────
def build_search_query(card: Card) -> str:
    parts = [card.player]
    if card.year:     parts.append(card.year)
    if card.card_set: parts.append(card.card_set)
    if card.variation: parts.append(card.variation)
    if card.grader and card.grade:
        parts.append(f"{card.grader} {card.grade}")
    elif card.grade:
        parts.append(card.grade)
    return " ".join(parts)


def fetch_ebay_sold(card: Card) -> list[dict]:
    """
    Fetch recently sold eBay listings via the Finding API (findCompletedItems).
    Requires EBAY_APP_ID set in config.json.
    """
    if not EBAY_APP_ID:
        return []

    query = build_search_query(card)
    url = "https://svcs.ebay.com/services/search/FindingService/v1"
    params = {
        "OPERATION-NAME":        "findCompletedItems",
        "SERVICE-VERSION":       "1.0.0",
        "SECURITY-APPNAME":      EBAY_APP_ID,
        "RESPONSE-DATA-FORMAT":  "JSON",
        "REST-PAYLOAD":          "",
        "keywords":              query,
        "itemFilter(0).name":    "SoldItemsOnly",
        "itemFilter(0).value":   "true",
        "sortOrder":             "EndTimeSoonest",
        "paginationInput.entriesPerPage": "20",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        items = (
            data.get("findCompletedItemsResponse", [{}])[0]
               .get("searchResult", [{}])[0]
               .get("item", [])
        )
        results = []
        for item in items:
            price_info = item.get("sellingStatus", [{}])[0].get("currentPrice", [{}])[0]
            price = float(price_info.get("__value__", 0))
            end_time = item.get("listingInfo", [{}])[0].get("endTime", [""])[0]
            view_url = item.get("viewItemURL", [""])[0]
            title = item.get("title", [""])[0]
            if price > 0:
                results.append({"price": price, "sale_date": end_time, "url": view_url, "title": title})
        return results
    except Exception as e:
        print(f"eBay API error: {e}")
        return []


def fetch_130point(card: Card) -> list[dict]:
    """
    Scrape 130point.com for recent card sales data.
    """
    query = build_search_query(card)
    search_url = f"https://www.130point.com/sales/?q={urllib.parse.quote(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        resp = requests.get(search_url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        # 130point sale rows typically have class 'sale-row' or similar
        rows = soup.select(".sale-row, .result-row, tr[data-price]")
        if not rows:
            # Try generic table rows
            rows = soup.select("table tbody tr")
        for row in rows[:20]:
            price_el = row.select_one(".price, .sale-price, td.price")
            date_el  = row.select_one(".date, .sale-date, td.date")
            title_el = row.select_one(".title, .card-title, td.title, td:first-child")
            if price_el:
                price_text = re.sub(r"[^\d.]", "", price_el.get_text())
                try:
                    price = float(price_text)
                    results.append({
                        "price":     price,
                        "sale_date": date_el.get_text(strip=True) if date_el else "",
                        "url":       search_url,
                        "title":     title_el.get_text(strip=True) if title_el else query,
                    })
                except ValueError:
                    pass
        return results
    except Exception as e:
        print(f"130point scrape error: {e}")
        return []


def refresh_card_prices(card: Card) -> int:
    """Fetch prices from all sources and store new records. Returns count added."""
    added = 0
    existing_urls = {r.listing_url for r in card.price_records if r.listing_url}

    for source_name, fetcher in [("ebay_sold", fetch_ebay_sold), ("130point", fetch_130point)]:
        records = fetcher(card)
        for rec in records:
            url = rec.get("url", "")
            if url and url in existing_urls:
                continue
            pr = PriceRecord(
                card_id     = card.id,
                source      = source_name,
                price       = rec["price"],
                sale_date   = rec.get("sale_date", ""),
                listing_url = url,
                title       = rec.get("title", ""),
            )
            db.session.add(pr)
            if url:
                existing_urls.add(url)
            added += 1

    if added > 0:
        recent = [r.price for r in card.price_records if r.price]
        if recent:
            card.estimated_value = round(statistics.median(recent[-20:]), 2)
        card.last_price_upd = datetime.utcnow()

    db.session.commit()
    return added


# ── Listing Generation ────────────────────────────────────────────────────────
EBAY_CONDITION_CODES = {
    "PSA": {"10": "3000", "9": "3000", "8": "4000", "7": "5000"},
    "BGS": {"10": "3000", "9.5": "3000", "9": "4000"},
    "SGC": {"10": "3000", "9.5": "3000", "9": "4000"},
    "Raw": {"NM-MT": "3000", "NM": "4000", "EX-MT": "5000", "EX": "5000", "VG": "6000", "Poor": "7000"},
}


def generate_listing(card: Card) -> dict:
    """Auto-generate a professional eBay listing draft."""
    # Build title (eBay max 80 chars)
    parts = []
    if card.year:     parts.append(card.year)
    parts.append(card.player)
    if card.card_set: parts.append(card.card_set)
    if card.variation: parts.append(card.variation)
    if card.grader and card.grade:
        parts.append(f"{card.grader} {card.grade}")
    if card.serial_number:
        parts.append(f"#{card.serial_number}")
    title = " ".join(parts)
    if len(title) > 80:
        title = title[:77] + "..."

    # Condition line
    if card.grader and card.grade and card.grader != "Raw":
        condition_line = f"Professionally graded by **{card.grader}** — Grade **{card.grade}**."
        condition_code = EBAY_CONDITION_CODES.get(card.grader, {}).get(card.grade, "4000")
    else:
        raw_cond = card.condition_raw or "See photos"
        condition_line = f"Raw card in **{raw_cond}** condition."
        condition_code = EBAY_CONDITION_CODES.get("Raw", {}).get(raw_cond, "4000")

    # Suggest price from recent comps
    prices = [r.price for r in card.price_records if r.price]
    if prices:
        comp_median = statistics.median(prices[-20:])
        buy_now = round(comp_median * 0.95, 2)   # slight undercut
        start   = round(buy_now * 0.85, 2)
    elif card.estimated_value:
        buy_now = round(card.estimated_value * 0.95, 2)
        start   = round(buy_now * 0.85, 2)
    else:
        buy_now = None
        start   = None

    description = f"""<h2>{card.year or ""} {card.player} {card.card_set or ""}</h2>

<p>{condition_line}</p>

<ul>
  <li><strong>Player:</strong> {card.player}</li>
  <li><strong>Year:</strong> {card.year or "N/A"}</li>
  <li><strong>Set:</strong> {card.card_set or "N/A"}</li>
  {"<li><strong>Variation:</strong> " + card.variation + "</li>" if card.variation else ""}
  {"<li><strong>Serial #:</strong> " + card.serial_number + "</li>" if card.serial_number else ""}
  {"<li><strong>Grade:</strong> " + card.grader + " " + card.grade + "</li>" if card.grade else ""}
</ul>

<p>Please see all photos for condition details. Card ships in a rigid top-loader and soft sleeve inside a bubble mailer with tracking.</p>

<p>Questions welcome! Happy to provide additional photos.</p>"""

    return {
        "title":          title,
        "description":    description,
        "starting_price": start,
        "buy_now_price":  buy_now,
        "condition_code": condition_code,
    }


# ── Photo helpers ─────────────────────────────────────────────────────────────
ALLOWED = {"png", "jpg", "jpeg", "gif", "webp", "heic"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED

def save_photo(file, card_id, side):
    """Save uploaded photo, create thumbnail, return relative URL path."""
    ext = file.filename.rsplit(".", 1)[-1].lower()
    filename = secure_filename(f"card_{card_id}_{side}_{int(time.time())}.{ext}")
    path = os.path.join(UPLOAD_DIR, filename)
    file.save(path)
    # Resize to max 1200px for display
    try:
        img = Image.open(path)
        img.thumbnail((1200, 1200), Image.LANCZOS)
        img.save(path, quality=90, optimize=True)
    except Exception:
        pass
    return f"/static/uploads/{filename}"


# ── API Routes ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/static/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


# ─ Dashboard ─
@app.route("/api/dashboard")
def dashboard():
    cards = Card.query.all()
    total_invested = sum(c.purchase_price or 0 for c in cards)
    total_value    = sum(c.estimated_value or c.purchase_price or 0 for c in cards)
    sell_alerts    = [c for c in cards if c.to_dict()["recommendation"] == "sell"]
    recent = sorted(cards, key=lambda c: c.created_at, reverse=True)[:5]

    return jsonify({
        "total_cards":    len(cards),
        "total_invested": round(total_invested, 2),
        "total_value":    round(total_value, 2),
        "total_profit":   round(total_value - total_invested, 2),
        "sell_alerts":    len(sell_alerts),
        "recent_cards":   [c.to_dict() for c in recent],
        "sell_alert_cards": [c.to_dict() for c in sell_alerts[:5]],
    })


# ─ Cards CRUD ─
@app.route("/api/cards", methods=["GET"])
def list_cards():
    q      = request.args.get("q", "").lower()
    sort   = request.args.get("sort", "created_at")
    order  = request.args.get("order", "desc")

    query = Card.query
    if q:
        query = query.filter(
            db.or_(
                Card.player.ilike(f"%{q}%"),
                Card.card_set.ilike(f"%{q}%"),
                Card.year.ilike(f"%{q}%"),
            )
        )
    sort_col = getattr(Card, sort, Card.created_at)
    if order == "desc":
        query = query.order_by(sort_col.desc())
    else:
        query = query.order_by(sort_col.asc())

    cards = query.all()
    return jsonify([c.to_dict() for c in cards])


@app.route("/api/cards", methods=["POST"])
def create_card():
    data = request.get_json()
    card = Card(
        player         = data.get("player", "Unknown"),
        year           = data.get("year"),
        card_set       = data.get("card_set"),
        variation      = data.get("variation"),
        serial_number  = data.get("serial_number"),
        grade          = data.get("grade"),
        grader         = data.get("grader"),
        condition_raw  = data.get("condition_raw"),
        purchase_price = data.get("purchase_price"),
        purchase_date  = data.get("purchase_date"),
        notes          = data.get("notes"),
    )
    db.session.add(card)
    db.session.commit()
    return jsonify(card.to_dict()), 201


@app.route("/api/cards/<int:card_id>", methods=["GET"])
def get_card(card_id):
    card = Card.query.get_or_404(card_id)
    return jsonify(card.to_dict())


@app.route("/api/cards/<int:card_id>", methods=["PUT"])
def update_card(card_id):
    card = Card.query.get_or_404(card_id)
    data = request.get_json()
    for field in ["player", "year", "card_set", "variation", "serial_number",
                  "grade", "grader", "condition_raw", "purchase_price",
                  "purchase_date", "notes", "estimated_value"]:
        if field in data:
            setattr(card, field, data[field])
    db.session.commit()
    return jsonify(card.to_dict())


@app.route("/api/cards/<int:card_id>", methods=["DELETE"])
def delete_card(card_id):
    card = Card.query.get_or_404(card_id)
    db.session.delete(card)
    db.session.commit()
    return jsonify({"deleted": True})


# ─ Photo upload ─
@app.route("/api/cards/<int:card_id>/photos", methods=["POST"])
def upload_photos(card_id):
    card = Card.query.get_or_404(card_id)
    updated = {}

    for side in ("front", "back"):
        file = request.files.get(side)
        if file and allowed_file(file.filename):
            url = save_photo(file, card_id, side)
            if side == "front":
                card.front_photo = url
            else:
                card.back_photo = url
            updated[side] = url

    db.session.commit()
    return jsonify({"updated": updated, "front_photo": card.front_photo, "back_photo": card.back_photo})


# ─ Price history ─
@app.route("/api/cards/<int:card_id>/prices", methods=["GET"])
def get_prices(card_id):
    card = Card.query.get_or_404(card_id)
    records = sorted(card.price_records, key=lambda r: r.fetched_at, reverse=True)
    return jsonify([r.to_dict() for r in records])


@app.route("/api/cards/<int:card_id>/prices", methods=["POST"])
def add_manual_price(card_id):
    card = Card.query.get_or_404(card_id)
    data = request.get_json()
    pr = PriceRecord(
        card_id   = card_id,
        source    = "manual",
        price     = float(data["price"]),
        sale_date = data.get("sale_date", datetime.utcnow().strftime("%Y-%m-%d")),
        title     = data.get("title", "Manual entry"),
    )
    db.session.add(pr)
    recent = [r.price for r in card.price_records if r.price] + [pr.price]
    card.estimated_value = round(statistics.median(recent[-20:]), 2)
    card.last_price_upd = datetime.utcnow()
    db.session.commit()
    return jsonify(pr.to_dict()), 201


@app.route("/api/cards/<int:card_id>/refresh-prices", methods=["POST"])
def refresh_prices(card_id):
    card = Card.query.get_or_404(card_id)
    added = refresh_card_prices(card)
    return jsonify({"added": added, "estimated_value": card.estimated_value})


# ─ Listings ─
@app.route("/api/cards/<int:card_id>/generate-listing", methods=["POST"])
def generate_listing_route(card_id):
    card = Card.query.get_or_404(card_id)
    draft = generate_listing(card)
    listing = EbayListing(
        card_id        = card_id,
        title          = draft["title"],
        description    = draft["description"],
        starting_price = draft["starting_price"],
        buy_now_price  = draft["buy_now_price"],
        condition_code = draft["condition_code"],
        status         = "draft",
    )
    db.session.add(listing)
    db.session.commit()
    return jsonify(listing.to_dict()), 201


@app.route("/api/listings", methods=["GET"])
def list_listings():
    status = request.args.get("status", "")
    query = EbayListing.query
    if status:
        query = query.filter_by(status=status)
    listings = query.order_by(EbayListing.created_at.desc()).all()
    return jsonify([l.to_dict() for l in listings])


@app.route("/api/listings/<int:listing_id>", methods=["GET"])
def get_listing(listing_id):
    listing = EbayListing.query.get_or_404(listing_id)
    return jsonify(listing.to_dict())


@app.route("/api/listings/<int:listing_id>", methods=["PUT"])
def update_listing(listing_id):
    listing = EbayListing.query.get_or_404(listing_id)
    data = request.get_json()
    for field in ["title", "description", "starting_price", "buy_now_price",
                  "condition_code", "status", "ebay_item_id"]:
        if field in data:
            setattr(listing, field, data[field])
    db.session.commit()
    return jsonify(listing.to_dict())


@app.route("/api/listings/<int:listing_id>", methods=["DELETE"])
def delete_listing(listing_id):
    listing = EbayListing.query.get_or_404(listing_id)
    db.session.delete(listing)
    db.session.commit()
    return jsonify({"deleted": True})


# ─ Refresh all prices ─
@app.route("/api/refresh-all-prices", methods=["POST"])
def refresh_all():
    cards = Card.query.all()
    total = 0
    for card in cards:
        total += refresh_card_prices(card)
    return jsonify({"total_added": total, "cards_updated": len(cards)})


# ── Init DB ───────────────────────────────────────────────────────────────────
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    print("🃏  Card Maven running at http://localhost:5050")
    app.run(debug=True, host="0.0.0.0", port=5050)
