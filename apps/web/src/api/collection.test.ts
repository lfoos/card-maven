import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "./client";
import { collectionApi, StorageUploadError, uploadToStorage } from "./collection";

function client() {
  const request = vi.fn((_path: string, _options?: { method?: string; body?: unknown }) =>
    Promise.resolve({}),
  );
  const get = vi.fn((_path: string, _signal?: AbortSignal) => Promise.resolve({}));
  return { api: collectionApi({ request, get } as unknown as ApiClient), request, get };
}

describe("collectionApi", () => {
  it("builds list queries, skipping empty values", async () => {
    const { api, get } = client();
    await api.list({ q: "skenes", sport: "baseball", year: 2025, sort: "name" }, "cur", 10);
    expect(get).toHaveBeenCalledWith(
      "/api/v1/collection/items?q=skenes&sport=baseball&year=2025&sort=name&cursor=cur&limit=10",
      undefined,
    );
    await api.list({ q: "" });
    expect(get).toHaveBeenLastCalledWith("/api/v1/collection/items?limit=24", undefined);
  });

  it("uses the right method and path for each call", async () => {
    const { api, request, get } = client();
    await api.create({ card: {} } as never);
    await api.update("i1", { notes: "x" });
    await api.remove("i1");
    await api.startUpload("i1", {
      kind: "front",
      content_type: "image/jpeg",
      byte_size: 1,
      sha256: "a",
    });
    await api.completeUpload("i1", "img1");
    await api.removeImage("i1", "img1");
    expect(request.mock.calls.map(([path, opts]) => `${opts?.method} ${path}`)).toEqual([
      "POST /api/v1/collection/items",
      "PATCH /api/v1/collection/items/i1",
      "DELETE /api/v1/collection/items/i1",
      "POST /api/v1/collection/items/i1/images",
      "POST /api/v1/collection/items/i1/images/img1/complete",
      "DELETE /api/v1/collection/items/i1/images/img1",
    ]);
    await api.get("i1");
    await api.searchSets("chrome", "baseball", 2025);
    await api.searchPlayers("wem a", "basketball");
    await api.parallels("s1");
    expect(get.mock.calls.map(([path]) => path)).toEqual([
      "/api/v1/collection/items/i1",
      "/api/v1/catalog/sets?q=chrome&sport=baseball&year=2025",
      "/api/v1/catalog/players?q=wem+a&sport=basketball",
      "/api/v1/catalog/parallels?set_id=s1",
    ]);
  });
});

describe("uploadToStorage", () => {
  const upload = {
    url: "https://storage.test/bucket",
    fields: { key: "users/u/k", policy: "p", "Content-Type": "image/jpeg" },
  };

  it("sends the policy fields first and the file last", async () => {
    const fetchImpl = vi.fn<typeof fetch>(() =>
      Promise.resolve(new Response(null, { status: 204 })),
    );
    const file = new Blob(["jpeg"], { type: "image/jpeg" });
    await uploadToStorage(upload, file, fetchImpl);
    const [url, init] = fetchImpl.mock.calls[0]!;
    expect(url).toBe(upload.url);
    expect(init!.method).toBe("POST");
    const form = init!.body as FormData;
    expect([...form.keys()]).toEqual(["key", "policy", "Content-Type", "file"]);
  });

  it("reports rejections and network failures", async () => {
    const file = new Blob(["x"]);
    await expect(
      uploadToStorage(upload, file, () => Promise.resolve(new Response("denied", { status: 403 }))),
    ).rejects.toMatchObject({ status: 403 });
    const offline = uploadToStorage(upload, file, () => Promise.reject(new TypeError("offline")));
    await expect(offline).rejects.toBeInstanceOf(StorageUploadError);
    await expect(offline).rejects.toMatchObject({
      status: 0,
      message: "Could not reach file storage",
    });
  });
});
