// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ImportFromIssue } from "./ImportFromIssue";
import { api } from "@/lib/api";

vi.mock("@/lib/api", async (orig) => {
  const actual = await orig<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      listRepos: vi.fn(),
      listIssues: vi.fn(),
      getTree: vi.fn(),
      createTaskFromIssue: vi.fn(),
    },
  };
});

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

beforeEach(() => {
  mocked.listRepos.mockResolvedValue([
    {
      full_name: "octo/demo",
      private: false,
      default_branch: "main",
      description: null,
      html_url: "https://github.com/octo/demo",
      open_issues_count: 1,
      can_push: true,
    },
  ]);
  mocked.listIssues.mockResolvedValue([
    {
      number: 2,
      title: "percent() returns 0",
      state: "open",
      html_url: "https://github.com/octo/demo/issues/2",
      labels: ["bug"],
      created_at: "2026-10-01T00:00:00Z",
    },
  ]);
  mocked.getTree.mockResolvedValue({
    repo_full_name: "octo/demo",
    ref: "main",
    commit_sha: "5eec58f0eaa835c2e5d48884769ee91a3e6572b1",
    files: ["calculator.py", "test_calculator.py"],
  });
  mocked.createTaskFromIssue.mockResolvedValue({ id: 7 });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ImportFromIssue", () => {
  it("imports the chosen issue pinned to the branch, letting the agent find the file", async () => {
    const onCreated = vi.fn();
    render(<ImportFromIssue onCreated={onCreated} />);

    const repo = await screen.findByLabelText("Repository");
    fireEvent.change(repo, { target: { value: "octo/demo" } });

    fireEvent.click(await screen.findByText(/percent\(\) returns 0/));
    expect(screen.getByText("5eec58f")).toBeTruthy(); // shows the pinned commit
    fireEvent.change(screen.getByLabelText("Test command"), {
      target: { value: "python -m unittest" },
    });
    fireEvent.click(screen.getByRole("button", { name: /import issue as task/i }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith({ id: 7 }));
    expect(mocked.createTaskFromIssue).toHaveBeenCalledWith({
      repo_full_name: "octo/demo",
      issue_number: 2,
      base_branch: "main",
      target_path: null, // left empty → the agent localizes it
      test_command: "python -m unittest",
    });
  });

  it("keeps the import button disabled until an issue is picked", async () => {
    render(<ImportFromIssue onCreated={vi.fn()} />);
    fireEvent.change(await screen.findByLabelText("Repository"), {
      target: { value: "octo/demo" },
    });
    const button = await screen.findByRole("button", { name: /import issue as task/i });
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows the API error when repositories can't be listed", async () => {
    mocked.listRepos.mockRejectedValue(new Error("boom"));
    render(<ImportFromIssue onCreated={vi.fn()} />);
    expect(await screen.findByText("Failed to load repositories")).toBeTruthy();
  });
});
