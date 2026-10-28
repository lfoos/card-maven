import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo } from "react";
import { useApi } from "../../api/context";
import { marketApi } from "../../api/market";
import type { ManualSale, SyncJob } from "../../api/types";
import { collectionKeys } from "../collection/queries";

export const marketKeys = {
  item: (itemId: string) => ["market", "item", itemId] as const,
  job: (jobId: string) => ["market", "job", jobId] as const,
};

/** How often to check a running sync. */
export const POLL_MS = 2000;

export function useMarketApi() {
  const client = useApi();
  return useMemo(() => marketApi(client), [client]);
}

export function useItemMarket(itemId: string) {
  const api = useMarketApi();
  return useQuery({
    queryKey: marketKeys.item(itemId),
    queryFn: ({ signal }) => api.comps(itemId, signal),
  });
}

function isActive(job: SyncJob | undefined): boolean {
  return job?.status === "queued" || job?.status === "running";
}

/** Market data changed: reload comps, the item (its estimate), and lists. */
function useRefreshViews(itemId: string) {
  const queryClient = useQueryClient();
  return useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: marketKeys.item(itemId) });
    void queryClient.invalidateQueries({ queryKey: collectionKeys.item(itemId) });
    void queryClient.invalidateQueries({ queryKey: collectionKeys.lists() });
  }, [queryClient, itemId]);
}

/**
 * "Get comps": start (or join) a sync, poll it every POLL_MS until it
 * finishes, then reload the market view once. Returns the tracked job.
 */
export function useGetComps(itemId: string) {
  const api = useMarketApi();
  const refreshViews = useRefreshViews(itemId);
  const start = useMutation({ mutationFn: () => api.refresh(itemId) });
  const started = start.data;

  const poll = useQuery({
    queryKey: marketKeys.job(started?.id ?? "none"),
    queryFn: ({ signal }) => {
      if (!started) throw new Error("no sync started");
      return api.job(started.id, signal);
    },
    enabled: isActive(started),
    refetchInterval: (query) => (isActive(query.state.data ?? started) ? POLL_MS : false),
  });

  const job = poll.data ?? started;
  const finishedId = job && !isActive(job) ? job.id : null;
  useEffect(() => {
    if (finishedId) refreshViews();
  }, [finishedId, refreshViews]);

  return {
    start: () => start.mutate(),
    job,
    working: start.isPending || isActive(job),
    error: start.error ?? poll.error,
  };
}

export function useAddSales(itemId: string) {
  const api = useMarketApi();
  const queryClient = useQueryClient();
  const refreshViews = useRefreshViews(itemId);
  return useMutation({
    mutationFn: (sales: ManualSale[]) => api.addSales(itemId, sales),
    onSuccess: (result) => {
      queryClient.setQueryData(marketKeys.item(itemId), result.market);
      refreshViews();
    },
  });
}

export function useDeleteSale(itemId: string) {
  const api = useMarketApi();
  const refreshViews = useRefreshViews(itemId);
  return useMutation({
    mutationFn: (saleId: string) => api.deleteSale(saleId),
    onSuccess: refreshViews,
  });
}
