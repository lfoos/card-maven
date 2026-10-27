import { useMemo, type ReactNode } from "react";
import { useAuth } from "react-oidc-context";
import { config } from "../config";
import { ApiClient } from "./client";
import { ApiContext } from "./context";

/** Provides an ApiClient bound to the current access token (rebuilt when it renews). */
export function ApiProvider({ children }: { children: ReactNode }) {
  const token = useAuth().user?.access_token;
  const client = useMemo(() => new ApiClient(config.apiBaseUrl, () => token), [token]);
  return <ApiContext.Provider value={client}>{children}</ApiContext.Provider>;
}
