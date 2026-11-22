import * as React from "react";

import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export interface FieldControlProps {
  id: string;
  "aria-invalid"?: true;
  "aria-describedby"?: string;
}

/**
 * Label above the control, hint and error below — wired up for assistive tech:
 * the control gets `aria-invalid` and `aria-describedby` pointing at the hint
 * and the error, so a screen reader announces them with the field.
 */
export function Field({
  id,
  label,
  hint,
  error,
  labelAction,
  className,
  children,
}: {
  id: string;
  label: React.ReactNode;
  hint?: React.ReactNode;
  error?: string | null;
  /** Something on the label's row, e.g. a "Forgot password?" link. */
  labelAction?: React.ReactNode;
  className?: string;
  children: (control: FieldControlProps) => React.ReactNode;
}) {
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-baseline justify-between gap-2">
        <Label htmlFor={id} className="mb-0">
          {label}
        </Label>
        {labelAction}
      </div>
      {children({
        id,
        "aria-invalid": error ? true : undefined,
        "aria-describedby": describedBy,
      })}
      {hint && (
        <p id={hintId} className="text-xs text-muted-foreground">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="text-xs font-medium text-destructive-fg">
          {error}
        </p>
      )}
    </div>
  );
}
