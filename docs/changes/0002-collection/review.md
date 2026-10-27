# 0002: Identity and collection: Architecture review

**Verdict: approved after loop-backs.**

## Loop-backs

| # | Sent to | Finding | Resolution |
|---|---|---|---|
| R-1 | Implementer | `catalog` imported `brand_slug` from `market.tracked_sets`, so catalog depended on market. Dependencies should point toward the more stable context. | Moved slugging to `shared.text.slugify`. Both contexts use it. |
| R-2 | Implementer | The rate limiter was a module-level singleton configured per app (see QA-3), so configuration leaked across app instances. | Per-app limiter with declarative `@rate_limited` route markers. |
| R-3 | Implementer | `_services(session: object)` needed `type: ignore`s. | Typed as `Session`. |
| R-4 | Planner | The plan promised a "signed" cursor. Signing adds a secret to manage for no security gain: queries are owner-scoped, so a forged cursor only re-pages the caller's own data. | The plan now says "opaque, validated". |
| R-5 | Implementer | OpenAPI documented flask-openapi3's default 422 model rather than our problem shape. | `validation_error_model=ValidationProblemOut`, so the spec matches the responses. |

## Checked and accepted

- **Layering.**
  - Routes are thin: parse, call one service, present.
  - Services hold the business rules.
  - Repositories own queries. `OwnedRepository._scoped()` is the only way to build an owned query, which makes isolation structural rather than a per-endpoint habit.
- **Catalog design.**
  - Expression unique indexes give case-insensitive natural keys.
  - `get_or_create` with a savepoint handles races without locks.
  - Base parallels and subset-scoped parallels match how products are printed.
  - The `catalog_source` column leaves room for a reference catalog.
- **Upload design.**
  - Browser-to-storage presigned POST, with the policy pinning the key, type, and exact size.
  - Server-side verification of size, type, signature, and SHA-256 before an image goes live.
  - Object deletes run after commit, with logged orphans.
- **Contract-first front end.** The OpenAPI spec is generated from Pydantic models, checked in, and drift-tested. The web app's TypeScript types are generated from it, so a backend change that breaks the front end fails CI.
- **Pagination.** Keyset pagination with a total order (primary key last) for every sort, and an index matching the default sort.

## Accepted for later

- **Per-request auth transaction.** `require_user` commits a small provisioning transaction on every authenticated request. It's a no-op write unless the profile changed. If it shows up in profiling, cache by token `jti`/expiry.
- **Presigned URLs per page.** List responses presign two URLs per item. Signing is local HMAC (no network), so it's fine at 100 items per page. Revisit with a CDN in Phase 6.
- **The `ItemOut` presenter** is hand-mapped. That keeps domain models free of API concerns, at the cost of a little boilerplate.
