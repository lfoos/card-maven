import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { collectionApi } from "../../api/collection";
import { useApi } from "../../api/context";
import { useDebouncedValue } from "../../lib/useDebouncedValue";

export function useCollectionApi() {
  const client = useApi();
  return useMemo(() => collectionApi(client), [client]);
}

/** Debounced set-name suggestions from the shared catalog. */
export function useSetSuggestions(q: string, sport: string, year: string) {
  const api = useCollectionApi();
  const term = useDebouncedValue(q.trim());
  const yearNumber = Number(year) || undefined;
  return useQuery({
    queryKey: ["catalog", "sets", term, sport, yearNumber],
    queryFn: ({ signal }) => api.searchSets(term, sport, yearNumber, signal),
    enabled: term.length >= 2,
    staleTime: 60_000,
    select: (data) => data.items,
  });
}

export function usePlayerSuggestions(q: string, sport: string) {
  const api = useCollectionApi();
  // Suggest for the name being typed: the text after the last comma.
  const current = q.split(",").pop()?.trim() ?? "";
  const term = useDebouncedValue(current);
  return useQuery({
    queryKey: ["catalog", "players", term, sport],
    queryFn: ({ signal }) => api.searchPlayers(term, sport, signal),
    enabled: term.length >= 2,
    staleTime: 60_000,
    select: (data) => data.items,
  });
}
