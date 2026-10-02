import Link from "next/link";
import { AutoRefresh } from "@/components/auto-refresh";
import { ErrorState, Metric, PageHeader } from "@/components/ui";
import { apiTry } from "@/lib/api-server";
import { num, pct } from "@/lib/format";
import { datasetSchema, experimentSummarySchema, pageOf, statsSchema } from "@/lib/schemas";
import { requireSession } from "@/lib/session";
import { ExperimentTable } from "./experiment-table";
import { Filters } from "./filters";

const PAGE_SIZE = 20;

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

// Server Component: the initial list, stats, and dataset options are fetched on
// the server with the service token. Filters/selection are Client Components.
export default async function Dashboard({ searchParams }: { searchParams: SearchParams }) {
  await requireSession();
  const sp = await searchParams;
  const one = (k: string) => (typeof sp[k] === "string" ? (sp[k] as string) : "");
  const page = Math.max(1, Number(one("page")) || 1);
  const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String((page - 1) * PAGE_SIZE) });
  for (const k of ["q", "status", "dataset_id"]) if (one(k)) params.set(k, one(k));
  if (one("include_workflow") === "1") params.set("include_workflow", "true");

  const [list, stats, datasets] = await Promise.all([
    apiTry(`/api/experiments?${params}`, pageOf(experimentSummarySchema)),
    apiTry("/api/experiments/stats", statsSchema),
    apiTry("/api/datasets?limit=100", pageOf(datasetSchema)),
  ]);

  const active = (list.data?.items ?? []).some((e) => e.status === "queued" || e.status === "running");
  const totalPages = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE_SIZE)) : 1;
  const pageHref = (p: number) => {
    const next = new URLSearchParams(Object.entries(sp).filter(([, v]) => typeof v === "string") as [string, string][]);
    next.set("page", String(p));
    return `/?${next}`;
  };

  return (
    <>
      <PageHeader title="Experiments">
        <Link href="/experiments/new" className="btn-primary">
          New experiment
        </Link>
      </PageHeader>

      {stats.error ? (
        <ErrorState title="Could not load summary" message={stats.error.message} />
      ) : (
        <dl className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
          <Metric label="Saved runs" value={stats.data.total} />
          <Metric label="Completed" value={stats.data.by_status.completed ?? 0} />
          <Metric label="In progress" value={(stats.data.by_status.queued ?? 0) + (stats.data.by_status.running ?? 0)} />
          <Metric label="Failed" value={stats.data.by_status.failed ?? 0} />
          <Metric
            label="Workers online"
            value={stats.data.workers_online}
            className={stats.data.workers_online ? "text-emerald-700" : "text-rose-700"}
            hint={stats.data.workers_online ? undefined : "Start the worker to process runs"}
          />
        </dl>
      )}
      {stats.data?.best_sharpe && (
        <p className="mb-4 text-sm text-slate-600">
          Highest Sharpe among completed runs:{" "}
          <Link className="text-sky-800 underline" href={`/experiments/${stats.data.best_sharpe.id}`}>
            {stats.data.best_sharpe.name}
          </Link>{" "}
          (Sharpe {num(stats.data.best_sharpe.sharpe_ratio)}, total return {pct(stats.data.best_sharpe.total_return)}).
          Ranking past runs this way is descriptive, not a selection procedure.
        </p>
      )}

      <Filters datasets={datasets.data?.items ?? []} />
      <AutoRefresh active={active} />

      {list.error ? (
        <ErrorState title="Could not load experiments" message={list.error.message} />
      ) : (
        <>
          <ExperimentTable items={list.data.items} filtered={Boolean(one("q") || one("status") || one("dataset_id"))} />
          {totalPages > 1 && (
            <nav aria-label="Pagination" className="mt-4 flex items-center gap-3 text-sm">
              {page > 1 && <Link className="btn-secondary" href={pageHref(page - 1)}>Previous</Link>}
              <span>
                Page {page} of {totalPages} ({list.data.total} runs)
              </span>
              {page < totalPages && <Link className="btn-secondary" href={pageHref(page + 1)}>Next</Link>}
            </nav>
          )}
        </>
      )}
    </>
  );
}
