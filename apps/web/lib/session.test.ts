// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, setStoredToken, UNAUTHORIZED_EVENT } from "./api";

const respond = (status: number, body: unknown) =>
  vi.fn(async () => new Response(JSON.stringify(body), { status }));

let fired = 0;
const listener = () => {
  fired += 1;
};

beforeEach(() => {
  fired = 0;
  window.addEventListener(UNAUTHORIZED_EVENT, listener);
});

afterEach(() => {
  window.removeEventListener(UNAUTHORIZED_EVENT, listener);
  setStoredToken(null);
  vi.restoreAllMocks();
});

describe("session expiry signal", () => {
  it("fires when a signed-in request is rejected (e.g. revoked by a password reset)", async () => {
    setStoredToken("old-token");
    globalThis.fetch = respond(401, { detail: "Could not validate credentials" });
    await expect(api.listTasks()).rejects.toMatchObject({ status: 401 });
    expect(fired).toBe(1);
  });

  it("does not fire for a wrong password at login", async () => {
    setStoredToken("old-token");
    globalThis.fetch = respond(401, { detail: "Incorrect email or password" });
    await expect(api.login("a@b.com", "nope")).rejects.toMatchObject({ status: 401 });
    expect(fired).toBe(0);
  });

  it("does not fire when no session was sent", async () => {
    globalThis.fetch = respond(401, { detail: "Not authenticated" });
    await expect(api.listTasks()).rejects.toMatchObject({ status: 401 });
    expect(fired).toBe(0);
  });
});

describe("password reset client", () => {
  it("posts the email to forgot-password", async () => {
    const fetchMock = respond(202, { detail: "If an account exists…" });
    globalThis.fetch = fetchMock;
    await api.forgotPassword("a@b.com");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/api\/v1\/auth\/forgot-password$/);
    expect(JSON.parse(init.body as string)).toEqual({ email: "a@b.com" });
  });

  it("sends token + new_password and exposes per-field 422 errors", async () => {
    globalThis.fetch = respond(422, {
      detail: [
        {
          loc: ["body", "new_password"],
          msg: "Value error, password must be at least 8 characters",
        },
      ],
    });
    const err = await api.resetPassword("tok", "short").catch((e) => e);
    expect(err.status).toBe(422);
    expect(err.fields).toEqual({ new_password: "password must be at least 8 characters" });
    const init = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({ token: "tok", new_password: "short" });
  });
});
