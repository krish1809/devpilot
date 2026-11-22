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
              <span className="text-foreground/90">{e.message}</span>
            </p>
          </li>
        );
      })}
    </ol>
  );
}
