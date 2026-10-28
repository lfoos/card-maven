import type { ApiClient } from "./client";
import type { ItemMarket, ManualSale, SalesAdded, SyncJob } from "./types";

/** Typed calls for comps, market syncs, and manual sales. */
export function marketApi(client: ApiClient) {
  const items = "/api/v1/collection/items";
  return {
    comps(itemId: string, signal?: AbortSignal) {
      return client.get<ItemMarket>(`${items}/${itemId}/comps`, signal);
    },
    refresh(itemId: string) {
      return client.request<SyncJob>(`${items}/${itemId}/comps/refresh`, { method: "POST" });
    },
    addSales(itemId: string, sales: ManualSale[]) {
      return client.request<SalesAdded>(`${items}/${itemId}/comps`, {
        method: "POST",
        body: { sales },
      });
    },
    deleteSale(saleId: string) {
      return client.request<undefined>(`/api/v1/market/sales/${saleId}`, { method: "DELETE" });
    },
    job(jobId: string, signal?: AbortSignal) {
      return client.get<SyncJob>(`/api/v1/market/sync-jobs/${jobId}`, signal);
    },
  };
}

export type MarketApi = ReturnType<typeof marketApi>;
