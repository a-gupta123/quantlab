import Link from "next/link";
import { notFound } from "next/navigation";
import { AutoRefresh } from "@/components/auto-refresh";
import { ErrorState, PageHeader, StatusBadge, SyntheticBadge } from "@/components/ui";
import { apiTry } from "@/lib/api-server";
import { dateTime, num, pct } from "@/lib/format";
import { type ExperimentSummary, isTerminal, workflowDetailSchema } from "@/lib/schemas";
import { requireSession } from "@/lib/session";
import { ResumeButton } from "./resume-button";

const NODE_LABELS: Record<string, string> = {
  validate_dataset: "Validate dataset and periods",
  generate_configs: "Generate variant configs",
  run_development: "Backtest variants on development period",
  select_variant: "Select by fixed criterion",
  run_holdout: "Evaluate selected variant on held-out period (once)",
  summarize: "Write deterministic summary",
};

function RunRow({ e, selected }: { e: ExperimentSummary; selected?: boolean }) {
  return (
    <tr className={selected ? "bg-sky-50" : undefined}>
      <td>
        <Link href={`/experiments/${e.id}`} className="text-sky-800 hover:underline">{e.name}</Link>
        {selected && <span className="ml-2 text-xs font-medium text-sky-800">selected</span>}
      </td>
      <td><StatusBadge status={e.status} /></td>
      <td className="font-mono">{e.short_window}/{e.long_window}</td>
      <td className="text-xs">{e.start_date} → {e.end_date}</td>
      <td className="num">{pct(e.total_return)}</td>
      <td className="num">{pct(e.benchmark_total_return)}</td>
      <td className="num">{num(e.sharpe_ratio)}</td>
      <td className="num">{pct(e.max_drawdown)}</td>
    </tr>
  );
}

function RunTable({ rows, selectedWindows }: { rows: ExperimentSummary[]; selectedWindows?: [number, number] }) {
  return (
    <div className="overflow-x-auto">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Run</th><th scope="col">Status</th><th scope="col">Windows</th><th scope="col">Period</th>
            <th scope="col" className="num">Return</th><th scope="col" className="num">Buy &amp; hold</th>
            <th scope="col" className="num">Sharpe</th><th scope="col" className="num">Max DD</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((e) => (
            <RunRow key={e.id} e={e} selected={selectedWindows && e.short_window === selectedWindows[0] && e.long_window === selectedWindows[1]} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function WorkflowPage({ params }: PageProps<"/workflows/[id]">) {
  await requireSession();
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const res = await apiTry(`/api/workflows/${id}`, workflowDetailSchema);
  if (res.error?.status === 404) notFound();
  if (res.error) return <ErrorState title="Could not load the workflow" message={res.error.message} />;
  const w = res.data;
  const sel = w.selected_strategy_config;

  return (
    <>
      <PageHeader title={w.name}>
        {w.status === "failed" && <ResumeButton id={w.id} resumable={w.resumable} />}
      </PageHeader>
      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm text-slate-600">
        <StatusBadge status={w.status} />
        <span>{w.dataset.name} v{w.dataset.version}</span>
        {w.dataset.is_synthetic && <SyntheticBadge />}
        <span>Development {w.dev_start} → {w.dev_end}</span>
        <span>Held-out {w.holdout_start} → {w.holdout_end}</span>
      </div>
      <AutoRefresh active={!isTerminal(w.status)} />

      {w.error && (
        <div role="alert" className="card mb-6 border-rose-200 bg-rose-50 text-sm">
          <p className="font-medium text-rose-900">Workflow failed</p>
          <p className="mt-1 whitespace-pre-wrap text-rose-800">{w.error}</p>
          <p className="mt-2 text-xs text-slate-600">
            {w.resumable
              ? "Resume continues from the last saved checkpoint; completed steps are not repeated."
              : "This failure is permanent (e.g. invalid input); start a new workflow with corrected settings."}
          </p>
        </div>
      )}

      <div className="mb-6 grid gap-6 lg:grid-cols-[20rem_minmax(0,1fr)]">
        <section aria-labelledby="progress-h" className="card">
          <h2 id="progress-h" className="mb-3 text-lg font-semibold">Progress</h2>
          <ol className="space-y-3">
            {w.nodes.map((n, i) => (
              <li key={n.node} className="flex gap-3">
                <span className="mt-0.5 font-mono text-xs text-slate-400">{i + 1}</span>
                <div>
                  <p className="text-sm font-medium">{NODE_LABELS[n.node] ?? n.node}</p>
                  <div className="mt-0.5 flex items-center gap-2">
                    <StatusBadge status={n.status} />
                    {n.attempt > 1 && <span className="text-xs text-amber-700">attempt {n.attempt}</span>}
                  </div>
                  {n.message && <p className="mt-0.5 text-xs text-slate-600">{n.message}</p>}
                </div>
              </li>
            ))}
          </ol>
        </section>

        <div className="space-y-6">
          <section aria-labelledby="sel-h" className="card">
            <h2 id="sel-h" className="text-lg font-semibold">Selection rule (fixed before running)</h2>
            <p className="mt-1 text-sm text-slate-700">{w.selection_criterion}</p>
            {sel && (
              <p className="mt-2 text-sm">
                Selected: <span className="font-mono font-medium">MA {sel.short_window}/{sel.long_window}</span>
              </p>
            )}
          </section>

          <section aria-labelledby="dev-h" className="card">
            <h2 id="dev-h" className="mb-3 text-lg font-semibold">Development runs</h2>
            {w.development.length ? (
              <RunTable rows={w.development} selectedWindows={sel ? [sel.short_window, sel.long_window] : undefined} />
            ) : (
              <p className="text-sm text-slate-500">Not started yet.</p>
            )}
          </section>

          <section aria-labelledby="ho-h" className="card">
            <h2 id="ho-h" className="mb-3 text-lg font-semibold">Held-out evaluation</h2>
            {w.holdout ? <RunTable rows={[w.holdout]} /> : <p className="text-sm text-slate-500">Runs once, after selection.</p>}
          </section>
        </div>
      </div>

      {w.deterministic_summary && (
        <section aria-labelledby="sum-h" className="card mb-6">
          <h2 id="sum-h" className="text-lg font-semibold">Summary</h2>
          <p className="mt-1 text-xs text-slate-500">Template-generated from stored metrics. No language model involved.</p>
          <pre className="mt-3 font-sans text-sm whitespace-pre-wrap">{w.deterministic_summary}</pre>
        </section>
      )}
      {w.llm_explanation && (
        <section aria-labelledby="llm-h" className="card mb-6 border-violet-200">
          <h2 id="llm-h" className="text-lg font-semibold">Optional LLM explanation</h2>
          <p className="mt-1 text-xs text-violet-800">
            Written by {w.llm_model ?? "a language model"} from the summary above. Numbers were checked against stored
            metrics, but treat the wording as commentary, not analysis.
          </p>
          <p className="mt-3 text-sm whitespace-pre-wrap">{w.llm_explanation}</p>
        </section>
      )}

      <section aria-labelledby="ev-h" className="card">
        <details>
          <summary id="ev-h" className="cursor-pointer text-lg font-semibold">Event log ({w.events.length})</summary>
          <ol className="mt-3 space-y-1 font-mono text-xs">
            {w.events.map((ev) => (
              <li key={ev.id}>
                <span className="text-slate-500">{dateTime(ev.created_at)}</span> {ev.node} <span className="font-semibold">{ev.status}</span>
                {ev.attempt > 1 && ` (attempt ${ev.attempt})`} — {ev.message}
              </li>
            ))}
          </ol>
        </details>
      </section>
    </>
  );
}
