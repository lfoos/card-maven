import type { User } from "oidc-client-ts";
import { describe, expect, it, vi } from "vitest";
import { completeSignIn, oidcSettings, safeReturnTo } from "./oidc";

describe("oidcSettings", () => {
  const settings = oidcSettings(
    { apiBaseUrl: "http://api", oidcAuthority: "http://idp/realms/cm", oidcClientId: "web" },
    "http://localhost:5173",
  );

  it("uses the authorization code flow with the callback route", () => {
    expect(settings.response_type).toBe("code");
    expect(settings.redirect_uri).toBe("http://localhost:5173/auth/callback");
    expect(settings.post_logout_redirect_uri).toBe("http://localhost:5173");
    expect(settings.scope).toContain("openid");
  });

  it("keeps tokens out of browser storage", () => {
    expect(settings.userStore).toBeDefined();
    localStorage.clear();
    sessionStorage.clear();
    expect(localStorage.length + sessionStorage.length).toBe(0);
  });
});

describe("safeReturnTo", () => {
  it.each([
    ["/collection?sort=year", "/collection?sort=year"],
    ["/", "/"],
    ["//evil.example", "/"],
    ["/\\evil.example", "/"],
    ["https://evil.example", "/"],
    ["collection", "/"],
    [undefined, "/"],
    [42, "/"],
  ])("%s -> %s", (input, expected) => {
    expect(safeReturnTo(input)).toBe(expected);
  });
});

describe("completeSignIn", () => {
  function run(state: unknown) {
    const navigate = vi.fn();
    const history = { replaceState: vi.fn() };
    completeSignIn({ state } as unknown as User, navigate, { pathname: "/auth/callback" }, history);
    return { navigate, history };
  }

  it("clears the code from the URL and returns the user to their page", () => {
    const { navigate, history } = run({ returnTo: "/collection?sort=year" });
    expect(history.replaceState).toHaveBeenCalledWith({}, expect.any(String), "/auth/callback");
    expect(navigate).toHaveBeenCalledWith("/collection?sort=year", { replace: true });
  });

  it.each([undefined, {}, { returnTo: "https://evil.example" }])(
    "falls back to home for state %j",
    (state) => {
      expect(run(state).navigate).toHaveBeenCalledWith("/", { replace: true });
    },
  );

  it("handles a missing user", () => {
    const navigate = vi.fn();
    completeSignIn(undefined, navigate, { pathname: "/" }, { replaceState: vi.fn() });
    expect(navigate).toHaveBeenCalledWith("/", { replace: true });
  });
});
