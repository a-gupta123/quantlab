"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import type { Dataset } from "@/lib/schemas";

/** Filters live in the URL so results are shareable and the Server Component
 * re-fetches with the new query on navigation. */
export function Filters({ datasets }: { datasets: Dataset[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const [pending, startTransition] = useTransition();

  function update(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete("page");
    startTransition(() => router.replace(`${pathname}?${next}`));
  }

  useEffect(() => {
    const t = setTimeout(() => {
      if ((params.get("q") ?? "") !== q) update("q", q.trim());
    }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  return (
    <div role="search" className="mb-4 grid gap-3 rounded-lg border border-slate-200 bg-white p-4 sm:grid-cols-4" aria-busy={pending}>
      <div>
        <label htmlFor="q" className="label">Search by name</label>
        <input id="q" type="search" className="input mt-1" value={q} onChange={(e) => setQ(e.target.value)} maxLength={100} placeholder="e.g. 50/200" />
      </div>
      <div>
        <label htmlFor="status" className="label">Status</label>
        <select id="status" className="input mt-1" value={params.get("status") ?? ""} onChange={(e) => update("status", e.target.value)}>
          <option value="">Any</option>
          <option value="queued">Queued</option>
          <option value="running">Running</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
        </select>
      </div>
      <div>
        <label htmlFor="dataset" className="label">Dataset</label>
        <select id="dataset" className="input mt-1" value={params.get("dataset_id") ?? ""} onChange={(e) => update("dataset_id", e.target.value)}>
          <option value="">Any</option>
          {datasets.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name} v{d.version}{d.is_synthetic ? " (synthetic)" : ""}
            </option>
          ))}
        </select>
      </div>
      <div className="flex items-end">
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={params.get("include_workflow") === "1"} onChange={(e) => update("include_workflow", e.target.checked ? "1" : "")} />
          Include research-workflow runs
        </label>
      </div>
    </div>
  );
}
