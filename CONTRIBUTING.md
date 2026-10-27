# Contributing to Card Maven

## Workflow

1. **Branch from `master`**, named `<phase-or-type>/<short-name>` (e.g. `phase-1/collection-api`, `fix/outbox-backoff`).
2. **Plan the change** in `docs/changes/NNNN-slug/plan.md` (see [Change reports](#change-reports)). Small fixes can skip this.
3. **Write code and tests together.** `make check` must pass locally.
4. **Commit with [Conventional Commits](https://www.conventionalcommits.org/)** (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
5. **Open a PR.** CI must be green before review. Update [CHANGELOG.md](CHANGELOG.md) under *Unreleased*.

## Quality bar

- **Every behavior has tests:** the expected path, edge cases, and failure modes. Coverage gates are at least 90% for Python and at least 80% for the web app, but they are floors, not goals.
- **The database is tested for real.** Tests marked `db` run against Postgres + pgvector (`make up` provides it). Models must match migrations; a test fails otherwise.
- **No warnings.** pytest treats warnings as errors, and ESLint runs with `--max-warnings=0`.
- **Types:** mypy `--strict` for Python, `strict` TypeScript.
- **Schema changes go through Alembic.** Change the model, run `make migration m="..."`, read and tidy the generated file, and commit both.
- **Config changes** (`config/*.yaml`) are validated by `make check-config` and by a pre-commit hook.

## Architecture rules

- **Check against the [architecture doc](docs/architecture/README.md).** If your change alters a component, datastore, topic, or data flow, update the diagram in the same PR. Significant decisions get an [ADR](docs/adr/README.md).
- **Bounded contexts** live in `packages/card_maven/<context>/`. A context may import `shared` and reference other contexts' ids. Import another context's models only where the domain requires it (today: `collection` uses `catalog.CardVariant`).
- **External dependencies go behind a port**, with a fake for tests ([ADR-0002](docs/adr/0002-ports-and-adapters.md)).
- **Events are published through the outbox**, never directly ([ADR-0003](docs/adr/0003-transactional-outbox.md)). Event contracts follow [contracts/events/README.md](contracts/events/README.md).
- **Money and time** follow [ADR-0008](docs/adr/0008-money-time-and-identifier-conventions.md). No floats for money, and no naive datetimes.

## Change reports

Each feature-sized change passes through six roles. A condensed summary goes in the PR description, and full detail goes in `docs/changes/NNNN-slug/`:

| Role | Responsibility | Output |
|---|---|---|
| Planner | Design, data model, diagram impact, test plan | `plan.md` |
| Implementer | Code and unit tests | the PR |
| QA | Edge-case and failure testing; defects sent back | `qa.md` |
| Reviewer | Design and code review; loop-backs recorded | `review.md` |
| Security | Threats, hardening, dependency risk; blocking findings fixed before merge | `security.md` |
| Tech writer | README, API and usage docs, CHANGELOG, release notes | docs in the PR |

## Local tips

- `uv run pytest -m "not db"` runs the fast tests without Postgres.
- `uv run pytest packages/card_maven/tests/test_outbox.py -k poison` runs a single test.
- `cd apps/web && pnpm test:watch` watches web tests.
- `make reset && make bootstrap` gives you a clean database.
