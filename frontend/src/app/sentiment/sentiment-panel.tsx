"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/ui";
import { clientFetch, postJson } from "@/lib/api-client";
import { ApiError } from "@/lib/api-errors";
import { dateTime } from "@/lib/format";
import { isTerminal, type SentimentBatch, sentimentBatchSchema } from "@/lib/schemas";

const MAX_HEADLINES = 32;
const LABEL_STYLE = {
  positive: "bg-emerald-100 text-emerald-900",
  negative: "bg-rose-100 text-rose-900",
  neutral: "bg-slate-100 text-slate-800",
} as const;

function BatchView({ batch }: { batch: SentimentBatch }) {
  const first = batch.headlines.find((h) => h.result)?.result;
  return (
    <div className="card">
      <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
        <span className="font-medium">Batch #{batch.id}</span>
        <StatusBadge status={batch.status} />
        <span className="text-xs text-slate-500">{dateTime(batch.created_at)}</span>
        {first && <span className="font-mono text-xs text-slate-500">{first.model_name}@{first.model_revision.slice(0, 10)}</span>}
      </div>
      {batch.status === "failed" && (
        <p role="alert" className="mb-3 rounded-md bg-rose-50 p-3 text-sm text-rose-800">
          Classification unavailable: {batch.error ?? "unknown error"}. No labels were produced for these headlines.
        </p>
      )}
      {!isTerminal(batch.status) && (
        <p className="mb-3 text-sm text-slate-600" aria-live="polite">
          {batch.status === "queued" ? "Waiting for the worker…" : "Classifying (the first run loads the model, which can take a while)…"}
        </p>
      )}
      <ul className="divide-y divide-slate-100">
        {batch.headlines.map((h) => (
          <li key={h.id} className="py-2">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <p className="text-sm">
                {h.source === "sample" && (
                  <span className="mr-2 rounded bg-slate-200 px-1.5 py-0.5 text-xs font-medium text-slate-700">SAMPLE</span>
                )}
                {h.text}
              </p>
              {h.result ? (
                <span className={`rounded px-2 py-0.5 text-xs font-semibold ${LABEL_STYLE[h.result.label]}`}>{h.result.label}</span>
              ) : (
                <span className="text-xs text-slate-400">{batch.status === "failed" ? "not classified" : "pending"}</span>
              )}
            </div>
            {h.result && (
              <div className="mt-1 flex gap-4 font-mono text-xs text-slate-600" aria-label="Class probabilities">
                <span>pos {(h.result.score_positive * 100).toFixed(1)}%</span>
                <span>neg {(h.result.score_negative * 100).toFixed(1)}%</span>
                <span>neu {(h.result.score_neutral * 100).toFixed(1)}%</span>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SentimentPanel({ samples, recent }: { samples: string[]; recent: SentimentBatch[] }) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [includeSamples, setIncludeSamples] = useState(true);
  const [current, setCurrent] = useState<SentimentBatch | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);

  // Poll the submitted batch until the worker finishes it.
  useEffect(() => {
    if (!current || isTerminal(current.status)) return;
    const t = setTimeout(async () => {
      try {
        setCurrent(await clientFetch(`/sentiment/batches/${current.id}`, sentimentBatchSchema));
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Lost contact with the API.");
      }
    }, 1500);
    return () => clearTimeout(t);
  }, [current]);

  useEffect(() => {
    if (current && isTerminal(current.status)) router.refresh();
  }, [current, router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!lines.length && !includeSamples) return setError("Enter at least one headline or include the samples.");
    if (lines.length + (includeSamples ? samples.length : 0) > MAX_HEADLINES) {
      return setError(`At most ${MAX_HEADLINES} headlines per batch.`);
    }
    if (lines.some((l) => l.length > 300)) return setError("Each headline must be 300 characters or fewer.");
    setBusy(true);
    try {
      setCurrent(await postJson("/sentiment/batches", sentimentBatchSchema, { headlines: lines, include_samples: includeSamples }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <form onSubmit={submit} className="card space-y-4">
        <div>
          <label htmlFor="headlines" className="label">Headlines (one per line)</label>
          <textarea id="headlines" rows={6} className="input mt-1" value={text} onChange={(e) => setText(e.target.value)}
            placeholder="Central bank holds rates steady as inflation cools" aria-describedby="headlines-hint" />
          <p id="headlines-hint" className="hint">{lines.length} entered · max {MAX_HEADLINES} per batch, 300 characters each.</p>
        </div>
        <fieldset>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={includeSamples} onChange={(e) => setIncludeSamples(e.target.checked)} />
            Include the {samples.length} sample headlines
          </label>
          <ul className="mt-2 list-disc space-y-0.5 pl-6 text-xs text-slate-500">
            {samples.map((s) => <li key={s}>{s} <span className="text-slate-400">(illustrative sample, not real news)</span></li>)}
          </ul>
        </fieldset>
        {error && <p role="alert" className="text-sm text-rose-700">{error}</p>}
        <button className="btn-primary" disabled={busy || (current !== null && !isTerminal(current.status))}>
          {busy ? "Submitting…" : "Classify"}
        </button>
      </form>
      <div className="space-y-4">
        {current && <BatchView batch={current} />}
        {recent.filter((b) => b.id !== current?.id).length > 0 && (
          <>
            <h2 className="text-sm font-semibold text-slate-700">Recent batches</h2>
            {recent.filter((b) => b.id !== current?.id).map((b) => <BatchView key={b.id} batch={b} />)}
          </>
        )}
      </div>
    </div>
  );
}
