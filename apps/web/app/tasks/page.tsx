"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Bot, ChevronRight, GitBranch, Github, Plus, X } from "lucide-react";

import { ImportFromIssue } from "@/components/ImportFromIssue";
import { ErrorAlert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { EmptyState, ListSkeleton, PageHeader, PageLoading } from "@/components/ui/page";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Task } from "@/lib/types";
import { cn, formatDate } from "@/lib/utils";

const EMPTY = {
  repo_url: "",
  base_commit: "",
  test_command: "",
  target_path: "",
  description: "",
};

type Source = "issue" | "manual";

export default function TasksPage() {
  const { user, loading: authLoading, demoMode } = useAuth();
  const router = useRouter();
  const toast = useToast();

  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creatingOpen, setCreatingOpen] = useState(false);
  const [source, setSource] = useState<Source>("issue");
  const [form, setForm] = useState({ ...EMPTY });
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

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

  function created(task: Task) {
    toast({
      tone: "success",
      title: "Task created",
      description: "Run the agent when you're ready.",
    });
    router.push(`/tasks/${task.id}`);
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setFieldErrors({});
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
      created(task);
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fields).length) setFieldErrors(err.fields);
      else setFormError(err instanceof ApiError ? err.message : "Failed to create task");
    } finally {
      setCreating(false);
    }
  }

  if (authLoading || !user) return <PageLoading />;

  return (
    <div className="space-y-8">
      <PageHeader
        icon={Bot}
        title="Agent tasks"
        description={
          demoMode
            ? "Real runs recorded with DevPilot. Open one to see the plan, the retrieved context, the diff, the sandbox result, the trace and the pull request."
            : "Import a GitHub issue (or point at any repo with a failing test). The agent proposes a fix and opens a PR after your approval."
        }
        actions={
          !demoMode && (
            <Button
              onClick={() => setCreatingOpen((o) => !o)}
              aria-expanded={creatingOpen}
              aria-controls="new-task"
              variant={creatingOpen ? "outline" : "primary"}
            >
              {creatingOpen ? (
                <X className="h-4 w-4" aria-hidden />
              ) : (
                <Plus className="h-4 w-4" aria-hidden />
              )}
              {creatingOpen ? "Close" : "New task"}
            </Button>
          )
        }
      />

      {!demoMode && creatingOpen && (
        <Card id="new-task">
          <CardContent className="space-y-5 p-5">
            <div
              role="group"
              aria-label="Task source"
              className="inline-flex rounded-md border border-border p-0.5"
            >
              {(
                [
                  ["issue", "From a GitHub issue", Github],
                  ["manual", "Any git repository", GitBranch],
                ] as const
              ).map(([value, label, Icon]) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={source === value}
                  onClick={() => setSource(value)}
                  className={cn(
                    "inline-flex items-center gap-2 rounded px-3 py-1.5 text-sm font-medium transition-colors",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    source === value
                      ? "bg-muted text-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  <Icon className="h-4 w-4" aria-hidden />
                  {label}
                </button>
              ))}
            </div>

            {source === "issue" ? (
              <ImportFromIssue onCreated={created} />
            ) : (
              <form onSubmit={handleCreate} className="space-y-4">
                {formError && <ErrorAlert message={formError} />}
                <Field id="repo_url" label="Repository URL" error={fieldErrors.repo_url}>
                  {(c) => (
                    <Input
                      {...c}
                      value={form.repo_url}
                      onChange={(e) => set("repo_url", e.target.value)}
                      placeholder="https://github.com/you/repo.git"
                      required
                    />
                  )}
                </Field>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field
                    id="target_path"
                    label="Target file (optional)"
                    hint="Leave empty to let the agent find it."
                    error={fieldErrors.target_path}
                  >
                    {(c) => (
                      <Input
                        {...c}
                        value={form.target_path}
                        onChange={(e) => set("target_path", e.target.value)}
                        placeholder="src/module.py"
                      />
                    )}
                  </Field>
                  <Field
                    id="base_commit"
                    label="Base commit (optional)"
                    hint="HEAD if empty."
                    error={fieldErrors.base_commit}
                  >
                    {(c) => (
                      <Input
                        {...c}
                        value={form.base_commit}
                        onChange={(e) => set("base_commit", e.target.value)}
                        placeholder="5eec58f"
                      />
                    )}
                  </Field>
                </div>
                <Field id="test_command" label="Test command" error={fieldErrors.test_command}>
                  {(c) => (
                    <Input
                      {...c}
                      value={form.test_command}
                      onChange={(e) => set("test_command", e.target.value)}
                      placeholder="python -m unittest test_calculator"
                      required
                    />
                  )}
                </Field>
                <Field
                  id="description"
                  label="Description (optional)"
                  error={fieldErrors.description}
                >
                  {(c) => (
                    <Textarea
                      {...c}
                      value={form.description}
                      onChange={(e) => set("description", e.target.value)}
                      placeholder="What should the agent fix?"
                    />
                  )}
                </Field>
                <Button type="submit" disabled={creating}>
                  {creating && <Spinner />}
                  Create task
                </Button>
              </form>
            )}
          </CardContent>
        </Card>
      )}

      <section aria-label="Tasks" className="space-y-3">
        {error && (
          <div className="space-y-3">
            <ErrorAlert message={error} />
            <Button variant="outline" onClick={load}>
              Try again
            </Button>
          </div>
        )}
        {tasks === null && !error ? (
          <ListSkeleton label="Loading tasks" />
        ) : tasks && tasks.length === 0 ? (
          <EmptyState
            icon={Bot}
            title="No tasks yet"
            description={
              demoMode
                ? "The showcase data hasn't loaded yet."
                : "Create a task from a GitHub issue to run the agent on it."
            }
            action={
              !demoMode && (
                <Button onClick={() => setCreatingOpen(true)}>
                  <Plus className="h-4 w-4" aria-hidden /> New task
                </Button>
              )
            }
          />
        ) : (
          <ul className="space-y-3">
            {tasks?.map((task) => (
              <li key={task.id}>
                <Link
                  href={`/tasks/${task.id}`}
                  className="group block rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                >
                  <Card className="transition-colors group-hover:border-primary/60">
                    <CardContent className="flex items-center gap-4 p-4">
                      <div className="min-w-0 flex-1 space-y-1">
                        <p className="truncate text-sm text-muted-foreground">
                          {task.repo_full_name ?? task.repo_url}
                          {task.issue_number && ` · #${task.issue_number}`}
                        </p>
                        <p className="line-clamp-2 font-medium">
                          {task.issue_title ?? task.description ?? "Untitled task"}
                        </p>
                        <p className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                          <span className="font-mono">{task.target_path ?? "file: auto"}</span>
                          <span className="max-w-full truncate font-mono">{task.test_command}</span>
                          <span>{formatDate(task.created_at)}</span>
                        </p>
                      </div>
                      <ChevronRight
                        className="h-5 w-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
                        aria-hidden
                      />
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
