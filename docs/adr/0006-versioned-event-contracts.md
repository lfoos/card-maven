# 0006. Versioned CloudEvents-style event contracts

**Status:** Accepted · **Date:** 2026-10-26

## Context
Workers and future consumers (dbt sources, other services) depend on event shapes. Breaking a shape silently breaks consumers.

## Decision
- **Every event uses one envelope** (`id`, `type`, `source`, `time`, `subject`, `specversion`, `data`), defined in Python (`shared.events.Event`) and in JSON Schema (`contracts/events/`). A test keeps the two in sync.
- **Types are versioned:** `<context>.<entity>.<action>.v<N>`. The topic is the type minus its version.
- **Topics are declared explicitly.** Auto-creation is off.

## Consequences
- Compatible additions keep the version. Breaking changes bump it and run side by side until consumers migrate.
- Partitioning by `subject` gives per-entity ordering.

## Alternatives considered
- **Avro or Protobuf with a schema registry:** stronger tooling, but another service to run. Can be adopted later, because the envelope maps cleanly.
