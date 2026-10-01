// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import LoginPage from "./page";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, replace: vi.fn() }) }));

const auth = {
  user: null,
  loading: false,
  login: vi.fn(),
  loginDemo: vi.fn().mockResolvedValue(undefined),
  demoMode: true,
};
vi.mock("@/lib/auth", () => ({ useAuth: () => auth }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("LoginPage", () => {
  it("offers a one-click demo in showcase mode and hides sign-up", async () => {
    auth.demoMode = true;
    render(<LoginPage />);
    expect(screen.queryByText("Sign up")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /view the demo/i }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/tasks"));
    expect(auth.loginDemo).toHaveBeenCalled();
  });

  it("is a normal login page otherwise", () => {
    auth.demoMode = false;
    render(<LoginPage />);
    expect(screen.queryByRole("button", { name: /view the demo/i })).toBeNull();
    expect(screen.getByText("Sign up")).toBeTruthy();
  });
});
