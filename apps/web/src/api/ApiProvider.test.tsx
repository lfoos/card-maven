import { render, renderHook, screen } from "@testing-library/react";
import type { User } from "oidc-client-ts";
import { useAuth } from "react-oidc-context";
import { describe, expect, it, vi } from "vitest";
import { mockAuth } from "../test/mockAuth";
import { ApiProvider } from "./ApiProvider";
import { useApi } from "./context";

vi.mock("react-oidc-context", () => ({ useAuth: vi.fn() }));

function Probe({ onClient }: { onClient: (client: ReturnType<typeof useApi>) => void }) {
  onClient(useApi());
  return <p>ready</p>;
}

describe("ApiProvider", () => {
  it("sends the latest access token after renewal", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(() => Promise.resolve(new Response("{}", { status: 200 })));
    const clients: ReturnType<typeof useApi>[] = [];
    vi.mocked(useAuth).mockReturnValue(mockAuth({ user: { access_token: "first" } as User }));
    const { rerender } = render(
      <ApiProvider>
        <Probe onClient={(c) => clients.push(c)} />
      </ApiProvider>,
    );
    vi.mocked(useAuth).mockReturnValue(mockAuth({ user: { access_token: "second" } as User }));
    rerender(
      <ApiProvider>
        <Probe onClient={(c) => clients.push(c)} />
      </ApiProvider>,
    );
    expect(screen.getByText("ready")).toBeInTheDocument();

    await clients[1]!.get("/me");
    const headers = fetchSpy.mock.calls[0]![1]!.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer second");
  });

  it("throws outside the provider", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => renderHook(() => useApi())).toThrow(/inside <ApiProvider>/);
  });
});
