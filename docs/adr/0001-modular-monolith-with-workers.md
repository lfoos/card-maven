# 0001. Modular monolith API plus event-driven workers

**Status:** Accepted · **Date:** 2026-10-26

## Context
Card Maven has fast request/response work (collection CRUD) and slow, bursty work (market sync, photo recognition, grade estimation). It is built by a small team, and its domain boundaries are still settling.

## Decision
- **One API service**, organized internally by bounded context (identity, catalog, collection, market, recognition, grading).
- **Slow work runs in stateless Kafka-consumer workers.** They share one Python domain package (`packages/card_maven`) with the API.

## Consequences
- One deployable to reason about for synchronous traffic.
- Workers scale independently with load.
- Contexts can become separate services later by moving a subpackage. No rewrite is needed, because boundaries are already enforced by imports.
- Risk: the contexts couple over time. This is mitigated by referencing other contexts only by id, and by the review checklist.

## Alternatives considered
- **Microservices from day one:** operational cost and cross-service consistency problems before the boundaries are proven.
- **A single process doing slow work inline:** blocks requests, can't scale the expensive parts on their own.
