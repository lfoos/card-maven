import { ApiError, isProblem } from "./errors";

export type TokenProvider = () => string | undefined;

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
}

function newRequestId(): string {
  return `web-${crypto.randomUUID()}`;
}

/** Thin typed wrapper over fetch: auth header, request ids, and problem+json errors. */
export class ApiClient {
  private readonly baseUrl: string;
  private readonly getToken: TokenProvider;
  private readonly fetchImpl: typeof fetch;

  constructor(baseUrl: string, getToken: TokenProvider, fetchImpl: typeof fetch = fetch) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.getToken = getToken;
    this.fetchImpl = fetchImpl;
  }

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    if (!path.startsWith("/")) throw new Error(`API paths must start with "/": ${path}`);

    const headers = new Headers({ Accept: "application/json", "X-Request-ID": newRequestId() });
    const token = this.getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);

    const init: RequestInit = { method: options.method ?? "GET", headers };
    if (options.signal) init.signal = options.signal;
    if (options.body !== undefined) {
      headers.set("Content-Type", "application/json");
      init.body = JSON.stringify(options.body);
    }

    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}${path}`, init);
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
      throw new ApiError(0, "network_error", "Could not reach the Card Maven API");
    }

    if (response.status === 204) return undefined as T;

    const payload: unknown = await response.json().catch(() => undefined);
    if (!response.ok) {
      if (isProblem(payload)) {
        throw new ApiError(response.status, payload.code, payload.title, payload);
      }
      throw new ApiError(response.status, "http_error", `Request failed (${response.status})`);
    }
    return payload as T;
  }

  get<T>(path: string, signal?: AbortSignal): Promise<T> {
    return this.request<T>(path, signal ? { signal } : {});
  }
}
