import { Compass } from "lucide-react";

import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/page";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-lg py-12">
      <EmptyState
        icon={Compass}
        title="Page not found"
        description="That page doesn't exist, or it moved."
        action={<ButtonLink href="/">Go home</ButtonLink>}
      />
    </div>
  );
}
