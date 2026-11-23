import { AlertCircle, AlertTriangle, CheckCircle2, Info } from "lucide-react";

import { cn } from "@/lib/utils";

type Tone = "error" | "success" | "info" | "warning";

const TONES: Record<Tone, { box: string; Icon: typeof Info }> = {
  error: { box: "border-destructive/30 bg-destructive/10 text-destructive-fg", Icon: AlertCircle },
  success: { box: "border-success/30 bg-success/10 text-success-fg", Icon: CheckCircle2 },
  info: { box: "border-info/30 bg-info/10 text-info-fg", Icon: Info },
  warning: { box: "border-warning/40 bg-warning/10 text-warning-fg", Icon: AlertTriangle },
};

export function Alert({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: Tone;
  title?: string;
  children?: React.ReactNode;
  className?: string;
}) {
  const { box, Icon } = TONES[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn("flex items-start gap-2 rounded-md border px-3 py-2 text-sm", box, className)}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div className="min-w-0 space-y-0.5">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className={cn(title && "opacity-90")}>{children}</div>}
      </div>
    </div>
  );
}

export function ErrorAlert({ message, className }: { message: string; className?: string }) {
  return (
    <Alert tone="error" className={className}>
      {message}
    </Alert>
  );
}
