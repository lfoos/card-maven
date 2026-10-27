# Card Maven

Card Maven helps sports card collectors track what they own and value it against the market. You add cards by hand or by photographing a group of them, see recent comparable sales, get an estimated PSA grade, and follow price and volume trends across baseball, basketball, football, and hockey.

> **Status: Phase 1 (collection).** Collectors can sign in, add and edit cards, upload front and back photos, and browse their collection. Market data arrives in Phase 2. See the [implementation plan](docs/IMPLEMENTATION_PLAN.md) for the roadmap. The previous SQLite app is preserved on the [`legacy-v0`](https://github.com/lfoos/card-maven/tree/legacy-v0) branch.

## Features

| Feature | Phase | Status |
|---|---|---|
| Collection: sport, year, brand, player, parallel, card, team, grade, estimated value | 1 | **Available** (estimated value shows once Phase 2 lands) |
| Comps: last 5 sales for a card | 2 | Planned |
| Nightly market sync for tracked sets | 2 | Tracked-set config ready |
| Photo of many cards → cropped and identified, user confirms | 3 | Planned |
| Estimated PSA grade with grade-matched comps | 4 | Planned |
| Trends dashboard: price, volume, rising/falling players | 5 | Planned |

## Architecture

A React web app talks to a Flask API. Slow work (market sync, photo recognition, grading) runs in Kafka-driven workers. Everything persists in Postgres with pgvector, and dbt builds the analytics. Sign-in uses OIDC (Keycloak locally, Cognito on AWS). The services deploy to Kubernetes, with infrastructure in Terraform.

- [Architecture overview and diagram](docs/architecture/README.md). This is the source of truth and is kept current with every change.
- [Authentication design](docs/architecture/auth.md)
- [Architecture decision records](docs/adr/README.md)
- [API reference](docs/api/README.md) (OpenAPI contract: [`contracts/openapi.json`](contracts/openapi.json))
- [User guide: managing your collection](docs/user-guide/collection.md)

| Layer | Technology |
|---|---|
| Web | React 19, TypeScript, Vite, TanStack Query, React Router, oidc-client-ts |
| API | Python 3.12+, Flask 3, Pydantic 2, gunicorn |
| Domain and data | SQLAlchemy 2, Alembic, Postgres 16 + pgvector |
| Events | Kafka (KRaft locally, MSK on AWS), transactional outbox |
| Analytics | dbt (Phase 2+) |
| AI | Anthropic API behind a swappable `VisionModel` port (Phase 3+) |
| Auth | OIDC Authorization Code + PKCE: Keycloak / Cognito |
| Infra | Docker, Kubernetes (Helm), Terraform, AWS |

## Quick start

**Prerequisites** (`make doctor` checks them and prints install commands):
- Docker (with Compose v2)
- [uv](https://docs.astral.sh/uv/) 0.5+ (installs the pinned Python 3.13 from `.python-version` automatically)
- Node.js 22
- pnpm 10

```bash
git clone https://github.com/lfoos/card-maven.git
cd card-maven
make install      # checks prerequisites, then installs Python and web dependencies, git hooks
make bootstrap    # start Postgres, Kafka, SeaweedFS, Keycloak; migrate; seed; create the photo bucket
make api          # http://localhost:8000  (terminal 1)
make web          # http://localhost:5173  (terminal 2)
```

Open http://localhost:5173. The home page shows "API online" when everything is connected.

To sign in locally, click **Sign in** and use the local-only demo account: `collector@example.com` / `card-maven-local-only`. You can also register a new account. The Keycloak admin console is at http://localhost:8080 (`admin` / `admin`).

The full walkthrough, including troubleshooting, is in [docs/runbooks/local-development.md](docs/runbooks/local-development.md).

## Common commands

Run `make help` for everything. The most-used targets:

| Command | What it does |
|---|---|
| `make up` / `make down` / `make reset` | Start, stop, or wipe the local stack |
| `make migrate` | Apply database migrations |
| `make migration m="add sale table"` | Generate a migration from model changes |
| `make seed` | Load sports and brands, and sync tracked sets from `config/` |
| `make doctor` | Check that Docker, uv, Node 22, and pnpm are installed and running |
| `make openapi` | Regenerate `contracts/openapi.json` after changing the API (then `cd apps/web && pnpm gen:api`) |
| `make check` | Lint, typecheck, validate config, and run all tests (what CI runs) |
| `make relay` | Run the outbox relay (publishes events to Kafka) |

## Configuration

Settings come from `CARD_MAVEN_*` environment variables, and the defaults target the local stack. See [`.env.example`](.env.example) and [`apps/web/.env.example`](apps/web/.env.example). In `dev`/`prod`, the service refuses to start with local-only values (the default database password, `http://` identity provider URLs, or wildcard CORS).

### Tracked sets

The nightly market job covers the sets listed in [`config/tracked_sets.yaml`](config/tracked_sets.yaml). It currently tracks 2024–2026 of:

- **Baseball:** Bowman Chrome, Topps Chrome, Topps Series 1/2
- **Basketball and football:** Prizm, Select, Mosaic, Obsidian
- **Hockey:** Upper Deck Series 1 (Young Guns)

To expand coverage, edit the file and open a PR:

```yaml
defaults:
  years: { from: 2024, to: 2026 }      # widen to backfill every set
sets:
  - { sport: baseball, brand: Bowman, name: Bowman Draft, years: { from: 2020 } }
```

CI validates the file (`make check-config`). Brands and sports must exist in [`config/reference_data.yaml`](config/reference_data.yaml). Removing an entry deactivates it and keeps its history.

## Repository layout

```
apps/web/              React web app
services/api/          Flask HTTP API
services/workers/      Kafka workers and the `card-maven` admin CLI
packages/card_maven/   Shared domain: identity, catalog, collection, market, shared infra
db/migrations/         Alembic migrations (the schema's source of truth)
config/                Tracked sets and reference data (validated YAML)
contracts/openapi.json HTTP API contract (generated, drift-checked)
contracts/events/      Event envelope and payload JSON Schemas
infra/compose/         Local Docker stack
infra/helm/            Kubernetes chart
infra/terraform/       AWS modules and environments
docs/                  Plan, architecture, ADRs, runbooks, per-change reports
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow, quality bar (tests with every change, at least 90% Python coverage and at least 80% web coverage), and how each change is planned, reviewed, and documented.

## License

MIT
