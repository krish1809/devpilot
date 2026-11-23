import { ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";
import type { RunEvent } from "@/lib/types";

/** A consistent, keyboard-accessible collapsible section (native <details>). */
export function Disclosure({
  title,
  meta,
  children,
  onToggle,
  defaultOpen = false,
}: {
  title: string;
  meta?: React.ReactNode;
  children: React.ReactNode;
  onToggle?: (open: boolean) => void;
  defaultOpen?: boolean;
}) {
  return (
    <details
      open={defaultOpen}
      onToggle={(e) => onToggle?.((e.target as HTMLDetailsElement).open)}
      className="group rounded-md border border-border"
    >
      <summary
        className={cn(
          "flex cursor-pointer list-none items-center gap-2 rounded-md px-3 py-2.5 text-sm font-medium",
          "hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          "[&::-webkit-details-marker]:hidden",
        )}
      >
        <ChevronRight
          className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-90"
          aria-hidden
        />
        <span>{title}</span>
        {meta && (
          <span className="ml-auto truncate text-xs font-normal text-muted-foreground">{meta}</span>
        )}
      </summary>
      <div className="border-t border-border px-3 py-3">{children}</div>
    </details>
  );
}

export function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h3 className="mb-2 text-sm font-semibold">{children}</h3>;
}

const isFailure = (e: RunEvent) => /fail|error|reject|cancel/i.test(`${e.stage} ${e.message}`);

/** The run's events as a vertical stepper; the latest step pulses while running. */
export function Timeline({ events, running }: { events: RunEvent[]; running: boolean }) {
  return (
    <ol className="relative space-y-3 border-l border-border pl-5">
      {events.map((e, i) => {
        const last = i === events.length - 1;
        return (
          <li key={e.id} className="relative">
            <span
              aria-hidden
              className={cn(
                "absolute -left-[1.6rem] top-1.5 h-2.5 w-2.5 rounded-full ring-4 ring-surface",
                isFailure(e) ? "bg-destructive" : last ? "bg-primary" : "bg-muted-foreground/50",
                last && running && "animate-pulse",
              )}
            />
            <p className="text-sm">
              <span className="mr-2 inline-block rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
                {e.stage}
              </span>
              <span className="text-foreground/90 [overflow-wrap:anywhere]">{e.message}</span>
            </p>
          </li>
        );
      })}
    </ol>
  );
}

export const PIPELINE_STEPS = [
  "prepare",
  "retrieve",
  "plan",
  "code",
  "test",
  "review",
  "approve",
  "publish",
] as const;
export type PipelineStep = (typeof PIPELINE_STEPS)[number];
export type StepState = "done" | "current" | "waiting" | "failed" | "skipped" | "pending";

const STAGE_ALIASES: Record<string, PipelineStep> = { start: "prepare" };

// Where a finished run stopped, by status.
const FAILED_AT: Partial<Record<string, PipelineStep>> = {
  test_failed: "test",
  review_failed: "review",
  rejected: "approve",
  publish_failed: "publish",
};

/** Derive each pipeline step's state from the run's events and status. */
export function pipelineStates(stages: string[], status: string): Record<PipelineStep, StepState> {
  const reached = new Set<PipelineStep>();
  for (const s of stages) {
    const step = STAGE_ALIASES[s] ?? s;
    if ((PIPELINE_STEPS as readonly string[]).includes(step)) reached.add(step as PipelineStep);
  }
  // An approved or published run was approved, whatever the event log says.
  if (status === "approved" || status === "published") reached.add("approve");
  let furthest = -1;
  PIPELINE_STEPS.forEach((s, i) => reached.has(s) && (furthest = i));

  let stopAt = furthest;
  let stopState: StepState = "current";
  if (status === "published") {
    stopAt = PIPELINE_STEPS.length;
  } else if (status === "validated") {
    stopAt = PIPELINE_STEPS.indexOf("approve");
    stopState = "waiting";
  } else if (status === "approved") {
    stopAt = PIPELINE_STEPS.indexOf("publish");
  } else if (FAILED_AT[status]) {
    stopAt = PIPELINE_STEPS.indexOf(FAILED_AT[status]!);
    stopState = "failed";
  } else if (status === "error" || status === "cancelled") {
    stopState = "failed";
  }

  const states = {} as Record<PipelineStep, StepState>;
  PIPELINE_STEPS.forEach((step, i) => {
    if (i < stopAt) states[step] = reached.has(step) ? "done" : "skipped";
    else if (i === stopAt) states[step] = stopState;
    else states[step] = "pending";
  });
  return states;
}

const STEP_STYLE: Record<StepState, string> = {
  done: "border-success/40 bg-success/10 text-success-fg",
  current: "border-primary/60 bg-primary/15 text-foreground shadow-glow",
  waiting: "border-warning/50 bg-warning/10 text-warning-fg",
  failed: "border-destructive/50 bg-destructive/10 text-destructive-fg",
  skipped: "border-dashed border-border text-muted-foreground",
  pending: "border-border text-muted-foreground/70",
};

const STEP_LABEL: Record<StepState, string> = {
  done: "done",
  current: "in progress",
  waiting: "waiting for you",
  failed: "stopped here",
  skipped: "skipped",
  pending: "not reached",
};

/** The agent graph as a horizontal stepper: where this run is, or where it stopped. */
export function RunPipeline({ stages, status }: { stages: string[]; status: string }) {
  const states = pipelineStates(stages, status);
  return (
    <ol aria-label="Agent pipeline" className="flex flex-wrap items-center gap-x-1.5 gap-y-2">
      {PIPELINE_STEPS.map((step, i) => {
        const state = states[step];
        return (
          <li key={step} className="flex shrink-0 items-center gap-1.5">
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[11px] font-medium",
                STEP_STYLE[state],
              )}
              title={`${step}: ${STEP_LABEL[state]}`}
            >
              <span
                aria-hidden
                className={cn(
                  "h-1.5 w-1.5 rounded-full bg-current",
                  (state === "current" || state === "waiting") && "animate-pulse",
                  state === "pending" && "opacity-40",
                )}
              />
              {step}
              <span className="sr-only">: {STEP_LABEL[state]}</span>
            </span>
            {i < PIPELINE_STEPS.length - 1 && <span aria-hidden className="h-px w-3 bg-border" />}
          </li>
        );
      })}
    </ol>
  );
}
