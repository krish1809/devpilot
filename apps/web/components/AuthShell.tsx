import { CheckCircle2, GitPullRequest, ShieldCheck, TerminalSquare } from "lucide-react";

import { Logo } from "@/components/Logo";

const POINTS = [
  {
    Icon: TerminalSquare,
    text: "Fixes are tested in a network-less Docker sandbox",
  },
  { Icon: ShieldCheck, text: "Nothing ships until you approve the exact diff" },
  {
    Icon: GitPullRequest,
    text: "Approved fixes become real GitHub pull requests",
  },
];

/**
 * The shared frame for login, sign-up, forgot- and reset-password: the form
 * on the right, a short product panel on the left (large screens only).
 */
export function AuthShell({
  title,
  description,
  children,
  footer,
  aside,
}: {
  title: string;
  description?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  /** Optional content above the form (e.g. the showcase call-to-action). */
  aside?: React.ReactNode;
}) {
  return (
    <div className="mx-auto grid w-full max-w-5xl items-center gap-10 py-2 sm:py-6 lg:grid-cols-[1fr_minmax(0,28rem)] lg:gap-16">
      <section
        aria-hidden
        className="relative hidden overflow-hidden rounded-2xl border border-border bg-surface/60 p-10 shadow-panel lg:block"
      >
        <div className="bg-grid absolute inset-0 opacity-70" />
        <div className="absolute -left-24 -top-24 h-72 w-72 rounded-full bg-primary/20 blur-3xl" />
        <div className="absolute -bottom-24 -right-16 h-64 w-64 rounded-full bg-accent/10 blur-3xl" />
        <div className="relative space-y-8">
          <Logo size="lg" />
          <div className="space-y-3">
            <p className="text-3xl font-semibold leading-tight tracking-tight">
              <span className="text-gradient-brand">Issue in.</span>
              <br />
              Tested pull request out.
            </p>
            <p className="max-w-sm text-sm text-muted-foreground">
              DevPilot finds the code behind a GitHub issue, writes the fix and proves it with the
              repo&apos;s own tests — then waits for you.
            </p>
          </div>
          <ul className="space-y-3">
            {POINTS.map(({ Icon, text }) => (
              <li key={text} className="flex items-center gap-3 text-sm">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border bg-background/60">
                  <Icon className="h-4 w-4 text-primary" />
                </span>
                {text}
              </li>
            ))}
          </ul>
          <div className="rounded-xl border border-border bg-background/70 p-4 font-mono text-xs shadow-panel">
            <p className="mb-2 flex items-center gap-2 font-sans text-[11px] uppercase tracking-wider text-muted-foreground">
              <CheckCircle2 className="h-3.5 w-3.5 text-success-fg" />
              tests passed · awaiting your approval
            </p>
            <p className="text-destructive-fg">- return part // whole * 100</p>
            <p className="text-success-fg">+ return part / whole * 100</p>
          </div>
        </div>
      </section>

      <div className="mx-auto w-full max-w-md space-y-6">
        {aside}
        <div className="space-y-2">
          <Logo size="lg" className="lg:hidden" />
          <h1 className="pt-2 text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
          {description && <p className="text-sm text-muted-foreground">{description}</p>}
        </div>
        <div className="rounded-2xl border border-border bg-surface/80 p-6 shadow-panel backdrop-blur-sm sm:p-7">
          {children}
        </div>
        {footer && <div className="text-center text-sm text-muted-foreground">{footer}</div>}
      </div>
    </div>
  );
}

export const linkClass =
  "font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm";
