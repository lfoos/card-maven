# 0002: Identity and collection (Phase 1): Planner

**Phase:** 1 · **Features enabled:** Feature 1. Collectors can store and display their collection: sport, year, brand, player, parallel, card name, team, grade, and estimated value (shown as "—" until Phase 2 supplies market data).

**Diagram impact:** none structural. The web → API → Postgres and web → object storage (presigned) paths in the container diagram become live. The component status table is updated.

## User stories

1. As a collector, I sign up or sign in, and Card Maven knows who I am on every request.
2. I add a card by typing its details. Set and player fields suggest values Card Maven already knows.
3. I see my collection as a grid or a table, filter it (sport, year, brand, condition, free text), sort it, and page through it.
4. I open a card, edit its details, or delete it.
5. I attach a front and a back photo to a card and see them on the detail page.
6. No one else can see, change, or detect my cards.

## API (`/api/v1`, JSON, OpenAPI 3.1 generated from code)

| Method | Path | Purpose |
|---|---|---|
| GET | `/me` | The signed-in user. Provisioned on first call. |
| GET | `/catalog/sets?q=&sport=&year=` | Set autocomplete |
| GET | `/catalog/players?q=&sport=` | Player autocomplete |
| GET | `/catalog/parallels?set_id=` | Parallels known for a set |
| GET | `/collection/items` | List the caller's items: filters, sort, cursor pagination |
| POST | `/collection/items` | Add an item (resolves or creates the catalog card and variant) |
| GET | `/collection/items/{id}` | Item detail with image URLs |
| PATCH | `/collection/items/{id}` | Edit the holding and, optionally, the card identity |
| DELETE | `/collection/items/{id}` | Delete the item and its images |
| POST | `/collection/items/{id}/images` | Start an upload: returns a presigned POST and a pending image id |
| POST | `/collection/items/{id}/images/{image_id}/complete` | Verify the uploaded object and make it the item's front or back photo |
| DELETE | `/collection/items/{id}/images/{image_id}` | Remove a photo |

**Request and response conventions**

- **Errors** are RFC 9457 problem+json. Request validation failures use `code: invalid_input` with an `errors` list of `{loc, message}`.
- **Money** in JSON is `{ "amount": "49.99", "currency": "USD" }`. Using a decimal string means JavaScript never sees a float.
- **Ownership.** Another user's item returns **404**, never 403, so ids reveal nothing about other users' data.
- **Paging.** Lists return `{ items, next_cursor }`. The cursor is an opaque keyset token, validated on every request, so paging is stable while items are added.

## Domain design

- **Identity.** `IdentityService.provision(principal)` upserts `app_user` by (issuer, subject) and refreshes email and display name. The `require_user()` decorator combines token verification with provisioning and exposes `current_user()`.
- **Owner scoping.** `OwnedRepository[T]` takes `owner_id` at construction. Every query goes through `_scoped()`, so a missing owner filter can't happen by accident. Isolation tests cover every endpoint.
- **Catalog resolution.** `CatalogService.resolve_variant(spec)` finds or creates, in order: brand, set, players, card, parallel ("Base" when none is given), and variant.
  - **Matching** is case- and whitespace-insensitive on natural keys. Sets match on (sport, brand, year, lower(name)). Cards match on (set, upper(card_number)). Parallels match on (set, subset, lower(name)).
  - **Create races.** Each create runs in a savepoint. On a unique-key race, the savepoint rolls back and the code re-reads the winner. Two collectors adding the same new card at once end up with one catalog row.
  - **Shared catalog.** The catalog is shared and crowd-built (`catalog_source = user_confirmed`). When a card already exists for (set, number), the existing record wins and the response shows the canonical values. This is a known v1 limitation that the future reference catalog resolves.
  - **Unknown values.** An unknown brand is created (slugged), because collectors own brands beyond our seed list. An unknown sport is rejected, since sports are a closed list.
- **Validation (Pydantic).**
  - **Grades.** A graded item requires a grader and a grade. Grades run 1–10 in steps of 0.5. A raw item may not carry grade fields.
  - **Serial number and dates.** The serial number must not exceed the parallel's print run. `acquired_on` can't be in the future. Text fields are trimmed and length-capped.
