import { useEffect, type ReactNode } from "react";
import { useAuth } from "react-oidc-context";
import { useLocation } from "react-router";
import type { SignInState } from "./oidc";

/** Renders children only for signed-in users; otherwise starts sign-in. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const location = useLocation();
  const shouldSignIn =
    !auth.isLoading && !auth.isAuthenticated && !auth.activeNavigator && !auth.error;

  useEffect(() => {
    if (shouldSignIn) {
      const state: SignInState = { returnTo: `${location.pathname}${location.search}` };
      void auth.signinRedirect({ state });
    }
  }, [shouldSignIn, auth, location.pathname, location.search]);

  if (auth.error) {
    return (
      <div role="alert" className="notice notice--error">
        <h2>Sign-in failed</h2>
        <p>{auth.error.message}</p>
        <button type="button" className="button" onClick={() => void auth.signinRedirect()}>
          Try again
        </button>
      </div>
    );
  }
  if (!auth.isAuthenticated) {
    return (
      <p className="muted" aria-live="polite">
        Redirecting to sign in…
      </p>
    );
  }
  return <>{children}</>;
}
