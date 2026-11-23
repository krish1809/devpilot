import { Rocket } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

/** The shared frame for login, sign-up, forgot- and reset-password. */
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
  /** Optional content above the card (e.g. the showcase call-to-action). */
  aside?: React.ReactNode;
}) {
  return (
    <div className="mx-auto w-full max-w-md space-y-6 py-4 sm:py-10">
      {aside}
      <div className="space-y-2 text-center">
        <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10">
          <Rocket className="h-5 w-5 text-primary" aria-hidden />
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
      <Card>
        <CardContent className="p-6">{children}</CardContent>
      </Card>
      {footer && <div className="text-center text-sm text-muted-foreground">{footer}</div>}
    </div>
  );
}

export const linkClass =
  "font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm";
