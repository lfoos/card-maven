# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.3.0] - Phase 2: Market data

Collectors can now value their cards against the market.

### Added
- **Get comps.**
  - Each card's page has a Market panel showing its 5 most relevant recent sales (exact grade first, then the nearest grade), with links where available.
  - **Get comps** checks market sources and refreshes the panel.
  - Collectors who refresh the same card share one sync, and a sync that finished in the last 15 minutes is reused.
- **Estimated value** on every card: the median of up to 10 recent sales at the card's exact grade within 180 days, shown with what it's based on. Appears in the collection grid and table too.
- **Your own sales.** Record sales you know of, one at a time or by pasting or uploading CSV (up to 200 per import). They're private to you and count toward your comps and estimate.
- **Current eBay listings.** Asking prices with links (eBay Partner Network affiliate links when configured), clearly labelled as asks. They're never used for estimates.
- **Nightly sync.** Every tracked set is synced at 02:30 (America/Denver). An hourly maintenance job purges eBay listings older than 6 hours and abandoned photo uploads.
- **Market pipeline.**
  - `market-worker` consumes `market.sync.requested`, retries transient failures 3 times, and dead-letters to `market.sync.requested.dlq`.
  - Rule-based title matching uses eBay's trading-card vocabulary (`card-maven sync-ebay-taxonomy`).
  - Event payload schemas live in `contracts/events/`.
- **Analytics.** dbt project (`analytics/dbt`) with `mart_variant_value` and `mart_sales_daily`, unit tests, and a license-gate test. Runs nightly after the sync and in CI.
- **API.**
  - Comps: `GET /collection/items/{id}/comps`, `POST …/comps/refresh` (202), and `POST …/comps`.
  - Market: `DELETE /market/sales/{id}` and `GET /market/sync-jobs/{id}`.
  - `estimate` on every item.
- **CLI.** `market-worker`, `request-market-sync [--run-now]`, `purge-market-data`, `sweep-uploads`, `sync-ebay-taxonomy`, and `market-search`.
- **Infra.** market-worker Deployment and CronJobs (sync, maintenance, dbt) in the Helm chart, plus a `market-worker` compose service. CI adds Kafka integration tests, rendered-manifest validation, and a dbt job.
- **Docs.** [ADR-0009: market data licensing](docs/adr/0009-market-data-licensing.md) and the [comps user guide](docs/user-guide/market.md).

### Changed
- `ItemOut.estimated_value` is now populated, and the new `estimate` field explains it.
- `card_maven.reference_data` moved out of `catalog`. It now also seeds market sources.
- Invalid settings make the CLI print a one-line error instead of a traceback.

### Security
- eBay data is display-only (eBay API License Agreement §8.1, §9.5). This is enforced at ingestion, in queries, and in dbt.
- eBay keys are read from the environment, and only the market worker receives them in Kubernetes.
- Only http(s) links reach the browser.
- Manual sales are capped at 1,000 per collector per card.

## [0.2.0] - Phase 1: Identity and collection

Collectors can now sign in and manage a collection.

### Added
- **Collection.** Add, edit, view, and delete cards with sport, year, brand, set, card number, name, players, team, subset, parallel and print run, rookie/auto/memorabilia flags, raw or graded condition (PSA, BGS, SGC, CGC, TAG; half-point grades; cert number), serial number, price paid, acquisition date, and notes.
- **Browsing.** Grid and table views; free-text search (player, card, set, team, parallel, number); filters by sport, year, brand, and condition; five sort orders; cursor-based "Load more" paging. Filters live in the URL.
- **Photos.** Front and back photos (JPEG, PNG, WebP, HEIC, up to 15 MB), uploaded straight to object storage and verified server-side before they appear.
- **Shared catalog.** Cards resolve against a crowd-built catalog with case-insensitive matching and set and player autocomplete.
- **Accounts.** Collectors are created on first sign-in. `GET /api/v1/me`.
- **API.**
  - OpenAPI 3.1 contract generated from the code (`contracts/openapi.json`), served at `/api/v1/openapi.json`; the web app's TypeScript types are generated from it.
  - Field-level validation errors in problem+json.
  - Per-user rate limits.
- **Tooling.**
  - `make doctor` checks prerequisites; `make bootstrap` runs it first and now also creates the photo bucket (`card-maven init-storage`).
  - `make openapi`, plus storage tests against real SeaweedFS in CI.
- **Docs.** [API reference](docs/api/README.md) and [collection user guide](docs/user-guide/collection.md).

### Changed
- **Natural keys.** Set, card-number, and parallel matching is case-insensitive (migration `0002`, which also enables `pg_trgm`).
- **Local storage.** SeaweedFS is pinned to 4.51 and runs with small volumes, so photo uploads don't fail when a laptop is low on free disk.

### Security
- Owner-scoped repositories: another collector's cards and photos return 404 everywhere.
- Upload policy pins key, type, and exact size; server verifies signature and SHA-256.
- Deployed environments refuse local storage credentials.
- `X-Forwarded-For` trusted only for a configured number of proxies.

## [0.1.0] - Phase 0: Foundation

Replaces the legacy single-file app (preserved on the `legacy-v0` branch) with the new platform foundation. No user-facing features yet.

### Added
- **Monorepo.**
  - `apps/web` (React + TypeScript)
  - `services/api` (Flask)
  - `services/workers` (Kafka workers and the `card-maven` CLI)
  - `packages/card_maven` (shared domain)
  - `db/migrations` (Alembic)
- **Schema baseline:**
  - users (OIDC issuer and subject)
  - catalog: sports, brands, sets, players, cards, parallels, card variants
  - collection items with raw/graded condition, serial number, and purchase price
  - image metadata
  - tracked sets
  - transactional outbox
  - pgvector enabled
- **Tracked sets as configuration** (`config/tracked_sets.yaml`): 2024–2026 Bowman Chrome, Topps Chrome, Topps Series 1/2, Prizm/Select/Mosaic/Obsidian (basketball and football), and Upper Deck Series 1 Young Guns. Commands: `card-maven sync-tracked-sets` (with `--dry-run`) and `card-maven check-config`.
- **API:** health and readiness probes, RFC 9457 problem+json errors, request ids, security headers, a CORS allowlist, a 1 MB request limit, and a provider-agnostic OIDC JWT verifier.
- **Event pipeline:** a CloudEvents-style envelope with a JSON Schema contract, and an outbox relay to Kafka (safe to run as several replicas; poison messages are parked).
- **Web:** app shell, OIDC sign-in (code + PKCE, tokens in memory), a typed API client, and design tokens with dark mode.
- **Local stack** via Docker Compose: Postgres + pgvector, Kafka (KRaft), SeaweedFS (S3), Keycloak with a preconfigured realm.
- **Infrastructure:** hardened Dockerfiles, a Helm chart (API, outbox relay, migration and seed hooks), and Terraform modules for network, media bucket, and ECR, plus a `dev` environment.
- **CI:** lint, typecheck, tests with coverage gates, dependency audits, Helm lint, Terraform validate, and image builds. Dependabot is configured.
- **Docs:** architecture overview, auth design, ADRs 0001–0008, contributing guide, local development runbook.

### Removed
- The legacy SQLite app, along with its decommissioned eBay Finding API integration and the 130point scraper.
