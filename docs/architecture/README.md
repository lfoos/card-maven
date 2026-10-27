# Card Maven architecture

This is the source of truth for how Card Maven fits together. **Every change checks against this page.** If a change adds, removes, or rewires a component or data flow, the same PR updates the diagram and the status table (see [Keeping this current](#keeping-this-current)).

## System (container view)

```mermaid
flowchart LR
  subgraph Client
    WEB["Web app<br/>React + TypeScript"]
  end

  subgraph Edge
    IDP["Identity provider (OIDC)<br/>Keycloak local / Cognito AWS"]
  end

  subgraph Services["Kubernetes (kind local / EKS AWS)"]
    API["API service<br/>Flask"]
    OUTBOX["Outbox relay"]
    ING["Market ingestion worker"]
    REC["Recognition worker<br/>segment → embed → identify"]
    GRD["Grading worker<br/>CV centering + LLM"]
    CRON["Nightly CronJob<br/>tracked sets"]
  end

  subgraph Messaging["Kafka (local / MSK)"]
    T1[["market.sync.requested"]]
    T2[["market.sales.ingested"]]
    T3[["scan.requested / scan.completed"]]
    T4[["grade.requested / grade.completed"]]
  end

  subgraph Data
    PG[("Postgres 16 + pgvector<br/>app · embeddings · analytics")]
    S3[("Object storage<br/>SeaweedFS local / S3 AWS")]
    DBT["dbt<br/>staging → marts"]
  end

  subgraph External
    MDS["Market data sources<br/>(MarketDataSource adapters)"]
    LLM["Vision model<br/>Anthropic API (VisionModel port)"]
  end

  WEB -- "OIDC login (code + PKCE)" --> IDP
  WEB -- "REST + JWT" --> API
  WEB -- "presigned upload" --> S3
  API -- "verify JWT (JWKS)" --> IDP
  API --> PG
  API -- "writes outbox rows" --> PG
  OUTBOX -- "reads outbox" --> PG
  OUTBOX --> T1 & T3 & T4
  CRON --> T1
  T1 --> ING
  ING --> MDS
  ING --> PG
  ING --> T2
  T3 --> REC
  REC --> S3
  REC --> LLM
  REC --> PG
  T4 --> GRD
  GRD --> S3
  GRD --> LLM
  GRD --> PG
  T2 -. "triggers incremental build" .-> DBT
  DBT --> PG
```

## Component status

| Component | Technology | Code | Status |
|---|---|---|---|
| Web app | React 19, TypeScript, Vite, TanStack Query, oidc-client-ts | `apps/web` | Shell, routing, auth, API client (Phase 0) |
| API service | Flask 3, gunicorn | `services/api` | Health, errors, OIDC verifier (Phase 0). Features from Phase 1. |
| Shared domain | SQLAlchemy 2, Pydantic 2 | `packages/card_maven` | Shared infra and schema for identity, catalog, collection, tracked sets (Phase 0) |
| Outbox relay | confluent-kafka | `services/workers` | Built (Phase 0) |
| Admin CLI | Click | `services/workers` (`card-maven`) | `seed`, `sync-tracked-sets`, `check-config`, `outbox-relay` (Phase 0) |
| Market ingestion worker, nightly CronJob | Kafka consumers | `services/workers` | Phase 2 |
| Recognition worker | OpenCV, CLIP, Anthropic API | `services/workers` | Phase 3 |
| Grading worker | OpenCV, Anthropic API | `services/workers` | Phase 4 |
| dbt project | dbt-postgres | `analytics/dbt` | Phase 2 (sales), Phase 5 (trends) |
| Postgres + pgvector | Postgres 16 | `db/migrations` | Schema baseline (Phase 0) |
| Kafka | Apache Kafka 3.9 (KRaft) / MSK | `infra/compose/kafka/topics.txt`, `contracts/events` | Local topics + envelope contract (Phase 0) |
| Object storage | SeaweedFS (S3 API) / S3 | `infra/terraform/modules/media_bucket` | Local service + Terraform module (Phase 0). Used from Phase 1. |
| Identity provider | Keycloak 26 / Cognito | `infra/compose/keycloak` | Local realm (Phase 0). Cognito in Phase 6. |
| Infrastructure | Terraform, Helm | `infra/terraform`, `infra/helm` | Network, media bucket, ECR modules, chart (Phase 0). EKS, RDS, MSK, Cognito in Phase 6. |

## Code layout (component view)

```mermaid
flowchart TB
  subgraph pkg["packages/card_maven (shared domain)"]
    direction LR
    identity --> shared
    catalog --> shared
    collection --> catalog
    collection --> shared
    market --> catalog
    market --> shared
  end
  api["services/api"] --> pkg
  workers["services/workers"] --> pkg
  db["db/migrations"] --> pkg
```

- **Bounded contexts** (`identity`, `catalog`, `collection`, `market`, and later `recognition` and `grading`) each own their models and services. Contexts reference each other only through the `card_variant` and `app_user` ids.
- **`shared` holds infrastructure only.** That covers config, logging, errors, money, clock, the database base, events, and the outbox. It never imports a context.
- **Ports and adapters.** External dependencies sit behind ports (`EventPublisher` today; `MarketDataSource`, `VisionModel`, `ImageEmbedder`, `ReferenceCatalog`, and `ObjectStore` as they arrive). Each port has a fake for tests.

## Data model

See [plan §3](../IMPLEMENTATION_PLAN.md#3-core-data-model) for the full entity diagram. The rule that holds everything together is that **collection items and market data both point at a `card_variant`** (card × parallel). Every set has a "Base" parallel, so a variant always exists.

## Cross-cutting decisions

- **Auth:** [auth.md](auth.md).
- **ADRs:** [../adr](../adr/README.md). Each records one decision and its trade-offs.

## Keeping this current

A PR must update this page when it does any of the following:

- adds, removes, or renames a deployable component, datastore, topic, or external dependency
- changes how two components talk (sync vs. async, a new topic, a new port)
- changes where data lives or who owns it

The Planner states the "diagram impact" in each change's `plan.md`, and the Reviewer checks it. Changes that don't fit the current picture also get an ADR.
