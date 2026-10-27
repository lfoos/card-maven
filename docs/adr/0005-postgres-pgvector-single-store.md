# 0005. Postgres + pgvector as the single datastore

**Status:** Accepted · **Date:** 2026-10-26

## Context
The app needs relational data (catalog, collections, sales), vector similarity (card image embeddings), and analytics (dbt marts). It is early, and operational simplicity matters.

## Decision
One Postgres 16 database with pgvector:
- application tables in `public`
- embeddings in vector columns with HNSW indexes (Phase 3)
- dbt models in an `analytics` schema

## Consequences
- One system to back up, secure, and monitor.
- Joins across app data, vectors, and analytics are trivial.
- Analytics load shares resources with the app. Mitigations: dbt runs off-peak, a read replica, or a move to Redshift or Snowflake, which dbt makes a contained change.

## Alternatives considered
- **A dedicated vector DB plus a warehouse:** three systems before there's a scale need.
