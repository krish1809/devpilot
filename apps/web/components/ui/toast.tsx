"use client";

import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

import { cn } from "@/lib/utils";

type ToastTone = "success" | "error" | "info";

interface ToastItem {
  id: number;
  tone: ToastTone;
  title: string;
  description?: string;
}

type ToastFn = (toast: Omit<ToastItem, "id">) => void;

const ToastContext = createContext<ToastFn | undefined>(undefined);

const DURATION_MS = 5000;

const TONES: Record<ToastTone, { Icon: typeof Info; cls: string }> = {
  success: { Icon: CheckCircle2, cls: "text-success-fg" },
  error: { Icon: AlertCircle, cls: "text-destructive-fg" },
  info: { Icon: Info, cls: "text-info-fg" },
};

/**
 * App-wide toasts. Mounted in the root layout, so a toast survives the
 * navigation that often follows an action ("Password updated" → /login).
 * Announced politely to screen readers (errors assertively).
 */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((all) => all.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback<ToastFn>(
    (t) => {
      const id = nextId.current++;
      setToasts((all) => [...all.slice(-3), { ...t, id }]);
      window.setTimeout(() => dismiss(id), DURATION_MS);
    },
    [dismiss],
  );

  const value = useMemo(() => toast, [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 p-4 sm:items-end"
      >
        {toasts.map((t) => {
          const { Icon, cls } = TONES[t.tone];
          return (
            <div
              key={t.id}
              role={t.tone === "error" ? "alert" : "status"}
              className="animate-toast-in pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-lg border border-border bg-surface p-3 shadow-lg"
            >
              <Icon className={cn("mt-0.5 h-5 w-5 shrink-0", cls)} aria-hidden />
              <div className="min-w-0 flex-1 text-sm">
                <p className="font-medium">{t.title}</p>
                {t.description && <p className="mt-0.5 text-muted-foreground">{t.description}</p>}
              </div>
              <button
                type="button"
                onClick={() => dismiss(t.id)}
                aria-label="Dismiss notification"
                className="rounded p-0.5 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

const noop: ToastFn = () => undefined;

/** `toast({ tone, title, description })`. A no-op outside the provider (tests). */
export function useToast(): ToastFn {
  return useContext(ToastContext) ?? noop;
}
