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
