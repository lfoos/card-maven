/** RFC 9457 problem details, as returned by every API error. */
export interface Problem {
  type?: string;
  title: string;
  status: number;
  code: string;
  detail?: string;
  request_id?: string;
  [extra: string]: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: string | undefined;
  readonly requestId: string | undefined;
  readonly problem: Problem | undefined;

  constructor(status: number, code: string, message: string, problem?: Problem) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = problem?.detail;
    this.requestId = problem?.request_id;
    this.problem = problem;
  }

  /** Network failure or timeout: no response from the server. */
  get isNetworkError(): boolean {
    return this.status === 0;
  }

  get isUnauthenticated(): boolean {
    return this.status === 401;
  }
}

export function isProblem(value: unknown): value is Problem {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return typeof candidate.status === "number" && typeof candidate.code === "string";
}
