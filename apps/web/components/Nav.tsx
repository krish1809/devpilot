"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Rocket } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";

export function Nav() {
  const { user, logout, demoMode } = useAuth();
  const router = useRouter();

  function handleLogout() {
    logout();
    router.push("/login");
  }

  return (
    <header className="sticky top-0 z-10 border-b border-border bg-background/80 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <Rocket className="h-5 w-5 text-primary" />
          <span>DevPilot</span>
        </Link>

        {user ? (
          <div className="flex items-center gap-2 sm:gap-3">
            <Link href="/tasks">
              <Button variant="ghost" size="sm">
                Tasks
              </Button>
            </Link>
            <Link href="/evals">
              <Button variant="ghost" size="sm">
                Benchmarks
              </Button>
            </Link>
            <Link href="/projects">
              <Button variant="ghost" size="sm">
                Projects
              </Button>
            </Link>
            <span className="hidden text-sm text-muted-foreground sm:inline">
              {user.email}
            </span>
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              Log out
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <Link href="/login">
              <Button variant="ghost" size="sm">
                Log in
              </Button>
            </Link>
            <Link href="/register">
              <Button size="sm">Sign up</Button>
            </Link>
          </div>
        )}
      </div>
      {demoMode && (
        <div className="border-t border-border bg-primary/10 px-4 py-1.5 text-center text-xs text-muted-foreground">
          Read-only showcase of real DevPilot runs. Starting the agent needs Docker, so it runs
          locally —{" "}
          <a
            href="https://github.com/krish1809/devpilot"
            className="text-primary hover:underline"
            target="_blank"
            rel="noreferrer"
          >
            see the code
          </a>
          .
        </div>
      )}
    </header>
  );
}
