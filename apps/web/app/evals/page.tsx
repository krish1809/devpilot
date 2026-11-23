"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, CircleDashed, FlaskConical, Minus, X, XCircle } from "lucide-react";

import { DiffView } from "@/components/DiffView";
import { ErrorAlert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Select } from "@/components/ui/input";
import { EmptyState, PageHeader, PageLoading, Skeleton } from "@/components/ui/page";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { EvalConfigSummary, EvalResult, EvalRunDetail, EvalRunSummary } from "@/lib/types";
import { cn, formatDate } from "@/lib/utils";

const CONFIG_LABELS: Record<string, string> = {
  rag: "RAG, issue only (realistic)",
  "oracle-file": "Oracle file, no retrieval",
  "oracle-file+rag": "Oracle file + RAG context",
  gold: "Reference patch (environment ceiling)",
};

const pct = (x: number) => `${Math.round(x * 100)}%`;

const errMsg = (err: unknown, fallback: string) =>
  err instanceof ApiError ? err.message : fallback;

export default function EvalsPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [runs, setRuns] = useState<EvalRunSummary[] | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<EvalRunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [user, authLoading, router]);

  useEffect(() => {
    if (!user) return;
    api
      .listEvals()
      .then((list) => {
        setRuns(list);
        if (list.length) setSelected(list[0].id);
      })
      .catch((err) => setError(errMsg(err, "Failed to load benchmark runs")));
  }, [user]);

  useEffect(() => {
    if (selected === null) return;
    setDetail(null);
    api
      .getEval(selected)
      .then(setDetail)
      .catch((err) => setError(errMsg(err, "Failed to load benchmark run")));
  }, [selected]);

  if (authLoading || !user) return <PageLoading />;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={FlaskConical}
        title="Benchmarks"
        description={
          <>
            DevPilot on SWE-bench Lite, scored with the official SWE-bench harness. Produced by{" "}
            <code className="font-mono text-[0.9em]">python -m scripts.swebench_eval</code>.
          </>
        }
      />

      {error && <ErrorAlert message={error} />}

      {runs === null && !error ? (
        <div role="status" aria-label="Loading benchmark runs" className="space-y-4">
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-96 w-full" />
        </div>
      ) : runs && runs.length === 0 ? (
        <EmptyState
          icon={FlaskConical}
          title="No benchmark runs yet"
          description="Run the SWE-bench harness locally; results appear here."
        />
      ) : (
        runs && (
          <>
            {runs.length > 1 && (
              <Field id="eval-run" label="Benchmark run" className="max-w-md">
                {(c) => (
                  <Select
                    {...c}
                    value={selected ?? ""}
                    onChange={(e) => setSelected(Number(e.target.value))}
                  >
                    {runs.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.name} · {r.instance_count} instances · {formatDate(r.created_at)}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
            )}
            {detail ? (
              <RunDetail run={detail} />
            ) : (
              <div role="status" aria-label="Loading benchmark run" className="space-y-4">
                <Skeleton className="h-48 w-full" />
                <Skeleton className="h-96 w-full" />
              </div>
            )}
          </>
        )
      )}
    </div>
  );
}

function ResultMark({ r }: { r: EvalResult }) {
  if (r.resolved === true)
    return (
      <>
        <CheckCircle2 className="h-4 w-4 text-success-fg" aria-hidden />
        <span className="sr-only">resolved</span>
      </>
    );
  if (r.resolved === false)
    return (
      <>
        <XCircle className="h-4 w-4 text-destructive-fg" aria-hidden />
        <span className="sr-only">not resolved</span>
      </>
    );
  return (
    <>
      <CircleDashed className="h-4 w-4 text-muted-foreground" aria-hidden />
      <span className="sr-only">not scored yet</span>
    </>
  );
}

