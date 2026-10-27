import { describe, expect, it } from "vitest";
import { loadConfig } from "./config";

describe("loadConfig", () => {
  it("defaults to the local stack", () => {
    expect(loadConfig({})).toEqual({
      apiBaseUrl: "http://localhost:8000",
      oidcAuthority: "http://localhost:8080/realms/card-maven",
      oidcClientId: "card-maven-web",
    });
  });

  it("uses provided values and strips trailing slashes", () => {
    const config = loadConfig({
      VITE_API_BASE_URL: "https://api.cardmaven.app/",
      VITE_OIDC_AUTHORITY: "https://auth.cardmaven.app//",
      VITE_OIDC_CLIENT_ID: " web ",
    });
    expect(config).toEqual({
      apiBaseUrl: "https://api.cardmaven.app",
      oidcAuthority: "https://auth.cardmaven.app",
      oidcClientId: "web",
    });
  });

  it.each(["not a url", "ftp://files.example", "/relative"])("rejects %s", (value) => {
    expect(() => loadConfig({ VITE_API_BASE_URL: value })).toThrow(/VITE_API_BASE_URL/);
  });
});
