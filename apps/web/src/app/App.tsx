import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { AuthProvider } from "react-oidc-context";
import { createBrowserRouter, RouterProvider } from "react-router";
import { ApiProvider } from "../api/ApiProvider";
import { completeSignIn, oidcSettings } from "../auth/oidc";
import { config } from "../config";
import { routes } from "./routes";

const router = createBrowserRouter(routes);

const onSigninCallback = (user: Parameters<typeof completeSignIn>[0]) =>
  completeSignIn(user, (to, options) => router.navigate(to, options));

export function App() {
  const [queryClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { staleTime: 30_000 } } }),
  );
  return (
    <AuthProvider
      {...oidcSettings(config, window.location.origin)}
      onSigninCallback={onSigninCallback}
    >
      <QueryClientProvider client={queryClient}>
        <ApiProvider>
          <RouterProvider router={router} />
        </ApiProvider>
      </QueryClientProvider>
    </AuthProvider>
  );
}
