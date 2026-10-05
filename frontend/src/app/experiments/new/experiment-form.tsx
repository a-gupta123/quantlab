"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { SyntheticBadge } from "@/components/ui";
import { clientFetch, postJson } from "@/lib/api-client";
import { ApiError } from "@/lib/api-errors";
import { type Dataset, experimentDetailSchema, warmupSchema } from "@/lib/schemas";

export type StrategyOption = { versionId: number; label: string };

type Form = {
  name: string;
  dataset_id: string;
  strategy: string; // "ma" or a strategy version id
  start_date: string;
  end_date: string;
  initial_capital: string;
  short_window: string;
  long_window: string;
  fee_bps: string;
  slippage_bps: string;
  allow_fractional: boolean;
  seed: string;
  bootstrap_block_length: string;
};

type Errors = Partial<Record<keyof Form, string>>;

function validate(f: Form, ds: Dataset | undefined, earliest: string | null, warmup: number | null): Errors {
  const e: Errors = {};
  const int = (v: string) => /^\d+$/.test(v.trim());
  if (!f.name.trim()) e.name = "Give the run a name.";
  if (!ds) e.dataset_id = "Choose a dataset.";
  if (!f.start_date) e.start_date = "Pick a start date.";
  if (!f.end_date) e.end_date = "Pick an end date.";
  if (f.start_date && f.end_date && f.start_date >= f.end_date) e.end_date = "End date must be after the start date.";
  if (ds && f.end_date > ds.end_date) e.end_date = `The dataset ends on ${ds.end_date}.`;
  if (earliest && f.start_date && f.start_date < earliest) {
    e.start_date = `This strategy needs ${warmup ?? "some"} trading days of history first; earliest valid start is ${earliest}.`;
  }
  const cap = Number(f.initial_capital);
  if (!(cap >= 100 && cap <= 1e9)) e.initial_capital = "Use an amount between $100 and $1,000,000,000.";
  if (f.strategy === "ma") {
    if (!int(f.short_window) || Number(f.short_window) < 1) e.short_window = "Whole number, at least 1.";
    if (!int(f.long_window) || Number(f.long_window) > 400) e.long_window = "Whole number, at most 400.";
    if (!e.short_window && !e.long_window && Number(f.short_window) >= Number(f.long_window)) {
      e.long_window = "Long window must be larger than the short window.";
    }
  }
  for (const k of ["fee_bps", "slippage_bps"] as const) {
    const v = Number(f[k]);
    if (f[k] === "" || !(v >= 0 && v <= 500)) e[k] = "Between 0 and 500 basis points.";
  }
  if (!int(f.seed)) e.seed = "Non-negative whole number.";
  const bl = Number(f.bootstrap_block_length);
  if (!int(f.bootstrap_block_length) || bl < 1 || bl > 250) e.bootstrap_block_length = "Between 1 and 250 days.";
  return e;
}

function Field({ id, label, hint, error, children }: { id: keyof Form; label: string; hint?: string; error?: string; children: React.ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="label">{label}</label>
      {children}
      {error ? <p id={`${id}-error`} className="field-error">{error}</p> : hint ? <p id={`${id}-hint`} className="hint">{hint}</p> : null}
    </div>
  );
}

