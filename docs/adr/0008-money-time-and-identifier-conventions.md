# 0008. Money, time, and identifier conventions

**Status:** Accepted · **Date:** 2026-10-26

## Context
Prices come from several sources and currencies. Rounding bugs and timezone bugs are common, and expensive to fix after data accumulates.

## Decision
- **Money** is stored as integer minor units plus an ISO 4217 code (`*_minor` and `*_currency` columns, enforced together by a check constraint). In code it is the `Money` value object, with banker's rounding at the edges. Floats are never used.
- **Time** is always timezone-aware UTC (`timestamptz`). `shared.clock.utcnow()` is the only clock.
- **Identifiers** are UUID primary keys generated in Python, so ids exist before insert (the outbox needs this) and are safe to expose. Small reference tables (`sport`, `brand`) use readable natural keys.

## Consequences
- Arithmetic is exact, and cross-currency mistakes raise errors.
- UUIDv4 keys index less compactly than sequential keys. Revisit with UUIDv7 if write volume makes index locality matter.
