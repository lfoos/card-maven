import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { useAuth } from "react-oidc-context";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { useApi } from "../api/context";
import type { ApiClient } from "../api/client";
import { ApiError } from "../api/errors";
import { mockAuth } from "../test/mockAuth";
import { AuthCallbackPage } from "./AuthCallbackPage";
import { CollectionPage } from "./CollectionPage";
import { HomePage } from "./HomePage";
import { NotFoundPage } from "./NotFoundPage";
import { TrendsPage } from "./TrendsPage";

vi.mock("react-oidc-context", () => ({ useAuth: vi.fn() }));
vi.mock("../api/context", () => ({ useApi: vi.fn() }));

function withProviders(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

function apiReturning(result: Promise<unknown>): ApiClient {
  return { get: vi.fn(() => result) } as unknown as ApiClient;
}

describe("HomePage", () => {
  it("shows the API as online", async () => {
    vi.mocked(useApi).mockReturnValue(apiReturning(Promise.resolve({ status: "ok" })));
    withProviders(<HomePage />);
    expect(screen.getByTestId("api-status")).toHaveTextContent("Checking API");
    expect(await screen.findByText("API online")).toBeInTheDocument();
  });

  it("shows the API as unavailable", async () => {
    vi.mocked(useApi).mockReturnValue(
      apiReturning(Promise.reject(new ApiError(0, "network_error", "unreachable"))),
    );
    withProviders(<HomePage />);
    expect(await screen.findByText("API unavailable")).toBeInTheDocument();
  });
});

describe("static pages", () => {
  it("collection empty state", () => {
    withProviders(<CollectionPage />);
    expect(screen.getByRole("heading", { name: "Collection" })).toBeInTheDocument();
    expect(screen.getByText("No cards yet.")).toBeInTheDocument();
  });

  it("trends empty state", () => {
    withProviders(<TrendsPage />);
    expect(screen.getByRole("heading", { name: "Trends" })).toBeInTheDocument();
  });

  it("not found links home", () => {
    withProviders(<NotFoundPage />);
    expect(screen.getByRole("link", { name: /back to home/i })).toHaveAttribute("href", "/");
  });
});

describe("AuthCallbackPage", () => {
  it("shows progress", () => {
    vi.mocked(useAuth).mockReturnValue(mockAuth({ isLoading: true }));
    withProviders(<AuthCallbackPage />);
    expect(screen.getByText(/signing you in/i)).toBeInTheDocument();
  });

  it("shows errors", () => {
    vi.mocked(useAuth).mockReturnValue(mockAuth({ error: new Error("state mismatch") as never }));
    withProviders(<AuthCallbackPage />);
    expect(screen.getByRole("alert")).toHaveTextContent("state mismatch");
  });
});
