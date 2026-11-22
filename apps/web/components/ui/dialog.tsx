"use client";

import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";

/**
 * A confirmation dialog on the native <dialog> element: showModal() gives a
 * focus trap, Escape to close, and an inert background for free — no library.
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  destructive = false,
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description: React.ReactNode;
  confirmLabel: string;
  destructive?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", ""); // jsdom
    } else if (!open && dialog.open) {
      if (typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
    }
  }, [open]);

  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault(); // Escape: let the parent own the state
        if (!busy) onCancel();
      }}
      onClick={(e) => {
        if (e.target === ref.current && !busy) onCancel(); // backdrop click
      }}
      aria-labelledby="confirm-title"
      aria-describedby="confirm-description"
      className="w-[calc(100%-2rem)] max-w-md rounded-lg border border-border bg-surface p-0 text-foreground shadow-xl"
    >
      <div className="space-y-2 p-5">
        <h2 id="confirm-title" className="text-lg font-semibold tracking-tight">
          {title}
        </h2>
        <div id="confirm-description" className="text-sm text-muted-foreground">
          {description}
        </div>
      </div>
      <div className="flex flex-col-reverse gap-2 border-t border-border p-4 sm:flex-row sm:justify-end">
        <Button variant="outline" onClick={onCancel} disabled={busy} autoFocus>
          Cancel
        </Button>
        <Button
          variant={destructive ? "destructive" : "primary"}
          onClick={onConfirm}
          disabled={busy}
        >
          {busy && <Spinner />}
          {confirmLabel}
        </Button>
      </div>
    </dialog>
  );
}
