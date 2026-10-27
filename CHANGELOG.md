# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
