"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Bot, Plus } from "lucide-react";

import { ImportFromIssue } from "@/components/ImportFromIssue";
import { ErrorAlert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Task } from "@/lib/types";
import { formatDate } from "@/lib/utils";

const EMPTY = {
  repo_url: "",
  base_commit: "",
  test_command: "",
  target_path: "",
  description: "",
};

export default function TasksPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ ...EMPTY });
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [user, authLoading, router]);

  const load = useCallback(async () => {
    setError(null);
    try {
      setTasks(await api.listTasks());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load tasks");
    }
  }, []);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  function set(field: keyof typeof EMPTY, value: string) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setCreating(true);
    try {
      const task = await api.createTask({
        repo_url: form.repo_url.trim(),
        base_commit: form.base_commit.trim() || null,
        test_command: form.test_command.trim(),
        target_path: form.target_path.trim() || null,
        description: form.description.trim() || null,
      });
      setForm({ ...EMPTY });
      await load();
      router.push(`/tasks/${task.id}`);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Failed to create task");
    } finally {
      setCreating(false);
    }
  }

  if (authLoading || !user) {
    return (
      <div className="flex justify-center py-24 text-muted-foreground">
        <Spinner className="mr-2" /> Loading…
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Bot className="h-6 w-6 text-primary" /> Agent tasks
        </h1>
        <p className="text-sm text-muted-foreground">
          Import a GitHub issue (or point at any repo with a failing test); the agent proposes a
          fix and opens a PR after your approval.
        </p>
      </div>

      <ImportFromIssue onCreated={(task) => router.push(`/tasks/${task.id}`)} />

      <details className="group">
        <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">
          Or create a task manually (any git URL)
        </summary>
        <Card className="mt-3">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Plus className="h-4 w-4" /> New task
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleCreate} className="space-y-4">
              {formError && <ErrorAlert message={formError} />}
              <div>
                <Label htmlFor="repo_url">Repository URL</Label>
                <Input
                  id="repo_url"
                  value={form.repo_url}
                  onChange={(e) => set("repo_url", e.target.value)}
                  placeholder="https://github.com/you/repo.git"
                  required
                />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label htmlFor="target_path">Target file (optional)</Label>
                  <Input
                    id="target_path"
                    value={form.target_path}
                    onChange={(e) => set("target_path", e.target.value)}
                    placeholder="empty = let the agent find it"
                  />
                </div>
                <div>
                  <Label htmlFor="base_commit">Base commit (optional)</Label>
                  <Input
                    id="base_commit"
                    value={form.base_commit}
                    onChange={(e) => set("base_commit", e.target.value)}
                    placeholder="HEAD if empty"
                  />
                </div>
              </div>
              <div>
                <Label htmlFor="test_command">Test command</Label>
                <Input
                  id="test_command"
                  value={form.test_command}
                  onChange={(e) => set("test_command", e.target.value)}
                  placeholder="python -m unittest test_calculator"
                  required
                />
              </div>
              <div>
                <Label htmlFor="description">Description (optional)</Label>
                <Textarea
                  id="description"
                  value={form.description}
                  onChange={(e) => set("description", e.target.value)}
                  placeholder="What should the agent fix?"
                />
              </div>
              <Button type="submit" disabled={creating}>
                {creating && <Spinner />}
                Create task
              </Button>
            </form>
          </CardContent>
        </Card>
      </details>

      <section>
        {error && <ErrorAlert message={error} className="mb-4" />}
        {tasks === null && !error ? (
          <div className="flex justify-center py-12 text-muted-foreground">
            <Spinner className="mr-2" /> Loading tasks…
          </div>
        ) : tasks && tasks.length === 0 ? (
          <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border py-12 text-center text-muted-foreground">
            <Bot className="h-8 w-8" />
            <p>No tasks yet. Create one above to run the agent.</p>
          </div>
        ) : (
          <ul className="space-y-3">
            {tasks?.map((task) => (
              <li key={task.id}>
                <Link href={`/tasks/${task.id}`}>
                  <Card className="transition-colors hover:border-primary">
                    <CardContent className="p-4">
                      <div className="flex items-center justify-between gap-4">
                        <div className="min-w-0">
                          <p className="truncate font-medium">
                            {task.repo_full_name ?? task.repo_url}
                            {task.issue_number && (
                              <span className="text-muted-foreground">
                                {" "}
                                #{task.issue_number} {task.issue_title}
                              </span>
                            )}
                          </p>
                          <p className="truncate font-mono text-xs text-muted-foreground">
                            {task.target_path ?? "file: auto"} · {task.test_command}
                          </p>
                        </div>
                        <span className="shrink-0 text-xs text-muted-foreground">
                          {formatDate(task.created_at)}
                        </span>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
