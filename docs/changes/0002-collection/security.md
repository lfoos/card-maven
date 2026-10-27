# 0002: Identity and collection: Security review

**Verdict: no blocking findings.**

## Threats considered and mitigations

| Threat | Mitigation | Verified by |
|---|---|---|
| **IDOR.** Reading or editing another collector's cards or photos. | All owned queries go through `OwnedRepository._scoped()`. Images are additionally matched to their item. Others' rows return **404** (no existence oracle). | Isolation tests cover every endpoint. |
| **Malicious upload.** HTML/SVG posing as an image, oversized files, path traversal. | Server-chosen keys. A presigned POST policy pins key, `Content-Type`, and exact `content-length-range`. Completion re-checks size and type, the file signature, and SHA-256; failures delete the object. Only verified images are ever linked. | Policy enforcement tested against real SeaweedFS. Signature and checksum tests. |
| **Stored XSS via photos.** | Only verified JPEG/PNG/WebP/HEIC bytes go live, and the bucket is private. Downloads use 10-minute presigned URLs on a separate origin from the app. | Signature tests. |
| **Brute force and scraping.** | Rate limits per user (or IP when anonymous): 300/min by default, 60/min on writes, 30/min to start uploads. `X-Forwarded-For` is trusted only for the configured proxy count. | Rate-limit tests, including a spoofed header. |
| **Mass assignment.** | Every request model is `extra="forbid"`. Owner, ids, and timestamps are never client-settable. | Unknown-field tests. |
| **SQL wildcard / ILIKE injection.** | Queries are parameterized, and `%`, `_`, and `\` are escaped in search patterns. | `like_pattern` tests. |
| **Leaking local credentials into deployments.** | Settings refuse the local S3 endpoint and keys in `dev` and `prod`, so AWS uses the IAM role. `init-storage` refuses to run in deployed environments. | Config guard tests. |
| **Token misuse.** | Tokens are verified once per request; failures are kept and raised only on protected routes. Rate limits key on *verified* identities only, so an attacker can't burn another user's quota with a forged `sub`. | Auth and rate-limit tests. |

## Accepted risks and follow-ups

1. **EXIF metadata (Phase 3).** Card photos may carry GPS and other EXIF data. Photos are private to their owner today. Strip metadata in the Phase 3 image pipeline, before any sharing feature exists.
2. **Shared rate-limit storage (Phase 6).** The default `memory://` storage is per process. Multi-replica deployments must set `CARD_MAVEN_RATE_LIMIT_STORAGE_URI` to Redis/ElastiCache.
3. **Catalog spam.** Any collector can add catalog rows. Rate limits bound the volume. Moderation and reference-catalog precedence come later.
4. **Abandoned uploads (Phase 2).** Pending images and orphaned objects are swept by a scheduled job that arrives with Phase 2's scheduler. Until then they consume only storage.
5. **Carried over from 0001:** web CSP (Phase 6) and SHA-pinned Actions (before Phase 6).
