# 0003: Market data pipeline: Architecture review

**Verdict: approved after loop-backs.**

## Loop-backs

| # | Sent to | Finding | Resolution |
|---|---|---|---|
| R-1 | Implementer | `reference_data` lived in `catalog` but seeded market sources, so catalog depended on market. | Moved it to the package root (`card_maven.reference_data`). |
| R-2 | Implementer | The job-status poll ran side effects (cache invalidation) inside `queryFn`, which re-ran on every poll. | An effect fires once when the tracked job reaches a terminal state. |
| R-3 | Implementer | Routes called four market services directly, so ownership and license rules would be repeated in every route. | `CollectorMarket` facade. Routes parse, call one method, and present. |
| R-4 | Planner | `processed_event` and abandoned jobs grew without bound. | The hourly purge drops both after 30 days. Kafka retention is far shorter, so dedupe stays correct. |
| R-5 | Implementer | `sync_job_out` returned `Optional`, forcing `assert`s at call sites. | Non-optional; the one nullable caller checks. |
| R-6 | Planner | dbt v2 is the default install now, but it has no Postgres adapter. | Pinned to dbt-core 1.12 / dbt-postgres 1.11 in an isolated, locked project. Revisit when analytics moves to a v2-supported warehouse. |

## Checked and accepted

- **License as data, enforced structurally.** `market_source.license` drives three independent gates: ingestion rejects display-only sales, queries filter on license, and dbt never declares `listing` as a source and has a test for it. Adding a paid analytics provider is a seed row plus an adapter.
- **Plan / fetch / store.** No database transaction is held open across network calls. The processed marker and the results commit together, so a redelivery after a crash is a no-op. Offsets commit only after that.
- **Shared, deduplicated jobs.** One job per card within the reuse window protects source quotas. Visibility comes from holding the card, not from being the requester.
- **Estimates online, marts offline.** Per-collector estimates include private comps, so they can't come from a shared mart. They're one windowed query per page (no N+1). The marts are the shared view for Phase 5.
- **Explainable matching.** Rules plus the eBay Taxonomy vocabulary, with a method tag on every match (`rules_v1`), so re-matching with a better method later is a data migration, not a mystery.

## Accepted for later

- **Re-matching unmatched sales.** Tracked-set syncs store analytics sales unmatched when the catalog lacks the card. They match on the card's next variant sync. A batch re-match job fits Phase 3, with the reference catalog.
- **Vector-similarity matching** is deferred to Phase 3 (embedding model), as planned.
- **Outbox table growth** (published rows) predates this change. Fold it into the purge job in Phase 6.
