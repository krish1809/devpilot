"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ExternalLink, Play, RotateCcw, Square } from "lucide-react";

import { ErrorAlert } from "@/components/ui/alert";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type {
  AgentRun,
  RunCheckpoint,
  RunRetrieval,
  RunSummary,
  RunTrace,
  Task,
} from "@/lib/types";
import { formatDate } from "@/lib/utils";

const POLL_MS = 1500;

const errMsg = (err: unknown, fallback: string) =>
  err instanceof ApiError ? err.message : fallback;

export default function TaskDetailPage() {
  const { user, loading: authLoading, demoMode } = useAuth();
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const taskId = Number(params.id);

  const [task, setTask] = useState<Task | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [run, setRun] = useState<AgentRun | null>(null);
  const [starting, setStarting] = useState(false);
  const [acting, setActing] = useState(false);
  const [useRag, setUseRag] = useState(true);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [user, authLoading, router]);

  const loadRuns = useCallback(async () => {
    const list = await api.listTaskRuns(taskId);
    setRuns(list);
    return list;
  }, [taskId]);

  const load = useCallback(async () => {
    setLoadError(null);
    setNotFound(false);
    try {
      setTask(await api.getTask(taskId));
      const list = await loadRuns();
      if (list.length > 0) setRun(await api.getRun(list[0].id));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setNotFound(true);
      else setLoadError(errMsg(err, "Failed to load task"));
    }
  }, [taskId, loadRuns]);

  useEffect(() => {
    if (user && Number.isFinite(taskId)) load();
  }, [user, taskId, load]);

  // Poll while the graph is working in the background.
  const runId = run?.id;
  const isRunning = run?.status === "running";
  useEffect(() => {
    if (!runId || !isRunning) return;
    const timer = setInterval(async () => {
      try {
        const next = await api.getRun(runId);
        setRun(next);
        if (next.status !== "running") loadRuns().catch(() => undefined);
      } catch {
        /* transient polling failure: try again next tick */
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [runId, isRunning, loadRuns]);

  async function act(fn: () => Promise<AgentRun>, fallback: string) {
    setActionError(null);
    setActing(true);
    try {
      setRun(await fn());
      await loadRuns();
    } catch (err) {
      setActionError(errMsg(err, fallback));
    } finally {
      setActing(false);
    }
  }

  async function handleRun() {
    setStarting(true);
    await act(() => api.runTask(taskId, useRag), "Could not start the run");
    setStarting(false);
  }

  async function selectRun(id: number) {
    setActionError(null);
    try {
      setRun(await api.getRun(id));
    } catch (err) {
      setActionError(errMsg(err, "Failed to load run"));
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
                  #{task.issue_number} {task.issue_title}{" "}
                  <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>
                <span className="text-muted-foreground">Target file:</span>{" "}
                <span className="font-mono">
                  {task.target_path ?? "not set — the agent localizes it"}
                </span>
              </p>
              <p>
                <span className="text-muted-foreground">Test:</span>{" "}
                <span className="font-mono">{task.test_command}</span>
              </p>
              <p>
                <span className="text-muted-foreground">Base:</span>{" "}
                <span className="font-mono">
                  {task.base_branch ?? "default branch"} @{" "}
                  {task.base_commit?.slice(0, 12) || "HEAD"}
                </span>
              </p>
              {task.description && (
                <p className="whitespace-pre-wrap text-muted-foreground">
                  {task.description}
                </p>
              )}
              {!demoMode && (
                <div className="flex flex-wrap items-center gap-4 pt-2">
                  <Button onClick={handleRun} disabled={starting || isRunning}>
                    {starting ? <Spinner /> : <Play className="h-4 w-4" />}
                    {isRunning
                      ? "Agent is running…"
                      : runs.length
                        ? "Run again"
                        : "Run agent"}
                  </Button>
                  <label className="inline-flex items-center gap-2 text-sm text-muted-foreground">
                    <input
                      type="checkbox"
                      checked={useRag}
                      onChange={(e) => setUseRag(e.target.checked)}
                    />
                    Use repository context (RAG)
                  </label>
                </div>
              )}
            </CardContent>
          </Card>

          {runs.length > 1 && (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-muted-foreground">Runs:</span>
              {runs.map((r) => (
                <button
                  key={r.id}
                  onClick={() => selectRun(r.id)}
                  className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 ${
                    r.id === run?.id
                      ? "border-primary"
                      : "border-border hover:border-primary"
                  }`}
                >
                  #{r.id} <StatusBadge status={r.status} />
                </button>
              ))}
            </div>
          )}

          {actionError && <ErrorAlert message={actionError} />}

          {run && (
            <RunView
              run={run}
              readOnly={demoMode}
              acting={acting}
              onApprove={(d) =>
                act(() => api.approveRun(run.id, d), "Action failed")
              }
              onCancel={() =>
                act(() => api.cancelRun(run.id), "Could not cancel")
              }
              onResume={() =>
                act(() => api.resumeRun(run.id), "Could not resume")
              }
            />
          )}
        </>
      )}
    </div>
  );
}

function RunView({
  run,
  readOnly,
  acting,
  onApprove,
  onCancel,
  onResume,
}: {
  run: AgentRun;
  readOnly: boolean;
  acting: boolean;
  onApprove: (d: "approved" | "rejected") => void;
  onCancel: () => void;
  onResume: () => void;
}) {
  const tokens = run.prompt_tokens + run.completion_tokens;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between text-base">
          <span className="flex items-center gap-2">
            Run #{run.id} {run.status === "running" && <Spinner />}
          </span>
          <StatusBadge status={run.status} />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-xs text-muted-foreground">
          model <span className="font-mono">{run.model}</span> ·{" "}
          {run.base_commit && (
            <>
              commit{" "}
              <span className="font-mono">{run.base_commit.slice(0, 7)}</span>{" "}
              ·{" "}
            </>
          )}
          {run.attempts} attempt{run.attempts === 1 ? "" : "s"} ·{" "}
          {run.llm_calls} LLM call
          {run.llm_calls === 1 ? "" : "s"} · {tokens.toLocaleString()} tokens ·
          test{" "}
          {run.test_passed === null
            ? "—"
            : run.test_passed
              ? "passed ✓"
              : "failed ✗"}{" "}
          · {formatDate(run.updated_at)}
        </p>

        {run.target_path && (
          <p className="text-sm">
            <span className="text-muted-foreground">Editing:</span>{" "}
            <span className="font-mono">{run.target_path}</span>
            {run.use_rag && (
              <span className="ml-2 text-xs text-muted-foreground">
                (RAG on)
              </span>
            )}
          </p>
        )}

        {run.error && <ErrorAlert message={run.error} />}

        {run.status === "running" && !readOnly && (
          <div className="flex items-center gap-3">
            <Button
              variant="secondary"
              onClick={onCancel}
              disabled={acting || run.cancel_requested}
            >
              <Square className="h-4 w-4" />
              {run.cancel_requested ? "Cancelling…" : "Cancel"}
            </Button>
            <span className="text-xs text-muted-foreground">
              Working in the background — this page updates live.
            </span>
          </div>
        )}

        {(run.status === "error" || run.status === "cancelled") &&
          !readOnly && (
            <Button variant="secondary" onClick={onResume} disabled={acting}>
              {acting ? <Spinner /> : <RotateCcw className="h-4 w-4" />} Resume
              from last checkpoint
            </Button>
          )}

        {run.plan && (
          <div>
            <p className="mb-1 text-sm font-medium">Plan</p>
            <pre className="whitespace-pre-wrap rounded-md border border-border bg-muted p-3 text-xs">
              {run.plan}
            </pre>
          </div>
        )}

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

        {run.sandbox_output && (
          <details>
            <summary className="cursor-pointer text-sm font-medium">
              Sandbox output
            </summary>
            <pre className="mt-1 max-h-72 overflow-auto rounded-md border border-border bg-muted p-3 font-mono text-xs">
              {run.sandbox_output}
            </pre>
          </details>
        )}

        {run.retrieval && <RetrievalView retrieval={run.retrieval} />}

        <TraceView runId={run.id} status={run.status} />

        <Checkpoints runId={run.id} status={run.status} />

        {run.pull_request && (
          <a
            href={run.pull_request.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
          >
            <ExternalLink className="h-4 w-4" /> View pull request #
            {run.pull_request.number}
          </a>
        )}

        {run.review_warnings && run.review_warnings.length > 0 && (
          <div className="rounded-md border border-warning/40 bg-warning/10 p-3 text-sm">
            <p className="mb-1 font-medium text-warning">
              Check before approving
            </p>
            <ul className="list-disc space-y-0.5 pl-5 text-muted-foreground">
              {run.review_warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
            <p className="mt-1 text-xs text-muted-foreground">
              The patch newly adds security-sensitive code. Repository and issue
              text are untrusted — make sure this isn&apos;t an injected
              instruction.
            </p>
          </div>
        )}

        {run.status === "validated" && !readOnly && (
          <div className="flex gap-2 border-t border-border pt-4">
            <Button onClick={() => onApprove("approved")} disabled={acting}>
              {acting && <Spinner />} Approve &amp; open PR
            </Button>
            <Button
              variant="secondary"
              onClick={() => onApprove("rejected")}
              disabled={acting}
            >
              Reject
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function RetrievalView({ retrieval }: { retrieval: RunRetrieval }) {
  const { index, candidates, context, boosted_paths } = retrieval;
  return (
    <details>
      <summary className="cursor-pointer text-sm font-medium">
        Retrieved context ({context.length} chunks · index of {index.files}{" "}
        files / {index.chunks} chunks
        {index.built_now ? ", built for this run" : ", reused"})
      </summary>
      <div className="mt-1 space-y-2 text-xs text-muted-foreground">
        {candidates.length > 0 && (
          <p>
            Candidate files:{" "}
            <span className="font-mono">{candidates.join(", ")}</span>
          </p>
        )}
        {boosted_paths.length > 0 && (
          <p>
            From the traceback:{" "}
            <span className="font-mono">{boosted_paths.join(", ")}</span>
          </p>
        )}
        <ol className="space-y-0.5 font-mono">
          {context.map((c) => (
            <li key={`${c.path}:${c.start_line}`}>
              {c.path}:{c.start_line}-{c.end_line}{" "}
              <span className="opacity-70">({c.score.toFixed(4)})</span>
            </li>
          ))}
        </ol>
        <p className="opacity-70">Embeddings: {index.model}</p>
      </div>
    </details>
  );
}

/** LLM calls and audited MCP tool calls for the run, loaded when expanded. */
function TraceView({ runId, status }: { runId: number; status: string }) {
  const [open, setOpen] = useState(false);
  const [trace, setTrace] = useState<RunTrace | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    api
      .getRunTrace(runId)
      .then(setTrace)
      .catch((err) => setError(errMsg(err, "Failed to load trace")));
  }, [open, runId, status]);

  return (
    <details onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary className="cursor-pointer text-sm font-medium">
        Trace (LLM + tool calls)
      </summary>
      {error ? (
        <ErrorAlert message={error} className="mt-2" />
      ) : trace === null ? (
        <p className="mt-1 text-xs text-muted-foreground">Loading…</p>
      ) : (
        <div className="mt-2 space-y-3 text-xs">
          <p className="text-muted-foreground">
            {trace.llm_calls.length} LLM calls ·{" "}
            {trace.total_tokens.toLocaleString()} tokens ·{" "}
            {(trace.llm_latency_ms / 1000).toFixed(1)}s model time ·{" "}
            {trace.tool_calls.length} tool calls
          </p>
          <table className="w-full">
            <thead className="text-left text-muted-foreground">
              <tr>
                <th className="pr-2">LLM call</th>
                <th className="pr-2">Prompt</th>
                <th className="pr-2">Completion</th>
                <th className="pr-2">Latency</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {trace.llm_calls.map((c) => (
                <tr key={c.id} className="border-t border-border">
                  <td className="pr-2">{c.node}</td>
                  <td className="pr-2">
                    {c.prompt_tokens.toLocaleString()}
                    {c.tokens_estimated && "~"}
                  </td>
                  <td className="pr-2">
                    {c.completion_tokens.toLocaleString()}
                  </td>
                  <td className="pr-2">{(c.latency_ms / 1000).toFixed(1)}s</td>
                  <td title={c.error ?? ""}>{c.ok ? "ok" : "error"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {trace.tool_calls.length > 0 && (
            <table className="w-full">
              <thead className="text-left text-muted-foreground">
                <tr>
                  <th className="pr-2">MCP tool</th>
                  <th className="pr-2">Decision</th>
                  <th className="pr-2">Latency</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {trace.tool_calls.map((t) => (
                  <tr key={t.id} className="border-t border-border">
                    <td className="pr-2">{t.tool}</td>
                    <td className="pr-2">
                      {!t.allowed ? "denied" : t.ok ? "allowed" : "failed"}
                    </td>
                    <td className="pr-2">
                      {(t.latency_ms / 1000).toFixed(1)}s
                    </td>
                    <td className="break-all text-muted-foreground">
                      {t.detail ?? ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </details>
  );
}

/** The run's persisted LangGraph checkpoints, loaded when expanded. */
function Checkpoints({ runId, status }: { runId: number; status: string }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<RunCheckpoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    api
      .getRunCheckpoints(runId)
      .then(setItems)
      .catch((err) => setError(errMsg(err, "Failed to load checkpoints")));
  }, [open, runId, status]);

  return (
    <details onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary className="cursor-pointer text-sm font-medium">
        Graph checkpoints
      </summary>
      {error ? (
        <ErrorAlert message={error} className="mt-2" />
      ) : items === null ? (
        <p className="mt-1 text-xs text-muted-foreground">Loading…</p>
      ) : items.length === 0 ? (
        <p className="mt-1 text-xs text-muted-foreground">
          No checkpoints for this run.
        </p>
      ) : (
        <ol className="mt-1 space-y-0.5 font-mono text-xs text-muted-foreground">
          {items.map((c) => (
            <li key={c.checkpoint_id}>
              step {c.step} → {c.next.length ? c.next.join(", ") : "end"}
              {c.waiting_for_approval && " (waiting for approval)"} · attempts{" "}
              {c.attempts} · llm {c.llm_calls}
            </li>
          ))}
        </ol>
      )}
    </details>
  );
}
