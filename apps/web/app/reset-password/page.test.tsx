// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ResetPasswordPage from "./page";
import { api, ApiError } from "@/lib/api";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, replace: vi.fn() }) }));

const logout = vi.fn();
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ logout }) }));

vi.mock("@/lib/api", async (orig) => {
  const actual = await orig<typeof import("@/lib/api")>();
  return { ...actual, api: { resetPassword: vi.fn() } };
});
const resetPassword = api.resetPassword as unknown as ReturnType<typeof vi.fn>;

function fill(password: string, confirm = password) {
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: password } });
  fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: confirm } });
  fireEvent.click(screen.getByRole("button", { name: /save new password/i }));
}

beforeEach(() => {
  window.history.replaceState(null, "", "/reset-password#token=good-token");
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ResetPasswordPage", () => {
  it("reads the token from the fragment and removes it from the address bar", async () => {
    render(<ResetPasswordPage />);
    await screen.findByLabelText("New password");
    expect(window.location.hash).toBe("");
  });

  it("resets, signs this browser out, and redirects to login", async () => {
    resetPassword.mockResolvedValue({ detail: "ok" });
    render(<ResetPasswordPage />);
    await screen.findByLabelText("New password");

    fill("brand-new-password");

    await waitFor(() => expect(push).toHaveBeenCalledWith("/login"));
    expect(resetPassword).toHaveBeenCalledWith("good-token", "brand-new-password");
    expect(logout).toHaveBeenCalled();
  });

  it("validates before calling the API", async () => {
    render(<ResetPasswordPage />);
    await screen.findByLabelText("New password");

    fill("short");
    expect(await screen.findByText(/at least 8 characters/)).toBeTruthy();
    fill("long-enough-1", "long-enough-2");
    expect(await screen.findByText(/don't match/)).toBeTruthy();
    expect(resetPassword).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Confirm new password").getAttribute("aria-invalid")).toBe(
      "true",
    );
  });

  it("shows the expired/used state when the API rejects the token", async () => {
    resetPassword.mockRejectedValue(new ApiError(400, "This reset link is invalid or has expired."));
    render(<ResetPasswordPage />);
    await screen.findByLabelText("New password");

    fill("brand-new-password");

    expect(await screen.findByText(/can't be used/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /request a new link/i }).getAttribute("href")).toBe(
      "/forgot-password",
    );
  });

  it("shows the invalid-link state when there is no token", async () => {
    window.history.replaceState(null, "", "/reset-password");
    render(<ResetPasswordPage />);
    expect(await screen.findByText(/can't be used/)).toBeTruthy();
  });
});
