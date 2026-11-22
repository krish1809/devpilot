import {
  Ban,
  CheckCircle2,
  CircleDashed,
  Clock,
  GitPullRequest,
  Loader2,
  ShieldAlert,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";
import type { RunStatus } from "@/lib/types";

const SUCCESS = "bg-success/15 text-success-fg border-success/30";
const WARNING = "bg-warning/15 text-warning-fg border-warning/30";
const DANGER = "bg-destructive/15 text-destructive-fg border-destructive/30";
const NEUTRAL = "bg-muted text-muted-foreground border-border";

// Color is never the only signal: every status has an icon and a label.
const STYLES: Record<string, { cls: string; Icon: LucideIcon; spin?: boolean }> = {
  running: { cls: "bg-info/15 text-info-fg border-info/30", Icon: Loader2, spin: true },
  validated: { cls: WARNING, Icon: Clock }, // waiting for a human decision
  approved: { cls: SUCCESS, Icon: CheckCircle2 },
  published: { cls: SUCCESS, Icon: GitPullRequest },
  test_failed: { cls: WARNING, Icon: XCircle },
  rejected: { cls: NEUTRAL, Icon: Ban },
  error: { cls: DANGER, Icon: XCircle },
  publish_failed: { cls: DANGER, Icon: XCircle },
  review_failed: { cls: WARNING, Icon: ShieldAlert },
  cancelled: { cls: NEUTRAL, Icon: Ban },
};

const LABELS: Record<string, string> = {
  validated: "awaiting approval",
};

export function StatusBadge({ status }: { status: RunStatus | string }) {
  const style = STYLES[status] ?? { cls: NEUTRAL, Icon: CircleDashed };
  const { Icon } = style;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium",
        style.cls,
      )}
    >
      <Icon className={cn("h-3 w-3", style.spin && "animate-spin")} aria-hidden />
      {LABELS[status] ?? status.replace(/_/g, " ")}
    </span>
  );
}
