import { useAuth } from "react-oidc-context";

/** The IdP redirects here; AuthProvider completes the code exchange. */
export function AuthCallbackPage() {
  const auth = useAuth();
  if (auth.error) {
    return (
      <div role="alert" className="notice notice--error">
        <h2>Sign-in failed</h2>
        <p>{auth.error.message}</p>
      </div>
    );
  }
  return (
    <p className="muted" aria-live="polite">
      Signing you in…
    </p>
  );
}
