# 0001: Foundation: Security review

**Verdict: no blocking findings.** Three issues were fixed before release. Two follow-ups are tracked for later phases.

## Fixed in this change

| # | Finding | Fix |
|---|---|---|
| S-1 | Settings defaults (local DB password, `http://` IdP URLs) could silently reach a deployed environment. | `Settings` rejects the local database URL and non-HTTPS issuer and JWKS URLs when `environment` is `dev` or `prod`. The service fails at startup, not in production. |
| S-2 | Nothing prevented a wildcard CORS origin. | `cors_origins` containing `*` is rejected in every environment. CORS never allows credentials. |
| S-3 | No automated dependency update path. | Added Dependabot for uv, npm, Actions, Docker, and Terraform. CI runs `pip-audit --strict` and `pnpm audit --prod --audit-level high`. Both are clean today. |

## Reviewed and accepted

- **Authentication.**
  - OIDC with Authorization Code + PKCE. Card Maven never handles passwords.
  - The API accepts only RS256 and ES256 (no `none`, no HMAC).
  - It requires `exp`, `iat`, `iss`, and `sub`, and checks `aud` and `iss`.
  - The JWKS is cached and refetched on key rotation.
  - A JWKS outage returns 503, never "allow".
- **Tokens in the browser.** Kept in memory only, never localStorage or sessionStorage. The post-login return path is restricted to same-origin paths, which closes open-redirect attempts.
- **Error handling.** 5xx responses return a generic title only. Internals are logged with the request id, never sent to clients.
- **HTTP hardening.**
  - Strict security headers: `default-src 'none'` CSP (the API serves JSON only), `nosniff`, `DENY` framing, `no-store`.
  - HSTS in production.
  - A 1 MB request cap.
  - Caller request ids are validated before they are logged or echoed, preventing log and header injection.
- **Data isolation.** Every user-owned table has a non-null, indexed `owner_id` with cascade delete. Scoped repositories and isolation tests arrive with the first user-facing endpoints in Phase 1.
- **Containers.**
  - Non-root (UID 10001), read-only root filesystem, all capabilities dropped, `RuntimeDefault` seccomp.
  - Service account tokens are not mounted.
  - Database credentials come only from a Kubernetes Secret, never from chart values.
- **Infrastructure.**
  - Media bucket: fully private, KMS encryption, TLS-only bucket policy, explicit CORS origins (validated against wildcards).
  - ECR: immutable tags, scan on push.
  - VPC: workloads in private subnets, an S3 gateway endpoint.
- **Committed credentials.** The only committed credentials are for the local Docker stack: the Keycloak demo user and SeaweedFS local keys. They are labeled local-only and unreachable outside a developer laptop. `detect-private-key` runs in pre-commit.
- **CI.** The workflow token is read-only (`contents: read`).

## Follow-ups (tracked, not blocking)

1. **Web CSP (Phase 6).** The nginx config sets basic headers but no Content-Security-Policy, because `connect-src` depends on per-environment API and IdP origins. Template it from Helm values when the web app is deployed.
2. **Action pinning (before Phase 6).** Pin third-party GitHub Actions by commit SHA.
3. **Rate limiting (Phase 1).** Per-user and per-IP limits ship with the first authenticated endpoints, as planned.