- **Images.**
  - **Upload flow.** The upload endpoint creates a `pending` image row. It returns an S3 **presigned POST** whose policy pins the exact key, `Content-Type`, and a `content-length-range` (max 15 MB, JPEG/PNG/WebP/HEIC only). The browser uploads directly to storage.
  - **Completion checks.** The completion endpoint checks the object exists and that size and type match. It reads the first bytes to confirm the file signature, so a renamed file is rejected. It then marks the image `ready` and retires any previous front or back for that item.
  - **Keys** are `users/{owner_id}/items/{item_id}/{image_id}`, server-generated so clients never choose paths.
  - **Downloads** are presigned GET URLs that expire after 10 minutes.
  - **Deletes.** Deleting an item or image removes its objects after the database commit. If storage is unavailable, the orphan is logged; a sweeper job comes with Phase 2's scheduler.
- **ObjectStore port** (`presign_upload`, `head`, `read_prefix`, `presign_download`, `delete`). The S3 adapter uses boto3 and works against AWS S3 and SeaweedFS. An in-memory fake is used in unit tests.

## Schema changes (migration 0002)

| Change | Why |
|---|---|
| `image.status` (`pending`/`ready`), `image.uploaded_at` | Upload lifecycle |
| Partial unique index `(collection_item_id, kind) WHERE status='ready' AND kind IN ('front','back')` | At most one live front and one live back per item |
| Case-insensitive unique indexes: `card_set (sport, brand, year, lower(name))`, `parallel (set, coalesce(subset,''), lower(name))`, `card (set, upper(card_number))`, replacing the exact-match constraints | "Bowman Chrome" and "bowman chrome" are one set |
| `pg_trgm` extension + trigram GIN indexes on `card.name`, `player.full_name`, `card_set.name` | Fast `ILIKE` autocomplete and free-text search |
| Index `(owner_id, created_at DESC, id DESC)` on `collection_item` | The default list sort and its keyset pagination |

## Cross-cutting

- **OpenAPI.** Adopt `flask-openapi3`, which is Pydantic v2-native. Routes declare request and response models, and the spec is generated from them. `card-maven-api export-openapi` writes `contracts/openapi.json`, and CI fails if it drifts from the code.
- **Rate limiting.** Flask-Limiter, keyed by user (or by IP when anonymous):
  - 300/min by default
  - 30/min to start uploads
  - 20/min for writes per item

  Storage is in-memory locally and configured through `CARD_MAVEN_RATE_LIMIT_STORAGE_URI`. Multi-replica deployments need Redis/ElastiCache, which lands in Phase 6.
- **Local storage bootstrap.** A `card-maven init-storage` command creates the bucket and applies CORS for the web origin. It is idempotent, and `make bootstrap` runs it.
- **Prerequisite check.** `make doctor` checks Docker, uv, Node 22, and pnpm, and prints install hints. `make bootstrap` runs it first.

## Web

- **Routes:**
  - `/collection`: grid or table toggle, filters in the URL query (shareable), and "Load more" via `useInfiniteQuery`
  - `/collection/new` and `/collection/:id/edit`: one `CardForm` with debounced autocomplete for set and player
  - `/collection/:id`: detail, photos, edit, delete
- **Photo upload.** Pick a file, compute its SHA-256 in the browser, request the upload, POST it to storage, then complete. Progress and errors show inline.
- **API errors** map onto form fields using the problem+json `errors[].loc`.

## Test plan

- **Domain.**
  - Catalog resolution: create, reuse, case and whitespace variants, a concurrent create race, Base parallel defaulting, an unknown sport, a new brand.
  - Provisioning: first login, a profile change, the same subject from a different issuer.
  - Validation: every rule above.
- **Repository.**
  - Owner scoping on get, list, update, and delete.
  - Keyset pagination for every sort: no gaps or duplicates while rows are inserted between pages, and a malformed cursor is rejected.
- **API.**
  - Every endpoint: happy path, 401 without a token, 404 for another user's item, and 422 problem+json with field locations.
  - Rate limit returns 429 with `Retry-After`.
  - The OpenAPI spec matches `contracts/openapi.json`.
- **Storage.**
  - The S3 adapter against moto (unit tests) **and against a real SeaweedFS** (verified locally).
  - The policy rejects the wrong content type, a file that's too large, and the wrong key.
  - Completion rejects a missing object, a size mismatch, a bad file signature, and another user's image.
- **Web.** The list with filters, sorting, and paging; form validation and server errors; the upload state machine; delete confirmation; empty, loading, and error states.
