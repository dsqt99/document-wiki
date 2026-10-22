/**
 * Thin fetch wrapper for the backend REST API.
 *
 * NEXT_PUBLIC_API_URL is inlined at build time. When it is defined at all (even as an
 * empty string) its value is used verbatim; only a completely unset variable falls back
 * to the local backend. Production builds set it to "" so the browser talks to the same
 * origin and goes through the Next rewrites.
 */
import { clearToken, readToken } from "./session";

export { clearToken, setToken } from "./session";

const API_BASE: string =
  process.env.NEXT_PUBLIC_API_URL !== undefined ? process.env.NEXT_PUBLIC_API_URL : "http://localhost:5055";

const DEFAULT_TIMEOUT_MS = 60_000;

export class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(status: number, message: string, data?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

/** Absolute URL for browser navigation (e.g. SSO redirects), not for fetch. */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

async function errorFromResponse(res: Response, fallbackPrefix: string): Promise<ApiError> {
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  let message = `${fallbackPrefix} ${res.status}`;
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === "string" && detail) message = detail;
    else if (detail !== undefined && detail !== null) message = JSON.stringify(detail);
  }
  return new ApiError(res.status, message, data);
}

export type ApiOptions = {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  timeoutMs?: number;
};

export async function api<T = unknown>(path: string, options: ApiOptions = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const isForm = typeof FormData !== "undefined" && options.body instanceof FormData;

  const headers: Record<string, string> = {};
  if (!isForm) headers["Content-Type"] = "application/json";
  const token = readToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  Object.assign(headers, options.headers ?? {});
  const requestToken = token && new Headers(headers).get("Authorization") === `Bearer ${token}` ? token : null;

  let body: BodyInit | undefined;
  if (options.body !== undefined && options.body !== null && method !== "GET") {
    body = isForm ? (options.body as FormData) : JSON.stringify(options.body);
  }

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { method, headers, body, signal: controller.signal });
  } catch (err) {
    if (timedOut) throw new ApiError(0, "Request timed out");
    throw err;
  } finally {
    clearTimeout(timer);
  }

  if (!res.ok) {
    if (res.status === 401 && requestToken) clearToken(requestToken);
    throw await errorFromResponse(res, "API Error");
  }

  const text = await res.text();
  if (!text) return {} as T;
  return JSON.parse(text) as T;
}

export async function apiUpload<T = unknown>(path: string, formData: FormData, timeoutMs = 120_000): Promise<T> {
  const headers: Record<string, string> = {};
  const token = readToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { method: "POST", headers, body: formData, signal: controller.signal });
  } catch (err) {
    if (timedOut) throw new ApiError(0, "Upload timed out");
    throw err;
  } finally {
    clearTimeout(timer);
  }

  if (!res.ok) {
    if (res.status === 401 && token) clearToken(token);
    throw await errorFromResponse(res, "Upload Error");
  }
  return (await res.json()) as T;
}
