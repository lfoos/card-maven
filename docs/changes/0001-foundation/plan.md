# 0001: Foundation (Phase 0): Planner

**Phase:** 0 · **Features enabled:** none user-facing (enables all later phases)
**Diagram impact:** none. This change implements the container view in `docs/architecture/README.md` as-is.

## Scope

| Area | Deliverable |
|---|---|
| Repo | Legacy code preserved on branch `legacy-v0` and removed from this branch. Monorepo layout per plan §4. uv workspace (Python) and pnpm (web). `Makefile` as the single entry point. pre-commit hooks. |
| Local stack | `infra/compose/docker-compose.yml`: Postgres 16 + pgvector, Kafka 3.9 (KRaft, single node), MinIO + bucket bootstrap, Keycloak with an imported `card-maven` realm. |
| Shared domain | `packages/card_maven`: settings, structured logging, error taxonomy, DB session and declarative base, money value object, event envelope, transactional outbox. |
| Schema | `identity.user`; catalog (`sport`, `brand`, `card_set`, `player`, `card`, `card_player`, `parallel`, `card_variant`); collection (`collection_item`, `image`); market config (`tracked_set`); `outbox_message`. One Alembic baseline migration, which also enables `vector`. |
| Config | `config/tracked_sets.yaml`, Pydantic-validated, plus a sync command (upsert, deactivate removed entries). Reference seed for sports and brands. |
| API | Flask app factory, `/healthz` and `/readyz`, RFC 9457 problem+json errors, request-id propagation, security headers, provider-agnostic OIDC JWT verifier (not yet mounted on routes). |
| Workers | Outbox relay (`SELECT … FOR UPDATE SKIP LOCKED`), Kafka publisher adapter, admin CLI (`sync-tracked-sets`, `seed`). |
| Web | Vite + React + TypeScript shell: routing, OIDC (`oidc-client-ts`) auth provider, typed API client, design tokens, placeholder pages. |
| Infra | Dockerfiles. Helm chart (api, outbox relay, migration job). Terraform modules `network`, `media_bucket`, `ecr` plus a `dev` env. |
| CI | GitHub Actions: Python lint, typecheck, and tests against a pgvector service; web lint, typecheck, tests, and build; Helm lint; Terraform fmt and validate. |
| Docs | README, architecture, ADRs 0001–0008, CONTRIBUTING, CHANGELOG, local-dev runbook. |

**Deferred by design** (keeps Phase 0 small and avoids speculative schema):
- `sale` and `listing` move to Phase 2.
- `scan`, `identification`, and `image_embedding` move to Phase 3.
- `grade_estimate` moves to Phase 4.
- The EKS, RDS, MSK, and Cognito Terraform modules move to Phase 6.

Each table arrives with the feature that uses it, in its own migration.

## Design notes

- **Ownership.** `OwnedMixin` adds a non-null, indexed `owner_id` FK to `user`. Phase 1 adds a scoped repository base that filters on it.
- **Identity of a card.** A `card` is unique on (set, card_number). A `parallel` is unique on (set, name). A `card_variant` is unique on (card, parallel). Base cards use a per-set "Base" parallel, so every holding and sale always points at a variant and there are no NULL-parallel special cases.
- **Catalog provenance.** `catalog_source` on `card_set`, `card`, and `parallel` (`user_confirmed` | `seed` | `reference:<provider>`) lets a licensed catalog be added later without a migration.
- **Grade on holdings.** `collection_item.condition` (`raw` | `graded`), with `grader`, `grade`, and `cert_number` nullable. A check constraint requires grader and grade when the condition is `graded`. Grader is a string with an application-level enum, so adding a grader (TAG, CGC) needs no migration.
- **Money.** Integer minor units plus an ISO 4217 code, wrapped in a `Money` value object. Floats are never used.
- **Keys.** UUID primary keys generated in Python. They are safe to expose in URLs and to generate before an insert, which the outbox needs.
- **Outbox.** `enqueue(session, event)` adds a row in the caller's transaction. The relay claims batches with `SKIP LOCKED` so multiple replicas are safe, marks rows `published_at`, and records `attempts` and `last_error`. Delivery is at-least-once, so consumers dedupe on `event.id`.
- **Tracked sets.** YAML defaults, with per-set year overrides. These expand to one row per (sport, brand, set name, year). A unique natural key makes sync idempotent. Removed entries get `active = false` and are never deleted.

## Test plan

- **Unit.** Money arithmetic and validation. Error-to-problem mapping. Event envelope serialization. Tracked-set config parsing (defaults, overrides, invalid years, duplicates, unknown keys). JWT verifier (valid, expired, wrong audience/issuer, unknown kid, bad signature, missing header). API health/readiness (DB up and down), request-id echo, security headers, 404/405/500 as problem+json.
- **Database** (real Postgres + pgvector): the migration applies cleanly and `downgrade base` round-trips. Constraints reject a duplicate variant, a graded item without a grade, and a negative price. Tracked-set sync is idempotent, deactivates removed entries, and reactivates re-added ones. The outbox relay publishes, survives a publisher failure (attempts and error recorded, row retried), and two concurrent relays never double-claim a row.
- **Web.** API client (auth header, problem+json parsing, network errors). The protected route redirects to login when signed out. The layout renders navigation.
- **Coverage gate.** At least 90% for `packages/`, at least 80% for `apps/web`.
