# 0003. Transactional outbox for publishing events

**Status:** Accepted · **Date:** 2026-10-26

## Context
API actions must both change the database and emit an event (for example, "scan requested"). Writing to Postgres and Kafka separately can lose events, or emit events for changes that rolled back.

## Decision
- **Writers call `outbox.enqueue(session, event)` in the same transaction as the change.**
- **A relay (`card-maven outbox-relay`) publishes pending rows to Kafka.** It claims batches with `SELECT … FOR UPDATE SKIP LOCKED`, marks each row published or records the error with exponential backoff, and parks undecodable rows instead of blocking on them.

## Consequences
- An event exists if and only if its change committed.
- Delivery is at-least-once, so consumers must deduplicate on `event.id`.
- The relay scales horizontally, because replicas never claim the same rows.
- Publish latency is roughly the poll interval (1s by default).
- Published rows need periodic pruning (to be added when volume warrants).

## Alternatives considered
- **Dual writes:** inconsistent on failure.
- **Debezium CDC:** robust, but heavier to operate at this stage. Can replace the relay later without changing writers.
