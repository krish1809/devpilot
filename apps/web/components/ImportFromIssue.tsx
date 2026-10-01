"use client";

import { useEffect, useMemo, useState } from "react";
import { CircleDot, Github } from "lucide-react";

import { ErrorAlert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { api, ApiError } from "@/lib/api";
import type { GitHubIssue, GitHubRepo, GitHubTree, Task } from "@/lib/types";

const errMsg = (err: unknown, fallback: string) =>
  err instanceof ApiError ? err.message : fallback;

/** Pick a repo → an open issue → the file to fix, and import it as a task. */
export function ImportFromIssue({ onCreated }: { onCreated: (task: Task) => void }) {
  const [repos, setRepos] = useState<GitHubRepo[] | null>(null);
  const [reposError, setReposError] = useState<string | null>(null);

  const [repo, setRepo] = useState("");
  const [issues, setIssues] = useState<GitHubIssue[] | null>(null);
  const [tree, setTree] = useState<GitHubTree | null>(null);
  const [repoLoading, setRepoLoading] = useState(false);
  const [repoError, setRepoError] = useState<string | null>(null);

  const [issueNumber, setIssueNumber] = useState<number | null>(null);
  const [targetPath, setTargetPath] = useState("");
  const [testCommand, setTestCommand] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listRepos()
      .then(setRepos)
      .catch((err) => setReposError(errMsg(err, "Failed to load repositories")));
  }, []);

  useEffect(() => {
    setIssues(null);
    setTree(null);
    setIssueNumber(null);
    setTargetPath("");
    setRepoError(null);
    if (!repo) return;
    let cancelled = false;
    setRepoLoading(true);
    Promise.all([api.listIssues(repo), api.getTree(repo)])
      .then(([i, t]) => {
        if (cancelled) return;
        setIssues(i);
        setTree(t);
      })
      .catch((err) => !cancelled && setRepoError(errMsg(err, "Failed to load repository")))
      .finally(() => !cancelled && setRepoLoading(false));
    return () => {
      cancelled = true;
    };
  }, [repo]);

  const selectedRepo = useMemo(() => repos?.find((r) => r.full_name === repo), [repos, repo]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!repo || issueNumber === null || !tree) return;
    setSubmitError(null);
    setSubmitting(true);
    try {
      const task = await api.createTaskFromIssue({
        repo_full_name: repo,
        issue_number: issueNumber,
        base_branch: tree.ref,
        target_path: targetPath.trim(),
        test_command: testCommand.trim(),
      });
      onCreated(task);
    } catch (err) {
      setSubmitError(errMsg(err, "Failed to import issue"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Github className="h-4 w-4" /> Import a GitHub issue
        </CardTitle>
      </CardHeader>
      <CardContent>
        {reposError ? (
          <ErrorAlert message={reposError} />
        ) : repos === null ? (
          <div className="flex items-center text-sm text-muted-foreground">
            <Spinner className="mr-2" /> Loading repositories…
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            {submitError && <ErrorAlert message={submitError} />}
            <div>
              <Label htmlFor="gh_repo">Repository</Label>
              <Select id="gh_repo" value={repo} onChange={(e) => setRepo(e.target.value)} required>
                <option value="">Select a repository…</option>
                {repos.map((r) => (
                  <option key={r.full_name} value={r.full_name}>
                    {r.full_name}
                    {r.private ? " (private)" : ""}
                    {r.can_push ? "" : " — read-only"}
                  </option>
                ))}
              </Select>
              {selectedRepo && !selectedRepo.can_push && (
                <p className="mt-1 text-xs text-muted-foreground">
                  The token can&apos;t push here, so opening a PR will fail.
                </p>
              )}
            </div>

            {repoError && <ErrorAlert message={repoError} />}
            {repoLoading && (
              <div className="flex items-center text-sm text-muted-foreground">
                <Spinner className="mr-2" /> Loading issues and files…
              </div>
            )}

            {issues && tree && (
              <>
                <p className="text-xs text-muted-foreground">
                  Base: <span className="font-mono">{tree.ref}</span> @{" "}
                  <span className="font-mono">{tree.commit_sha.slice(0, 7)}</span> — the task is
                  pinned to this commit.
                </p>
                <div>
                  <Label>Issue</Label>
                  {issues.length === 0 ? (
                    <p className="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground">
                      No open issues in this repository.
                    </p>
                  ) : (
                    <ul className="max-h-60 space-y-1 overflow-auto rounded-md border border-border p-1">
                      {issues.map((i) => (
                        <li key={i.number}>
                          <button
                            type="button"
                            onClick={() => setIssueNumber(i.number)}
                            className={`flex w-full items-start gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-muted ${
                              issueNumber === i.number ? "bg-muted ring-1 ring-primary" : ""
                            }`}
                          >
                            <CircleDot className="mt-0.5 h-4 w-4 shrink-0 text-green-600" />
                            <span className="min-w-0">
                              <span className="text-muted-foreground">#{i.number}</span> {i.title}
                              {i.labels.length > 0 && (
                                <span className="ml-2 text-xs text-muted-foreground">
                                  [{i.labels.join(", ")}]
                                </span>
                              )}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <Label htmlFor="gh_target">File to fix</Label>
                    <Input
                      id="gh_target"
                      list="gh_files"
                      value={targetPath}
                      onChange={(e) => setTargetPath(e.target.value)}
                      placeholder="path/to/file.py"
                      required
                    />
                    <datalist id="gh_files">
                      {tree.files.map((f) => (
                        <option key={f} value={f} />
                      ))}
                    </datalist>
                  </div>
                  <div>
                    <Label htmlFor="gh_test">Test command</Label>
                    <Input
                      id="gh_test"
                      value={testCommand}
                      onChange={(e) => setTestCommand(e.target.value)}
                      placeholder="python -m unittest test_calculator"
                      required
                    />
                  </div>
                </div>
                <Button type="submit" disabled={submitting || issueNumber === null}>
                  {submitting && <Spinner />}
                  Import issue as task
                </Button>
              </>
            )}
          </form>
        )}
      </CardContent>
    </Card>
  );
}
