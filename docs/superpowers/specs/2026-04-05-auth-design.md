# User Authentication Design — Card Maven

**Date:** 2026-04-05
**Scope:** Multi-user support with self-registration, username/password login, and logout
**Stack:** Flask-Login, Flask-WTF (CSRF-only), Werkzeug password hashing, server-side sessions

---

## Overview

Card Maven transitions from a single shared collection to per-user isolated collections. Each registered user sees only their own cards, price history, and listings. Authentication uses server-side session cookies managed by Flask-Login. CSRF protection is provided by Flask-WTF in token-only mode (no WTForms form objects). OAuth support is intentionally out of scope but designed for easy addition later.

---

## Architecture

- **Flask-Login** manages session cookies and the `current_user` proxy. All `/api/*` routes are protected with `@login_required`, returning `401 {"error": "login required"}` for unauthenticated requests.
- **Flask-WTF** provides CSRF token generation and validation via `generate_csrf()` and `validate_csrf()`. The JS fetches a token from `GET /auth/csrf` on login and includes it as an `X-CSRFToken` header on all `POST`, `PUT`, and `DELETE` requests.
- **Werkzeug** (already installed) handles password hashing — `generate_password_hash` / `check_password_hash`. No additional crypto dependency.
- All Card queries gain `.filter_by(user_id=current_user.uuid)` to enforce per-user data isolation.

---

## Data Model

### New: `User`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `uuid` | String(36) | PK | UUID4 generated with `str(uuid.uuid4())` on creation |
| `username` | String(80) | unique, not null | Used for login |
| `email` | String(200) | unique, nullable | Optional at registration |
| `password_hash` | String(256) | not null | Werkzeug hashed |
| `created_at` | DateTime | default=utcnow | |
| `updated_at` | DateTime | default=utcnow, onupdate=utcnow | Auto-updated on any column change |

Flask-Login requires a `get_id()` method — it returns `self.uuid`.

`User` → `Card` relationship: `cascade="all, delete-orphan"` so deleting a user removes all their cards and transitively their price records and listings.

### Modified: `Card`

Add column:

| Column | Type | Constraints |
|--------|------|-------------|
| `user_id` | String(36) | FK → `users.uuid`, not null |

`PriceRecord` and `EbayListing` are untouched — they already cascade through `Card`.

### Migration

There is no existing production data to preserve. Drop and recreate the SQLite database on first run after this change. If orphan cards exist in a future migration scenario, assign them to a designated admin user via a one-time script.

---

## Auth Routes

All auth routes return JSON. Errors use the format `{"error": "message"}`.

| Method | Route | Auth required | CSRF required | Description |
|--------|-------|:---:|:---:|-------------|
| `GET` | `/auth/csrf` | No | No | Returns `{"csrf_token": "..."}` for the JS to store |
| `POST` | `/auth/register` | No | Yes | Creates account and logs user in. Body: `{username, password, email?}` |
| `POST` | `/auth/login` | No | Yes | Verifies credentials, sets session. Body: `{username, password}` |
| `POST` | `/auth/logout` | Yes | Yes | Clears session |
| `GET` | `/auth/me` | Yes | No | Returns `{uuid, username, email}` for the current user |

### Validation Rules

- `username`: required, 3–80 chars, alphanumeric + underscores only, must be unique
- `password`: required, minimum 8 characters
- `email`: optional; if provided, must be valid format and unique

### Response Examples

**POST /auth/register — success:**
```json
{"uuid": "...", "username": "logan", "email": null}
```

**POST /auth/login — failure:**
```json
{"error": "Invalid username or password"}
```

**GET /auth/me — unauthenticated:**
```json
HTTP 401
{"error": "login required"}
```

---

## Configuration

Two new keys added to `app.config` (read from `config.json`, with fallback defaults for local dev):

| Key | Purpose | Dev default |
|-----|---------|-------------|
| `SECRET_KEY` | Signs session cookies and CSRF tokens | `"dev-secret-change-in-production"` |
| `WTF_CSRF_TIME_LIMIT` | CSRF token expiry | `None` (no expiry — token lives for the session) |

`config.json` gains an optional `secret_key` field. The README documents that this must be set to a strong random value in any non-local deployment.

---

## Frontend Changes

### Auth Overlay

- On `DOMContentLoaded`, the app calls `GET /auth/me` before rendering anything. If it returns `401`, a full-screen auth overlay is shown instead of the main app.
- The overlay contains two tabs: **Log In** and **Register**, built with the existing modal/form styling.
- On successful login or registration, the overlay is hidden and `loadDashboard()` runs normally.

### CSRF Handling

- On successful login/register, the JS calls `GET /auth/csrf` and stores the token in a module-level variable (`let csrfToken = null`).
- The existing `api()` utility function is updated to include `X-CSRFToken: csrfToken` on all `POST`, `PUT`, and `DELETE` requests.

### 401 Handling

- If any `api()` call returns `401`, the auth overlay is shown instead of a generic error toast.

### Logout

- A **Log Out** button is added to the sidebar bottom (above the existing "Add Card" button).
- It POSTs to `/auth/logout` with the CSRF token, then calls `window.location.reload()`.

---

## Dependencies

Add to `requirements.txt`:

```
flask-login>=0.6.0
flask-wtf>=1.2.0
```

---

## Out of Scope

- OAuth / "Sign in with Google" (designed for easy addition later — User model has no OAuth-specific columns that would conflict)
- Email verification
- Password reset / forgot password flow
- Admin user management UI
- Rate limiting on login attempts
