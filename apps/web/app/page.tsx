"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  Boxes,
  Check,
  CheckCircle2,
  FileSearch,
  FlaskConical,
  GitPullRequest,
  ListChecks,
  PlayCircle,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
  UserCheck,
} from "lucide-react";

import { ErrorAlert } from "@/components/ui/alert";
import { Button, ButtonLink, buttonClasses } from "@/components/ui/button";
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

// Measured results (SWE-bench Lite, 20 instances, official harness) — see /evals.
const STATS = [
  { value: "7/20", label: "SWE-bench Lite fixes with a file hint" },
  { value: "4/20", label: "from the issue text alone" },
  { value: "0", label: "PRs opened without approval" },
  { value: "290+", label: "backend tests on real Postgres" },
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
    <div className="space-y-24 pb-8 sm:space-y-32">
      <section className="relative -mx-4 -mt-8 overflow-hidden px-4 pb-4 pt-10 sm:-mx-6 sm:-mt-10 sm:px-6 sm:pt-20">
        <div aria-hidden className="bg-grid pointer-events-none absolute inset-0" />
        <div className="relative mx-auto max-w-3xl space-y-7 text-center">
          <p className="inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-medium text-foreground">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-success" />
            </span>
            Human-in-the-loop AI software engineer
          </p>
          <h1 className="text-balance text-4xl font-semibold tracking-tighter sm:text-6xl">
            <span className="text-gradient">From GitHub issue</span>
            <br />
            to tested pull request.
          </h1>
          <p className="mx-auto max-w-2xl text-pretty text-base text-muted-foreground sm:text-lg">
            DevPilot reads the issue, finds the broken code, writes a fix and proves it with the
            repo&apos;s own tests in a locked-down sandbox. It opens the PR only after you approve
            the exact diff.
          </p>
          {error && <ErrorAlert message={error} className="mx-auto max-w-md text-left" />}
          <div className="flex flex-col justify-center gap-3 sm:flex-row">
            {demoMode ? (
              <Button size="lg" onClick={openDemo} disabled={opening}>
                {opening ? <Spinner /> : <PlayCircle className="h-4 w-4" aria-hidden />}
                View the live demo
              </Button>
            ) : (
              <ButtonLink href="/register" size="lg">
                Get started
                <ArrowRight className="h-4 w-4" aria-hidden />
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
        </div>

        <ProductPreview />
      </section>

      <section aria-label="Results" className="mx-auto max-w-4xl">
        <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-border bg-border sm:grid-cols-4">
          {STATS.map(({ value, label }) => (
            <div key={label} className="flex flex-col bg-surface/90 px-5 py-6 text-center">
              <dt className="order-2 mt-1 text-xs text-muted-foreground">{label}</dt>
              <dd className="text-gradient text-3xl font-semibold tracking-tight">{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section aria-labelledby="how-heading" className="space-y-10">
        <SectionHeading id="how-heading" eyebrow="The loop" title="How a run works" />
        <ol className="relative grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <span
            aria-hidden
            className="absolute left-8 right-8 top-[2.15rem] hidden h-px bg-gradient-to-r from-primary/0 via-primary/50 to-primary/0 lg:block"
          />
          {STEPS.map(({ Icon, title, text }, i) => (
            <li
              key={title}
              className="card-interactive relative rounded-xl border border-border bg-surface/80 p-5"
            >
              <div className="flex items-center justify-between">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-primary/30 bg-background text-primary shadow-glow">
                  <Icon className="h-4 w-4" aria-hidden />
                </span>
                <span className="font-mono text-xs text-muted-foreground">0{i + 1}</span>
              </div>
              <p className="mt-4 font-medium">{title}</p>
              <p className="mt-1 text-sm text-muted-foreground">{text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="built-heading" className="space-y-10">
        <SectionHeading
          id="built-heading"
          eyebrow="Engineering"
          title="What's under the hood"
          text="Built to be trusted with real repositories: durable, sandboxed, audited and measured."
        />
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {HIGHLIGHTS.map(({ Icon, title, text }) => (
            <li
              key={title}
              className="card-interactive group rounded-xl border border-border bg-surface/60 p-6"
            >
              <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-primary/25 to-accent/10 ring-1 ring-inset ring-primary/25">
                <Icon className="h-5 w-5 text-primary" aria-hidden />
              </span>
              <p className="mt-4 font-medium">{title}</p>
              <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{text}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="relative overflow-hidden rounded-2xl border border-primary/25 bg-surface/80 px-6 py-12 text-center shadow-glow sm:px-12">
        <div
          aria-hidden
          className="absolute -top-24 left-1/2 h-48 w-[36rem] -translate-x-1/2 rounded-full bg-primary/25 blur-3xl"
        />
        <div className="relative space-y-5">
          <h2 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">
            See a real run, end to end.
          </h2>
          <p className="mx-auto max-w-xl text-sm text-muted-foreground sm:text-base">
            The retrieved code, the plan, the diff, the sandbox result, every LLM and tool call —
            and the pull request it opened.
          </p>
          <div className="flex justify-center">
            {demoMode ? (
              <Button size="lg" onClick={openDemo} disabled={opening}>
                {opening ? <Spinner /> : <PlayCircle className="h-4 w-4" aria-hidden />}
                Open the showcase
              </Button>
            ) : (
              <ButtonLink href="/register" size="lg">
                Create an account
                <ArrowRight className="h-4 w-4" aria-hidden />
              </ButtonLink>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

function SectionHeading({
  id,
  eyebrow,
  title,
  text,
}: {
  id: string;
  eyebrow: string;
  title: string;
  text?: string;
}) {
  return (
    <div className="mx-auto max-w-2xl space-y-3 text-center">
      <p className="font-mono text-xs uppercase tracking-[0.2em] text-primary">{eyebrow}</p>
      <h2 id={id} className="text-balance text-3xl font-semibold tracking-tight">
        {title}
      </h2>
      {text && <p className="text-muted-foreground">{text}</p>}
    </div>
  );
}

const PIPELINE = ["retrieve", "plan", "code", "test", "review", "approve"];

/** A static, illustrative mock of a finished run (not live data). */
function ProductPreview() {
  return (
    <figure className="relative mx-auto mt-16 max-w-4xl sm:mt-20">
      <div
        aria-hidden
        className="absolute -inset-x-10 -top-10 bottom-0 rounded-[2rem] bg-gradient-to-b from-primary/25 via-accent/5 to-transparent blur-2xl"
      />
      <div className="relative overflow-hidden rounded-2xl border border-border bg-surface/95 text-left shadow-panel ring-1 ring-primary/10">
        <div className="flex items-center gap-2 border-b border-border px-4 py-3">
          <span className="h-3 w-3 rounded-full bg-[#ff5f57]" />
          <span className="h-3 w-3 rounded-full bg-[#febc2e]" />
          <span className="h-3 w-3 rounded-full bg-[#28c840]" />
          <span className="ml-3 truncate font-mono text-xs text-muted-foreground">
            devpilot-demo · #2 percent() returns 0 for fractional results
          </span>
        </div>
        <div className="grid gap-0 md:grid-cols-[13rem_1fr]">
          <ol className="flex gap-1 overflow-x-auto border-b border-border p-3 md:flex-col md:border-b-0 md:border-r md:p-4">
            {PIPELINE.map((step, i) => {
              const last = i === PIPELINE.length - 1;
              return (
                <li
                  key={step}
                  className={
                    "flex shrink-0 items-center gap-2.5 rounded-md px-2.5 py-1.5 font-mono text-xs " +
                    (last ? "bg-primary/15 text-foreground" : "text-muted-foreground")
                  }
                >
                  {last ? (
                    <span className="h-2 w-2 animate-pulse rounded-full bg-primary" />
                  ) : (
                    <Check className="h-3.5 w-3.5 text-success-fg" aria-hidden />
                  )}
                  {step}
                </li>
              );
            })}
          </ol>
          <div className="min-w-0 space-y-4 p-4 sm:p-5">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-success/30 bg-success/10 px-2.5 py-1 font-medium text-success-fg">
                <CheckCircle2 className="h-3.5 w-3.5" aria-hidden /> 3 tests passed
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-warning/30 bg-warning/10 px-2.5 py-1 font-medium text-warning-fg">
                awaiting approval
              </span>
              <span className="font-mono text-muted-foreground">calculator.py · +1 −1</span>
            </div>
            <pre className="overflow-x-auto rounded-lg border border-border bg-background/80 py-3 font-mono text-[12.5px] leading-6">
              <code>
                <span className="block px-4 text-info-fg">@@ -4,4 +4,4 @@ def add(a, b):</span>
                <span className="block px-4 text-muted-foreground"> def percent(part, whole):</span>
                <span className="block bg-destructive/10 px-4 text-destructive-fg">
                  - return part // whole * 100
                </span>
                <span className="block bg-success/10 px-4 text-success-fg">
                  + return part / whole * 100
                </span>
              </code>
            </pre>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs text-muted-foreground">
                Approval is bound to this diff&apos;s SHA-256.
              </p>
              <div className="flex gap-2" aria-hidden>
                <span className={buttonClasses({ variant: "outline", size: "sm" })}>Reject</span>
                <span className={buttonClasses({ size: "sm" })}>
                  <GitPullRequest className="h-4 w-4" /> Approve &amp; open PR
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
      <figcaption className="sr-only">
        Illustration of a DevPilot run waiting for approval: tests passed and a one-line diff.
      </figcaption>
    </figure>
  );
}
