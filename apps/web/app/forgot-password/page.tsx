"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowLeft, MailCheck } from "lucide-react";

import { AuthShell, linkClass } from "@/components/AuthShell";
import { ErrorAlert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { api, ApiError } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.forgotPassword(email.trim());
      setSentTo(email.trim());
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 429
          ? "Too many reset requests. Please wait a while and try again."
          : err instanceof ApiError
            ? err.message
            : "Something went wrong",
      );
    } finally {
      setSubmitting(false);
    }
  }

  const backToLogin = (
    <Link href="/login" className={`inline-flex items-center gap-1 ${linkClass}`}>
      <ArrowLeft className="h-4 w-4" aria-hidden /> Back to log in
    </Link>
  );

  if (sentTo !== null) {
    // Deliberately the same whether or not the account exists (the API never says).
    return (
      <AuthShell title="Check your email" footer={backToLogin}>
        <div role="status" className="space-y-3 text-center text-sm">
          <MailCheck className="mx-auto h-10 w-10 text-success-fg" aria-hidden />
          <p>
            If an account exists for <span className="font-medium">{sentTo}</span>, we&apos;ve sent
            it a link to reset the password.
          </p>
          <p className="text-muted-foreground">
            The link works once and expires in 30 minutes. Didn&apos;t get it? Check your spam
            folder, or{" "}
            <button
              type="button"
              className={linkClass}
              onClick={() => {
                setSentTo(null);
                setError(null);
              }}
            >
              try again
            </button>
            .
          </p>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Forgot your password?"
      description="Enter your account's email and we'll send you a link to choose a new one."
      footer={backToLogin}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && <ErrorAlert message={error} />}
        <Field id="email" label="Email">
          {(control) => (
            <Input
              {...control}
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
            />
          )}
        </Field>
        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting && <Spinner />}
          Send reset link
        </Button>
      </form>
    </AuthShell>
  );
}
