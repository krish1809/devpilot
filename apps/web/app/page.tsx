"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  Boxes,
  CheckCircle2,
  FileSearch,
  FlaskConical,
  GitPullRequest,
  ListChecks,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
  UserCheck,
} from "lucide-react";

import { ErrorAlert } from "@/components/ui/alert";
import { Button, ButtonLink } from "@/components/ui/button";
import { PageLoading } from "@/components/ui/page";
import { Spinner } from "@/components/ui/spinner";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const STEPS = [
  {
    Icon: FileSearch,
    title: "Retrieve",
    text: "Indexes the repo and finds the code the issue is really about.",
  },
  {
    Icon: ListChecks,
    title: "Plan & patch",
    text: "Plans a fix and edits the file — bounded attempts, tokens and time.",
  },
  {
    Icon: TerminalSquare,
    title: "Test in a sandbox",
    text: "Runs the project's tests in a network-less Docker container.",
  },
  {
    Icon: UserCheck,
    title: "You approve",
    text: "You review the diff, plan and trace. Nothing ships without you.",
  },
  {
    Icon: GitPullRequest,
    title: "Pull request",
    text: "Only then does it push a branch and open the PR.",
  },
];

const HIGHLIGHTS = [
  {
    Icon: Boxes,
    title: "A durable agent",
    text: "A LangGraph state graph, checkpointed to Postgres after every step: cancel, resume after a crash, wait for approval across restarts.",
  },
  {
    Icon: ShieldCheck,
    title: "Untrusted code stays boxed",
    text: "Repository code only runs in a disposable container: no network, CPU/memory/PID limits, non-root, hard timeout.",
  },
  {
    Icon: UserCheck,
    title: "Approval bound to the diff",
    text: "Approving binds to the SHA-256 of the exact diff and base commit. Risky additions are flagged before you approve.",
  },
  {
    Icon: FileSearch,
    title: "Repository RAG",
    text: "Hybrid search — pgvector similarity plus Postgres full-text, fused with RRF — localizes the file when the issue doesn't name it.",
  },
  {
    Icon: Sparkles,
    title: "Its own MCP server",
    text: "Sandbox runs go through a permission-checked MCP server; every tool call, allowed or denied, is audited.",
  },
  {
    Icon: FlaskConical,
    title: "Honestly evaluated",
    text: "Scored on SWE-bench Lite with the official harness, comparing configurations — results are in the app.",
  },
];

export default function HomePage() {
  const { user, loading, demoMode, loginDemo } = useAuth();
  const router = useRouter();
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && user) router.replace("/tasks");
  }, [user, loading, router]);

  async function openDemo() {
    setError(null);
    setOpening(true);
    try {
      await loginDemo();
      router.push("/tasks");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not open the demo. The free API server may still be waking up — try again in a minute.",
      );
      setOpening(false);
    }
  }

  if (loading || user) return <PageLoading />;

  return (
    <div className="space-y-20 pb-8 sm:space-y-24">
      <section className="mx-auto max-w-3xl space-y-6 pt-6 text-center sm:pt-12">
        <p className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-xs font-medium text-muted-foreground">
          <CheckCircle2 className="h-3.5 w-3.5 text-success-fg" aria-hidden />
          Human-in-the-loop AI software engineer
        </p>
        <h1 className="text-balance text-4xl font-semibold tracking-tight sm:text-5xl">
          From GitHub issue to tested pull request.
          <span className="block text-muted-foreground">You stay in control.</span>
        </h1>
        <p className="mx-auto max-w-2xl text-pretty text-base text-muted-foreground sm:text-lg">
          DevPilot reads the issue, finds the broken code, writes a fix, runs the tests in a
          locked-down sandbox and shows you the diff. It opens the PR only after you approve.
        </p>
        {error && <ErrorAlert message={error} className="mx-auto max-w-md text-left" />}
        <div className="flex flex-col justify-center gap-3 sm:flex-row">
          {demoMode ? (
            <Button size="lg" onClick={openDemo} disabled={opening}>
              {opening ? <Spinner /> : <ArrowRight className="h-4 w-4" aria-hidden />}
              View the live demo
            </Button>
          ) : (
            <ButtonLink href="/register" size="lg">
              <ArrowRight className="h-4 w-4" aria-hidden />
              Get started
            </ButtonLink>
          )}
          <ButtonLink href="/login" size="lg" variant="outline">
            Log in
          </ButtonLink>
        </div>
        {demoMode && (
          <p className="text-xs text-muted-foreground">
            Read-only tour of real runs, no account needed. The free API server can take about a
            minute to wake up.
          </p>
        )}
      </section>

      <section aria-labelledby="how-heading" className="space-y-8">
        <h2 id="how-heading" className="text-center text-2xl font-semibold tracking-tight">
          How a run works
        </h2>
        <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {STEPS.map(({ Icon, title, text }, i) => (
            <li key={title} className="relative rounded-lg border border-border bg-surface p-4">
              <div className="flex items-center gap-2">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                  {i + 1}
                </span>
                <Icon className="h-4 w-4 text-muted-foreground" aria-hidden />
              </div>
              <p className="mt-3 font-medium">{title}</p>
              <p className="mt-1 text-sm text-muted-foreground">{text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="built-heading" className="space-y-8">
        <h2 id="built-heading" className="text-center text-2xl font-semibold tracking-tight">
          What&apos;s under the hood
        </h2>
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {HIGHLIGHTS.map(({ Icon, title, text }) => (
            <li key={title} className="rounded-lg border border-border p-5">
              <Icon className="h-5 w-5 text-primary" aria-hidden />
              <p className="mt-3 font-medium">{title}</p>
              <p className="mt-1 text-sm text-muted-foreground">{text}</p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
