// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RegisterPage from "./page";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, replace: vi.fn() }) }));

const auth = {
  user: null,
  loading: false,
  register: vi.fn(),
  loginDemo: vi.fn().mockResolvedValue(undefined),
  demoMode: true,
};
vi.mock("@/lib/auth", () => ({ useAuth: () => auth }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("RegisterPage", () => {
  it("explains that sign-up is off in showcase mode and offers the demo", async () => {
    auth.demoMode = true;
    render(<RegisterPage />);
    expect(screen.getByText(/sign-up is off/i)).toBeTruthy();
    expect(screen.queryByLabelText("Password")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /view the demo/i }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/tasks"));
  });

  it("shows the normal form otherwise", () => {
    auth.demoMode = false;
    render(<RegisterPage />);
    expect(screen.getByText("Create your account")).toBeTruthy();
  });
});
