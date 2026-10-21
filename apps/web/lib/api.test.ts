import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "./api";

function mockFetch(status: number, body: unknown, ok = status < 400) {
  return vi.fn(async () =>
    new Response(body === null ? "" : JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
      statusText: ok ? "OK" : "Error",
    }),
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("api client", () => {
  it("returns parsed body on success", async () => {
    globalThis.fetch = mockFetch(200, { access_token: "abc", token_type: "bearer" });
    const token = await api.login("a@b.com", "supersecret");
    expect(token.access_token).toBe("abc");
  });

  it("maps a string detail to an ApiError message", async () => {
    globalThis.fetch = mockFetch(401, { detail: "Incorrect email or password" });
    await expect(api.login("a@b.com", "x")).rejects.toMatchObject({
      status: 401,
      message: "Incorrect email or password",
    });
  });

  it("maps a Pydantic 422 detail array to a field message", async () => {
    globalThis.fetch = mockFetch(422, {
      detail: [{ loc: ["body", "password"], msg: "String should have at least 8 characters" }],
    });
    await expect(
      api.register("a@b.com", "short"),
    ).rejects.toThrowError(/password: String should have at least 8 characters/);
  });

  it("wraps network failures in an ApiError", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new TypeError("network down");
    });
    const err = await api.listProjects().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(0);
  });
});

describe("github + approval client", () => {
  it("encodes repo path segments", async () => {
    const { repoPath } = await import("./api");
    expect(repoPath("octo/my repo")).toBe("octo/my%20repo");
  });

  it("calls the issues endpoint for a repo", async () => {
    const fetchMock = mockFetch(200, []);
    globalThis.fetch = fetchMock;
    await api.listIssues("octo/demo");
    const calls = fetchMock.mock.calls as unknown as [string, RequestInit][];
    expect(calls[0][0]).toMatch(/\/api\/v1\/github\/repos\/octo\/demo\/issues$/);
  });

  it("omits base_branch on approve so the task's branch is used", async () => {
    const fetchMock = mockFetch(200, {});
    globalThis.fetch = fetchMock;
    await api.approveRun(1, "approved");
    const init = (fetchMock.mock.calls as unknown as [string, RequestInit][])[0][1];
    expect(JSON.parse(init.body as string)).toEqual({ decision: "approved" });
  });
});

describe("agent run lifecycle client", () => {
  it("posts cancel and resume to the run", async () => {
    const fetchMock = mockFetch(200, {});
    globalThis.fetch = fetchMock;
    await api.cancelRun(4);
    await api.resumeRun(4);
    const calls = fetchMock.mock.calls as unknown as [string, RequestInit][];
    expect(calls[0][0]).toMatch(/\/api\/v1\/runs\/4\/cancel$/);
    expect(calls[1][0]).toMatch(/\/api\/v1\/runs\/4\/resume$/);
    expect(calls[1][1].method).toBe("POST");
  });

  it("lists a task's runs", async () => {
    const fetchMock = mockFetch(200, []);
    globalThis.fetch = fetchMock;
    await api.listTaskRuns(7);
    const calls = fetchMock.mock.calls as unknown as [string, RequestInit][];
    expect(calls[0][0]).toMatch(/\/api\/v1\/tasks\/7\/runs$/);
  });
});

describe("run options", () => {
  it("sends use_rag only when specified", async () => {
    const fetchMock = mockFetch(202, {});
    globalThis.fetch = fetchMock;
    await api.runTask(3);
    await api.runTask(3, false);
    const calls = fetchMock.mock.calls as unknown as [string, RequestInit][];
    expect(calls[0][1].body).toBeUndefined();
    expect(JSON.parse(calls[1][1].body as string)).toEqual({ use_rag: false });
  });
});

describe("benchmarks client", () => {
  it("fetches eval runs and one run", async () => {
    const fetchMock = mockFetch(200, []);
    globalThis.fetch = fetchMock;
    await api.listEvals();
    await api.getEval(2);
    const calls = fetchMock.mock.calls as unknown as [string, RequestInit][];
    expect(calls[0][0]).toMatch(/\/api\/v1\/evals$/);
    expect(calls[1][0]).toMatch(/\/api\/v1\/evals\/2$/);
  });
});

describe("run trace client", () => {
  it("fetches a run's trace", async () => {
    const fetchMock = mockFetch(200, { llm_calls: [], tool_calls: [], total_tokens: 0 });
    globalThis.fetch = fetchMock;
    await api.getRunTrace(5);
    const calls = fetchMock.mock.calls as unknown as [string, RequestInit][];
    expect(calls[0][0]).toMatch(/\/api\/v1\/runs\/5\/trace$/);
  });
});

describe("streamRun (live run updates)", () => {
  function sseResponse(chunks: string[]) {
    const encoder = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        chunks.forEach((c) => controller.enqueue(encoder.encode(c)));
        controller.close();
      },
    });
    return vi.fn(
      async () => new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } }),
    );
  }

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("delivers each run snapshot and resolves when the server ends the stream", async () => {
    globalThis.fetch = sseResponse([
      'retry: 3000\n\nevent: run\ndata: {"id":7,"status":"running"}\n\n',
      'event: run\ndata: {"id":7,"sta',
      'tus":"validated"}\n\nevent: done\ndata: {"status":"validated"}\n\n',
    ]);
    const seen: string[] = [];

    await api.streamRun(7, (run) => seen.push(run.status), new AbortController().signal);

    expect(seen).toEqual(["running", "validated"]);
  });

  it("sends the token in the Authorization header, never in the URL", async () => {
    vi.stubGlobal("window", { localStorage: { getItem: () => "secret-token" } });
    const fetchMock = sseResponse([]);
    globalThis.fetch = fetchMock;

    await api.streamRun(3, () => undefined, new AbortController().signal);

    const [url, init] = (fetchMock.mock.calls as unknown as [string, RequestInit][])[0];
    expect(url).toMatch(/\/api\/v1\/runs\/3\/stream$/);
    expect(url).not.toContain("secret-token");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer secret-token");
  });

  it("rejects with an ApiError when the stream cannot be opened", async () => {
    globalThis.fetch = mockFetch(404, { detail: "Run not found" });
    await expect(
      api.streamRun(1, () => undefined, new AbortController().signal),
    ).rejects.toBeInstanceOf(ApiError);
  });
});
