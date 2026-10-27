# Card Maven API

The API is described by an OpenAPI 3.1 contract, [`contracts/openapi.json`](../../contracts/openapi.json). It is generated from the code (`make openapi`), checked in, and verified in CI, so it is always current. A running API also serves it at `GET /api/v1/openapi.json`. Load either into Swagger UI, Postman, or Insomnia to browse and try endpoints.

## Basics

| | |
|---|---|
| Base path | `/api/v1` |
| Format | JSON in and out |
| Auth | `Authorization: Bearer <access token>` from the identity provider (see [auth design](../architecture/auth.md)). Every `/api/v1` route requires it. |
| Errors | [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) `application/problem+json` (below) |
| Tracing | Send `X-Request-ID` to correlate logs; every response echoes it |

## Conventions

- **Money** is `{ "amount": "49.99", "currency": "USD" }`. The amount is a decimal **string**, never a JSON number, so no precision is lost. Sending a number is rejected.
- **Grades** are decimal strings in steps of 0.5 (`"9.5"`, `"10.0"`).
- **Ids** are UUIDs. Another collector's ids behave exactly like ids that don't exist (`404`).
- **Partial updates.** `PATCH` changes only the fields present in the body. Send `null` to clear a field. The merged result is re-validated (for example, switching a card to `raw` while it still has a grade is rejected).
- **Paging.** List endpoints return `{ "items": [...], "next_cursor": "..." }`. Pass `next_cursor` back as `cursor` to get the next page. It is `null` on the last page. Cursors are opaque and tied to the sort order; pages stay stable while cards are added.

## Errors

```json
{
  "type": "https://cardmaven.app/problems/invalid_input",
  "title": "Invalid input",
  "status": 422,
  "code": "invalid_input",
  "detail": "graded cards need a grader and a grade",
  "request_id": "web-6f1c…",
  "errors": [{ "loc": "card.year", "message": "Input should be greater than or equal to 1860" }]
}
```

| Status | `code` | When |
|---|---|---|
| 401 | `unauthenticated` | Missing, invalid, or expired token |
| 403 | `permission_denied` | Valid token without the required role |
| 404 | `not_found` | No such resource, or it belongs to someone else |
| 409 | `conflict` | The request clashes with current state (e.g. completing an upload before the file arrived) |
| 413 | `request_entity_too_large` | Body over 1 MB |
| 422 | `invalid_input` | Validation failed. `errors[].loc` is the dotted path to each bad field (`body` = the request as a whole) |
| 429 | `too_many_requests` | Rate limit exceeded. Wait `Retry-After` seconds |
| 503 | `dependency_unavailable` | Database, storage, or identity provider unreachable. Safe to retry |

## Rate limits

Limits apply per signed-in user (or per IP when anonymous). Every response carries `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset`.

| Scope | Limit |
|---|---|
| Default | 300 / minute |
| Creating, editing, deleting cards and photos | 60 / minute |
| Starting a photo upload | 30 / minute |

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/me` | The signed-in collector (created on first call) |
| GET | `/catalog/sets?q=&sport=&year=` | Set suggestions |
| GET | `/catalog/players?q=&sport=` | Player suggestions |
| GET | `/catalog/parallels?set_id=` | Parallels known for a set |
| GET | `/collection/items` | List your cards (`q`, `sport`, `year`, `brand`, `condition`, `sort`, `cursor`, `limit`) |
| POST | `/collection/items` | Add a card |
| GET | `/collection/items/{id}` | One card |
| PATCH | `/collection/items/{id}` | Edit a card |
| DELETE | `/collection/items/{id}` | Delete a card and its photos |
| POST | `/collection/items/{id}/images` | Start a photo upload |
| POST | `/collection/items/{id}/images/{image_id}/complete` | Finish a photo upload |
| DELETE | `/collection/items/{id}/images/{image_id}` | Remove a photo |

`sort` is one of `newest` (default), `oldest`, `year_desc`, `year_asc`, `name`.

## Adding a card

```http
POST /api/v1/collection/items
Content-Type: application/json
Authorization: Bearer eyJ…

{
  "card": {
    "sport": "baseball",
    "brand": "Bowman",
    "year": 2025,
    "set_name": "Bowman Chrome",
    "card_number": "CPA-JW",
    "name": "JJ Wetherholt",
    "players": ["JJ Wetherholt"],
    "team": "Cardinals",
    "subset": "Chrome Prospect Autographs",
    "parallel": { "name": "Gold Refractor", "print_run": 50 },
    "is_autograph": true
  },
  "condition": "graded",
  "grader": "PSA",
  "grade": "10",
  "serial_number": 12,
  "purchase_price": { "amount": "250.00", "currency": "USD" }
}
```

The `card` block describes what the card *is*. Card Maven finds it in the shared catalog, matching case- and spacing-insensitively, or adds it. Omit `parallel` for a base card. If the card already exists, the catalog's stored details (name, team, flags) are kept, and the response shows them.

## Uploading a photo

Photos go straight from the client to object storage. The API never sees the bytes.

1. **Start.** `POST /collection/items/{id}/images` with the file's details:
   ```json
   { "kind": "front", "content_type": "image/jpeg", "byte_size": 482113, "sha256": "9f86d0…" }
   ```
   Accepted types are `image/jpeg`, `image/png`, `image/webp`, and `image/heic`, up to 15 MB. The response contains `image_id` and a presigned POST (`upload.url` plus `upload.fields`), valid for 15 minutes.
2. **Upload.** `POST` to `upload.url` as `multipart/form-data`. Send every entry of `upload.fields` first, then the file as `file`. Storage rejects anything that doesn't match the declared type and size.
3. **Complete.** `POST /collection/items/{id}/images/{image_id}/complete`. The API checks the stored file's size, type, signature, and SHA-256, then makes it the card's front or back photo, replacing the previous one. A `409` here means the file hasn't arrived yet, or another upload of the same side finished first; retry. A `422` means the file failed verification, and it has been discarded; start over.

Photo URLs in responses (`images.front.url`) are short-lived presigned links (10 minutes). Re-fetch the card to get fresh ones.
