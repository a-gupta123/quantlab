import Link from "next/link";
import { notFound } from "next/navigation";
import { AutoRefresh } from "@/components/auto-refresh";
import { DrawdownChart, EquityChart } from "@/components/charts";
import { ErrorState, Metric, PageHeader, StatusBadge, SyntheticBadge } from "@/components/ui";
import { describeRun } from "@/lib/analysis";
import { apiTry } from "@/lib/api-server";
import { dateTime, num, pct, signClass, usd } from "@/lib/format";
import { type ConfidenceInterval, type ExperimentDetail, experimentDetailSchema, isTerminal, type Metrics, strategyLabel } from "@/lib/schemas";
import { requireSession } from "@/lib/session";
import { ExperimentActions } from "./actions";
import { TradesTable } from "./trades-table";

export default async function ExperimentPage({ params }: PageProps<"/experiments/[id]">) {
  await requireSession();
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const res = await apiTry(`/api/experiments/${id}`, experimentDetailSchema);
  if (res.error?.status === 404) notFound();
  if (res.error) return <ErrorState title="Could not load the experiment" message={res.error.message} />;
  const e = res.data;
  const cfg = e.strategy_config;

  return (
    <>
      <PageHeader title={e.name}>
        <ExperimentActions id={e.id} status={e.status} workflowOwned={e.workflow_run_id !== null} />
      </PageHeader>
      <div className="mb-6 flex flex-wrap items-center gap-3 text-sm text-slate-600">
        <StatusBadge status={e.status} />
        <span>
          {strategyLabel(cfg)} on {e.dataset.name} v{e.dataset.version} ({e.dataset.symbol})
        </span>
        {cfg.rules && (
          <Link href={`/strategies/${cfg.rules.strategy_id}`} className="text-sky-800 underline">
            Open in strategy builder ({cfg.rules.fidelity.toFixed(0)}% match)
          </Link>
        )}
        {e.dataset.is_synthetic && <SyntheticBadge />}
        {e.workflow_run_id && (
          <Link href={`/workflows/${e.workflow_run_id}`} className="text-sky-800 underline">
            Part of research workflow #{e.workflow_run_id} ({e.role})
          </Link>
        )}
        {e.rerun_of_id && (
          <Link href={`/experiments/${e.rerun_of_id}`} className="text-sky-800 underline">
            Re-run of #{e.rerun_of_id}
          </Link>
        )}
      </div>

      <AutoRefresh active={!isTerminal(e.status)} />
      <JobPanel e={e} />

      {e.result ? (
        <Results e={e} />
      ) : e.status === "failed" ? null : (
        <p className="card text-sm text-slate-600">Results will appear here when the worker finishes this run.</p>
      )}

      <Config e={e} />
    </>
  );
}

function JobPanel({ e }: { e: ExperimentDetail }) {
  if (e.status === "completed") return null;
  const job = e.job;
  return (
    <section aria-labelledby="job-h" className={`card mb-6 ${e.status === "failed" ? "border-rose-200 bg-rose-50" : ""}`}>
      <h2 id="job-h" className="text-sm font-semibold">
        {e.status === "failed" ? "This run failed" : e.status === "running" ? "Running on a worker" : "Waiting for a worker"}
      </h2>
      {e.error && <p className="mt-1 text-sm whitespace-pre-wrap text-rose-800">{e.error}</p>}
      {job && (
        <dl className="mt-2 grid gap-x-6 gap-y-1 text-xs text-slate-600 sm:grid-cols-4">
          <div><dt className="inline">Attempt: </dt><dd className="inline">{job.attempts} of {job.max_attempts}</dd></div>
          <div><dt className="inline">Worker: </dt><dd className="inline">{job.lease_owner ?? "—"}</dd></div>
          <div><dt className="inline">Last heartbeat: </dt><dd className="inline">{dateTime(job.heartbeat_at)}</dd></div>
          {job.last_error && e.status !== "failed" && (
            <div className="sm:col-span-4"><dt className="inline">Previous attempt error: </dt><dd className="inline">{job.last_error}</dd></div>
          )}
        </dl>
      )}
      {e.status === "failed" && (
        <p className="mt-2 text-xs text-slate-600">Use “Re-run” to queue a fresh copy with the same configuration.</p>
      )}
      {e.status === "queued" && (
        <p className="mt-2 text-xs text-slate-600">
          If this stays queued, check the dashboard: it shows whether a worker is online (or that runs execute
          serverlessly, in which case refreshing this page retries it).
        </p>
      )}
    </section>
  );
}

