# Card Maven analytics (dbt)

Shared-market marts built from the application database. Trends (Phase 5) read these. Per-collector estimates don't: they include private manual comps, so the API computes them online.

## Models

| Layer | Model | What it is |
|---|---|---|
| staging | `stg_market__sales` | Sales from `analytics`-licensed sources that are matched to a card and shared. Private manual comps are excluded. |
| staging | `stg_catalog__variants` | One row per card variant, with its set and parallel |
| intermediate | `int_sales_graded` | Adds `condition_bucket`: `Raw`, `PSA 10`, `BGS 9.5`, … |
| mart | `mart_variant_value` | Per variant and condition over the last 90 days (`value_window_days`): count, median, min, max, latest sale |
| mart | `mart_sales_daily` | Per set per day: sales count, total, and median |

Marts are tables with enforced contracts, in the `analytics` schema. Application tables stay in `public`.

## The license gate (ADR-0009)

eBay data is display-only and must never feed analytics. Three things keep it out:
1. **No source.** The `listing` table isn't declared as a source at all.
2. **Filtered staging.** `stg_market__sales` keeps only `analytics` sources.
3. **A singular test.** `assert_only_analytics_sales_reach_marts` fails the build if anything else gets through.

## Running

```bash
make dbt                      # against the local database (make up, make migrate)
cd analytics/dbt && uv run dbt build --profiles-dir . --vars '{as_of_date: "2026-10-27"}'
```

- **Connection** comes from `DBT_PG_HOST`, `DBT_PG_PORT`, `DBT_PG_USER`, `DBT_PG_PASSWORD` and `DBT_PG_DATABASE` (defaults match `make up`), plus `DBT_PG_SCHEMA` (default `analytics`).
- **In Kubernetes**, `bin/dbt-from-url` derives these variables from `CARD_MAVEN_DATABASE_URL`.

## Testing

- **Unit tests** (`unit_tests:` in the model YAML) check the median, the window edges, and the bucket formatting against fixed inputs.
- **CI** migrates a fresh database, loads the sample (fixture) sales, runs `dbt build`, and checks that the marts have rows.

## Versions

This project uses **dbt-core 1.12 with dbt-postgres 1.11**, locked in this folder's `uv.lock`, separate from the app's.
- dbt v2 doesn't support Postgres yet. It covers Snowflake, BigQuery, Databricks, Redshift, and a few others.
- dbt v1 is still fully supported.
- Revisit when we move analytics to a v2-supported warehouse, such as Redshift in Phase 6.
