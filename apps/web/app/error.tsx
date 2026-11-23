"use client";

import { TriangleAlert } from "lucide-react";
import { useEffect } from "react";

import { Button, ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/page";

/** Catches rendering errors below the root layout, so the shell stays usable. */
export default function GlobalError({ error, reset }: { error: Error; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="mx-auto max-w-lg py-12">
      <EmptyState
        icon={TriangleAlert}
        title="Something went wrong"
        description="The page hit an unexpected error. Try again, or go back to your tasks."
        action={
          <div className="flex gap-2">
            <Button onClick={reset}>Try again</Button>
            <ButtonLink href="/tasks" variant="outline">
              Go to tasks
            </ButtonLink>
          </div>
        }
      />
    </div>
  );
}
