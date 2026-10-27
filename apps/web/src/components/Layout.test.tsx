import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { User } from "oidc-client-ts";
import { useAuth } from "react-oidc-context";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { mockAuth } from "../test/mockAuth";
import { Layout } from "./Layout";

vi.mock("react-oidc-context", () => ({ useAuth: vi.fn() }));
const mockedUseAuth = vi.mocked(useAuth);

function renderLayout(path = "/") {
  const router = createMemoryRouter(
    [{ path: "/", element: <Layout />, children: [{ path: "*", element: <p>page body</p> }] }],
    { initialEntries: [path] },
  );
  return render(<RouterProvider router={router} />);
}

describe("Layout", () => {
  it("renders navigation and marks the active link", () => {
    mockedUseAuth.mockReturnValue(mockAuth());
    renderLayout("/trends");
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Trends" })).toHaveClass("nav__link--active");
    expect(screen.getByRole("link", { name: "Collection" })).not.toHaveClass("nav__link--active");
    expect(screen.getByText("page body")).toBeInTheDocument();
  });

  it("offers sign in when signed out", async () => {
    const auth = mockAuth();
    mockedUseAuth.mockReturnValue(auth);
    renderLayout();
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(auth.signinRedirect).toHaveBeenCalled();
  });

  it("disables sign in while auth initializes", () => {
    mockedUseAuth.mockReturnValue(mockAuth({ isLoading: true }));
    renderLayout();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeDisabled();
  });

  it("shows the user's name and signs out", async () => {
    const auth = mockAuth({
      isAuthenticated: true,
      user: { profile: { name: "Logan", sub: "1" } } as unknown as User,
    });
    mockedUseAuth.mockReturnValue(auth);
    renderLayout();
    expect(screen.getByText("Logan")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(auth.signoutRedirect).toHaveBeenCalled();
  });

  it("falls back to the username, or nothing", () => {
    mockedUseAuth.mockReturnValue(
      mockAuth({
        isAuthenticated: true,
        user: { profile: { preferred_username: "lfoos" } } as unknown as User,
      }),
    );
    renderLayout();
    expect(screen.getByText("lfoos")).toBeInTheDocument();
  });
});
