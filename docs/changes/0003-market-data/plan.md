# 0003: Market data pipeline (Phase 2): Planner

**Phase:** 2 · **Features enabled:** Feature 3 (Get Comps), Feature 6 (nightly sync), and estimated values on collection items.

**Diagram impact:** yes.
- The market ingestion worker, nightly CronJob, and dbt become real.
- New: a maintenance CronJob (purge stale listings, sweep abandoned uploads), the per-source **license gate**, and a `market_sync_job` resource.
- `docs/architecture/README.md` is updated.

## Licensing decision (input to every design choice below)

eBay's API License Agreement forbids using eBay content to "suggest or model prices" (§9.5) or to derive statistics like average selling prices (§8.1(d)(1)) without eBay's written permission. Displayed listing data must be at most 6 hours stale and deleted once no longer public (§8.1(b–c)). Decision (with the user): **eBay data is display-only.** Recorded in [ADR-0009](../../adr/0009-market-data-licensing.md).

So every market source carries a `license`:

| License | May appear as | May feed comps, estimates, dbt marts, trends | Retention |
|---|---|---|---|
| `analytics` | Sales (comps) | **Yes** | Kept |
| `display_only` | Current asks only | **No** | Rows not re-observed within `max_age_hours` are deleted |

Enforced in three places: ingestion rejects sales from `display_only` sources; comps and valuation queries filter on license; a dbt test fails if any non-`analytics` row reaches a mart.

## Sources (Phase 2)

| Code | License | What it provides | How it arrives |
|---|---|---|---|
| `fixture` | analytics | Deterministic sample sales for tracked sets (dev and tests only; refused in prod) | `FixtureSource`, pulled by the sync worker |
| `manual` | analytics | Sales a collector enters or imports from CSV. **Private to that collector.** | API: `POST /collection/items/{id}/comps` |
| `ebay_browse` | display_only (6 h) | Current eBay asks with affiliate links | `EbayBrowseSource`, pulled by the sync worker |

The eBay Taxonomy API is used separately: `card-maven sync-ebay-taxonomy` loads the trading-card item specifics (parallels, graders, grades, manufacturers) into a `catalog_term` vocabulary that the title parser uses. This is category metadata, not listing content.

Sandbox keys are used now (`CARD_MAVEN_EBAY_ENVIRONMENT=sandbox`). Production keys and the EPN campaign id plug in through environment variables later. Sandbox returns mock data, so the adapter is tested against **recorded response fixtures**.

## Data model (migration 0003)

