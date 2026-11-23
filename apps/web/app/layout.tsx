import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";

import { Nav } from "@/components/Nav";
import { ThemeToggle, themeInitScript } from "@/components/theme";
import { ToastProvider } from "@/components/ui/toast";
import { AuthProvider } from "@/lib/auth";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: { default: "DevPilot — GitHub issues to tested pull requests", template: "%s · DevPilot" },
  description:
    "An AI software engineer that turns GitHub issues into tested pull requests — and never ships without a human's approval.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#111317" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // data-theme is set before paint by the inline script, so React must not
    // complain that the server HTML lacked it.
    <html
      lang="en"
      className={`${inter.variable} ${jetbrainsMono.variable}`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="flex min-h-screen flex-col font-sans antialiased">
        <a
          href="#main"
          className="sr-only z-50 rounded-md bg-primary px-4 py-2 text-primary-foreground focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
        >
          Skip to content
        </a>
        <ToastProvider>
          <AuthProvider>
            <Nav />
            <main id="main" className="mx-auto w-full max-w-page flex-1 px-4 py-8 sm:px-6 sm:py-10">
              {children}
            </main>
            <footer className="border-t border-border">
              <div className="mx-auto flex max-w-page flex-col gap-2 px-4 py-6 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6">
                <p>DevPilot — a human-supervised AI software engineer. Portfolio project.</p>
                <ThemeToggle className="self-start sm:hidden" />
                <a
                  href="https://github.com/krish1809/devpilot"
                  target="_blank"
                  rel="noreferrer"
                  className="hover:text-foreground"
                >
                  Source on GitHub
                </a>
              </div>
            </footer>
          </AuthProvider>
        </ToastProvider>
      </body>
    </html>
  );
}
