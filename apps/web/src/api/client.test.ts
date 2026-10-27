import { describe, expect, it, vi } from "vitest";
import { ApiClient } from "./client";
import { ApiError } from "./errors";

function jsonResponse(body: unknown, status = 200, contentType = "application/json"): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": contentType } });
}

function setup(response: Response | Error | DOMException, token?: string) {
  const fetchImpl = vi.fn<typeof fetch>(() =>
    response instanceof Response ? Promise.resolve(response) : Promise.reject(response),
  );
  const client = new ApiClient("http://api.test/", () => token, fetchImpl);
  return { client, fetchImpl };
}

function sentHeaders(fetchImpl: ReturnType<typeof setup>["fetchImpl"]): Headers {
  return fetchImpl.mock.calls[0]![1]!.headers as Headers;
}

describe("ApiClient", () => {
  it("returns parsed JSON and joins the base URL", async () => {
    const { client, fetchImpl } = setup(jsonResponse({ status: "ok" }));
    await expect(client.get("/healthz")).resolves.toEqual({ status: "ok" });
    expect(fetchImpl.mock.calls[0]![0]).toBe("http://api.test/healthz");
  });

  it("sends the bearer token and a request id", async () => {
    const { client, fetchImpl } = setup(jsonResponse({}), "token-abc");
    await client.get("/me");
    const headers = sentHeaders(fetchImpl);
    expect(headers.get("Authorization")).toBe("Bearer token-abc");
    expect(headers.get("X-Request-ID")).toMatch(/^web-[0-9a-f-]{36}$/);
  });

  it("omits Authorization when signed out", async () => {
    const { client, fetchImpl } = setup(jsonResponse({}));
    await client.get("/healthz");
    expect(sentHeaders(fetchImpl).has("Authorization")).toBe(false);
  });

  it("serializes JSON bodies", async () => {
    const { client, fetchImpl } = setup(jsonResponse({ id: 1 }, 201));
    await client.request("/cards", { method: "POST", body: { player: "Skenes" } });
    const init = fetchImpl.mock.calls[0]![1]!;
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"player":"Skenes"}');
    expect(sentHeaders(fetchImpl).get("Content-Type")).toBe("application/json");
  });

  it("returns undefined for 204", async () => {
    const { client } = setup(new Response(null, { status: 204 }));
    await expect(client.request("/cards/1", { method: "DELETE" })).resolves.toBeUndefined();
  });

  it("turns problem+json into ApiError", async () => {
    const problem = {
      title: "Invalid input",
      status: 422,
      code: "invalid_input",
      detail: "year must be after 1860",
      request_id: "req-1",
    };
    const { client } = setup(jsonResponse(problem, 422, "application/problem+json"));
    const error = await client.get("/cards").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 422,
      code: "invalid_input",
      message: "Invalid input",
      detail: "year must be after 1860",
      requestId: "req-1",
    });
  });

  it("handles non-problem error bodies", async () => {
    const { client } = setup(new Response("<html>bad gateway</html>", { status: 502 }));
    const error = (await client.get("/x").catch((e: unknown) => e)) as ApiError;
    expect(error.status).toBe(502);
    expect(error.code).toBe("http_error");
    expect(error.isUnauthenticated).toBe(false);
  });

  it("flags 401 as unauthenticated", async () => {
    const { client } = setup(
      jsonResponse({ title: "Authentication required", status: 401, code: "unauthenticated" }, 401),
    );
    const error = (await client.get("/me").catch((e: unknown) => e)) as ApiError;
    expect(error.isUnauthenticated).toBe(true);
  });

  it("maps fetch failures to a network error", async () => {
    const { client } = setup(new TypeError("Failed to fetch"));
    const error = (await client.get("/healthz").catch((e: unknown) => e)) as ApiError;
    expect(error.isNetworkError).toBe(true);
    expect(error.code).toBe("network_error");
  });

  it("propagates aborts untouched", async () => {
    const { client } = setup(new DOMException("aborted", "AbortError"));
    await expect(client.get("/healthz", new AbortController().signal)).rejects.toMatchObject({
      name: "AbortError",
    });
  });

  it("rejects relative paths", async () => {
    const { client } = setup(jsonResponse({}));
    await expect(client.get("healthz")).rejects.toThrow(/must start with/);
  });
});
