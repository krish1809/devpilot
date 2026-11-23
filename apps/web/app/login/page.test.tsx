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
  registrationOpen: false,
  googleClientId: "",
  loginWithGoogle: vi.fn().mockResolvedValue(undefined),
};
vi.mock("@/lib/auth", () => ({ useAuth: () => auth }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("LoginPage", () => {
  it("offers a one-click demo in showcase mode and hides sign-up", async () => {
    Object.assign(auth, { demoMode: true, registrationOpen: false });
    render(<LoginPage />);
    expect(screen.queryByText("Sign up")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /view the demo/i }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/tasks"));
    expect(auth.loginDemo).toHaveBeenCalled();
  });

  it("is a normal login page otherwise", () => {
    Object.assign(auth, { demoMode: false, registrationOpen: true });
    render(<LoginPage />);
    expect(screen.queryByRole("button", { name: /view the demo/i })).toBeNull();
    expect(screen.getByText("Sign up")).toBeTruthy();
  });
});

describe("LoginPage links", () => {
  it("links to forgot-password and explains an ended session", () => {
    Object.assign(auth, { demoMode: false, sessionExpired: true });
    render(<LoginPage />);
    expect(screen.getByRole("link", { name: /forgot password/i }).getAttribute("href")).toBe(
      "/forgot-password",
    );
    expect(screen.getByText(/session has ended/i)).toBeTruthy();
    Object.assign(auth, { sessionExpired: false });
  });
});

describe("Sign in with Google", () => {
  afterEach(() => {
    delete window.google;
    auth.googleClientId = "";
  });

  it("is hidden when the API has no Google client ID", () => {
    Object.assign(auth, { demoMode: false, googleClientId: "" });
    render(<LoginPage />);
    expect(screen.queryByText(/or continue with email/i)).toBeNull();
  });

  it("sends Google's credential to the API and opens the app", async () => {
    let callback: ((r: { credential?: string }) => void) | undefined;
    const renderButton = vi.fn();
    window.google = {
      accounts: {
        id: {
          initialize: (config) => {
            expect(config.client_id).toBe("cid.apps.googleusercontent.com");
            callback = config.callback;
          },
          renderButton,
        },
      },
    };
    Object.assign(auth, { demoMode: false, googleClientId: "cid.apps.googleusercontent.com" });
    render(<LoginPage />);

    expect(screen.getByText(/or continue with email/i)).toBeTruthy();
    await waitFor(() => expect(renderButton).toHaveBeenCalled());
    callback?.({ credential: "google-id-token" });
    await waitFor(() => expect(push).toHaveBeenCalledWith("/tasks"));
    expect(auth.loginWithGoogle).toHaveBeenCalledWith("google-id-token");
  });

  it("shows the API's error when Google sign-in is refused", async () => {
    let callback: ((r: { credential?: string }) => void) | undefined;
    window.google = {
      accounts: { id: { initialize: (c) => (callback = c.callback), renderButton: vi.fn() } },
    };
    const { ApiError } = await import("@/lib/api");
    auth.loginWithGoogle.mockRejectedValueOnce(new ApiError(401, "Google sign-in failed."));
    Object.assign(auth, { demoMode: false, googleClientId: "cid" });
    render(<LoginPage />);
    await waitFor(() => expect(callback).toBeDefined());
    callback?.({ credential: "bad" });
    expect(await screen.findByText("Google sign-in failed.")).toBeTruthy();
    expect(push).not.toHaveBeenCalled();
  });
});
