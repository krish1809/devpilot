// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProjectDetailPage from "./page";
import { api } from "@/lib/api";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  useParams: () => ({ id: "5" }),
}));
vi.mock("@/lib/auth", () => ({
  useAuth: () => ({ user: { id: 1, email: "a@b.com" }, loading: false, demoMode: false }),
}));
vi.mock("@/lib/api", async (orig) => {
  const actual = await orig<typeof import("@/lib/api")>();
  return { ...actual, api: { getProject: vi.fn(), updateProject: vi.fn(), deleteProject: vi.fn() } };
});
const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

beforeEach(() => {
  mocked.getProject.mockResolvedValue({
    id: 5,
    owner_id: 1,
    name: "Alpha",
    description: null,
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-01T00:00:00Z",
  });
  mocked.deleteProject.mockResolvedValue(undefined);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ProjectDetailPage", () => {
  it("asks for confirmation before deleting", async () => {
    render(<ProjectDetailPage />);
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    expect(mocked.deleteProject).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /delete project/i }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/projects"));
    expect(mocked.deleteProject).toHaveBeenCalledWith(5);
  });

  it("keeps Save disabled until something changes", async () => {
    render(<ProjectDetailPage />);
    const save = (await screen.findByRole("button", { name: /save changes/i })) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Beta" } });
    expect(save.disabled).toBe(false);
  });
});
