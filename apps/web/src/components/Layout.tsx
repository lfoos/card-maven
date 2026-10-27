import { useAuth } from "react-oidc-context";
import { NavLink, Outlet } from "react-router";

const NAV_ITEMS = [
  { to: "/collection", label: "Collection" },
  { to: "/trends", label: "Trends" },
] as const;

export function Layout() {
  const auth = useAuth();
  const name = auth.user?.profile.name ?? auth.user?.profile.preferred_username;

  return (
    <div className="shell">
      <header className="shell__header">
        <NavLink to="/" className="brand" aria-label="Card Maven home">
          <span className="brand__mark" aria-hidden="true" />
          Card Maven
        </NavLink>
        <nav aria-label="Main">
          <ul className="nav">
            {NAV_ITEMS.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  className={({ isActive }) =>
                    isActive ? "nav__link nav__link--active" : "nav__link"
                  }
                >
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="shell__account">
          {auth.isAuthenticated ? (
            <>
              {name ? <span className="muted">{name}</span> : null}
              <button
                type="button"
                className="button button--quiet"
                onClick={() => void auth.signoutRedirect()}
              >
                Sign out
              </button>
            </>
          ) : (
            <button
              type="button"
              className="button"
              onClick={() => void auth.signinRedirect()}
              disabled={auth.isLoading}
            >
              Sign in
            </button>
          )}
        </div>
      </header>
      <main className="shell__main" id="main">
        <Outlet />
      </main>
    </div>
  );
}
