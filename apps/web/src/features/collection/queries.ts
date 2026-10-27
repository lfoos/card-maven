import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ItemChanges, ItemFilters, NewItem } from "../../api/types";
import { useCollectionApi } from "./useSuggestions";

export const collectionKeys = {
  all: ["collection"] as const,
  lists: () => [...collectionKeys.all, "list"] as const,
  list: (filters: ItemFilters) => [...collectionKeys.lists(), filters] as const,
  item: (id: string) => [...collectionKeys.all, "item", id] as const,
};

export function useItems(filters: ItemFilters) {
  const api = useCollectionApi();
  return useInfiniteQuery({
    queryKey: collectionKeys.list(filters),
    queryFn: ({ pageParam, signal }) => api.list(filters, pageParam, 24, signal),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

export function useItem(id: string) {
  const api = useCollectionApi();
  return useQuery({
    queryKey: collectionKeys.item(id),
    queryFn: ({ signal }) => api.get(id, signal),
  });
}

export function useCreateItem() {
  const api = useCollectionApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: NewItem) => api.create(body),
    onSuccess: (item) => {
      queryClient.setQueryData(collectionKeys.item(item.id), item);
      void queryClient.invalidateQueries({ queryKey: collectionKeys.lists() });
    },
  });
}

export function useUpdateItem(id: string) {
  const api = useCollectionApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ItemChanges) => api.update(id, body),
    onSuccess: (item) => {
      queryClient.setQueryData(collectionKeys.item(id), item);
      void queryClient.invalidateQueries({ queryKey: collectionKeys.lists() });
    },
  });
}

export function useDeleteItem() {
  const api = useCollectionApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.remove(id),
    onSuccess: (_result, id) => {
      queryClient.removeQueries({ queryKey: collectionKeys.item(id) });
      void queryClient.invalidateQueries({ queryKey: collectionKeys.lists() });
    },
  });
}
