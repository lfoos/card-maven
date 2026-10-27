# 0004. OIDC with an external identity provider

**Status:** Accepted · **Date:** 2026-10-26

## Context
The product must be multi-tenant from day one and follow industry-standard account security: signup, verification, MFA, recovery, and lockout.

## Decision
- **The browser authenticates with OIDC Authorization Code + PKCE** against an external identity provider: Keycloak locally, Cognito on AWS.
- **The API verifies access-token JWTs** against the provider's JWKS (issuer, audience, expiry; RS256/ES256 only).
- **Users are provisioned on first login**, keyed by `(issuer, subject)`.

Details: [auth.md](../architecture/auth.md).

## Consequences
- Card Maven never stores passwords.
- Switching providers is configuration only.
- The API is stateless.
- Local development needs a Keycloak container. Token claims differ slightly between providers; roles are normalized in `extract_roles`.

## Alternatives considered
- **Hand-rolled auth:** high risk, low value.
- **Server-side sessions:** stateful, and harder to share with workers and future clients.
