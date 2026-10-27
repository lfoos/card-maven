import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { createMemoryRouter, RouterProvider, type RouteObject } from "react-router";
import { vi } from "vitest";
import type { ApiClient } from "../api/client";
import { ApiContext } from "../api/context";

type Handler = (path: string, options?: { method?: string; body?: unknown }) => unknown;

/** A stand-in ApiClient: every call goes to `handler`, and is recorded. */
export function fakeClient(handler: Handler) {
  const request = vi.fn((path: string, options?: { method?: string; body?: unknown }) =>
    Promise.resolve().then(() => handler(path, options)),
  );
  const get = vi.fn((path: string) => request(path, { method: "GET" }));
  return { client: { request, get } as unknown as ApiClient, request };
}

export function renderWithApi(
  client: ApiClient,
  options: { routes?: RouteObject[]; path?: string; element?: ReactNode } = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const routes = options.routes ?? [{ path: "*", element: options.element }];
  const router = createMemoryRouter(routes, { initialEntries: [options.path ?? "/"] });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <ApiContext.Provider value={client}>
        <RouterProvider router={router} />
      </ApiContext.Provider>
    </QueryClientProvider>,
  );
  return { ...view, router, queryClient };
}
