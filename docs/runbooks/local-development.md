# Runbook: local development

## First run

```bash
make install     # uv sync, pnpm install, pre-commit hooks
make bootstrap   # docker compose up (postgres, kafka, seaweedfs, keycloak) + topics, migrate, seed
make api         # terminal 1: http://localhost:8000
make web         # terminal 2: http://localhost:5173
```

## Services and ports

| Service | URL | Credentials (local only) |
|---|---|---|
| Web app | http://localhost:5173 | `collector@example.com` / `card-maven-local-only` |
| API | http://localhost:8000/healthz, `/readyz` | Bearer token from Keycloak |
| Keycloak | http://localhost:8080 (realm `card-maven`) | admin console: `admin` / `admin` |
| Postgres | `localhost:5432`, databases `card_maven` and `card_maven_test` | `card_maven` / `card_maven` |
| Kafka | `localhost:9092` (containers use `kafka:29092`) | none |
| SeaweedFS (S3 API) | http://localhost:8333 | `card-maven-local` / `card-maven-local-secret` |

## Phase 0 smoke test

1. `make bootstrap` exits 0.
2. Run `curl localhost:8000/readyz`. It should return `{"checks":{"database":"ok"},"status":"ready"}`.
3. Open http://localhost:5173. It should show "API online".
4. Click **Collection**. You're redirected to Keycloak. Sign in, and you land back on Collection.
5. Run `uv run card-maven sync-tracked-sets --dry-run`. It should report `unchanged=39`.
6. Publish an event end to end:
   ```bash
   uv run python -c "
   from card_maven.shared.config import Settings
   from card_maven.shared.db import make_engine, make_session_factory, session_scope
   from card_maven.shared.events import Event
   from card_maven.shared.outbox import enqueue
   f = make_session_factory(make_engine(Settings().database_url.get_secret_value()))
   with session_scope(f) as s: enqueue(s, Event(type='market.sync.requested.v1', source='smoke'))
   "
   uv run card-maven outbox-relay --once     # published=1 failed=0
   docker compose -f infra/compose/docker-compose.yml exec kafka \
     /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server kafka:29092 \
     --topic market.sync.requested --from-beginning --max-messages 1
   ```

## Running everything in containers

```bash
docker compose -f infra/compose/docker-compose.yml --profile app up --build
```

This also runs the API (port 8000) and the outbox relay in containers. Run migrations first with `make migrate`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Database tests are skipped | Set `CARD_MAVEN_TEST_DATABASE_URL`, which `make test-python` does for you, and run `make up`. |
| `could not open extension control file "vector"` | You're on a plain Postgres. Use the compose `pgvector/pgvector:pg16` image. |
| `UnknownTopicOrPartitionException` | Topics are created by `kafka-init`. Run `make up` again, or add the topic to `infra/compose/kafka/topics.txt`. |
| Sign-in loops or fails with "invalid redirect" | The web app must run on `http://localhost:5173`, which is the redirect URI registered in the realm. |
| API returns 401 for every call | The token's `aud` must include `card-maven-api`. Re-import the realm with `make reset && make bootstrap`. |
| Port already in use | Stop whatever holds 5432, 8000, 8080, 8333, or 9092, or change the port mapping in `docker-compose.yml`. |
