"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Bot, FlaskConical, FolderKanban, LogOut, Menu, X } from "lucide-react";

import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/theme";
import { Button, ButtonLink } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/tasks", label: "Tasks", Icon: Bot },
  { href: "/evals", label: "Benchmarks", Icon: FlaskConical },
  { href: "/projects", label: "Projects", Icon: FolderKanban },
];

const isActive = (pathname: string, href: string) =>
  pathname === href || pathname.startsWith(`${href}/`);

export function Nav() {
  const { user, logout, demoMode, registrationOpen } = useAuth();
  const router = useRouter();
  const pathname = usePathname() ?? "/";
  const [menuOpen, setMenuOpen] = useState(false);

  // Close the mobile menu whenever the route changes.
  useEffect(() => setMenuOpen(false), [pathname]);

  function handleLogout() {
    logout();
    setMenuOpen(false);
    router.push("/login");
  }

  return (
    <header className="sticky top-0 z-40 border-b border-border/70 bg-background/80 backdrop-blur-xl supports-[backdrop-filter]:bg-background/60">
      <div className="mx-auto flex h-14 max-w-page items-center justify-between gap-4 px-4 sm:px-6">
        <Link
          href="/"
          className="flex items-center gap-2.5 rounded-md font-semibold tracking-tight focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Logo />
          DevPilot
        </Link>

        {user && (
          <nav aria-label="Main" className="hidden flex-1 md:block">
            <ul className="flex items-center gap-1">
              {LINKS.map(({ href, label, Icon }) => {
                const active = isActive(pathname, href);
                return (
                  <li key={href}>
                    <Link
                      href={href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        active
                          ? "bg-muted text-foreground shadow-[inset_0_0_0_1px_hsl(var(--border))]"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground",
                      )}
                    >
                      <Icon className="h-4 w-4" aria-hidden />
                      {label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
        )}

        <div className="flex items-center gap-2">
          <ThemeToggle className="hidden sm:inline-flex" />
          {user ? (
            <>
              <span
                className="hidden max-w-[14rem] items-center gap-2 truncate rounded-full border border-border bg-surface/60 py-1 pl-1 pr-3 text-sm text-muted-foreground lg:inline-flex"
                title={user.email}
              >
                <span
                  aria-hidden
                  className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/15 text-xs font-semibold uppercase text-primary"
                >
                  {user.email[0]}
                </span>
                <span className="truncate">{user.email}</span>
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleLogout}
                className="hidden md:inline-flex"
              >
                <LogOut className="h-4 w-4" aria-hidden />
                Log out
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="md:hidden"
                aria-label={menuOpen ? "Close menu" : "Open menu"}
                aria-expanded={menuOpen}
                aria-controls="mobile-nav"
                onClick={() => setMenuOpen((o) => !o)}
              >
                {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
              </Button>
            </>
          ) : (
            <>
              <ButtonLink href="/login" variant="ghost" size="sm">
                Log in
              </ButtonLink>
              {registrationOpen && (
                <ButtonLink href="/register" size="sm">
                  Sign up
                </ButtonLink>
              )}
            </>
          )}
        </div>
      </div>

      {user && menuOpen && (
        <nav
          id="mobile-nav"
          aria-label="Main (mobile)"
          className="border-t border-border bg-background px-4 pb-4 pt-2 md:hidden"
        >
          <ul className="space-y-1">
            {LINKS.map(({ href, label, Icon }) => {
              const active = isActive(pathname, href);
              return (
                <li key={href}>
                  <Link
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      active ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted",
                    )}
                  >
                    <Icon className="h-4 w-4" aria-hidden />
                    {label}
                  </Link>
                </li>
              );
            })}
          </ul>
          <div className="mt-3 flex items-center justify-between gap-2 border-t border-border pt-3">
            <span className="min-w-0 truncate text-sm text-muted-foreground">{user.email}</span>
            <ThemeToggle />
          </div>
          <Button variant="outline" className="mt-3 w-full" onClick={handleLogout}>
            <LogOut className="h-4 w-4" aria-hidden />
            Log out
          </Button>
        </nav>
      )}

      {demoMode && (
        <div className="border-t border-border/70 bg-primary/[0.06] px-4 py-1.5 text-center text-xs text-muted-foreground">
          Read-only showcase of real DevPilot runs. The agent needs Docker, so it runs locally —{" "}
          <a
            href="https://github.com/krish1809/devpilot"
            className="font-medium text-primary underline-offset-4 hover:underline"
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
