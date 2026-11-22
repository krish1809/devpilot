// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ForgotPasswordPage from "./page";
import { api, ApiError } from "@/lib/api";

vi.mock("@/lib/api", async (orig) => {
  const actual = await orig<typeof import("@/lib/api")>();
  return { ...actual, api: { forgotPassword: vi.fn() } };
});
const forgotPassword = api.forgotPassword as unknown as ReturnType<typeof vi.fn>;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function submit(email: string) {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: email } });
  fireEvent.click(screen.getByRole("button", { name: /send reset link/i }));
}

describe("ForgotPasswordPage", () => {
  it("shows the same neutral confirmation whatever the account status", async () => {
    forgotPassword.mockResolvedValue({ detail: "If an account exists…" });
    render(<ForgotPasswordPage />);
    submit("someone@example.com");

    expect(await screen.findByText("Check your email")).toBeTruthy();
    expect(screen.getByText(/If an account exists for/)).toBeTruthy();
    expect(forgotPassword).toHaveBeenCalledWith("someone@example.com");
  });

  it("explains rate limiting", async () => {
    forgotPassword.mockRejectedValue(new ApiError(429, "Too many requests"));
    render(<ForgotPasswordPage />);
    submit("someone@example.com");
    expect(await screen.findByText(/too many reset requests/i)).toBeTruthy();
  });
});
