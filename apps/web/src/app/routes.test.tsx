import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { useAuth } from "react-oidc-context";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { useApi } from "../api/context";
import type { ApiClient } from "../api/client";
import { mockAuth } from "../test/mockAuth";
import { routes } from "./routes";

vi.mock("react-oidc-context", () => ({ useAuth: vi.fn() }));
vi.mock("../api/context", () => ({ useApi: vi.fn() }));

function renderAt(path: string) {
  vi.mocked(useApi).mockReturnValue({
    get: vi.fn(() => Promise.resolve({ status: "ok" })),
  } as unknown as ApiClient);
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("routes", () => {
  it.each([
    ["/", /priced by the market/i],
    ["/trends", /^Trends$/],
    ["/somewhere/else", /page not found/i],
  ])("%s renders publicly", (path, heading) => {
    vi.mocked(useAuth).mockReturnValue(mockAuth());
    renderAt(path);
    expect(screen.getByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
  });

  it("protects the collection", () => {
    const auth = mockAuth();
    vi.mocked(useAuth).mockReturnValue(auth);
    renderAt("/collection");
    expect(screen.queryByRole("heading", { name: "Collection" })).not.toBeInTheDocument();
    expect(auth.signinRedirect).toHaveBeenCalled();
  });

  it("shows the collection when signed in", () => {
    vi.mocked(useAuth).mockReturnValue(mockAuth({ isAuthenticated: true }));
    renderAt("/collection");
    expect(screen.getByRole("heading", { name: "Collection" })).toBeInTheDocument();
  });
});
