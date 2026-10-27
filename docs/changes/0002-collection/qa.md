# 0002: Identity and collection: QA report

**Result: pass.**
- **Python:** 420 tests, 99% line and branch coverage (gate 90%).
- **Web:** 118 tests, 97% lines and 93% branches (gate 80%).

## How it was tested

| Layer | Approach |
|---|---|
| Domain | Catalog resolution, provisioning, collection service, image service, and keyset pagination, run against real Postgres + pgvector + pg_trgm. |
| Storage adapter | Every test runs twice: against **moto**, and against a **real SeaweedFS 4.51** server. The SeaweedFS run is what proves the storage server itself rejects oversized files, wrong content types, and tampered keys; moto doesn't enforce POST policies. CI starts SeaweedFS for the same coverage. |
| API | Flask test client over a real database with committed transactions, signed JWTs for several users, and an in-memory object store. Every endpoint is covered for the happy path, 401, 404-for-another-user, and 422 problem+json with field locations. |
| Contract | `contracts/openapi.json` is regenerated in a test and must match byte for byte. Every operation must declare bearer security and a 401. The web app's TypeScript types are generated from the same file (`pnpm check:api`). |
| Web | Testing Library against a fake API client: forms, list (filters, sort, paging, URL state), detail, delete confirmation, and the photo upload state machine. |

## Edge cases covered (selection)

- **Catalog:**
  - "Bowman Chrome" and "bowman  chrome" resolve to one set; card numbers match case-insensitively.
  - A second collector's typo doesn't overwrite an existing card.
  - Parallels are scoped to their subset, but "Base" is set-wide.
  - Two "Will Smith"s in different sports stay separate.
  - Racing inserts converge on one row, while unexplained integrity errors still surface.
- **Pagination:** every sort at page sizes 1, 3, and 100, with no gaps or repeats. Inserting rows between pages doesn't shift results. Cursors from another sort, and garbage cursors, are rejected.
- **Validation:**
  - grades in 0.5 steps and grade-versus-condition rules, also re-checked after a PATCH merge
  - serial number versus print run, including after the parallel changes
  - prices sent as JSON floats (rejected) or with 3 decimals
  - future acquisition dates and unknown fields
- **Search:** `%` and `_` in queries are literal. Free text matches player names on multi-player cards, team, set, parallel, and card number.
- **Photos:**
  - JPEG, PNG, WebP, and HEIC signatures, plus a renamed HTML file
  - size mismatch and checksum mismatch, with chunked hashing of a 3 MB file
  - completing before uploading (409) and idempotent completion
  - replacing a photo deletes the old object only after commit
  - a storage outage during cleanup doesn't fail the request
- **Isolation:** another user's item or image returns 404 on every endpoint, and their list is empty.
- **Rate limits:**
  - 429 problem with `Retry-After`
  - separate buckets per user and for anonymous callers
  - probes exempt
  - `X-Forwarded-For` trusted only when `trusted_proxy_count` is set; otherwise a spoofed header can't dodge the limit

## Defects found and sent back to the Implementer

| # | Defect | Fix |
|---|---|---|
| QA-1 | **Upload race.** Two uploads of the same side completing at once: the loser hit the "one live photo" unique index and got a **500**. | The swap runs in a savepoint. A unique-index violation becomes a retryable **409**. Test simulates the race. |
| QA-2 | **Autoflush warning.** Creating a card attached it to its set before its players were looked up, so the lookup's autoflush hit a half-built card (an `SAWarning`, which the suite treats as a failure). | Players are resolved before the card is built. |
| QA-3 | **Limiter state leaked between app instances.** A module-level `Limiter` let a second app overwrite the first app's default limits. Also, Flask-Limiter keeps only a weak reference, so a per-app limiter was garbage-collected mid-request. | One limiter per app, held on `app.extensions`. Routes declare limits with `@rate_limited(...)`. |
| QA-4 | **Local SeaweedFS ran out of volumes.** Each bucket reserves volumes, but the default is 8 slots of 30 GB. Auto-sizing (`-volume.max=0`) was tried and was worse: it divides free disk by 30 GB, so a laptop with 29 GB free got **one** slot and uploads to a second bucket failed with a 500. | Compose and CI run SeaweedFS with 1 GB volumes and 100 slots (`-master.volumeSizeLimitMB=1024 -volume.max=100`). Volumes are sparse, so this needs little disk. The image is pinned to 4.51, and tests share one bucket. |

## Found in CI

| # | Defect | Fix |
|---|---|---|
| QA-5 | **Unhandled rejection on a failed delete.** The error message showed, but the rejected promise escaped. Vitest flags that as an error, and an earlier local check read only the pass count, not the exit code. | Delete uses `mutate` with an `onSuccess` navigation; failures show only through the mutation's error state. Local verification now checks exit codes. |
| QA-6 | **Python version drift.** CI used the runner's Python 3.12. 3.13 renamed HTTP 422's phrase ("Unprocessable Entity" → "Unprocessable Content"), so the generated OpenAPI contract differed and the drift test failed. | `.python-version` pins 3.13 for uv everywhere: laptops, CI, and the Docker images (already 3.13). CI now annotates each failing test, so failures are readable without the raw log. |
| QA-7 | **SeaweedFS unreachable in CI.** `-ip=127.0.0.1` bound it to the container's own loopback, so the published port couldn't reach it. | CI uses the same flags as the compose file (no `-ip`). |

## Known limitations (accepted)

- **Stale pending images.** Abandoned uploads leave `pending` image rows and possibly orphaned objects. A sweeper lands with the Phase 2 scheduler.
- **HEIC display.** HEIC photos upload fine, but Chrome and Firefox can't display them. Conversion to JPEG belongs in the Phase 3 image pipeline. iOS Safari usually converts on upload anyway.
- **Shared catalog quality.** The catalog is crowd-built, so typos become catalog rows. A reference catalog is the long-term fix.

## Not verified here

There's no Docker daemon in this workspace, so the full compose stack and the browser flow against real Keycloak weren't run end to end. The manual smoke test in `docs/runbooks/local-development.md` (Phase 1 section) covers that.
