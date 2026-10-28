# Architecture decision records

Each ADR records one significant decision: the context, the choice, and its consequences. ADRs are immutable once accepted. A later ADR that changes a decision marks the earlier one "Superseded by ADR-NNNN".

To add one, copy [template.md](template.md) as the next number and open it as part of the PR that makes the change.

| # | Decision | Status |
|---|---|---|
| [0001](0001-modular-monolith-with-workers.md) | Modular monolith API plus event-driven workers | Accepted |
| [0002](0002-ports-and-adapters.md) | Ports and adapters for external dependencies | Accepted |
| [0003](0003-transactional-outbox.md) | Transactional outbox for publishing events | Accepted |
| [0004](0004-oidc-authentication.md) | OIDC with an external identity provider | Accepted |
| [0005](0005-postgres-pgvector-single-store.md) | Postgres + pgvector as the single datastore | Accepted |
| [0006](0006-versioned-event-contracts.md) | Versioned CloudEvents-style event contracts | Accepted |
| [0007](0007-model-provenance.md) | Record model provenance on every inference | Accepted |
| [0008](0008-money-time-and-identifier-conventions.md) | Money, time, and identifier conventions | Accepted |
| [0009](0009-market-data-licensing.md) | Market data licensed per source; eBay display-only | Accepted |
