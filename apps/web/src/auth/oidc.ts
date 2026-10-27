import {
  InMemoryWebStorage,
  WebStorageStateStore,
  type User,
  type UserManagerSettings,
} from "oidc-client-ts";
import type { AppConfig } from "../config";

/** Where to send the user after sign-in, carried through the OIDC `state`. */
export interface SignInState {
  returnTo: string;
}

/**
 * Authorization Code + PKCE (oidc-client-ts uses PKCE for the code flow).
 * Tokens are kept in memory only, never localStorage, so XSS can't lift them
 * from storage. A page reload re-authenticates silently via the IdP session.
 */
export function oidcSettings(config: AppConfig, origin: string): UserManagerSettings {
  return {
    authority: config.oidcAuthority,
    client_id: config.oidcClientId,
    redirect_uri: `${origin}/auth/callback`,
    post_logout_redirect_uri: origin,
    response_type: "code",
    scope: "openid profile email",
    automaticSilentRenew: true,
    userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
  };
}

/** Only same-origin paths are allowed as return targets (no open redirects). */
export function safeReturnTo(value: unknown): string {
  if (typeof value !== "string") return "/";
  if (!value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) return "/";
  return value;
}

/**
 * Runs after the IdP redirects back: strips `?code=&state=` from the URL, then
 * navigates to where the user was headed before sign-in.
 */
export function completeSignIn(
  user: User | undefined,
  navigate: (to: string, options: { replace: boolean }) => unknown,
  location: Pick<Location, "pathname"> = window.location,
  history: Pick<History, "replaceState"> = window.history,
): void {
  const returnTo = safeReturnTo((user?.state as Partial<SignInState> | undefined)?.returnTo);
  history.replaceState({}, document.title, location.pathname);
  void navigate(returnTo, { replace: true });
}
