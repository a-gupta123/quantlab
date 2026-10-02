"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** Re-render the current Server Component tree every few seconds while work is
 * in progress, so queued/running rows update without a manual reload. */
export function AutoRefresh({ active, intervalMs = 3000 }: { active: boolean; intervalMs?: number }) {
  const router = useRouter();
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => router.refresh(), intervalMs);
    return () => clearInterval(id);
  }, [active, intervalMs, router]);
  return active ? (
    <p className="text-xs text-slate-500" aria-live="polite">
      Updating automatically while runs are in progress…
    </p>
  ) : null;
}
