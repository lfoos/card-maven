/** Runtime configuration from Vite env vars, with defaults for the local stack. */
export interface AppConfig {
  apiBaseUrl: string;
  oidcAuthority: string;
  oidcClientId: string;
}

type Env = Partial<Record<keyof ImportMetaEnv, string | undefined>>;

function requireUrl(name: string, value: string): string {
  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") throw new Error("bad protocol");
  } catch {
    throw new Error(`${name} must be an absolute http(s) URL, got "${value}"`);
  }
  return value.replace(/\/+$/, "");
}

export function loadConfig(env: Env): AppConfig {
  const clientId = env.VITE_OIDC_CLIENT_ID?.trim() || "card-maven-web";
  return {
    apiBaseUrl: requireUrl("VITE_API_BASE_URL", env.VITE_API_BASE_URL || "http://localhost:8000"),
    oidcAuthority: requireUrl(
      "VITE_OIDC_AUTHORITY",
      env.VITE_OIDC_AUTHORITY || "http://localhost:8080/realms/card-maven",
    ),
    oidcClientId: clientId,
  };
}

export const config: AppConfig = loadConfig(import.meta.env);
