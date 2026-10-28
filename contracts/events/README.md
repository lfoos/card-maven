# Event contracts

Every Kafka message is a JSON [envelope](envelope.schema.json) carrying a typed payload.

## Rules

- **Naming.** The event `type` is `<context>.<entity>.<action>.v<N>`, for example `market.sync.requested.v1`.
- **Topics.** The topic is the type without its version (`market.sync.requested`). Topics are declared in `infra/compose/kafka/topics.txt` locally and in Terraform for AWS. Auto-creation is off.
- **Compatibility.**
  - Adding an optional field is a compatible change. Keep the version.
  - Removing or renaming a field, or changing its meaning, is breaking. Bump `vN` and keep publishing the old version until every consumer has migrated.
- **Delivery.** Delivery is at-least-once, through the transactional outbox. Consumers must be idempotent on `id`.
- **Ordering.** Ordering is guaranteed only per `subject`, which is the partition key.

## Payload schemas

Each event type gets a `<type>.schema.json` file here, describing its `data`. Contract tests check that real producer output validates.

| Type | Producer | Consumer | Data |
|---|---|---|---|
| `market.sync.requested.v1` | API (Get comps), `request-market-sync` (nightly) | `market-worker` | [schema](market.sync.requested.v1.schema.json) |
| `market.sales.ingested.v1` | `market-worker` | none yet (Phase 5 trends) | [schema](market.sales.ingested.v1.schema.json) |

## Dead-letter topics

A consumer that can't process a message (undecodable, invalid, or still failing after 3 attempts) publishes it unchanged to `<topic>.dlq`, with headers `dlq_reason` and `dlq_source_topic`, then moves on. Replay is manual: fix the cause, then re-publish from the DLQ.
