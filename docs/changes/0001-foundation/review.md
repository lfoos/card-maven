# 0001: Foundation: Architecture review

**Verdict: approved after one loop-back.**

## Loop-backs

| # | Sent to | Finding | Resolution |
|---|---|---|---|
| R-1 | Implementer | `shared.events` imported `utcnow` from `shared.db`, so the event envelope depended on the database layer. Pure domain code should not depend on infrastructure. | Extracted `shared/clock.py`. `db`, `events`, and `outbox` all import from it. |
| R-2 | Planner | The plan named MinIO for local object storage. MinIO Community Edition stopped publishing images in Oct 2025, and its repository has since been archived. | Switched to SeaweedFS (Apache-2.0, S3-compatible). Updated the architecture diagram and plan. Code only ever sees the S3 API, so this is a config-level choice. |
| R-3 | Implementer | `ApiProvider` read a ref during render to avoid rebuilding the client. That is fragile under concurrent rendering, and the React Hooks lint rule rejects it. | The client is memoized on the access token, so it rebuilds only on token renewal (every few minutes). This is simpler and pure. |

## Checked and accepted

- **Bounded contexts.** `identity`, `catalog`, `collection`, and `market` each own their models. Cross-context references go only through `card_variant` and `app_user`, matching the plan's ER diagram.
- **Data model extensibility.**
  - Base parallels mean every holding and sale has a variant, with no NULL branches downstream.
  - `catalog_source` and the JSONB `attributes` / `external_ids` columns absorb a future reference catalog without a migration.
  - The grader is a string with an app-level enum, so adding a grader needs no migration.
  - Tables for later phases are deliberately absent, so no schema is speculative.
- **Outbox.** Single transaction, `SKIP LOCKED`, at-least-once delivery, exponential backoff capped at 5 minutes, a partial index on pending rows. The publisher port returns per-message results, so the Kafka adapter can batch and flush once.
- **API.** App factory with injected dependencies (no module globals), RFC 9457 errors, stateless JWT verification.
- **Config as data.** Tracked sets and reference data are validated YAML, with CI checks. Adding coverage is a config edit.

## Accepted for later (not blocking)

- **Tracked-set sync scale.** `sync_tracked_sets` loads the whole table. That's fine at hundreds of rows. Revisit only if tracked sets reach the tens of thousands.
- **Pinned actions.** Third-party GitHub Actions are pinned by major tag. Pinning by commit SHA (with Dependabot updates) is recommended before Phase 6.
- **SeaweedFS image tag.** The image uses `:latest`, because no stable tag could be verified from this environment. Pin it once the stack has been verified on a laptop.
