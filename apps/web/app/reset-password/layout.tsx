import type { Metadata } from "next";

// The reset token lives in the URL fragment, which browsers never send in a
// Referer header anyway; no-referrer is defence in depth for this page.
export const metadata: Metadata = { title: "Reset password", referrer: "no-referrer" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
