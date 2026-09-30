"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Spinner } from "@/components/ui/spinner";
import { useAuth } from "@/lib/auth";

export default function HomePage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    router.replace(user ? "/tasks" : "/login");
  }, [user, loading, router]);

  return (
    <div className="flex items-center justify-center py-24 text-muted-foreground">
      <Spinner className="mr-2" />
      Loading…
    </div>
  );
}
