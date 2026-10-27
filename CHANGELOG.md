# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