export function ExperimentForm({
  datasets,
  strategies,
  initialStrategy,
}: {
  datasets: Dataset[];
  strategies: StrategyOption[];
  initialStrategy: number | null;
}) {
  const router = useRouter();
  const first = datasets[0];
  const initialOption = strategies.find((s) => s.versionId === initialStrategy);
  const [f, setF] = useState<Form>({
    name: initialOption ? initialOption.label : "MA 50/200",
    dataset_id: String(first.id),
    strategy: initialOption ? String(initialOption.versionId) : "ma",
    start_date: "",
    end_date: first.end_date,
    initial_capital: "10000",
    short_window: "50",
    long_window: "200",
    fee_bps: "5",
    slippage_bps: "5",
    allow_fractional: true,
    seed: "42",
    bootstrap_block_length: "20",
  });
  const [touched, setTouched] = useState(false);
  const [earliest, setEarliest] = useState<string | null>(null);
  const [warmup, setWarmup] = useState<number | null>(null);
  const isMa = f.strategy === "ma";
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const ds = useMemo(() => datasets.find((d) => String(d.id) === f.dataset_id), [datasets, f.dataset_id]);

  // Ask the backend for the first date with enough warm-up history.
  useEffect(() => {
    const lw = Number(f.long_window);
    if (!ds) return;
    if (f.strategy === "ma" && (!Number.isInteger(lw) || lw < 2 || lw > 400)) return;
    const query = f.strategy === "ma" ? `long_window=${lw}` : `strategy_version_id=${f.strategy}`;
    let cancelled = false;
    clientFetch(`/datasets/${ds.id}/warmup?${query}`, warmupSchema)
      .then((w) => {
        if (cancelled) return;
        setEarliest(w.earliest_start);
        setWarmup(w.warmup_bars);
        setF((prev) => (prev.start_date ? prev : { ...prev, start_date: w.earliest_start ?? "" }));
      })
      .catch(() => !cancelled && setEarliest(null));
    return () => {
      cancelled = true;
    };
  }, [ds, f.long_window, f.strategy]);

  const errors = validate(f, ds, earliest, warmup);
  const show = (k: keyof Form) => (touched ? errors[k] : undefined);
  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setF({ ...f, [k]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value });
  const aria = (k: keyof Form) => ({
    id: k,
    "aria-invalid": Boolean(show(k)) || undefined,
    "aria-describedby": show(k) ? `${k}-error` : `${k}-hint`,
  });

  function chooseStrategy(e: React.ChangeEvent<HTMLSelectElement>) {
    const label = (v: string) => strategies.find((s) => String(s.versionId) === v)?.label ?? `MA ${f.short_window}/${f.long_window}`;
    // Keep a name the user typed; replace one we filled in.
    const autoNamed = f.name === "MA 50/200" || f.name === label(f.strategy);
    setF({ ...f, strategy: e.target.value, start_date: "", name: autoNamed ? label(e.target.value) : f.name });
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    setServerError(null);
    if (Object.keys(errors).length) return;
    setSubmitting(true);
    try {
      const created = await postJson("/experiments", experimentDetailSchema, {
        name: f.name.trim(),
        dataset_id: Number(f.dataset_id),
        start_date: f.start_date,
        end_date: f.end_date,
        initial_capital: Number(f.initial_capital),
        ...(isMa
          ? { short_window: Number(f.short_window), long_window: Number(f.long_window) }
          : { strategy_version_id: Number(f.strategy) }),
        fee_bps: Number(f.fee_bps),
        slippage_bps: Number(f.slippage_bps),
        allow_fractional: f.allow_fractional,
        seed: Number(f.seed),
        bootstrap_block_length: Number(f.bootstrap_block_length),
      });
      router.push(`/experiments/${created.id}`);
      router.refresh();
    } catch (err) {
      setServerError(err instanceof ApiError ? err.message : "Could not create the experiment.");
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="card max-w-3xl space-y-6" aria-describedby="form-note">
      <p id="form-note" className="text-sm text-slate-600">
        Run the long/cash moving-average crossover or a strategy you built in the{" "}
        <Link href="/strategies" className="text-sky-800 underline">strategy builder</Link>. Signals use each day&apos;s
        close; orders execute at the next day&apos;s open with the fee and slippage below. Buy-and-hold over the same
        dates is computed as the benchmark.
      </p>

      <fieldset className="grid gap-4 sm:grid-cols-2">
        <legend className="mb-2 text-sm font-semibold text-slate-800">Data and period</legend>
        <Field id="name" label="Run name" error={show("name")}>
          <input {...aria("name")} className="input mt-1" value={f.name} onChange={set("name")} maxLength={120} />
        </Field>
        <Field id="dataset_id" label="Dataset" error={show("dataset_id")} hint={ds ? `${ds.row_count} bars, ${ds.start_date} to ${ds.end_date}, ${ds.adjustment}` : undefined}>
          <select {...aria("dataset_id")} className="input mt-1" value={f.dataset_id} onChange={(e) => setF({ ...f, dataset_id: e.target.value, start_date: "", end_date: datasets.find((d) => String(d.id) === e.target.value)?.end_date ?? "" })}>
            {datasets.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} v{d.version} ({d.symbol}){d.is_synthetic ? " — SYNTHETIC" : ""}
              </option>
            ))}
          </select>
        </Field>
        {ds?.is_synthetic && (
          <p className="text-xs text-amber-900 sm:col-span-2">
            <SyntheticBadge /> This dataset is generated random data, not historical market prices.
          </p>
        )}
        <Field id="start_date" label="Start date" error={show("start_date")} hint={earliest ? `Earliest valid start (${warmup ?? "required"} days of warm-up): ${earliest}` : undefined}>
          <input {...aria("start_date")} type="date" className="input mt-1" value={f.start_date} min={earliest ?? ds?.start_date} max={ds?.end_date} onChange={set("start_date")} />
        </Field>
        <Field id="end_date" label="End date" error={show("end_date")}>
          <input {...aria("end_date")} type="date" className="input mt-1" value={f.end_date} min={ds?.start_date} max={ds?.end_date} onChange={set("end_date")} />
        </Field>
      </fieldset>

      <fieldset className="grid gap-4 sm:grid-cols-3">
        <legend className="mb-2 text-sm font-semibold text-slate-800">Strategy and costs</legend>
        <div className="sm:col-span-3">
          <Field id="strategy" label="Strategy" hint={isMa ? undefined : "Each version's rules are fixed; refine it in the strategy builder to get a new version."}>
            <select {...aria("strategy")} className="input mt-1" value={f.strategy} onChange={chooseStrategy}>
              <option value="ma">Moving-average crossover (long / cash)</option>
              {strategies.length > 0 && (
                <optgroup label="Built with the strategy builder">
                  {strategies.map((s) => (
                    <option key={s.versionId} value={s.versionId}>{s.label}</option>
                  ))}
                </optgroup>
              )}
            </select>
          </Field>
        </div>
        {isMa && (
          <>
            <Field id="short_window" label="Short window (days)" error={show("short_window")}>
              <input {...aria("short_window")} inputMode="numeric" className="input mt-1" value={f.short_window} onChange={set("short_window")} />
            </Field>
            <Field id="long_window" label="Long window (days)" error={show("long_window")}>
              <input {...aria("long_window")} inputMode="numeric" className="input mt-1" value={f.long_window} onChange={set("long_window")} />
            </Field>
          </>
        )}
        <Field id="initial_capital" label="Initial capital (USD)" error={show("initial_capital")}>
          <input {...aria("initial_capital")} inputMode="decimal" className="input mt-1" value={f.initial_capital} onChange={set("initial_capital")} />
        </Field>
        <Field id="fee_bps" label="Transaction fee (bps)" hint="Per trade, on notional. 1 bp = 0.01%." error={show("fee_bps")}>
          <input {...aria("fee_bps")} inputMode="decimal" className="input mt-1" value={f.fee_bps} onChange={set("fee_bps")} />
        </Field>
        <Field id="slippage_bps" label="Slippage (bps)" hint="Adverse move from the open price." error={show("slippage_bps")}>
          <input {...aria("slippage_bps")} inputMode="decimal" className="input mt-1" value={f.slippage_bps} onChange={set("slippage_bps")} />
        </Field>
        <div className="flex items-center pt-6">
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={f.allow_fractional} onChange={set("allow_fractional")} />
            Allow fractional shares
          </label>
        </div>
      </fieldset>

      <details className="rounded-md border border-slate-200 p-4">
        <summary className="cursor-pointer text-sm font-semibold text-slate-800">Reproducibility and confidence interval</summary>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <Field id="seed" label="Random seed" hint="Seeds the bootstrap resampling." error={show("seed")}>
            <input {...aria("seed")} inputMode="numeric" className="input mt-1" value={f.seed} onChange={set("seed")} />
          </Field>
          <Field id="bootstrap_block_length" label="Bootstrap block length (days)" hint="Consecutive days resampled together." error={show("bootstrap_block_length")}>
            <input {...aria("bootstrap_block_length")} inputMode="numeric" className="input mt-1" value={f.bootstrap_block_length} onChange={set("bootstrap_block_length")} />
          </Field>
        </div>
      </details>

      {serverError && (
        <p role="alert" className="rounded-md bg-rose-50 p-3 text-sm text-rose-800">
          {serverError}
        </p>
      )}
      {touched && Object.keys(errors).length > 0 && (
        <p role="alert" className="text-sm text-rose-700">Fix the highlighted fields before submitting.</p>
      )}
      <div className="flex gap-3">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? "Submitting…" : "Run experiment"}
        </button>
      </div>
    </form>
  );
}
