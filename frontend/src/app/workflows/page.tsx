import Link from "next/link";
import { AutoRefresh } from "@/components/auto-refresh";
import { EmptyState, ErrorState, PageHeader, StatusBadge } from "@/components/ui";
import { apiTry } from "@/lib/api-server";
import { dateTime } from "@/lib/format";
import { datasetSchema, pageOf, variantSchema, workflowSummarySchema } from "@/lib/schemas";
import { requireSession } from "@/lib/session";
import { z } from "zod";
import { WorkflowForm } from "./workflow-form";

export const metadata = { title: "Research workflow · QuantLab" };

export default async function WorkflowsPage() {
  await requireSession();
  const [runs, datasets, variants] = await Promise.all([
    apiTry("/api/workflows?limit=20", pageOf(workflowSummarySchema)),
    apiTry("/api/datasets?limit=100", pageOf(datasetSchema)),
    apiTry("/api/workflows/variants", z.array(variantSchema)),
  ]);
  const active = (runs.data?.items ?? []).some((r) => r.status === "queued" || r.status === "running");

  return (
    <>
      <PageHeader title="Research workflow" />
      <p className="mb-6 max-w-3xl text-sm text-slate-600">
        A bounded, repeatable procedure: backtest up to three predefined variants on a development period, pick one
        using a criterion fixed in advance, then evaluate only that variant once on a later held-out period. The
        held-out result is reported whether it is good or bad.
      </p>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <section aria-labelledby="new-wf" className="card">
          <h2 id="new-wf" className="mb-4 text-lg font-semibold">Start a workflow</h2>
          {datasets.error || variants.error ? (
            <ErrorState title="Could not load form data" message={(datasets.error ?? variants.error)!.message} />
          ) : datasets.data.items.length === 0 ? (
            <EmptyState title="No datasets imported" />
          ) : (
            <WorkflowForm datasets={datasets.data.items} variants={variants.data} />
          )}
        </section>
        <section aria-labelledby="past-wf">
          <h2 id="past-wf" className="mb-3 text-lg font-semibold">Recent workflows</h2>
          <AutoRefresh active={active} />
          {runs.error ? (
            <ErrorState title="Could not load workflows" message={runs.error.message} />
          ) : runs.data.items.length === 0 ? (
            <EmptyState title="No workflows yet" />
          ) : (
            <ul className="space-y-2">
              {runs.data.items.map((r) => (
                <li key={r.id} className="card flex items-center justify-between gap-3 p-3">
                  <div>
                    <Link href={`/workflows/${r.id}`} className="font-medium text-sky-800 hover:underline">{r.name}</Link>
                    <p className="text-xs text-slate-500">
                      {r.dataset_name} · {dateTime(r.created_at)}
                      {r.selected_label && ` · selected ${r.selected_label}`}
                    </p>
                  </div>
                  <StatusBadge status={r.status} />
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}
