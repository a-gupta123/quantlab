import Link from "next/link";
import { DrawdownChart, EquityChart } from "@/components/charts";
import { ErrorState, PageHeader, SyntheticBadge } from "@/components/ui";
import { apiTry } from "@/lib/api-server";
import { num, pct, usd } from "@/lib/format";
import { compareSchema, experimentSummarySchema, type Metrics, pageOf, strategyLabel } from "@/lib/schemas";
import { requireSession } from "@/lib/session";
import { ExperimentTable } from "../experiment-table";

export const metadata = { title: "Compare · QuantLab" };

export default async function ComparePage({ searchParams }: PageProps<"/compare">) {
  await requireSession();
  const raw = (await searchParams).ids;
  const ids = typeof raw === "string" ? raw.split(",").filter((x) => /^\d+$/.test(x)) : [];

  if (ids.length < 2) {
    const done = await apiTry("/api/experiments?status=completed&limit=50&include_workflow=true", pageOf(experimentSummarySchema));
    return (
      <>
        <PageHeader title="Compare runs" />
        <p className="mb-4 max-w-3xl text-sm text-slate-600">
          Select two or three completed runs. They must use the same dataset version and the same evaluation period, so
          that differences come from the strategy settings rather than from different market windows.
        </p>
        {done.error ? <ErrorState title="Could not load runs" message={done.error.message} /> : <ExperimentTable items={done.data.items} filtered />}
      </>
    );
  }

  const res = await apiTry(`/api/experiments/compare?ids=${ids.slice(0, 3).join(",")}`, compareSchema);
  if (res.error) {
    return (
      <>
        <PageHeader title="Compare runs" />
        <ErrorState title="These runs cannot be compared" message={res.error.message} />
        <Link href="/compare" className="btn-secondary mt-4">Choose different runs</Link>
      </>
    );
  }
  const cmp = res.data;
  const runs = cmp.experiments.filter((e) => e.result);
  const first = runs[0];
  const dates = first.result!.equity_curve.dates;
  const synthetic = first.dataset.is_synthetic;

  const metricRows: [string, (m: Metrics) => string, "max" | "min" | null][] = [
    ["Final equity", (m) => usd(m.final_equity), "max"],
    ["Total return", (m) => pct(m.total_return), "max"],
    ["CAGR", (m) => pct(m.cagr), "max"],
    ["Annualized volatility", (m) => pct(m.annualized_volatility), null],
    ["Sharpe ratio", (m) => num(m.sharpe_ratio), "max"],
    ["Max drawdown", (m) => pct(m.max_drawdown), "max"],
    ["Exposure", (m) => pct(m.exposure, 1), null],
    ["Trades", (m) => String(m.n_trades), null],
    ["Fees + slippage", (m) => usd(m.total_fees + m.total_slippage), null],
  ];
  const valueOf: Record<string, (m: Metrics) => number | null> = {
    "Final equity": (m) => m.final_equity,
    "Total return": (m) => m.total_return,
    CAGR: (m) => m.cagr,
    "Sharpe ratio": (m) => m.sharpe_ratio,
    "Max drawdown": (m) => m.max_drawdown,
  };

  return (
    <>
      <PageHeader title="Compare runs" />
      <p className="mb-4 text-sm text-slate-600">
        {runs.length} runs on {first.dataset.name} v{first.dataset.version} {synthetic && <SyntheticBadge />}, evaluated{" "}
        {cmp.eval_start} to {cmp.eval_end}. Buy-and-hold is identical for all of them because the dates and data match.
      </p>

      <section className="card mb-6 space-y-6">
        <EquityChart
          title="Equity"
          dates={dates}
          series={[
            ...runs.map((e) => ({ key: `e${e.id}`, label: e.name, values: e.result!.equity_curve.strategy })),
            { key: "bh", label: "Buy & hold", values: first.result!.equity_curve.benchmark, dashed: true },
          ]}
        />
        <DrawdownChart
          title="Drawdown"
          dates={dates}
          series={runs.map((e) => ({ key: `e${e.id}`, label: e.name, values: e.result!.equity_curve.strategy_drawdown }))}
        />
      </section>

      <section className="card overflow-x-auto">
        <table className="table">
          <caption className="mb-2 text-left text-sm text-slate-600">
            Bold marks the best value in a row. Picking the best past run this way is in-sample; use the research workflow for a held-out check.
          </caption>
          <thead>
            <tr>
              <th scope="col">Metric</th>
              {runs.map((e) => (
                <th key={e.id} scope="col" className="num">
                  <Link href={`/experiments/${e.id}`} className="text-sky-800 normal-case underline">{e.name}</Link>
                  <div className="font-normal normal-case">{strategyLabel(e.strategy_config)}</div>
                </th>
              ))}
              <th scope="col" className="num">Buy &amp; hold</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {metricRows.map(([label, fmt, best]) => {
              const vals = runs.map((e) => valueOf[label]?.(e.result!.strategy_metrics) ?? null);
              const finite = vals.filter((v): v is number => v !== null);
              const target = best && finite.length ? (best === "max" ? Math.max(...finite) : Math.min(...finite)) : null;
              return (
                <tr key={label}>
                  <th scope="row" className="!bg-white !text-sm !font-normal !normal-case">{label}</th>
                  {runs.map((e, i) => (
                    <td key={e.id} className={`num ${target !== null && vals[i] === target ? "font-bold" : ""}`}>
                      {fmt(e.result!.strategy_metrics)}
                    </td>
                  ))}
                  <td className="num text-slate-600">{fmt(first.result!.benchmark_metrics)}</td>
                </tr>
              );
            })}
            <tr>
              <th scope="row" className="!bg-white !text-sm !font-normal !normal-case">Mean daily return CI</th>
              {runs.map((e) => {
                const ci = e.result!.confidence_intervals.strategy;
                return <td key={e.id} className="num text-xs">{ci.status === "ok" ? `${pct(ci.low, 3)} to ${pct(ci.high, 3)}` : ci.status}</td>;
              })}
              <td className="num text-xs text-slate-600">
                {(() => {
                  const ci = first.result!.confidence_intervals.benchmark;
                  return ci.status === "ok" ? `${pct(ci.low, 3)} to ${pct(ci.high, 3)}` : ci.status;
                })()}
              </td>
            </tr>
          </tbody>
        </table>
      </section>
    </>
  );
}
