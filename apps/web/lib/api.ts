import type {
  AgentRun,
  AuditLog,
  EvalRunDetail,
  EvalRunSummary,
  GitHubIssue,
  GitHubRepo,
  GitHubTree,
  MessageResponse,
  PublicConfig,
  Project,
  RunCheckpoint,
  RunTrace,
  RunSummary,
  ProjectCreateInput,
  ProjectUpdateInput,
  Task,
  TaskCreateInput,
  TaskFromIssueInput,
  Token,
  User,
} from "./types";
import { createSseParser } from "./sse";

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
  /** Per-field messages from a 422 validation error, keyed by field name. */
  fields: Record<string, string>;

  constructor(status: number, message: string, fields: Record<string, string> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fields = fields;
  }
}

/** Fired on `window` when a signed-in request gets 401 (expired or revoked session). */
export const UNAUTHORIZED_EVENT = "devpilot:unauthorized";

// Endpoints where 401 means "wrong credentials", not "your session ended".
const CREDENTIAL_PATHS = ["/api/v1/auth/login", "/api/v1/auth/demo", "/api/v1/auth/google"];

function signalUnauthorized(path: string, sentToken: boolean): void {
  if (!sentToken || typeof window === "undefined") return;
  if (CREDENTIAL_PATHS.some((p) => path.startsWith(p))) return;
  window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
}

/** Pydantic prefixes custom validator messages with "Value error, ". */
const cleanMsg = (msg: string) => msg.replace(/^Value error, /, "");

function fieldName(loc: unknown): string {
  return Array.isArray(loc) && loc.length ? String(loc[loc.length - 1]) : "";
}

/** Turn a FastAPI/Pydantic error body into a readable message. */
function extractMessage(status: number, body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const first = detail[0] as { msg?: string; loc?: unknown[] } | undefined;
      if (first?.msg) {
        const field = fieldName(first.loc);
        return field ? `${field}: ${cleanMsg(first.msg)}` : cleanMsg(first.msg);
      }
    }
  }
  return `Request failed (${status})`;
}

function extractFields(body: unknown): Record<string, string> {
  const fields: Record<string, string> = {};
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (Array.isArray(detail)) {
      for (const item of detail as { msg?: string; loc?: unknown[] }[]) {
        const field = fieldName(item?.loc);
        if (field && item.msg && !(field in fields)) fields[field] = cleanMsg(item.msg);
      }
    }
  }
  return fields;
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
    if (response.status === 401) signalUnauthorized(path, Boolean(authToken));
    throw new ApiError(
      response.status,
      extractMessage(response.status, data),
      response.status === 422 ? extractFields(data) : {},
    );
  }
  return data as T;
}

/**
 * Live run updates over Server-Sent Events. Uses fetch (not EventSource) so the
 * bearer token travels in a header instead of the URL. Calls `onRun` with each
 * snapshot; resolves when the server ends the stream (run finished or timed
 * out) and rejects on network/HTTP errors or when `signal` aborts.
 */
