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
| SeaweedFS (S3 API) | http://localhost:8333, bucket `card-maven-media` | `card-maven-local` / `card-maven-local-secret` |

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

## Phase 1 smoke test

1. `make bootstrap` (rerun it after pulling: it applies migration `0002` and creates the photo bucket).
2. Open http://localhost:5173 and sign in.
3. **Collection → Add card.** Enter `Bowman`, `Bowman Chrome`, `2025`, `CPA-JW`, `JJ Wetherholt`, parallel `Gold Refractor` with print run `50`, serial `12`, condition Graded / PSA / 10. Save. You land on the card's page.
4. Upload a front photo (any JPEG). It appears after "Checking file…". Upload another to replace it.
5. Add a second card. In **Add card**, start typing `chrome` in Set; the suggestion appears.
6. Back on **Collection**: switch Grid ↔ Table, search `wether`, filter by year. The address bar updates.
7. Sign out, register a second account, and open the first card's URL. You see "That card isn't in your collection."
8. Delete a card. It disappears from the list.

## Phase 2 smoke test

1. Pull, then run `make bootstrap`. It applies migration `0003`, seeds the market sources, and creates the `market.sync.requested.dlq` topic.
2. Start everything in four terminals: `make api`, `make web`, `make relay`, and `make market-worker`.
3. Add the card **2024 Topps Chrome #1 Paul Skenes**, graded PSA 10. On its page, the Market panel says "Not synced yet".
4. Click **Get comps**. Within a few seconds you should see:
   - **Recent sales:** the sample PSA 10 sales first, then a PSA 9 marked *nearest*.
   - **Estimated value:** $98.75, "Median of 2 PSA 10 sales…".
   - **Collection:** the card shows the same estimate.
5. Click **Get comps** again. It returns at once, because a sync from the last 15 minutes is reused.
6. Open **Add sales you know of** and paste:
   ```csv
   date,price,grader,grade
   2026-10-20,110.00,PSA,10
   ```
   The sale appears with a **Delete** button, and the estimate moves.
7. Sign in as a second collector and add the same card. Your manual sale isn't visible there.
8. Nightly job: `make market-sync` queues 39 tracked-set jobs, and the worker processes them. `make maintenance` purges stale listings.
9. Analytics: `make dbt`. Every node passes. The marts are in the `analytics` schema.

**Without Kafka:** `uv run card-maven request-market-sync --run-now` runs every tracked-set sync inline.

### eBay sandbox

1. Put your keyset in `.env` (git-ignored): `CARD_MAVEN_EBAY_ENVIRONMENT=sandbox`, `CARD_MAVEN_EBAY_CLIENT_ID`, and `CARD_MAVEN_EBAY_CLIENT_SECRET`.
2. Check the keys: `uv run card-maven market-search Topps Chrome --year 2024`.
   - Records printed means OAuth and search work.
   - The sandbox returns eBay's mock items, which rarely match real cards. That's expected; production keys return real listings.
3. Load the trading-card vocabulary with `uv run card-maven sync-ebay-taxonomy`. Expect "loaded N eBay taxonomy terms".
4. Restart `make market-worker`. **Get comps** now also shows eBay asks under **Current listings** when a listing matches the card.

**Switching to production:**
- Set `CARD_MAVEN_EBAY_ENVIRONMENT=production` with the production keyset.
- Optionally set `CARD_MAVEN_EBAY_CAMPAIGN_ID` (eBay Partner Network) for affiliate links.
- In Kubernetes, put the keys in the app Secret as `ebay-client-id` and `ebay-client-secret`.

## Running everything in containers

```bash
docker compose -f infra/compose/docker-compose.yml --profile app up --build
```

This also runs the API (port 8000), the outbox relay, and the market worker in containers. eBay keys pass through from your shell or `.env`. Run migrations first with `make migrate`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Database tests are skipped | Set `CARD_MAVEN_TEST_DATABASE_URL`, which `make test-python` does for you, and run `make up`. |
| `could not open extension control file "vector"` | You're on a plain Postgres. Use the compose `pgvector/pgvector:pg16` image. |
| `UnknownTopicOrPartitionException` | Topics are created by `kafka-init`. Run `make up` again, or add the topic to `infra/compose/kafka/topics.txt`. |
| Sign-in loops or fails with "invalid redirect" | The web app must run on `http://localhost:5173`, which is the redirect URI registered in the realm. |
| API returns 401 for every call | The token's `aud` must include `card-maven-api`. Re-import the realm with `make reset && make bootstrap`. |
| Photo upload fails with a CORS error | Run `make storage` to (re)apply the bucket's CORS rules for `http://localhost:5173`. |
| `make install` / `make bootstrap` says a tool is missing | Follow the install hint `make doctor` prints, then open a new terminal. |
| Get comps stays on "Checking market sources…" | The relay or the market worker isn't running (`make relay`, `make market-worker`). A stuck job stops blocking new requests after 10 minutes. |
| `market_source_skipped reason='eBay keys not set'` | Expected without eBay keys. Comps come from the sample source locally. |
| `invalid settings: the fixture market source is sample data…` | Deployed environments must set `CARD_MAVEN_MARKET_SOURCES='["ebay_browse"]'`. |
| `make dbt` fails to connect | dbt reads `DBT_PG_*` (defaults match `make up`); see `analytics/dbt/README.md`. |
| Port already in use | Stop whatever holds 5432, 8000, 8080, 8333, or 9092, or change the port mapping in `docker-compose.yml`. |
