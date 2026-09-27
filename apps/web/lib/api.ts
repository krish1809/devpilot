import type {
  AuditLog,
  Project,
  ProjectCreateInput,
  ProjectUpdateInput,
  Token,
  User,
} from "./types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

const TOKEN_KEY = "devpilot_token";

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setStoredToken(token: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore storage failures (private mode, etc.) */
  }
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Turn a FastAPI/Pydantic error body into a readable message. */
function extractMessage(status: number, body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const first = detail[0] as { msg?: string; loc?: unknown[] } | undefined;
      if (first?.msg) {
        const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : "";
        return field ? `${field}: ${first.msg}` : first.msg;
      }
    }
  }
  return `Request failed (${status})`;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  token?: string | null;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, token } = options;
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const authToken = token ?? getStoredToken();
  if (authToken) headers["Authorization"] = `Bearer ${authToken}`;

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "Could not reach the API. Is the backend running?");
  }

  if (response.status === 204) return undefined as T;

  let data: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, extractMessage(response.status, data));
  }
  return data as T;
}

export const api = {
  register: (email: string, password: string) =>
    request<User>("/api/v1/auth/register", {
      method: "POST",
      body: { email, password },
    }),

  login: (email: string, password: string) =>
    request<Token>("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
    }),

  me: (token?: string) => request<User>("/api/v1/auth/me", { token }),

  listProjects: () => request<Project[]>("/api/v1/projects"),

  createProject: (input: ProjectCreateInput) =>
    request<Project>("/api/v1/projects", { method: "POST", body: input }),

  getProject: (id: number) => request<Project>(`/api/v1/projects/${id}`),

  updateProject: (id: number, input: ProjectUpdateInput) =>
    request<Project>(`/api/v1/projects/${id}`, { method: "PATCH", body: input }),

  deleteProject: (id: number) =>
    request<void>(`/api/v1/projects/${id}`, { method: "DELETE" }),

  myAudit: () => request<AuditLog[]>("/api/v1/audit/me"),
};
