"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { clientFetch, postJson } from "@/lib/api-client";
import { ApiError } from "@/lib/api-errors";
import { type Dataset, type Variant, warmupSchema, workflowDetailSchema } from "@/lib/schemas";

const MAX_VARIANTS = 3;

const addDays = (iso: string, n: number) => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};

/** Suggest a chronological split: the first ~70% of usable dates for development. */
function suggestSplit(earliest: string, end: string) {
  const a = Date.parse(earliest);
  const b = Date.parse(end);
  const devEnd = new Date(a + (b - a) * 0.7).toISOString().slice(0, 10);
  return { dev_start: earliest, dev_end: devEnd, holdout_start: addDays(devEnd, 1), holdout_end: end };
}

export function WorkflowForm({ datasets, variants }: { datasets: Dataset[]; variants: Variant[] }) {
  const router = useRouter();
  const [datasetId, setDatasetId] = useState(String(datasets[0].id));
  const [name, setName] = useState("Crossover research");
  const [keys, setKeys] = useState<string[]>(variants.slice(0, MAX_VARIANTS).map((v) => v.key));
  const [periods, setPeriods] = useState({ dev_start: "", dev_end: "", holdout_start: "", holdout_end: "" });
  const [capital, setCapital] = useState("10000");
  const [fee, setFee] = useState("5");
  const [slip, setSlip] = useState("5");
  const [seed, setSeed] = useState("42");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const ds = datasets.find((d) => String(d.id) === datasetId)!;
  const maxLong = useMemo(
    () => Math.max(2, ...variants.filter((v) => keys.includes(v.key)).map((v) => v.long_window)),
    [variants, keys],
  );

  useEffect(() => {
    let cancelled = false;
    clientFetch(`/datasets/${ds.id}/warmup?long_window=${maxLong}`, warmupSchema)
      .then((w) => {
        if (!cancelled && w.earliest_start) setPeriods(suggestSplit(w.earliest_start, ds.end_date));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [ds, maxLong]);

  const ordered =
    periods.dev_start < periods.dev_end && periods.dev_end < periods.holdout_start && periods.holdout_start < periods.holdout_end;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (keys.length === 0) return setError("Choose at least one variant.");
    if (!ordered) return setError("Periods must be in order: development start < development end < held-out start < held-out end.");
    setBusy(true);
    try {
      const wf = await postJson("/workflows", workflowDetailSchema, {
        name: name.trim(),
        dataset_id: ds.id,
        ...periods,
        initial_capital: Number(capital),
        fee_bps: Number(fee),
        slippage_bps: Number(slip),
        seed: Number(seed),
        variant_keys: keys,
      });
      router.push(`/workflows/${wf.id}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start the workflow.");
      setBusy(false);
    }
  }

  const dateField = (k: keyof typeof periods, label: string) => (
    <div>
      <label htmlFor={k} className="label">{label}</label>
      <input id={k} type="date" className="input mt-1" value={periods[k]} min={ds.start_date} max={ds.end_date}
        onChange={(e) => setPeriods({ ...periods, [k]: e.target.value })} required />
    </div>
  );

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="wf-name" className="label">Name</label>
          <input id="wf-name" className="input mt-1" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} required />
        </div>
        <div>
          <label htmlFor="wf-ds" className="label">Dataset</label>
          <select id="wf-ds" className="input mt-1" value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>
            {datasets.map((d) => (
              <option key={d.id} value={d.id}>{d.name} v{d.version}{d.is_synthetic ? " — SYNTHETIC" : ""}</option>
            ))}
          </select>
        </div>
      </div>

      <fieldset>
        <legend className="label">Variants (up to {MAX_VARIANTS})</legend>
        <div className="mt-2 space-y-1">
          {variants.map((v) => (
            <label key={v.key} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={keys.includes(v.key)}
                disabled={!keys.includes(v.key) && keys.length >= MAX_VARIANTS}
                onChange={(e) => setKeys(e.target.checked ? [...keys, v.key] : keys.filter((k) => k !== v.key))}
              />
              {v.label} <span className="font-mono text-xs text-slate-500">({v.short_window}/{v.long_window})</span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="grid gap-4 sm:grid-cols-2">
        <legend className="label mb-1">Periods (suggested: first 70% for development)</legend>
        {dateField("dev_start", "Development start")}
        {dateField("dev_end", "Development end")}
        {dateField("holdout_start", "Held-out start")}
        {dateField("holdout_end", "Held-out end")}
      </fieldset>

      <div className="grid gap-4 sm:grid-cols-4">
        <div><label htmlFor="wf-cap" className="label">Capital</label><input id="wf-cap" inputMode="decimal" className="input mt-1" value={capital} onChange={(e) => setCapital(e.target.value)} /></div>
        <div><label htmlFor="wf-fee" className="label">Fee (bps)</label><input id="wf-fee" inputMode="decimal" className="input mt-1" value={fee} onChange={(e) => setFee(e.target.value)} /></div>
        <div><label htmlFor="wf-slip" className="label">Slippage (bps)</label><input id="wf-slip" inputMode="decimal" className="input mt-1" value={slip} onChange={(e) => setSlip(e.target.value)} /></div>
        <div><label htmlFor="wf-seed" className="label">Seed</label><input id="wf-seed" inputMode="numeric" className="input mt-1" value={seed} onChange={(e) => setSeed(e.target.value)} /></div>
      </div>

      {error && <p role="alert" className="text-sm text-rose-700">{error}</p>}
      <button className="btn-primary" disabled={busy}>{busy ? "Starting…" : "Start workflow"}</button>
    </form>
  );
}
