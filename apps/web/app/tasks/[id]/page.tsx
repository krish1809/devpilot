"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ExternalLink, Play } from "lucide-react";

import { ErrorAlert } from "@/components/ui/alert";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AgentRun, Task } from "@/lib/types";
import { formatDate } from "@/lib/utils";

export default function TaskDetailPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const taskId = Number(params.id);

  const [task, setTask] = useState<Task | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const [run, setRun] = useState<AgentRun | null>(null);
  const [running, setRunning] = useState(false);
  const [acting, setActing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [user, authLoading, router]);

  const load = useCallback(async () => {
    setLoadError(null);
    setNotFound(false);
    try {
      setTask(await api.getTask(taskId));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setNotFound(true);
      else setLoadError(err instanceof ApiError ? err.message : "Failed to load task");
    }
  }, [taskId]);

  useEffect(() => {
    if (user && Number.isFinite(taskId)) load();
  }, [user, taskId, load]);

  async function handleRun() {
    setActionError(null);
    setRunning(true);
    setRun(null);
    try {
      setRun(await api.runTask(taskId));
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Run failed");
    } finally {
      setRunning(false);
    }
  }

  async function handleApprove(decision: "approved" | "rejected") {
    if (!run) return;
    setActionError(null);
    setActing(true);
    try {
      setRun(await api.approveRun(run.id, decision));
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Action failed");
    } finally {
      setActing(false);
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
    <div className="mx-auto max-w-3xl space-y-6">
      <Link
        href="/tasks"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" /> Back to tasks
      </Link>

      {notFound ? (
        <ErrorAlert message="Task not found (it may not exist or may not be yours)." />
      ) : loadError ? (
        <ErrorAlert message={loadError} />
      ) : task === null ? (
        <div className="flex justify-center py-12 text-muted-foreground">
          <Spinner className="mr-2" /> Loading task…
        </div>
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="break-all text-lg">
                {task.repo_full_name ?? task.repo_url}
              </CardTitle>
              {task.issue_number && (
                <a
                  href={task.issue_url ?? "#"}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
                >
                  #{task.issue_number} {task.issue_title} <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>
                <span className="text-muted-foreground">Target file:</span>{" "}
                <span className="font-mono">{task.target_path}</span>
              </p>
              <p>
                <span className="text-muted-foreground">Test:</span>{" "}
                <span className="font-mono">{task.test_command}</span>
              </p>
              <p>
                <span className="text-muted-foreground">Base:</span>{" "}
                <span className="font-mono">
                  {task.base_branch ?? "default branch"} @ {task.base_commit?.slice(0, 12) || "HEAD"}
                </span>
              </p>
              {task.description && (
                <p className="whitespace-pre-wrap text-muted-foreground">{task.description}</p>
              )}
              <div className="pt-2">
                <Button onClick={handleRun} disabled={running}>
                  {running ? <Spinner /> : <Play className="h-4 w-4" />}
                  {running ? "Running agent…" : "Run agent"}
                </Button>
                {running && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Cloning, calling the model, and running the test in a sandbox — this can take up to a minute.
                  </p>
                )}
              </div>
            </CardContent>
          </Card>

          {actionError && <ErrorAlert message={actionError} />}

          {run && <RunView run={run} onApprove={handleApprove} acting={acting} />}
        </>
      )}
    </div>
  );
}

function RunView({
  run,
  onApprove,
  acting,
}: {
  run: AgentRun;
  onApprove: (d: "approved" | "rejected") => void;
  acting: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between text-base">
          <span>Run #{run.id}</span>
          <StatusBadge status={run.status} />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-xs text-muted-foreground">
          model <span className="font-mono">{run.model}</span> ·{" "}
          {run.base_commit && (
            <>
              commit <span className="font-mono">{run.base_commit.slice(0, 7)}</span> ·{" "}
            </>
          )}
          test {run.test_passed === null ? "—" : run.test_passed ? "passed ✓" : "failed ✗"} ·{" "}
          {formatDate(run.updated_at)}
        </p>

        {run.error && <ErrorAlert message={run.error} />}

        {run.events.length > 0 && (
          <div>
            <p className="mb-1 text-sm font-medium">Timeline</p>
            <ol className="space-y-1 text-sm">
              {run.events.map((e) => (
                <li key={e.id} className="flex gap-2">
                  <span className="w-20 shrink-0 font-mono text-xs text-muted-foreground">
                    {e.stage}
                  </span>
                  <span className="text-muted-foreground">{e.message}</span>
                </li>
              ))}
            </ol>
          </div>
        )}

        {run.diff && (
          <div>
            <p className="mb-1 text-sm font-medium">Proposed diff</p>
            <pre className="max-h-96 overflow-auto rounded-md border border-border bg-muted p-3 font-mono text-xs">
              {run.diff}
            </pre>
          </div>
        )}

        {run.pull_request && (
          <a
            href={run.pull_request.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
          >
            <ExternalLink className="h-4 w-4" /> View pull request #{run.pull_request.number}
          </a>
        )}

        {run.status === "validated" && (
          <div className="flex gap-2 border-t border-border pt-4">
            <Button onClick={() => onApprove("approved")} disabled={acting}>
              {acting && <Spinner />} Approve &amp; open PR
            </Button>
            <Button variant="secondary" onClick={() => onApprove("rejected")} disabled={acting}>
              Reject
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