function RunDetail({ run }: { run: EvalRunDetail }) {
  const seed = run.settings["seed"];
  const attempted = new Set(
    run.results.filter((r) => r.config !== "gold").map((r) => r.instance_id),
  ).size;
  return (
    <>
      <ul
        aria-label="Resolve rate by configuration"
        className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
      >
        {run.summary.map((s) => {
          const rate = s.scored ? s.resolved / s.scored : 0;
          const gold = s.config === "gold";
          return (
            <li
              key={s.config}
              className="rounded-xl border border-border bg-surface/80 p-4 shadow-panel"
            >
              <p className="truncate text-xs text-muted-foreground">
                {CONFIG_LABELS[s.config] ?? s.config}
              </p>
              <p className="mt-2 flex items-baseline gap-1.5">
                <span
                  className={cn(
                    "text-3xl font-semibold tracking-tight",
                    gold ? "text-muted-foreground" : "text-gradient",
                  )}
                >
                  {s.resolved}
                </span>
                <span className="text-sm text-muted-foreground">/ {s.scored} resolved</span>
              </p>
              <div
                className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted"
                role="img"
                aria-label={`${pct(rate)} resolved`}
              >
                <div
                  className={cn(
                    "h-full rounded-full",
                    gold
                      ? "bg-muted-foreground/50"
                      : "bg-[linear-gradient(90deg,hsl(var(--primary)),hsl(var(--accent)))]",
                  )}
                  style={{ width: `${Math.round(rate * 100)}%` }}
                />
              </div>
              {gold && (
                <p className="mt-2 text-[11px] text-muted-foreground">
                  Reference patches: checks the harness itself.
                </p>
              )}
            </li>
          );
        })}
      </ul>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {run.name} — {attempted} of {run.instance_count} sampled instances attempted
            {seed !== undefined && ` (seed ${String(seed)})`}
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            {run.dataset} · model <span className="font-mono">{run.model}</span> · the agent never
            sees the benchmark&apos;s tests
          </p>
        </CardHeader>
        <CardContent className="relative overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Results per configuration</caption>
            <thead className="text-left text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="whitespace-nowrap py-1 pr-3 font-medium">
                  Config
                </th>
                <th scope="col" className="whitespace-nowrap py-1 pr-3 font-medium">
                  Resolved
                </th>
                <th scope="col" className="whitespace-nowrap py-1 pr-3 font-medium">
                  Rate (95% CI)
                </th>
                <th scope="col" className="whitespace-nowrap py-1 pr-3 font-medium">
                  Patch
                </th>
                <th scope="col" className="whitespace-nowrap py-1 pr-3 font-medium">
                  Gold file
                </th>
                <th scope="col" className="whitespace-nowrap py-1 pr-3 font-medium">
                  Tokens
                </th>
                <th scope="col" className="whitespace-nowrap py-1 font-medium">
                  Time
                </th>
              </tr>
            </thead>
            <tbody>
              {run.summary.map((s) => (
                <SummaryRow key={s.config} s={s} />
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
      <ResultsMatrix run={run} />
    </>
  );
}

function SummaryRow({ s }: { s: EvalConfigSummary }) {
  return (
    <tr className="border-t border-border">
      <th scope="row" className="min-w-[10rem] py-2 pr-3 text-left font-medium">
        {CONFIG_LABELS[s.config] ?? s.config}
      </th>
      <td className="py-2 pr-3 font-mono">
        {s.resolved}/{s.scored}
        {s.scored < s.generated && (
          <span className="ml-1 text-xs text-muted-foreground">
            ({s.generated - s.scored} unscored)
          </span>
        )}
      </td>
      <td className="whitespace-nowrap py-2 pr-3">
        {s.resolve_rate === null || !s.ci95
          ? "—"
          : `${pct(s.resolve_rate)} (${pct(s.ci95[0])}–${pct(s.ci95[1])})`}
      </td>
      <td className="py-2 pr-3 font-mono">
        {s.with_patch}/{s.generated}
      </td>
      <td className="py-2 pr-3 font-mono">
        {s.localized}/{s.generated}
      </td>
      <td className="py-2 pr-3 font-mono">{Math.round(s.avg_tokens).toLocaleString()}</td>
      <td className="py-2 font-mono">{Math.round(s.avg_seconds)}s</td>
    </tr>
  );
}

function ResultsMatrix({ run }: { run: EvalRunDetail }) {
  const [open, setOpen] = useState<EvalResult | null>(null);
  const byKey = useMemo(() => {
    const m = new Map<string, EvalResult>();
    run.results.forEach((r) => m.set(`${r.instance_id}|${r.config}`, r));
    return m;
  }, [run]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Per instance</CardTitle>
        <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <CheckCircle2 className="h-3.5 w-3.5 text-success-fg" aria-hidden /> resolved
          </span>
          <span className="inline-flex items-center gap-1">
            <XCircle className="h-3.5 w-3.5 text-destructive-fg" aria-hidden /> not resolved
          </span>
          <span className="inline-flex items-center gap-1">
            <CircleDashed className="h-3.5 w-3.5" aria-hidden /> not scored yet
          </span>
          <span className="inline-flex items-center gap-1">
            <Minus className="h-3.5 w-3.5" aria-hidden /> not run
          </span>
          <span>Select a cell to see its patch.</span>
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="relative overflow-x-auto rounded-md border border-border">
          <table className="w-full text-sm">
            <caption className="sr-only">
              Result for each benchmark instance and configuration
            </caption>
            <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="sticky left-0 bg-surface px-3 py-2 font-medium">
                  Instance
                </th>
                {run.configs.map((c) => (
                  <th key={c} scope="col" className="whitespace-nowrap px-3 py-2 font-medium">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {run.instance_ids.map((iid) => (
                <tr key={iid} className="border-t border-border">
                  <th
                    scope="row"
                    title={iid}
                    className="sticky left-0 max-w-[8.5rem] truncate whitespace-nowrap bg-surface px-3 py-1.5 text-left font-mono text-xs font-normal sm:max-w-none"
                  >
                    {iid}
                  </th>
                  {run.configs.map((c) => {
                    const r = byKey.get(`${iid}|${c}`);
                    const selected = r !== undefined && open === r;
                    return (
                      <td key={c} className="px-1.5 py-1">
                        {r ? (
                          <button
                            type="button"
                            onClick={() => setOpen(selected ? null : r)}
                            aria-pressed={selected}
                            title={r.error ?? r.status}
                            className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded px-1.5 py-1 text-left hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                              selected ? "bg-primary/10 ring-1 ring-primary" : ""
                            }`}
                          >
                            <ResultMark r={r} />
                            <span className="hidden text-xs text-muted-foreground sm:inline">
                              {r.status}
                            </span>
                          </button>
                        ) : (
                          <span className="inline-flex px-1.5 text-muted-foreground">
                            <Minus className="h-4 w-4" aria-hidden />
                            <span className="sr-only">not run</span>
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {open && (
          <section
            aria-label={`Patch for ${open.instance_id} (${open.config})`}
            className="space-y-3 rounded-md border border-border p-4 text-sm"
          >
            <div className="flex items-start justify-between gap-3">
              <p className="min-w-0 break-words">
                <span className="font-mono font-medium">{open.instance_id}</span> · {open.config} ·
                edited <span className="font-mono">{open.target_path ?? "—"}</span> (gold{" "}
                <span className="font-mono">{open.gold_path}</span>) · {open.llm_calls} LLM calls ·{" "}
                {(open.prompt_tokens + open.completion_tokens).toLocaleString()} tokens
              </p>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setOpen(null)}
                aria-label="Close patch"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
            {open.error && <ErrorAlert message={open.error} />}
            {open.patch ? (
              <DiffView diff={open.patch} />
            ) : (
              <p className="text-muted-foreground">No patch submitted.</p>
            )}
          </section>
        )}
      </CardContent>
    </Card>
  );
}
