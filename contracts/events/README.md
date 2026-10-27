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

Each event type gets a `<type>.schema.json` file here when its producer is built. The first ones arrive in Phase 2 (`market.sync.requested.v1`, `market.sales.ingested.v1`).
