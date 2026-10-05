"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { EmptyState, StatusBadge, SyntheticBadge } from "@/components/ui";
import { num, pct, signClass } from "@/lib/format";
import type { ExperimentSummary } from "@/lib/schemas";

const MAX_COMPARE = 3;

export function ExperimentTable({ items, filtered }: { items: ExperimentSummary[]; filtered: boolean }) {
  const router = useRouter();
  const [selected, setSelected] = useState<number[]>([]);

  if (items.length === 0) {
    return (
      <EmptyState title={filtered ? "No runs match these filters" : "No experiments yet"}>
        {filtered ? (
          "Try clearing the search or status filter."
        ) : (
          <>
            Import the demo dataset, then{" "}
            <Link href="/experiments/new" className="text-sky-800 underline">create your first experiment</Link>.
          </>
        )}
      </EmptyState>
    );
  }

  const toggle = (id: number) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : s.length < MAX_COMPARE ? [...s, id] : s));

  return (
    <div className="card overflow-x-auto p-0">
      <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-2 text-sm">
        <span className="text-slate-600" aria-live="polite">
          {selected.length ? `${selected.length} selected for comparison (max ${MAX_COMPARE})` : "Select 2–3 completed runs to compare"}
        </span>
        <button
          className="btn-secondary"
          disabled={selected.length < 2}
          onClick={() => router.push(`/compare?ids=${selected.join(",")}`)}
        >
          Compare selected
        </button>
      </div>
      <table className="table">
        <caption className="sr-only">Saved experiments</caption>
        <thead>
          <tr>
            <th scope="col"><span className="sr-only">Select</span></th>
            <th scope="col">Name</th>
            <th scope="col">Status</th>
            <th scope="col">Dataset</th>
            <th scope="col">Windows</th>
            <th scope="col">Period</th>
            <th scope="col" className="num">Total return</th>
            <th scope="col" className="num">Buy &amp; hold</th>
            <th scope="col" className="num">Sharpe</th>
            <th scope="col" className="num">Max DD</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {items.map((e) => (
            <tr key={e.id} className="hover:bg-slate-50">
              <td>
                <input
                  type="checkbox"
                  aria-label={`Select ${e.name} for comparison`}
                  checked={selected.includes(e.id)}
                  disabled={e.status !== "completed" || (!selected.includes(e.id) && selected.length >= MAX_COMPARE)}
                  onChange={() => toggle(e.id)}
                />
              </td>
              <td>
                <Link href={`/experiments/${e.id}`} className="font-medium text-sky-800 hover:underline">
                  {e.name}
                </Link>
                {e.role !== "standalone" && <span className="ml-2 text-xs text-slate-500">({e.role})</span>}
              </td>
              <td><StatusBadge status={e.status} /></td>
              <td>
                {e.dataset_name} {e.dataset_is_synthetic && <SyntheticBadge />}
              </td>
              <td className={e.short_window === null ? "" : "font-mono"}>{e.strategy_label}</td>
              <td className="text-xs">{e.start_date} → {e.end_date}</td>
              <td className={`num ${signClass(e.total_return)}`}>{pct(e.total_return)}</td>
              <td className={`num ${signClass(e.benchmark_total_return)}`}>{pct(e.benchmark_total_return)}</td>
              <td className="num">{num(e.sharpe_ratio)}</td>
              <td className="num">{pct(e.max_drawdown)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
