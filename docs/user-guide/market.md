# Comps and estimated values

Every card's page has a **Market** panel showing what the card has sold for recently, what it's listed for now, and what it's probably worth.

## Get comps

Click **Get comps** to check market sources for this card. It usually takes a few seconds; the panel updates when it's done.
- If you (or another collector) checked this card in the last 15 minutes, you get those results straight away.
- Every card in a tracked set is also checked nightly.

## Recent sales

Up to five recent sales of this exact card: same set, number, and parallel.
- **Order:** sales at **your card's grade** come first. A PSA 10 is compared with PSA 10 sales, and a raw card with raw sales.
- **Nearest:** when there aren't enough of those, the closest grades fill in, marked **nearest**.
- **Source:** the Source column links to the sale where we have a link.

## Estimated value

The estimate is the **median** price of up to the 10 most recent sales at your card's exact grade in the last 180 days. Under the number you'll see how many sales it's based on and the date of the latest one.
- **No estimate ("—"):** there are no recent sales at that grade.
- **Your own sales count:** sales you add (below) are included.
- **Listings don't:** asking prices never affect the estimate.

## Current listings

Cards currently for sale on eBay, cheapest first, with how long ago each price was seen.
- **Asks, not sales.** These are asking prices, not what anyone paid. That's why they're never used for comps or the estimate.
- **Freshness.** Listings older than 6 hours disappear until the next sync.
- **Affiliate links.** Links may be affiliate links, which can earn Card Maven a commission at no cost to you.

## Adding sales you know of

Seen a sale somewhere else: a card show, a Facebook group, eBay's sold listings, or Terapeak? Open **Add sales you know of**:
- **One sale:** enter the date, price, grader and grade (or leave it raw), plus an optional note and link.
- **Many sales:** paste CSV, or choose a `.csv` file. The first row names the columns:

  ```csv
  date,price,grader,grade,title,url
  2026-10-01,95.00,PSA,10,eBay auction,https://www.ebay.com/itm/123
  10/03/2026,$41,PSA,9,Card show,
  2026-09-28,14.00,,,Raw copy,
  ```

  - **Required columns:** `date` (YYYY-MM-DD or MM/DD/YYYY) and `price`.
  - **Optional columns:** `currency` (default USD), `grader` and `grade` (both, or neither for raw), `title`, `url`, and `type` (`auction`, `fixed_price`, `best_offer`, or `other`).
  - **Problems are listed by line,** and nothing is saved until they're fixed.
  - **Limits:** up to 200 rows per import and 1,000 sales per card.

**Only you see the sales you add.** They count toward your comps and estimate, never anyone else's. Delete one with **Delete** in the Recent sales table.