async function streamRun(
  runId: number,
  onRun: (run: AgentRun) => void,
  signal: AbortSignal,
): Promise<void> {
  const token = getStoredToken();
  const headers: Record<string, string> = { Accept: "text/event-stream" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const response = await fetch(`${API_URL}/api/v1/runs/${runId}/stream`, {
    headers,
    cache: "no-store",
    signal,
  });
  if (!response.ok || !response.body) {
    if (response.status === 401) signalUnauthorized("/api/v1/runs", Boolean(token));
    throw new ApiError(response.status, `Live updates unavailable (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const feed = createSseParser((message) => {
    if (message.event === "run") onRun(JSON.parse(message.data) as AgentRun);
  });
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return;
    feed(decoder.decode(value, { stream: true }));
  }
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

  /** Always resolves with the same generic message, whether or not the account exists. */
  forgotPassword: (email: string) =>
    request<MessageResponse>("/api/v1/auth/forgot-password", {
      method: "POST",
      body: { email },
    }),

  resetPassword: (token: string, newPassword: string) =>
    request<MessageResponse>("/api/v1/auth/reset-password", {
      method: "POST",
      body: { token, new_password: newPassword },
    }),

  /** Public flags (e.g. read-only showcase mode). */
  getConfig: () => request<PublicConfig>("/api/v1/config"),

  /** Showcase only: a session as the read-only demo user. */
  demoLogin: () => request<Token>("/api/v1/auth/demo", { method: "POST" }),

  /** Exchange a Google ID token (from Google's sign-in button) for a DevPilot token. */
  googleLogin: (credential: string) =>
    request<Token>("/api/v1/auth/google", {
      method: "POST",
      body: JSON.stringify({ credential }),
    }),

  listProjects: () => request<Project[]>("/api/v1/projects"),

  createProject: (input: ProjectCreateInput) =>
    request<Project>("/api/v1/projects", { method: "POST", body: input }),

  getProject: (id: number) => request<Project>(`/api/v1/projects/${id}`),

  updateProject: (id: number, input: ProjectUpdateInput) =>
    request<Project>(`/api/v1/projects/${id}`, {
      method: "PATCH",
      body: input,
    }),

  deleteProject: (id: number) => request<void>(`/api/v1/projects/${id}`, { method: "DELETE" }),

  myAudit: () => request<AuditLog[]>("/api/v1/audit/me"),

  // --- Agent ---
  listTasks: () => request<Task[]>("/api/v1/tasks"),

  createTask: (input: TaskCreateInput) =>
    request<Task>("/api/v1/tasks", { method: "POST", body: input }),

  getTask: (id: number) => request<Task>(`/api/v1/tasks/${id}`),

  /** Start a run; `useRag` overrides the server default for this run. */
  runTask: (id: number, useRag?: boolean) =>
    request<AgentRun>(`/api/v1/tasks/${id}/run`, {
      method: "POST",
      body: useRag === undefined ? undefined : { use_rag: useRag },
    }),

  getRun: (id: number) => request<AgentRun>(`/api/v1/runs/${id}`),

  streamRun,

  listTaskRuns: (taskId: number) => request<RunSummary[]>(`/api/v1/tasks/${taskId}/runs`),

  getRunCheckpoints: (id: number) => request<RunCheckpoint[]>(`/api/v1/runs/${id}/checkpoints`),

  getRunTrace: (id: number) => request<RunTrace>(`/api/v1/runs/${id}/trace`),

  cancelRun: (id: number) => request<AgentRun>(`/api/v1/runs/${id}/cancel`, { method: "POST" }),

  resumeRun: (id: number) => request<AgentRun>(`/api/v1/runs/${id}/resume`, { method: "POST" }),

  // The PR targets the task's base branch unless one is given here.
  approveRun: (id: number, decision: "approved" | "rejected", baseBranch?: string) =>
    request<AgentRun>(`/api/v1/runs/${id}/approve`, {
      method: "POST",
      body: baseBranch ? { decision, base_branch: baseBranch } : { decision },
    }),

  // --- Benchmarks ---
  listEvals: () => request<EvalRunSummary[]>("/api/v1/evals"),

  getEval: (id: number) => request<EvalRunDetail>(`/api/v1/evals/${id}`),

  // --- GitHub ---
  listRepos: () => request<GitHubRepo[]>("/api/v1/github/repos"),

  listIssues: (fullName: string) =>
    request<GitHubIssue[]>(`/api/v1/github/repos/${repoPath(fullName)}/issues`),

  getTree: (fullName: string, ref?: string) =>
    request<GitHubTree>(
      `/api/v1/github/repos/${repoPath(fullName)}/tree` +
        (ref ? `?ref=${encodeURIComponent(ref)}` : ""),
    ),

  createTaskFromIssue: (input: TaskFromIssueInput) =>
    request<Task>("/api/v1/tasks/from-issue", { method: "POST", body: input }),
};

/** "owner/name" -> "owner/name" with each segment URL-encoded. */
export function repoPath(fullName: string): string {
  return fullName.split("/").map(encodeURIComponent).join("/");
}