function Results({ e }: { e: ExperimentDetail }) {
  const r = e.result!;
  const s = r.strategy_metrics;
  const b = r.benchmark_metrics;
  const curve = r.equity_curve;
  return (
    <>
      <section aria-labelledby="metrics-h" className="mb-6">
        <h2 id="metrics-h" className="mb-3 text-lg font-semibold">Headline metrics</h2>
        <dl className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <Metric label="Final equity" value={usd(s.final_equity)} hint={`Buy & hold ${usd(b.final_equity)}`} />
          <Metric label="Total return" value={pct(s.total_return)} className={signClass(s.total_return)} hint={`Buy & hold ${pct(b.total_return)}`} />
          <Metric label="CAGR" value={pct(s.cagr)} hint={`Buy & hold ${pct(b.cagr)}`} />
          <Metric label="Sharpe" value={num(s.sharpe_ratio)} hint={s.undefined.sharpe_ratio ?? `Buy & hold ${num(b.sharpe_ratio)}`} />
          <Metric label="Max drawdown" value={pct(s.max_drawdown)} className="text-rose-700" hint={`Buy & hold ${pct(b.max_drawdown)}`} />
        </dl>
      </section>

      <section aria-labelledby="charts-h" className="card mb-6 space-y-6">
        <h2 id="charts-h" className="sr-only">Charts</h2>
        <EquityChart
          title={`Equity, ${r.eval_start} to ${r.eval_end} (marked at each close)`}
          dates={curve.dates}
          series={[
            { key: "strategy", label: strategyLabel(e.strategy_config), values: curve.strategy },
            { key: "benchmark", label: "Buy & hold", values: curve.benchmark, dashed: true },
          ]}
        />
        <DrawdownChart
          title="Drawdown from running peak"
          dates={curve.dates}
          series={[
            { key: "strategy", label: "Strategy", values: curve.strategy_drawdown },
            { key: "benchmark", label: "Buy & hold", values: curve.benchmark_drawdown },
          ]}
        />
      </section>

      <div className="mb-6 grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="analysis-h" className="card">
          <h2 id="analysis-h" className="text-lg font-semibold">Analysis</h2>
          <p className="mt-1 text-xs text-slate-500">Generated from the computed metrics; no model or LLM involved.</p>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm">
            {describeRun(s, b, r.confidence_intervals.strategy).map((line) => <li key={line}>{line}</li>)}
          </ul>
          {r.notes.length > 0 && (
            <>
              <h3 className="mt-4 text-sm font-semibold">Engine notes</h3>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-xs text-slate-600">
                {r.notes.map((n) => <li key={n}>{n}</li>)}
              </ul>
            </>
          )}
        </section>
        <section aria-labelledby="ci-h" className="card">
          <h2 id="ci-h" className="text-lg font-semibold">Uncertainty: mean daily return</h2>
          <CiTable strategy={r.confidence_intervals.strategy} benchmark={r.confidence_intervals.benchmark} />
        </section>
      </div>

      <section aria-labelledby="detail-h" className="card mb-6 overflow-x-auto">
        <h2 id="detail-h" className="mb-3 text-lg font-semibold">All metrics</h2>
        <MetricsTable s={s} b={b} />
      </section>

      <section aria-labelledby="trades-h" className="card mb-6">
        <h2 id="trades-h" className="mb-3 text-lg font-semibold">Trades ({e.trades.length})</h2>
        <TradesTable trades={e.trades} />
      </section>
    </>
  );
}

