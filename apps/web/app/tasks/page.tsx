"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  Bot,
  ChevronRight,
  CircleDot,
  FileCode2,
  GitBranch,
  Github,
  Plus,
  TerminalSquare,
  X,
} from "lucide-react";

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
              className="inline-flex rounded-lg border border-border bg-background/60 p-1"
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
                    "inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    source === value
                      ? "bg-primary/15 text-foreground ring-1 ring-inset ring-primary/30"
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
                  className="card-interactive group flex items-center gap-4 rounded-xl border border-border bg-surface/70 p-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background sm:p-5"
                >
                  <span className="hidden h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-border bg-background/70 sm:flex">
                    {task.issue_number ? (
                      <CircleDot className="h-5 w-5 text-success-fg" aria-hidden />
                    ) : (
                      <GitBranch className="h-5 w-5 text-muted-foreground" aria-hidden />
                    )}
                  </span>
                  <div className="min-w-0 flex-1 space-y-1.5">
                    <p className="flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
                      <Github className="h-3.5 w-3.5 shrink-0" aria-hidden />
                      <span className="truncate">{task.repo_full_name ?? task.repo_url}</span>
                      {task.issue_number && (
                        <span className="shrink-0 rounded-full border border-border px-1.5 font-mono">
                          #{task.issue_number}
                        </span>
                      )}
                    </p>
                    <p className="line-clamp-2 font-medium leading-snug group-hover:text-foreground">
                      {task.issue_title ?? task.description ?? "Untitled task"}
                    </p>
                    <p className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                      <span className="inline-flex items-center gap-1.5 font-mono">
                        <FileCode2 className="h-3.5 w-3.5" aria-hidden />
                        {task.target_path ?? "auto-located"}
                      </span>
                      <span className="inline-flex min-w-0 max-w-full items-center gap-1.5 font-mono">
                        <TerminalSquare className="h-3.5 w-3.5 shrink-0" aria-hidden />
                        <span className="truncate">{task.test_command}</span>
                      </span>
                      <span>{formatDate(task.created_at)}</span>
                    </p>
                  </div>
                  <ChevronRight
                    className="h-5 w-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary"
                    aria-hidden
                  />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
