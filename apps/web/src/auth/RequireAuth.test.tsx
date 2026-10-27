import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useAuth } from "react-oidc-context";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { mockAuth } from "../test/mockAuth";
import { RequireAuth } from "./RequireAuth";

vi.mock("react-oidc-context", () => ({ useAuth: vi.fn() }));
const mockedUseAuth = vi.mocked(useAuth);

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <RequireAuth>
        <p>secret collection</p>
      </RequireAuth>
    </MemoryRouter>,
  );
}

describe("RequireAuth", () => {
  beforeEach(() => mockedUseAuth.mockReset());

  it("renders children when signed in", () => {
    mockedUseAuth.mockReturnValue(mockAuth({ isAuthenticated: true }));
    renderAt("/collection");
    expect(screen.getByText("secret collection")).toBeInTheDocument();
  });

  it("starts sign-in with a return path when signed out", () => {
    const auth = mockAuth();
    mockedUseAuth.mockReturnValue(auth);
    renderAt("/collection?sort=year");
    expect(screen.queryByText("secret collection")).not.toBeInTheDocument();
    expect(screen.getByText(/redirecting to sign in/i)).toBeInTheDocument();
    expect(auth.signinRedirect).toHaveBeenCalledWith({
      state: { returnTo: "/collection?sort=year" },
    });
  });

  it("waits while auth is loading", () => {
    const auth = mockAuth({ isLoading: true });
    mockedUseAuth.mockReturnValue(auth);
    renderAt("/collection");
    expect(auth.signinRedirect).not.toHaveBeenCalled();
  });

  it("does not start a second redirect while one is in flight", () => {
    const auth = mockAuth({ activeNavigator: "signinRedirect" });
    mockedUseAuth.mockReturnValue(auth);
    renderAt("/collection");
    expect(auth.signinRedirect).not.toHaveBeenCalled();
  });

  it("shows an error with a retry", async () => {
    const auth = mockAuth({
      error: Object.assign(new Error("IdP unreachable"), { source: "signinCallback" }) as never,
    });
    mockedUseAuth.mockReturnValue(auth);
    renderAt("/collection");
    expect(screen.getByRole("alert")).toHaveTextContent("IdP unreachable");
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(auth.signinRedirect).toHaveBeenCalledTimes(1);
  });
});
