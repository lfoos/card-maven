import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "./client";
import { marketApi } from "./market";

describe("marketApi", () => {
  it("uses the right method and path for each call", async () => {
    const request = vi.fn(() => Promise.resolve({}));
    const get = vi.fn(() => Promise.resolve({}));
    const api = marketApi({ request, get } as unknown as ApiClient);
    await api.comps("i1");
    await api.job("j1");
    await api.refresh("i1");
    await api.addSales("i1", [
      { sold_on: "2026-10-01", price: { amount: "5", currency: "USD" }, condition: "raw" },
    ]);
    await api.deleteSale("s1");
    expect(get.mock.calls).toEqual([
      ["/api/v1/collection/items/i1/comps", undefined],
      ["/api/v1/market/sync-jobs/j1", undefined],
    ]);
    expect(request.mock.calls).toEqual([
      ["/api/v1/collection/items/i1/comps/refresh", { method: "POST" }],
      [
        "/api/v1/collection/items/i1/comps",
        {
          method: "POST",
          body: {
            sales: [
              { sold_on: "2026-10-01", price: { amount: "5", currency: "USD" }, condition: "raw" },
            ],
          },
        },
      ],
      ["/api/v1/market/sales/s1", { method: "DELETE" }],
    ]);
  });
});
