import Link from "next/link";
import { ArrowLeft, type LucideIcon } from "lucide-react";

import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

/** The one page title pattern: icon + h1 + description, actions on the right. */
export function PageHeader({
  title,
  description,
  icon: Icon,
  actions,
  back,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  icon?: LucideIcon;
  actions?: React.ReactNode;
  back?: { href: string; label: string };
}) {
  return (
    <header className="space-y-3">
      {back && (
        <Link
          href={back.href}
          className="inline-flex items-center gap-1 rounded text-sm text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden /> {back.label}
        </Link>
      )}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0 space-y-1">
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight sm:text-3xl">
            {Icon && <Icon className="h-6 w-6 shrink-0 text-primary sm:h-7 sm:w-7" aria-hidden />}
            <span className="min-w-0 break-words">{title}</span>
          </h1>
          {description && (
            <p className="max-w-prose text-sm text-muted-foreground sm:text-base">{description}</p>
          )}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
      </div>
    </header>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded-md bg-muted", className)} />;
}

/** Placeholder rows while a list loads (announced once as "Loading…"). */
export function ListSkeleton({ rows = 3, label }: { rows?: number; label: string }) {
  return (
    <div role="status" aria-label={label} className="space-y-3">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-[4.5rem] w-full" />
      ))}
    </div>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: LucideIcon;
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border px-6 py-12 text-center">
      <div className="rounded-full bg-muted p-3">
        <Icon className="h-6 w-6 text-muted-foreground" aria-hidden />
      </div>
      <div className="space-y-1">
        <p className="font-medium">{title}</p>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function PageLoading({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" className="flex justify-center py-24 text-muted-foreground">
      <Spinner className="mr-2" /> {label}
    </div>
  );
}
