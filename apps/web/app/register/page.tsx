"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AuthShell, linkClass } from "@/components/AuthShell";
import { ErrorAlert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { Spinner } from "@/components/ui/spinner";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { passwordProblem } from "@/lib/validation";

export default function RegisterPage() {
  const { user, loading, register, demoMode, loginDemo } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace("/tasks");
  }, [user, loading, router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const problem = passwordProblem(password);
    if (problem) {
      setFieldErrors({ password: problem });
      return;
    }
    setFieldErrors({});
    setSubmitting(true);
    try {
      await register(email, password);
      router.push("/tasks");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setFieldErrors({ email: "An account with this email already exists." });
      } else if (err instanceof ApiError && Object.keys(err.fields).length) {
        setFieldErrors(err.fields);
      } else {
        setError(err instanceof ApiError ? err.message : "Something went wrong");
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDemo() {
    setError(null);
    setSubmitting(true);
    try {
      await loginDemo();
      router.push("/tasks");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not open the demo");
    } finally {
      setSubmitting(false);
    }
  }

  // The public showcase can't run the agent (no Docker sandbox, no LLM key), so
  // accounts there would have nothing to do: sign-up is off and the API refuses it.
  if (demoMode) {
    return (
      <AuthShell
        title="Sign-up is off on the public showcase"
        description="This site is a read-only tour of real DevPilot runs."
      >
        <div className="space-y-4 text-sm text-muted-foreground">
          {error && <ErrorAlert message={error} />}
          <p>
            Running the agent needs Docker and an LLM key, so it runs on your own machine — where
            you can sign up normally.
          </p>
          <Button className="w-full" onClick={handleDemo} disabled={submitting}>
            {submitting && <Spinner />}
            View the demo — no account needed
          </Button>
          <p className="text-center">
            <a
              href="https://github.com/krish1809/devpilot#run-it-locally"
              className={linkClass}
              target="_blank"
              rel="noreferrer"
            >
              How to run it locally
            </a>
          </p>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Create your account"
      description="Point DevPilot at a GitHub issue and review the fix it proposes."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className={linkClass}>
            Log in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && <ErrorAlert message={error} />}
        <Field id="email" label="Email" error={fieldErrors.email}>
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
        <Field id="password" label="Password" hint="8–128 characters." error={fieldErrors.password}>
          {(control) => (
            <PasswordInput
              {...control}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          )}
        </Field>
        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting && <Spinner />}
          Sign up
        </Button>
      </form>
    </AuthShell>
  );
}
