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
| Web app | React 19, TypeScript, Vite, TanStack Query, oidc-client-ts | `apps/web` | Shell and auth (Phase 0). Collection grid/table, add/edit, detail, photo upload (Phase 1). API types generated from the OpenAPI contract. |
| API service | Flask 3 + flask-openapi3, Flask-Limiter, gunicorn | `services/api` | Health, errors, OIDC (Phase 0). `/me`, catalog autocomplete, collection CRUD, photo uploads, rate limits, OpenAPI contract (Phase 1). |
| Shared domain | SQLAlchemy 2, Pydantic 2 | `packages/card_maven` | Identity provisioning, catalog resolution, collection service, image verification, owner-scoped repositories, keyset pagination, `ObjectStore` port (Phase 1) |
| Outbox relay | confluent-kafka | `services/workers` | Built (Phase 0) |
| Admin CLI | Click | `services/workers` (`card-maven`) | `seed`, `sync-tracked-sets`, `check-config`, `outbox-relay` (Phase 0). `init-storage` (Phase 1). |
| Market ingestion worker, nightly CronJob | Kafka consumers | `services/workers` | Phase 2 |
| Recognition worker | OpenCV, CLIP, Anthropic API | `services/workers` | Phase 3 |
| Grading worker | OpenCV, Anthropic API | `services/workers` | Phase 4 |
| dbt project | dbt-postgres | `analytics/dbt` | Phase 2 (sales), Phase 5 (trends) |
| Postgres + pgvector + pg_trgm | Postgres 16 | `db/migrations` | Schema baseline (Phase 0). Case-insensitive natural keys, trigram search, image lifecycle (Phase 1). |
| Kafka | Apache Kafka 3.9 (KRaft) / MSK | `infra/compose/kafka/topics.txt`, `contracts/events` | Local topics + envelope contract (Phase 0) |
| Object storage | SeaweedFS 4.51 (S3 API) / S3 | `shared/storage`, `infra/terraform/modules/media_bucket` | Card photos via presigned POST, verified server-side (Phase 1) |
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
- **Ports and adapters.** External dependencies sit behind ports (`EventPublisher` and `ObjectStore` today; `MarketDataSource`, `VisionModel`, `ImageEmbedder`, and `ReferenceCatalog` as they arrive). Each port has a fake for tests.
- **Owner scoping.** Every query over user-owned rows is built by `OwnedRepository._scoped()`, so isolation between collectors is structural, not a per-endpoint check.
- **Contract-first API.** Routes declare Pydantic request and response models. The OpenAPI spec is generated from them into `contracts/openapi.json`, and the web app's TypeScript types are generated from that file. CI fails if either drifts.

## Photo upload flow

```mermaid
sequenceDiagram
  autonumber
  participant W as Web app
  participant A as API
  participant D as Postgres
  participant S as Object storage
  W->>W: SHA-256 of the file
  W->>A: POST /items/{id}/images (kind, type, size, sha256)
  A->>D: insert image (status=pending)
  A-->>W: presigned POST (key, type, exact size pinned)
  W->>S: POST file directly
  S-->>W: 204 (or 403/400 if the policy is violated)
  W->>A: POST /items/{id}/images/{image_id}/complete
  A->>S: HEAD + stream bytes
  A->>A: verify size, type, signature, SHA-256
  A->>D: retire old front/back, mark ready (one transaction)
  A->>S: delete replaced object (after commit)
  A-->>W: image with 10-minute download URL
```

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