function CiTable({ strategy, benchmark }: { strategy: ConfidenceInterval; benchmark: ConfidenceInterval }) {
  const row = (label: string, ci: ConfidenceInterval) => (
    <tr key={label}>
      <th scope="row" className="!bg-white !text-sm !font-medium !normal-case">{label}</th>
      <td className="num">{pct(ci.point_estimate, 3)}</td>
      <td className="num">{ci.status === "ok" ? `${pct(ci.low, 3)} to ${pct(ci.high, 3)}` : "—"}</td>
      <td className="text-xs whitespace-normal text-slate-600">{ci.status === "ok" ? "" : ci.detail}</td>
    </tr>
  );
  const c = strategy;
  return (
    <>
      <table className="table mt-3">
        <thead>
          <tr><th scope="col">Series</th><th scope="col" className="num">Mean</th><th scope="col" className="num">{pct(c.confidence_level, 0)} CI</th><th scope="col"><span className="sr-only">Notes</span></th></tr>
        </thead>
        <tbody>{[row("Strategy", strategy), row("Buy & hold", benchmark)]}</tbody>
      </table>
      <p className="mt-3 text-xs text-slate-600">
        {c.method}; block length {c.block_length} days, {c.n_resamples.toLocaleString()} resamples, seed {c.seed},
        {" "}{c.n_returns} daily returns{c.dropped_oldest_days ? ` (oldest ${c.dropped_oldest_days} dropped to fill whole blocks)` : ""}.
        This is a confidence interval for the historical mean under the resampling assumptions — not a prediction interval for future returns.
      </p>
    </>
  );
}

function MetricsTable({ s, b }: { s: Metrics; b: Metrics }) {
  const rows: [string, (m: Metrics) => string][] = [
    ["Final equity", (m) => usd(m.final_equity)],
    ["Total return", (m) => pct(m.total_return)],
    ["CAGR (252-day year)", (m) => pct(m.cagr)],
    ["Annualized volatility", (m) => pct(m.annualized_volatility)],
    ["Sharpe ratio", (m) => num(m.sharpe_ratio)],
    ["Max drawdown", (m) => pct(m.max_drawdown)],
    ["Mean daily return", (m) => pct(m.mean_daily_return, 4)],
    ["Exposure (days in a position)", (m) => pct(m.exposure, 1)],
    ["Trades", (m) => String(m.n_trades)],
    ["Fees paid", (m) => usd(m.total_fees)],
    ["Slippage cost", (m) => usd(m.total_slippage)],
    ["Trading days", (m) => String(m.n_days)],
  ];
  return (
    <table className="table">
      <thead><tr><th scope="col">Metric</th><th scope="col" className="num">Strategy</th><th scope="col" className="num">Buy &amp; hold</th></tr></thead>
      <tbody className="divide-y divide-slate-100">
        {rows.map(([label, f]) => (
          <tr key={label}><th scope="row" className="!bg-white !text-sm !font-normal !normal-case">{label}</th><td className="num">{f(s)}</td><td className="num">{f(b)}</td></tr>
        ))}
      </tbody>
    </table>
  );
}

function Config({ e }: { e: ExperimentDetail }) {
  const c = e.strategy_config;
  const items: [string, string][] = [
    ["Dataset", `${e.dataset.name} v${e.dataset.version} · ${e.dataset.source} · ${e.dataset.adjustment}`],
    ["Dataset SHA-256", e.dataset_sha256],
    ["Engine version", e.engine_version],
    ["Requested period", `${e.start_date} to ${e.end_date}`],
    ["Initial capital", usd(e.initial_capital)],
    c.rules
      ? ["Rules", c.rules.rules_text.join(" · ")]
      : ["Windows", `${c.short_window} / ${c.long_window} trading days`],
    ["Fee / slippage", `${c.fee_bps} bps / ${c.slippage_bps} bps`],
    ["Fractional shares", c.allow_fractional ? "Allowed" : "Whole shares only (leftover cash stays uninvested)"],
    ["Risk-free rate (annual)", pct(e.risk_free_rate)],
    ["Bootstrap", `block ${e.bootstrap_block_length}, ${e.bootstrap_resamples} resamples, ${pct(e.confidence_level, 0)}, seed ${e.seed}`],
    ["Created", dateTime(e.created_at)],
    ["Completed", dateTime(e.completed_at)],
  ];
  return (
    <section aria-labelledby="config-h" className="card mb-6">
      <h2 id="config-h" className="mb-3 text-lg font-semibold">Configuration and provenance</h2>
      <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
        {items.map(([k, v]) => (
          <div key={k} className="flex gap-2">
            <dt className="w-44 shrink-0 text-slate-500">{k}</dt>
            <dd className="font-mono text-xs break-all text-slate-800">{v}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-4 text-xs text-slate-500">
        Execution model: signal at day t close, fill at day t+1 open. Any open position is marked to the final close and not sold.
        Dividends and splits are only reflected if the dataset is adjusted; the engine does not apply corporate actions.{" "}
        <a className="text-sky-800 underline" href={`/api/backend/experiments/${e.id}/artifact`}>Download result JSON</a>
      </p>
    </section>
  );
}