- **`market_source`:** code (pk), name, `license`, `max_age_hours`, `enabled`. Seeded from `config/reference_data.yaml` (`market_sources:`), like sports and brands.
- **`sale`:** id; `source_code`; `source_listing_id` (unique with the source); `variant_id` (nullable) with `match_confidence` and `match_method`; raw title; price (minor units + currency); `sold_at`; `sale_type`; condition, grader, and grade; url; `submitted_by` (nullable; set for private manual comps); `payload` (JSONB, the source's raw fields).
- **`listing`:** same identity and match fields. Price, `buying_option`, `bid_count`, condition, grader, grade, url (affiliate when available), image url, `observed_at`, `ends_at`. Only *matched* listings are stored (data minimization).
- **`market_sync_job`:** id, target (`variant` or `tracked_set` plus its id), status (`queued` → `running` → `succeeded`/`failed`), `requested_by`, counts, error, timestamps. Exposed to the web app so it can poll "Get comps".
- **`processed_event`:** (consumer, event_id) primary key. Makes Kafka consumers idempotent under at-least-once delivery.
- **`catalog_term`:** (source, aspect, value) vocabulary from eBay Taxonomy.

Indexes: `sale (variant_id, sold_at DESC)`, `listing (variant_id, observed_at DESC)`, `listing (observed_at)` for purging.

## Title parsing and matching (`market/parsing.py`, `market/matching.py`)

**Parser:** title → `ParsedTitle`.
- year
- grader and grade (`PSA 10`, `PSA GEM MT 10`, `BGS 9.5`, `SGC 9`, `CGC 9.5`, `TAG 10`)
- serial and print run (`12/50`, `/50`, `#'d /99`)
- card number tokens
- flags: auto, RC
- parallel phrases from the vocabulary
- **disqualifiers:** lot, "you pick", break, reprint, custom, digital

**Matcher:** scores a parsed title against a target variant, from 0 to 1:
- **Required:** the year, plus the card number *or* every player's surname.
- **Parallel:** for a base variant, no known non-base parallel phrase may appear. Otherwise the parallel name must appear, and a print run, if present, must match.
- **Grade:** the condition and grade are taken from the title, so comps can be grouped by grade.
- **Threshold:** at least 0.75 to store. Anything else is dropped (listings) or stored unmatched (`analytics` sales, for re-matching as the catalog grows).

The plan's "vector similarity fallback" is **deferred to Phase 3**, when the embedding model arrives. The rule-based matcher covers what Phase 2 needs, and its decisions are explainable.

## Pipeline

```
API (Get comps)   ─┐                          ┌─> market-worker ─> sources ─> parse/match ─> upsert sale/listing
CronJob (nightly) ─┴─> outbox ─> market.sync.requested ┘        └─> market.sales.ingested (event)
CronJob (maintenance): purge stale display-only listings · sweep abandoned uploads
CronJob (analytics):   dbt build
```

- **Event:** `market.sync.requested.v1`. Data: `job_id`, `target`, optional `sources`. Subject: the target, so syncs for the same card stay ordered.
- **Worker** (`card-maven market-worker`):
  - Consumes, skips already-processed `event.id`s, and marks the job running.
  - Runs each enabled source, then upserts. Sales upsert `ON CONFLICT DO UPDATE` and listings refresh `observed_at`.
  - Marks the job succeeded or failed, and emits `market.sales.ingested.v1`. The event and the processed-marker are written in the same transaction.
  - Offsets are committed after the transaction.
- **Failures:**
  - Transient (`DependencyUnavailableError`, timeouts): up to 3 attempts with backoff, then `market.sync.requested.dlq`.
  - Invalid payloads: straight to the DLQ.
  - One failing source doesn't fail the others; the job records per-source counts and errors.
- **Nightly:** `card-maven request-market-sync` enqueues one job per active tracked set. Helm CronJob at 02:30 America/Denver. `--run-now` also runs the jobs inline, without Kafka (local dev and CI).
- **Get Comps:** `POST /collection/items/{id}/comps/refresh` returns `202` with a job.
  - Reuses a queued or running job for the same variant.
  - Returns the last job if it succeeded within 15 minutes. This protects eBay rate limits and our quota.
  - Rate-limited to 10/min per user.

## Comps and valuation (`market/comps.py`, `market/collector.py`)

- **Comps for an item:** the 5 most relevant eligible sales of its variant. Eligible means an `analytics` source, and either shared or submitted by the viewer.
  - **Order:** exact condition and grade first (same grader and grade; raw for raw), then nearest grade (absolute difference), then newest. Each comp is flagged `exact` or `nearest`.
- **Current asks:** up to 5 fresh `display_only` listings, labelled as asks, with their "as of" time.
- **Estimated value:** the median of up to the 10 most recent exact-grade eligible sales in the last 180 days. It's returned with its basis (count, grade, window) so the UI can explain it; `null` if there are none.
  - Batch-computed for a whole page of items in one query (window functions), so there's no N+1.
- **Manual comps:** `POST /collection/items/{id}/comps` takes 1–200 sales (date, price, condition, grader, grade, title, url). They're private to the submitter, capped at 1,000 per collector per card. `DELETE /market/sales/{id}` removes your own.
- **Facade:** `CollectorMarket(session, viewer)` is the API's single entry point: overview, refresh, job lookup, and manual sales, with ownership and the license gate applied inside.
- **Shared jobs:** sync jobs are shared, so two collectors refreshing one card reuse a job. A variant job is visible to anyone who holds that variant, and it never exposes who requested it.
  - The web app parses CSV in the browser and posts rows, keeping the 1 MB JSON limit.

## dbt (`analytics/dbt`)

- **Sources:** `sale`, `listing`, `market_source`, `card_variant`, `card`, `card_set`, `parallel`.
- **Models:**
  - `stg_sales`: analytics-licensed, matched, shared sales only.
  - `int_sales_graded`: adds the condition bucket.
  - `mart_variant_value`: median, count, and latest sale per variant and condition bucket over 90 days.
  - `mart_sales_daily`: sport, set, and day; volume and median. This is groundwork for Phase 5.
- **Tests:** `not_null`/`unique`/`accepted_values`, **dbt unit tests** for the median and bucketing logic, and a singular test that no non-`analytics` source reaches a mart.
- **CI** migrates a fresh database, loads the sample sales (`request-market-sync --run-now`), runs `dbt build`, and checks the marts aren't empty. A Helm CronJob runs `dbt build` at 04:30, after the 02:30 sync.
- **Version:** dbt-core 1.12 + dbt-postgres 1.11, with its own lockfile. dbt v2 (2026) has no Postgres adapter, and v1 remains fully supported.
- **Note:** per-collector estimates are computed online, not in dbt, because they include the viewer's private manual comps. The dbt marts are the *shared-market* view used by Phase 5 trends.

## API additions

| Method | Path | Purpose |
|---|---|---|
| GET | `/collection/items/{id}/comps` | Comps, current asks, estimate, and the latest sync job |
| POST | `/collection/items/{id}/comps/refresh` | Start (or reuse) a sync job. Returns 202 |
| POST | `/collection/items/{id}/comps` | Add manual sales (1–200) |
| DELETE | `/market/sales/{sale_id}` | Delete one of your manual sales |
| GET | `/market/sync-jobs/{job_id}` | Poll a sync job (owner only) |

`ItemOut.estimated_value` is populated, and a new `estimate` object carries the basis.

## Web

The detail page gets a **Market** panel:
- the estimate and its basis
- **Get comps**, which starts a refresh and polls until it finishes
- a comps table (date, price, grade, source, link) with exact/nearest markers
- **Current listings** (eBay asks), clearly labelled as asking prices, showing their age, with affiliate links
- **Add sales**: a single sale form, or CSV paste or file

The collection table shows estimated values.

## Maintenance

- **`card-maven purge-market-data`:** deletes `display_only` listings not re-observed within the source's `max_age_hours`, sync jobs older than 30 days (including abandoned ones), and `processed_event` markers older than 30 days. Runs hourly.
- **`card-maven sweep-uploads`:** deletes `pending` images older than 24 h, along with their objects. This was promised in 0002.

## Test plan

- **Parser:** a table of real-world-style titles (graded slabs, serials, autos, lots, reprints).
- **Matcher:**
  - base vs. parallel confusion
  - wrong year or number
  - multi-player cards
  - the threshold boundary
- **Sources:**
  - the fixture source is deterministic
  - eBay OAuth: token caching and expiry, the 401 refresh, 429 and 5xx retries mapped to `DependencyUnavailableError`
  - Browse mapping from a recorded response, including the affiliate header and a missing `itemAffiliateWebUrl`
  - Taxonomy load is idempotent
- **Ingestion:**
  - idempotent upserts and duplicate events
  - display-only sales rejected
  - partial source failure
  - retry, then DLQ
  - job state transitions
- **Comps and valuation:**
  - exact/nearest ordering
  - private manual comps visible only to their owner
  - display-only listings never in comps or estimates
  - stale listings hidden and purged
  - median correctness for odd and even counts
  - batch estimates match single estimates
- **API:** every new endpoint (auth, isolation, validation, 202 dedupe, rate limit). OpenAPI contract and TypeScript types regenerated.
- **Kafka:** consumer loop against a fake (unit tests) plus a **real Kafka broker in CI** (produce → consume → DLQ round trip).
- **dbt:** `dbt build` with unit tests in CI.
- **Web:** Market panel states (empty, loading, polling, done, failed), CSV parsing, and the manual sale form.
