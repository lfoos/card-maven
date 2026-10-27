# 0001: Foundation: QA report

**Result: pass.** 230 Python tests (99% line and branch coverage, gate 90%). 60 web tests (94% lines, 100% branches, gate 80%).

## How it was tested

| Layer | Approach |
|---|---|
| Domain and shared code | Pure unit tests: money, errors, events, config, logging, tracked-set config. |
| Schema | Real Postgres 16 + pgvector. Every check constraint, unique key, FK, and cascade is exercised directly. The migration is applied, round-tripped (`downgrade base`, then `upgrade head`), and compared against the models (`compare_metadata` must be empty). |
| Outbox | Real Postgres with real commits, because row locking needs separate connections. Two relays run concurrently and are shown to claim disjoint rows. |
| API | Flask test client with an injected unreachable database (outage paths) and the real database (happy path). JWTs are signed with freshly generated RSA and EC keys. |
| Workers / CLI | Click `CliRunner` against the test database. Kafka is replaced by a fake producer that can deliver, fail, time out, or reject each message. |
| Web | Vitest + Testing Library. `useAuth` and `useApi` are mocked at the module boundary. Routes run in a memory router. |

## Edge cases covered (selection)

- **Money:** banker's rounding at half-cents, 0-decimal currencies (JPY), bool-as-int rejection, NaN/Infinity, and cross-currency arithmetic.
- **Tracked sets:**
  - inverted or out-of-range years
  - per-set overrides with either bound omitted
  - duplicates that differ only by case or spacing
  - unknown keys
  - sport and brand references unknown to the catalog (rejected before any write)
  - deactivate, then reactivate
  - reactivation combined with a focus change
- **Catalog:** "Refractor" is unique set-wide even when `subset` is NULL (`NULLS NOT DISTINCT`), but the same name is allowed in two different subsets. A parallel in use can't be deleted.
- **Collection:** every invalid condition, grader, and grade combination; serial 0; a price without a currency and a currency without a price; negative prices. Images and items cascade when a user is deleted.
- **Auth:**
  - expired tokens, and clock skew inside the leeway
  - wrong `aud`, wrong `iss`, future `nbf`, missing `sub`/`iat`
  - a foreign signing key or an unknown `kid`
  - HS256 algorithm confusion and `alg: none`
  - malformed tokens, and a JWKS endpoint outage (503, not 401)
- **API:**
  - unsafe `X-Request-ID` values are replaced, not echoed
  - 5xx responses never leak internal details
  - a body over 1 MB returns 413
  - disallowed CORS origins get no CORS headers
- **Web:**
  - open-redirect attempts in the sign-in return path (`//evil`, `/\evil`, absolute URLs)
  - auth errors, plus not starting a second redirect while one is in flight
  - network vs. HTTP vs. problem+json errors, and aborts

## Defects found and sent back to the Implementer

| # | Defect | Fix |
|---|---|---|
| QA-1 | **Poison message.** One outbox row with an undecodable payload raised inside the batch, rolled back the whole claim, and blocked every event behind it forever. | Rows are decoded one at a time. Bad rows are parked with `attempts`, `last_error`, and a backoff, and the rest of the batch publishes. Covered by `TestPoisonMessages`. |
| QA-2 | **Connection leak.** CLI commands created a database engine per invocation and never disposed it, leaving open connections (surfaced as `ResourceWarning`, which the suite treats as an error). | The engine is created lazily, once per command, and disposed via `ctx.call_on_close`. |
| QA-3 | **Duplicate brands slipped through.** Tracked-set duplicate detection compared raw brand names, so `Upper Deck` and `upper  deck` weren't caught, though both map to the same slug. | Duplicates are compared on the normalized slug. |
| QA-4 | **Log context leak.** A request's `request_id` stayed bound in the logging context after the request ended. | Cleared in `teardown_request`. Test added. |

## Not verified locally

This workspace has no Docker daemon, and it can't download Helm or Terraform. The checks below run only in CI (`helm`, `terraform`, and `images` jobs) and should be confirmed green on the PR:

- `docker compose` stack startup (Kafka topic init, SeaweedFS, Keycloak realm import)
- Container image builds
- `helm lint` / `helm template`
- `terraform fmt` / `validate`

A manual smoke test of `make bootstrap` on a laptop is the Phase 0 demo step (see the runbook).
