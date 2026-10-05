import type { Metadata } from "next";
import Link from "next/link";
import { hasSession } from "@/lib/session";
import { logout } from "./login/actions";
import "./globals.css";

export const metadata: Metadata = {
  title: "QuantLab",
  description: "Trading-strategy research dashboard",
};

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/strategies", label: "Strategy builder" },
  { href: "/experiments/new", label: "New experiment" },
  { href: "/compare", label: "Compare" },
  { href: "/workflows", label: "Research workflow" },
  { href: "/sentiment", label: "Headline sentiment" },
  { href: "/datasets", label: "Datasets" },
];

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const signedIn = await hasSession();
  return (
    <html lang="en">
      <body className="min-h-screen">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:rounded focus:bg-white focus:px-3 focus:py-2"
        >
          Skip to content
        </a>
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
            <Link href="/" className="text-lg font-semibold tracking-tight text-sky-800">
              QuantLab
            </Link>
            {signedIn && (
              <>
                <nav aria-label="Main" className="flex flex-1 flex-wrap gap-x-4 gap-y-1 text-sm">
                  {NAV.map((n) => (
                    <Link key={n.href} href={n.href} className="text-slate-700 hover:text-sky-800">
                      {n.label}
                    </Link>
                  ))}
                </nav>
                <form action={logout}>
                  <button type="submit" className="text-sm text-slate-600 hover:text-slate-900">
                    Sign out
                  </button>
                </form>
              </>
            )}
          </div>
        </header>
        <main id="main" className="mx-auto max-w-7xl px-4 py-6">
          {children}
        </main>
        <footer className="mx-auto max-w-7xl px-4 pb-8 text-xs text-slate-500">
          Research tool for education. Backtests describe the past under stated assumptions and are
          not investment advice.
        </footer>
      </body>
    </html>
  );
}
