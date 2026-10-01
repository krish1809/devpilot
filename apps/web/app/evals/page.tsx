"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { FlaskConical } from "lucide-react";

import { ErrorAlert } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type {
  EvalConfigSummary,
  EvalResult,
  EvalRunDetail,
  EvalRunSummary,
} from "@/lib/types";
import { formatDate } from "@/lib/utils";

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

  if (authLoading || !user) {
    return (
      <div className="flex justify-center py-24 text-muted-foreground">
        <Spinner className="mr-2" /> Loading…
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <FlaskConical className="h-6 w-6 text-primary" /> Benchmarks
        </h1>
        <p className="text-sm text-muted-foreground">
          DevPilot on SWE-bench Lite, scored with the official SWE-bench
          harness. Produced by{" "}
          <span className="font-mono">python -m scripts.swebench_eval</span>.
        </p>
      </div>

      {error && <ErrorAlert message={error} />}

      {runs === null && !error ? (
        <div className="flex justify-center py-12 text-muted-foreground">
          <Spinner className="mr-2" /> Loading…
        </div>
      ) : runs && runs.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border py-12 text-center text-muted-foreground">
          No benchmark runs yet.
        </div>
      ) : (
        runs && (
          <>
            {runs.length > 1 && (
              <Select
                value={selected ?? ""}
                onChange={(e) => setSelected(Number(e.target.value))}
                className="max-w-sm"
              >
                {runs.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name} · {r.instance_count} instances ·{" "}
                    {formatDate(r.created_at)}
                  </option>
                ))}
              </Select>
            )}
            {detail ? (
              <RunDetail run={detail} />
            ) : (
              <div className="flex justify-center py-12 text-muted-foreground">
                <Spinner className="mr-2" /> Loading run…
              </div>
            )}
          </>
        )
      )}
    </div>
  );
}

function RunDetail({ run }: { run: EvalRunDetail }) {
  const seed = run.settings["seed"];
  const attempted = new Set(
    run.results.filter((r) => r.config !== "gold").map((r) => r.instance_id),
  ).size;
  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {run.name} — {attempted} of {run.instance_count} sampled instances
            attempted
            {seed !== undefined && ` (seed ${String(seed)})`}
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            {run.dataset} · model <span className="font-mono">{run.model}</span>{" "}
            · the agent never sees the benchmark&apos;s tests
          </p>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr>
                <th className="py-1 pr-3">Config</th>
                <th className="py-1 pr-3">Resolved</th>
                <th className="py-1 pr-3">Rate (95% CI)</th>
                <th className="py-1 pr-3">Patch</th>
                <th className="py-1 pr-3">Gold file</th>
                <th className="py-1 pr-3">Tokens</th>
                <th className="py-1">Time</th>
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
      <td className="py-2 pr-3">{CONFIG_LABELS[s.config] ?? s.config}</td>
      <td className="py-2 pr-3 font-mono">
        {s.resolved}/{s.scored}
        {s.scored < s.generated && (
          <span className="ml-1 text-xs text-muted-foreground">
            ({s.generated - s.scored} unscored)
          </span>
        )}
      </td>
      <td className="py-2 pr-3">
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
      <td className="py-2 pr-3 font-mono">
        {Math.round(s.avg_tokens).toLocaleString()}
      </td>
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
      </CardHeader>
      <CardContent className="space-y-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground">
            <tr>
              <th className="py-1 pr-3">Instance</th>
              {run.configs.map((c) => (
                <th key={c} className="py-1 pr-3">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {run.instance_ids.map((iid) => (
              <tr key={iid} className="border-t border-border">
                <td className="py-1.5 pr-3 font-mono text-xs">{iid}</td>
                {run.configs.map((c) => {
                  const r = byKey.get(`${iid}|${c}`);
                  return (
                    <td key={c} className="py-1.5 pr-3">
                      {r ? (
                        <button
                          onClick={() => setOpen(r)}
                          className="text-left hover:underline"
                          title={r.error ?? r.status}
                        >
                          {r.resolved === true
                            ? "✅"
                            : r.resolved === false
                              ? "❌"
                              : "·"}{" "}
                          <span className="text-xs text-muted-foreground">
                            {r.status}
                          </span>
                        </button>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-xs text-muted-foreground">
          ✅ resolved · ❌ not resolved · · not scored yet · — not run. Click a
          cell for its patch.
        </p>
        {open && (
          <div className="space-y-2 rounded-md border border-border p-3 text-sm">
            <p>
              <span className="font-mono">{open.instance_id}</span> ·{" "}
              {open.config} · edited{" "}
              <span className="font-mono">{open.target_path ?? "—"}</span> (gold{" "}
              <span className="font-mono">{open.gold_path}</span>) ·{" "}
              {open.llm_calls} LLM calls ·{" "}
              {(open.prompt_tokens + open.completion_tokens).toLocaleString()}{" "}
              tokens
            </p>
            {open.error && <ErrorAlert message={open.error} />}
            {open.patch ? (
              <pre className="max-h-96 overflow-auto rounded-md bg-muted p-3 font-mono text-xs">
                {open.patch}
              </pre>
            ) : (
              <p className="text-muted-foreground">No patch submitted.</p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
