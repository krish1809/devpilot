"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";

import { AuthShell, linkClass } from "@/components/AuthShell";
import { GoogleSignIn, OrDivider } from "@/components/GoogleSignIn";
import { Alert, ErrorAlert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { Spinner } from "@/components/ui/spinner";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const {
    user,
    loading,
    login,
    demoMode,
    loginDemo,
    sessionExpired,
    registrationOpen,
    googleClientId,
  } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<"form" | "demo" | null>(null);

  useEffect(() => {
    if (!loading && user) router.replace("/tasks");
  }, [user, loading, router]);

  async function handleDemo() {
    setError(null);
    setSubmitting("demo");
    try {
      await loginDemo();
      router.push("/tasks");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not open the demo");
    } finally {
      setSubmitting(null);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting("form");
    try {
      await login(email, password);
      router.push("/tasks");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setSubmitting(null);
    }
  }

  return (
    <AuthShell
      title="Welcome back"
      description="Log in to turn GitHub issues into tested pull requests — with you approving every one."
      aside={
        demoMode && (
          <div className="rounded-2xl border border-primary/30 bg-primary/[0.07] p-5 shadow-glow">
            <p className="flex items-center gap-2 font-medium">
              <Sparkles className="h-4 w-4 text-primary" aria-hidden />
              Explore the showcase
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              A read-only tour of real runs — plans, diffs, sandbox results, traces and SWE-bench
              Lite results. No account needed.
            </p>
            <Button className="mt-4 w-full" onClick={handleDemo} disabled={submitting !== null}>
              {submitting === "demo" && <Spinner />}
              View the demo — no account needed
            </Button>
          </div>
        )
      }
      footer={
        registrationOpen && (
          <>
            No account?{" "}
            <Link href="/register" className={linkClass}>
              Sign up
            </Link>
          </>
        )
      }
    >
      <div className="space-y-5">
        {sessionExpired && !error && (
          <Alert tone="info">Your session has ended. Please log in again.</Alert>
        )}
        {error && <ErrorAlert message={error} />}
        <GoogleSignIn onSuccess={() => router.push("/tasks")} onError={setError} />
        {googleClientId && <OrDivider />}
        <form onSubmit={handleSubmit} className="space-y-4">
          <Field id="email" label="Email">
            {(control) => (
              <Input
                {...control}
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            )}
          </Field>
          <Field
            id="password"
            label="Password"
            labelAction={
              <Link href="/forgot-password" className={`text-sm ${linkClass}`}>
                Forgot password?
              </Link>
            }
          >
            {(control) => (
              <PasswordInput
                {...control}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            )}
          </Field>
          <Button type="submit" className="w-full" disabled={submitting !== null}>
            {submitting === "form" && <Spinner />}
            Log in
          </Button>
        </form>
      </div>
    </AuthShell>
  );
}
