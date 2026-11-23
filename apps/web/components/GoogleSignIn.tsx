"use client";

import { useEffect, useRef, useState } from "react";

import { Spinner } from "@/components/ui/spinner";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/** Google Identity Services: the official "Sign in with Google" button. */
const GSI_SRC = "https://accounts.google.com/gsi/client";

interface GsiCredentialResponse {
  credential?: string;
}

interface GoogleAccountsId {
  initialize: (config: {
    client_id: string;
    callback: (response: GsiCredentialResponse) => void;
    ux_mode?: "popup" | "redirect";
    auto_select?: boolean;
    cancel_on_tap_outside?: boolean;
    context?: "signin" | "signup" | "use";
  }) => void;
  renderButton: (parent: HTMLElement, options: Record<string, unknown>) => void;
}

declare global {
  interface Window {
    google?: { accounts: { id: GoogleAccountsId } };
  }
}

let gsiLoader: Promise<void> | null = null;

/** Load Google's script once per page, however many buttons mount. */
function loadGsi(): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("no window"));
  if (window.google?.accounts?.id) return Promise.resolve();
  if (!gsiLoader) {
    gsiLoader = new Promise<void>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = GSI_SRC;
      script.async = true;
      script.defer = true;
      script.onload = () => resolve();
      script.onerror = () => {
        gsiLoader = null; // allow a retry on the next mount
        reject(new Error("Google sign-in could not load"));
      };
      document.head.appendChild(script);
    });
  }
  return gsiLoader;
}

/**
 * Renders Google's button when the API has a Google client ID configured, and
 * nothing otherwise. Google hands the browser a signed ID token; we send it
 * to the API, which verifies it and returns a normal DevPilot session.
 */
export function GoogleSignIn({
  onSuccess,
  onError,
  context = "signin",
}: {
  onSuccess: () => void;
  onError: (message: string) => void;
  context?: "signin" | "signup";
}) {
  const { googleClientId, loginWithGoogle } = useAuth();
  const container = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "signing-in" | "unavailable">(
    "loading",
  );
  // Keep the latest callbacks without re-rendering Google's button.
  const handlers = useRef({ onSuccess, onError, loginWithGoogle });
  handlers.current = { onSuccess, onError, loginWithGoogle };

  useEffect(() => {
    if (!googleClientId) return;
    let cancelled = false;
    loadGsi()
      .then(() => {
        const el = container.current;
        const gsi = window.google?.accounts.id;
        if (cancelled || !el || !gsi) return;
        gsi.initialize({
          client_id: googleClientId,
          ux_mode: "popup",
          context,
          cancel_on_tap_outside: true,
          callback: async ({ credential }) => {
            if (!credential) {
              handlers.current.onError("Google didn't return a sign-in. Please try again.");
              return;
            }
            setStatus("signing-in");
            try {
              await handlers.current.loginWithGoogle(credential);
              handlers.current.onSuccess();
            } catch (err) {
              handlers.current.onError(
                err instanceof ApiError ? err.message : "Google sign-in failed. Please try again.",
              );
              setStatus("ready");
            }
          },
        });
        // Google's button takes a pixel width (max 400); match our column.
        const width = Math.min(400, Math.max(200, Math.round(el.getBoundingClientRect().width)));
        el.replaceChildren();
        gsi.renderButton(el, {
          type: "standard",
          theme: "filled_black",
          size: "large",
          shape: "pill",
          text: context === "signup" ? "signup_with" : "continue_with",
          logo_alignment: "left",
          width,
        });
        setStatus("ready");
      })
      .catch(() => !cancelled && setStatus("unavailable"));
    return () => {
      cancelled = true;
    };
  }, [googleClientId, context]);

  if (!googleClientId) return null;

  return (
    <div className="space-y-2">
      <div className="relative flex min-h-[44px] items-center justify-center">
        <div
          ref={container}
          className={status === "signing-in" ? "invisible w-full" : "flex w-full justify-center"}
        />
        {(status === "loading" || status === "signing-in") && (
          <div
            className="absolute inset-0 flex items-center justify-center gap-2 rounded-full border border-border bg-surface text-sm text-muted-foreground"
            role="status"
          >
            <Spinner />
            {status === "signing-in" ? "Signing you in…" : "Loading Google sign-in…"}
          </div>
        )}
      </div>
      {status === "unavailable" && (
        <p className="text-center text-xs text-muted-foreground">
          Google sign-in couldn&apos;t load (blocked by the browser or network). Use email instead.
        </p>
      )}
    </div>
  );
}

/** "or" divider between Google and the email form. */
export function OrDivider({ label = "or continue with email" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-xs uppercase tracking-wider text-muted-foreground">
      <span className="h-px flex-1 bg-border" />
      {label}
      <span className="h-px flex-1 bg-border" />
    </div>
  );
}
