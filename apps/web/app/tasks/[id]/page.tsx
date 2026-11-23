"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Bot,
  CheckCircle2,
  ExternalLink,
  GitPullRequest,
  Play,
  RotateCcw,
  ShieldAlert,
  Square,
  XCircle,
} from "lucide-react";

import { DiffView } from "@/components/DiffView";
import { Disclosure, RunPipeline, SectionTitle, Timeline } from "@/components/RunParts";
import { Alert, ErrorAlert } from "@/components/ui/alert";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState, PageHeader, PageLoading, Skeleton } from "@/components/ui/page";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";
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
import { cn, formatDate } from "@/lib/utils";

const POLL_MS = 1500;

const errMsg = (err: unknown, fallback: string) =>
  err instanceof ApiError ? err.message : fallback;

const FINISHED_TOASTS: Record<string, { tone: "success" | "error" | "info"; title: string }> = {
  validated: { tone: "success", title: "Tests pass — the patch is ready for your review" },
  test_failed: { tone: "error", title: "The agent couldn't make the tests pass" },
  review_failed: { tone: "error", title: "The patch was refused by the review guard" },
  error: { tone: "error", title: "The run stopped with an error" },
  cancelled: { tone: "info", title: "Run cancelled" },
};

export default function TaskDetailPage() {
  const { user, loading: authLoading, demoMode } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const params = useParams<{ id: string }>();
  const taskId = Number(params.id);

  const [task, setTask] = useState<Task | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [run, setRun] = useState<AgentRun | null>(null);
  const [starting, setStarting] = useState(false);
  const [acting, setActing] = useState<null | "approve" | "reject" | "cancel" | "resume">(null);
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

  // Toast once when a run we watched leave "running" finishes.
  const watched = useRef<number | null>(null);

  // While the graph works in the background, stream its progress (SSE); fall
  // back to polling if the stream can't be opened or ends early.
  const runId = run?.id;
  const isRunning = run?.status === "running";
  useEffect(() => {
    if (!runId || !isRunning) return;
    watched.current = runId;
    const controller = new AbortController();
    let timer: ReturnType<typeof setInterval> | undefined;
    let finished = false;

    const onUpdate = (next: AgentRun) => {
      setRun(next);
      if (next.status !== "running" && !finished) {
        finished = true;
        loadRuns().catch(() => undefined);
        const t = FINISHED_TOASTS[next.status];
        if (t && watched.current === next.id) toast({ ...t, description: `Run #${next.id}` });
      }
    };
    const startPolling = () => {
      if (finished || controller.signal.aborted || timer) return;
      timer = setInterval(async () => {
        try {
          onUpdate(await api.getRun(runId));
        } catch {
          /* transient polling failure: try again next tick */
        }
      }, POLL_MS);
    };

    api.streamRun(runId, onUpdate, controller.signal).then(startPolling, startPolling); // no-op once the run has finished

    return () => {
      controller.abort();
      if (timer) clearInterval(timer);
    };
  }, [runId, isRunning, loadRuns, toast]);

  async function act(
    kind: NonNullable<typeof acting>,
    fn: () => Promise<AgentRun>,
    fallback: string,
    success?: string,
  ) {
    setActionError(null);
    setActing(kind);
    try {
      const next = await fn();
      setRun(next);
      await loadRuns();
      if (success) toast({ tone: "success", title: success, description: `Run #${next.id}` });
    } catch (err) {
      setActionError(errMsg(err, fallback));
      toast({ tone: "error", title: fallback });
    } finally {
      setActing(null);
    }
  }

  async function handleRun() {
    setStarting(true);
    setActionError(null);
    try {
      const next = await api.runTask(taskId, useRag);
      setRun(next);
      await loadRuns();
      toast({ tone: "info", title: "Agent started", description: "This page updates live." });
    } catch (err) {
      setActionError(errMsg(err, "Could not start the run"));
    } finally {
      setStarting(false);
    }
  }

  async function selectRun(id: number) {
    setActionError(null);
    try {
      setRun(await api.getRun(id));
    } catch (err) {
      setActionError(errMsg(err, "Failed to load run"));
    }
  }

  if (authLoading || !user) return <PageLoading />;

  const back = { href: "/tasks", label: "All tasks" };

  if (notFound) {
    return (
      <div className="space-y-6">
        <PageHeader title="Task not found" back={back} />
        <EmptyState
          icon={Bot}
          title="This task doesn't exist"
          description="It may have been removed, or it belongs to another account."
        />
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="space-y-6">
        <PageHeader title="Task" back={back} />
        <ErrorAlert message={loadError} />
        <Button variant="outline" onClick={load}>
          Try again
        </Button>
      </div>
    );
  }

  if (task === null) {
    return (
      <div role="status" aria-label="Loading task" className="space-y-6">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-9 w-2/3" />
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <Skeleton className="h-96" />
          <Skeleton className="h-64" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        back={back}
        title={task.repo_full_name ?? task.repo_url}
        description={
          task.issue_number ? (
            <a
              href={task.issue_url ?? "#"}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
            >
              #{task.issue_number} {task.issue_title}
              <ExternalLink className="h-3.5 w-3.5 shrink-0" aria-hidden />
              <span className="sr-only">(opens GitHub)</span>
            </a>
          ) : undefined
        }
      />

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        {/* Task facts + controls: first on mobile, a sidebar on large screens. */}
        <aside className="space-y-4 lg:order-2 lg:sticky lg:top-20">
          <Card>
            <CardContent className="space-y-4 p-5">
              <dl className="space-y-3 text-sm">
                <Fact label="File to fix">
                  {task.target_path ?? (
                    <span className="text-muted-foreground">found by the agent</span>
                  )}
                </Fact>
                <Fact label="Test command">{task.test_command}</Fact>
                <Fact label="Base">
                  {task.base_branch ?? "default branch"} @{" "}
                  {task.base_commit?.slice(0, 12) || "HEAD"}
                </Fact>
              </dl>
              {!demoMode && (
                <div className="space-y-3 border-t border-border pt-4">
                  <label className="flex items-start gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={useRag}
                      onChange={(e) => setUseRag(e.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-border accent-[hsl(var(--primary))]"
                    />
                    <span>
                      Use repository context (RAG)
                      <span className="block text-xs text-muted-foreground">
                        Retrieves related code to find and fix the real bug.
                      </span>
                    </span>
                  </label>
                  <Button className="w-full" onClick={handleRun} disabled={starting || isRunning}>
                    {starting || isRunning ? <Spinner /> : <Play className="h-4 w-4" aria-hidden />}
                    {isRunning ? "Agent is running…" : runs.length ? "Run again" : "Run agent"}
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
          {task.description && (
            <Disclosure title="Issue text">
              <p className="whitespace-pre-wrap break-words text-sm text-muted-foreground">
                {task.description}
              </p>
            </Disclosure>
          )}
        </aside>

        <section aria-label="Runs" className="min-w-0 space-y-4 lg:order-1">
          {runs.length > 1 && (
            <div className="flex items-center gap-2 overflow-x-auto pb-1">
              <span className="shrink-0 text-sm text-muted-foreground">Runs</span>
              {runs.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => selectRun(r.id)}
                  aria-pressed={r.id === run?.id}
                  className={cn(
                    "inline-flex shrink-0 items-center gap-1.5 rounded-md border px-2 py-1 text-sm transition-colors",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    r.id === run?.id
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/60",
                  )}
                >
                  #{r.id} <StatusBadge status={r.status} />
                </button>
              ))}
            </div>
          )}

          {actionError && <ErrorAlert message={actionError} />}

          {run ? (
            <RunView
              run={run}
              readOnly={demoMode}
              acting={acting}
              onApprove={(d) =>
                act(
                  d === "approved" ? "approve" : "reject",
                  () => api.approveRun(run.id, d),
                  d === "approved" ? "Could not open the pull request" : "Could not reject the run",
                  d === "approved" ? "Approved — pull request opened" : "Patch rejected",
                )
              }
              onCancel={() =>
                act("cancel", () => api.cancelRun(run.id), "Could not cancel", "Cancel requested")
              }
              onResume={() =>
                act("resume", () => api.resumeRun(run.id), "Could not resume", "Run resumed")
              }
            />
          ) : (
            <EmptyState
              icon={Bot}
              title="No runs yet"
              description={
                demoMode
                  ? "This task hasn't been run."
                  : "Run the agent to get a plan, a patch and a sandboxed test result."
              }
            />
          )}
        </section>
      </div>
    </div>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 break-all font-mono text-[13px]">{children}</dd>
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
  acting: null | "approve" | "reject" | "cancel" | "resume";
  onApprove: (d: "approved" | "rejected") => void;
  onCancel: () => void;
  onResume: () => void;
}) {
  const tokens = run.prompt_tokens + run.completion_tokens;
  const awaitingApproval = run.status === "validated" && !readOnly;
  // Early showcase runs predate usage tracking: say so instead of showing 0.
  const untracked = run.llm_calls === 0 && Boolean(run.diff) && run.status !== "running";
  const notRecorded = (
    <span className="text-muted-foreground" title="This run predates usage tracking">
      not recorded
    </span>
  );
  const meta: [string, React.ReactNode][] = [
    [
      "Model",
      <span key="m" className="font-mono" title={run.model}>
        {run.model.replace(/^openai\//, "")}
      </span>,
    ],
    ["Attempts", untracked ? notRecorded : run.attempts],
    ["LLM calls", untracked ? notRecorded : run.llm_calls],
    ["Tokens", untracked ? notRecorded : tokens.toLocaleString()],
    [
      "Tests",
      run.test_passed === null ? (
        "—"
      ) : run.test_passed ? (
        <span key="t" className="inline-flex items-center gap-1 text-success-fg">
          <CheckCircle2 className="h-3.5 w-3.5" aria-hidden /> passed
        </span>
      ) : (
        <span key="t" className="inline-flex items-center gap-1 text-destructive-fg">
          <XCircle className="h-3.5 w-3.5" aria-hidden /> failed
        </span>
      ),
    ],
  ];

  return (
    <Card>
      <div className="space-y-4 border-b border-border px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            Run <span className="font-mono text-muted-foreground">#{run.id}</span>
          </h2>
          <StatusBadge status={run.status} />
        </div>
        <RunPipeline stages={run.events.map((e) => e.stage)} status={run.status} />
      </div>

      <CardContent className="space-y-6 p-5">
        <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-border bg-border text-sm sm:grid-cols-3 xl:grid-cols-5">
          {meta.map(([label, value]) => (
            <div key={label} className="min-w-0 bg-surface px-3.5 py-3">
              <dt className="text-[11px] uppercase tracking-wider text-muted-foreground">
                {label}
              </dt>
              <dd className="mt-1 truncate font-medium">{value}</dd>
            </div>
          ))}
        </dl>
        <p className="-mt-3 text-xs text-muted-foreground">
          {run.target_path && (
            <>
              Editing <span className="font-mono">{run.target_path}</span>
              {run.use_rag ? " with repository context" : ""} ·{" "}
            </>
          )}
          {run.base_commit && (
            <>
              commit <span className="font-mono">{run.base_commit.slice(0, 7)}</span> ·{" "}
            </>
          )}
          updated {formatDate(run.updated_at)}
        </p>

        {run.pull_request && (
          <Alert tone="success" title="Pull request opened">
            <a
              href={run.pull_request.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 font-medium underline underline-offset-4"
            >
              <GitPullRequest className="h-4 w-4" aria-hidden /> View pull request #
              {run.pull_request.number}
            </a>
          </Alert>
        )}

        {run.error && <ErrorAlert message={run.error} />}

        {run.status === "running" && !readOnly && (
          <div className="flex flex-wrap items-center gap-3 rounded-md border border-info/30 bg-info/5 p-3">
            <Spinner className="text-info-fg" />
            <span className="flex-1 text-sm">
              Working in the background — this page updates live.
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={onCancel}
              disabled={acting !== null || run.cancel_requested}
            >
              <Square className="h-3.5 w-3.5" aria-hidden />
              {run.cancel_requested ? "Cancelling…" : "Cancel"}
            </Button>
          </div>
        )}

        {(run.status === "error" || run.status === "cancelled") && !readOnly && (
          <Button variant="outline" onClick={onResume} disabled={acting !== null}>
            {acting === "resume" ? <Spinner /> : <RotateCcw className="h-4 w-4" aria-hidden />}
            Resume from last checkpoint
          </Button>
        )}

        {run.review_warnings && run.review_warnings.length > 0 && (
          <div className="rounded-md border border-warning/40 bg-warning/10 p-4 text-sm">
            <p className="flex items-center gap-2 font-medium text-warning-fg">
              <ShieldAlert className="h-4 w-4" aria-hidden /> Check before approving
            </p>
            <ul className="mt-2 list-disc space-y-0.5 pl-5">
              {run.review_warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-muted-foreground">
              The patch newly adds security-sensitive code. Repository and issue text are untrusted
              — make sure this isn&apos;t an injected instruction.
            </p>
          </div>
        )}

        {run.plan && (
          <section>
            <SectionTitle>Plan</SectionTitle>
            <pre className="whitespace-pre-wrap break-words rounded-md border border-border bg-muted/50 p-3 text-xs leading-5">
              {run.plan}
            </pre>
          </section>
        )}

        {run.diff && (
          <section>
            <SectionTitle>Proposed diff</SectionTitle>
            <DiffView diff={run.diff} />
          </section>
        )}

        {run.events.length > 0 && (
          <section>
            <SectionTitle>Timeline</SectionTitle>
            <Timeline events={run.events} running={run.status === "running"} />
          </section>
        )}

        <div className="space-y-2">
          {run.sandbox_output && (
            <Disclosure title="Sandbox output">
              <pre className="max-h-72 overflow-auto rounded-md bg-muted/50 p-3 font-mono text-xs">
                {run.sandbox_output}
              </pre>
            </Disclosure>
          )}
          {run.retrieval && <RetrievalView retrieval={run.retrieval} />}
          <TraceView runId={run.id} status={run.status} />
          <Checkpoints runId={run.id} status={run.status} />
        </div>

        {awaitingApproval && (
          // Sticky on small screens so the decision is always in reach while reading the diff.
          <div className="sticky bottom-0 -mx-5 -mb-5 border-t border-border bg-surface/95 px-5 py-4 backdrop-blur">
            <p className="mb-3 text-sm">
              <span className="font-medium">Your decision.</span>{" "}
              <span className="text-muted-foreground">
                Approving pushes a branch and opens a PR for exactly this diff.
              </span>
            </p>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button onClick={() => onApprove("approved")} disabled={acting !== null}>
                {acting === "approve" ? (
                  <Spinner />
                ) : (
                  <GitPullRequest className="h-4 w-4" aria-hidden />
                )}
                Approve &amp; open PR
              </Button>
              <Button
                variant="outline"
                onClick={() => onApprove("rejected")}
                disabled={acting !== null}
              >
                {acting === "reject" && <Spinner />}
                Reject
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function RetrievalView({ retrieval }: { retrieval: RunRetrieval }) {
  const { index, candidates, context, boosted_paths } = retrieval;
  return (
    <Disclosure
      title="Retrieved context"
      meta={`${context.length} chunks · ${index.files} files indexed${index.built_now ? " · built for this run" : ""}`}
    >
      <div className="space-y-2 text-xs text-muted-foreground">
        {candidates.length > 0 && (
          <p>
            Candidate files: <span className="break-all font-mono">{candidates.join(", ")}</span>
          </p>
        )}
        {boosted_paths.length > 0 && (
          <p>
            From the traceback:{" "}
            <span className="break-all font-mono">{boosted_paths.join(", ")}</span>
          </p>
        )}
        <ol className="space-y-0.5 font-mono">
          {context.map((c) => (
            <li key={`${c.path}:${c.start_line}`} className="break-all">
              {c.path}:{c.start_line}-{c.end_line}{" "}
              <span className="opacity-70">({c.score.toFixed(4)})</span>
            </li>
          ))}
        </ol>
        <p className="opacity-70">
          Embeddings: {index.model} · index of {index.chunks} chunks
        </p>
      </div>
    </Disclosure>
  );
}

const th = "whitespace-nowrap py-1.5 pr-4 font-medium";
const td = "whitespace-nowrap py-1.5 pr-4";

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
    <Disclosure title="Trace (LLM + tool calls)" onToggle={setOpen}>
      {error ? (
        <ErrorAlert message={error} />
      ) : trace === null ? (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Spinner /> Loading trace…
        </p>
      ) : (
        <div className="space-y-4 text-xs">
          <p className="text-muted-foreground">
            {trace.llm_calls.length} LLM calls · {trace.total_tokens.toLocaleString()} tokens ·{" "}
            {(trace.llm_latency_ms / 1000).toFixed(1)}s model time · {trace.tool_calls.length} tool
            calls
          </p>
          <div className="relative overflow-x-auto">
            <table className="w-full">
              <caption className="sr-only">LLM calls</caption>
              <thead className="text-left text-muted-foreground">
                <tr>
                  <th scope="col" className={th}>
                    LLM call
                  </th>
                  <th scope="col" className={th}>
                    Prompt
                  </th>
                  <th scope="col" className={th}>
                    Completion
                  </th>
                  <th scope="col" className={th}>
                    Latency
                  </th>
                  <th scope="col" className={th}>
                    Result
                  </th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {trace.llm_calls.map((c) => (
                  <tr key={c.id} className="border-t border-border">
                    <td className={td}>{c.node}</td>
                    <td className={td}>
                      {c.prompt_tokens.toLocaleString()}
                      {c.tokens_estimated && "~"}
                    </td>
                    <td className={td}>{c.completion_tokens.toLocaleString()}</td>
                    <td className={td}>{(c.latency_ms / 1000).toFixed(1)}s</td>
                    <td
                      className={cn(td, c.ok ? "text-success-fg" : "text-destructive-fg")}
                      title={c.error ?? ""}
                    >
                      {c.ok ? "ok" : "error"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {trace.tool_calls.length > 0 && (
            <div className="relative overflow-x-auto">
              <table className="w-full">
                <caption className="sr-only">MCP tool calls</caption>
                <thead className="text-left text-muted-foreground">
                  <tr>
                    <th scope="col" className={th}>
                      MCP tool
                    </th>
                    <th scope="col" className={th}>
                      Decision
                    </th>
                    <th scope="col" className={th}>
                      Latency
                    </th>
                    <th scope="col" className={th}>
                      Detail
                    </th>
                  </tr>
                </thead>
                <tbody className="font-mono">
                  {trace.tool_calls.map((t) => (
                    <tr key={t.id} className="border-t border-border">
                      <td className={td}>{t.tool}</td>
                      <td
                        className={cn(
                          td,
                          !t.allowed || !t.ok ? "text-destructive-fg" : "text-success-fg",
                        )}
                      >
                        {!t.allowed ? "denied" : t.ok ? "allowed" : "failed"}
                      </td>
                      <td className={td}>{(t.latency_ms / 1000).toFixed(1)}s</td>
                      <td className="min-w-[12rem] break-all py-1.5 text-muted-foreground">
                        {t.detail ?? ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </Disclosure>
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
    <Disclosure title="Graph checkpoints" onToggle={setOpen}>
      {error ? (
        <ErrorAlert message={error} />
      ) : items === null ? (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Spinner /> Loading checkpoints…
        </p>
      ) : items.length === 0 ? (
        <p className="text-xs text-muted-foreground">No checkpoints for this run.</p>
      ) : (
        <ol className="space-y-0.5 font-mono text-xs text-muted-foreground">
          {items.map((c) => (
            <li key={c.checkpoint_id}>
              step {c.step} → {c.next.length ? c.next.join(", ") : "end"}
              {c.waiting_for_approval && " (waiting for approval)"} · attempts {c.attempts} · llm{" "}
              {c.llm_calls}
            </li>
          ))}
        </ol>
      )}
    </Disclosure>
  );
}
