import { cn } from "@/lib/utils";
import type { RunStatus } from "@/lib/types";

const STYLES: Record<string, string> = {
  running: "bg-info/15 text-info border-info/30",
  validated: "bg-success/15 text-success border-success/30",
  approved: "bg-success/15 text-success border-success/30",
  published: "bg-success/15 text-success border-success/30",
  test_failed: "bg-warning/15 text-warning border-warning/30",
  rejected: "bg-muted text-muted-foreground border-border",
  error: "bg-destructive/15 text-destructive border-destructive/30",
  publish_failed: "bg-destructive/15 text-destructive border-destructive/30",
};

export function StatusBadge({ status }: { status: RunStatus | string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium",
        STYLES[status] ?? "bg-muted text-muted-foreground border-border",
      )}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}
