# 0003: Market data pipeline: QA report

**Result: pass, with two items verified only in CI (below).**
- **Python:** 597 tests, 99% line and branch coverage (gate 90%).
- **Web:** 141 tests, 98% lines and 93% branches (gate 80%).
- **dbt:** 26 nodes, covering models, data tests, 2 unit tests, and 2 singular tests.

## How it was tested

| Layer | Approach |
|---|---|
| **Parsing and matching** | Table-driven titles: graded slabs (PSA/BGS/SGC/CGC/TAG, "GEM MT 10"), serials (`12/50`, `/50`, `#'d /99`), autos, RCs, lots, breaks, "you pick", reprints, and multiples. Base-vs-parallel confusion, wrong year or number, multi-player cards, and the 0.75 threshold boundary. |
| **Sources** | The fixture source is deterministic. eBay OAuth token caching, early refresh, and retry on 401. 429/5xx map to `DependencyUnavailableError`, other 4xx to `MarketSourceError`. Browse mapping covers auctions, the affiliate header, and a missing `itemAffiliateWebUrl`. Taxonomy aspect loading, all over `respx` (HTTP mocked at the transport). |
| **Ingestion** | Real Postgres. Plan/fetch/store transitions, idempotent upserts (a worse re-ingest never un-matches a sale), display-only sales rejected, only matched listings kept, a partial source failure, a crashing adapter contained, every source failing, and disabled or unregistered sources ignored. Variant-sync dedupe and the 10-minute staleness rule are also covered. |
| **Worker** | `ConsumerLoop` against a fake consumer: commit after handling, retry with capped backoff, DLQ after 3 attempts, poison messages and permanent errors to the DLQ without retry, and no commit when the DLQ publish itself fails. `MarketSyncHandler` against real Postgres covers redelivery (processed once), transient retry until the last attempt then a recorded failure, and invalid payloads. |
| **Comps and valuation** | Exact-then-nearest ordering, private manual comps visible only to their owner, and display-only data never in comps or estimates. Stale and ended asks are hidden and purged. Odd and even medians. Batch estimates match single estimates. |
| **API** | Every new endpoint: happy path, 401, 404 for another collector, and 422 with field locations. Refresh returns 202, two collectors share one job, holders can poll a job and others get 404, and the job body doesn't reveal the requester. A `javascript:` URL is never returned. The 10/min refresh limit returns 429. |
| **Contracts** | OpenAPI regenerated and drift-tested, with TypeScript types regenerated (`check:api`). Event payload JSON Schemas are validated against real producer output, for both success and failure. |
| **Web** | Market panel: estimate and its basis, comps with the nearest marker, asks with `rel="sponsored"` and an affiliate disclosure, and empty, loading, and failed states. Get comps starts, polls until done, then reloads; polling while running and a failed sync are covered, as is 429. The single-sale form, CSV paste and file (including oversized), and parse and server errors are covered. Deleting your own sale works, and its failure is reported. |
| **dbt** | Unit tests check median, window edges, and bucket formatting. Singular tests: no non-analytics sale reaches a mart, and mart counts match eligible sales. Run end to end locally against a freshly migrated database with sample data. |

## Defects found and sent back

| # | Found in | Defect | Fix |
|---|---|---|---|
| QA-1 | Manual comps | A sale dated today was stamped 12:00 UTC. Before noon UTC it counted as "in the future", so it was skipped by estimates until midday. | `sold_at` is clamped to now. Regression test added. |
| QA-2 | CLI | The CLI never imported the identity models, so the first write to `market_sync_job` (FK to `app_user`) failed outside tests. The suite imports everything, which hid it. | Entry points import the full model registry. A fresh-interpreter test checks both the API and the CLI. |
| QA-3 | CLI | Invalid settings printed a Pydantic traceback. | A one-line `invalid settings: …` message. |
| QA-4 | Ingestion | An unexpected exception in one adapter aborted the whole job, losing the other sources' results. | Contained per source, logged, and shown to collectors as a generic message. |

## Not verified here (CI only)

- **Real Kafka round trip** (`test_kafka_integration.py`): there's no broker in this workspace. CI starts `apache/kafka:3.9.0`.
- **Helm rendering**: `helm` couldn't be installed here. CI lints, renders, checks resource counts, and validates the manifests with kubeconform.
- **Live eBay**: the adapter is tested against fixtures built to eBay's documented response schema, not responses recorded from the API. Sandbox keys stay with the founder. `card-maven market-search … --source ebay_browse` is the smoke test to run with them (runbook).
