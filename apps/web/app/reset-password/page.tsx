"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { LinkIcon } from "lucide-react";

import { AuthShell, linkClass } from "@/components/AuthShell";
import { ErrorAlert } from "@/components/ui/alert";
import { Button, ButtonLink } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { PasswordInput } from "@/components/ui/password-input";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { passwordProblem, tokenFromHash } from "@/lib/validation";

type State = "reading" | "ready" | "invalid";

export default function ResetPasswordPage() {
  const router = useRouter();
  const toast = useToast();
  const { logout } = useAuth();

  const [state, setState] = useState<State>("reading");
  const [token, setToken] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{ password?: string; confirm?: string }>({});
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const read = useRef(false);

  // The token arrives in the URL fragment (#token=…), which browsers never send
  // to a server. Read it once, then drop it from the address bar and history.
  useEffect(() => {
    if (read.current) return; // React StrictMode runs effects twice in dev
    read.current = true;
    const found = tokenFromHash(window.location.hash);
    if (window.location.hash) {
      window.history.replaceState(null, "", window.location.pathname);
    }
    setToken(found);
    setState(found ? "ready" : "invalid");
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const problems = {
      password: passwordProblem(password) ?? undefined,
      confirm: password !== confirm ? "The passwords don't match." : undefined,
    };
    setFieldErrors(problems);
    if (problems.password || problems.confirm || !token) return;

    setSubmitting(true);
    try {
      await api.resetPassword(token, password);
      // Every existing session was just revoked server-side; drop ours too.
      logout();
      toast({
        tone: "success",
        title: "Password updated",
        description: "Log in with your new password. Other sessions were signed out.",
      });
      router.push("/login");
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setState("invalid");
      } else if (err instanceof ApiError && err.fields.new_password) {
        setFieldErrors({ password: err.fields.new_password });
      } else if (err instanceof ApiError && err.status === 429) {
        setError("Too many attempts. Please wait a minute and try again.");
      } else {
        setError(err instanceof ApiError ? err.message : "Something went wrong");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (state === "reading") {
    return (
      <AuthShell title="Choose a new password">
        <div role="status" className="flex justify-center py-6 text-muted-foreground">
          <Spinner className="mr-2" /> Checking your link…
        </div>
      </AuthShell>
    );
  }

  if (state === "invalid") {
    return (
      <AuthShell
        title="This link can't be used"
        footer={
          <Link href="/login" className={linkClass}>
            Back to log in
          </Link>
        }
      >
        <div className="space-y-4 text-center text-sm">
          <LinkIcon className="mx-auto h-10 w-10 text-warning-fg" aria-hidden />
          <p className="text-muted-foreground">
            Reset links expire after 30 minutes and stop working once any of them has been used.
            Request a fresh link to continue.
          </p>
          <ButtonLink href="/forgot-password" className="w-full">
            Request a new link
          </ButtonLink>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Choose a new password"
      description="After you save it, you'll be signed out everywhere and can log in again."
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && <ErrorAlert message={error} />}
        <Field
          id="new-password"
          label="New password"
          hint="8–128 characters."
          error={fieldErrors.password}
        >
          {(control) => (
            <PasswordInput
              {...control}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoFocus
            />
          )}
        </Field>
        <Field id="confirm-password" label="Confirm new password" error={fieldErrors.confirm}>
          {(control) => (
            <PasswordInput
              {...control}
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
            />
          )}
        </Field>
        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting && <Spinner />}
          Save new password
        </Button>
      </form>
    </AuthShell>
  );
}
