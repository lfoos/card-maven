import type { ApiClient } from "./client";
import type {
  Item,
  ItemChanges,
  ItemFilters,
  ItemImage,
  ItemPage,
  NewItem,
  Parallel,
  PlayerSuggestion,
  SetSuggestion,
  UploadStarted,
} from "./types";

function query(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

/** Typed calls for the collection and catalog endpoints. */
export function collectionApi(client: ApiClient) {
  const items = "/api/v1/collection/items";
  return {
    list(filters: ItemFilters, cursor?: string, limit = 24, signal?: AbortSignal) {
      return client.get<ItemPage>(`${items}${query({ ...filters, cursor, limit })}`, signal);
    },
    get(id: string, signal?: AbortSignal) {
      return client.get<Item>(`${items}/${id}`, signal);
    },
    create(body: NewItem) {
      return client.request<Item>(items, { method: "POST", body });
    },
    update(id: string, body: ItemChanges) {
      return client.request<Item>(`${items}/${id}`, { method: "PATCH", body });
    },
    remove(id: string) {
      return client.request<undefined>(`${items}/${id}`, { method: "DELETE" });
    },
    startUpload(
      id: string,
      body: { kind: "front" | "back"; content_type: string; byte_size: number; sha256: string },
    ) {
      return client.request<UploadStarted>(`${items}/${id}/images`, { method: "POST", body });
    },
    completeUpload(id: string, imageId: string) {
      return client.request<ItemImage>(`${items}/${id}/images/${imageId}/complete`, {
        method: "POST",
      });
    },
    removeImage(id: string, imageId: string) {
      return client.request<undefined>(`${items}/${id}/images/${imageId}`, { method: "DELETE" });
    },
    searchSets(q: string, sport?: string, year?: number, signal?: AbortSignal) {
      return client.get<{ items: SetSuggestion[] }>(
        `/api/v1/catalog/sets${query({ q, sport, year })}`,
        signal,
      );
    },
    searchPlayers(q: string, sport?: string, signal?: AbortSignal) {
      return client.get<{ items: PlayerSuggestion[] }>(
        `/api/v1/catalog/players${query({ q, sport })}`,
        signal,
      );
    },
    parallels(setId: string, signal?: AbortSignal) {
      return client.get<{ items: Parallel[] }>(
        `/api/v1/catalog/parallels${query({ set_id: setId })}`,
        signal,
      );
    },
  };
}

export type CollectionApi = ReturnType<typeof collectionApi>;

export class StorageUploadError extends Error {
  readonly status: number;
  constructor(status: number) {
    super(
      status === 0
        ? "Could not reach file storage"
        : `File storage rejected the upload (${status})`,
    );
    this.name = "StorageUploadError";
    this.status = status;
  }
}

/**
 * Upload straight to object storage with a presigned POST. The signed policy
 * fields go first and the file last, as S3 requires.
 */
export async function uploadToStorage(
  upload: UploadStarted["upload"],
  file: Blob,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const form = new FormData();
  for (const [name, value] of Object.entries(upload.fields)) form.append(name, value);
  form.append("file", file);
  let response: Response;
  try {
    response = await fetchImpl(upload.url, { method: "POST", body: form });
  } catch {
    throw new StorageUploadError(0);
  }
  if (!response.ok) throw new StorageUploadError(response.status);
}
