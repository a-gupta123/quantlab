"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { z } from "zod";
import { clientFetch } from "@/lib/api-client";
import { ApiError } from "@/lib/api-errors";
import { datasetSchema } from "@/lib/schemas";

const MAX_BYTES = 5 * 1024 * 1024;
const issueSchema = z.object({ row: z.number().nullable(), column: z.string().nullable(), message: z.string() });
const importSchema = z.object({ dataset: datasetSchema, warnings: z.array(issueSchema) });
const errorBodySchema = z.object({ errors: z.array(issueSchema).optional(), warnings: z.array(issueSchema).optional() });
type Issue = z.infer<typeof issueSchema>;

function IssueList({ title, items, tone }: { title: string; items: Issue[]; tone: "error" | "warning" }) {
  if (!items.length) return null;
  return (
    <div className={`rounded-md p-3 text-xs ${tone === "error" ? "bg-rose-50 text-rose-900" : "bg-amber-50 text-amber-900"}`}>
      <p className="font-semibold">{title} ({items.length})</p>
      <ul className="mt-1 max-h-48 list-disc space-y-0.5 overflow-y-auto pl-5">
        {items.slice(0, 50).map((i, k) => (
          <li key={k}>{i.row !== null && `Row ${i.row}: `}{i.column && `${i.column} — `}{i.message}</li>
        ))}
        {items.length > 50 && <li>…and {items.length - 50} more</li>}
      </ul>
    </div>
  );
}

export function UploadForm() {
  const router = useRouter();
  const [synthetic, setSynthetic] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [errors, setErrors] = useState<Issue[]>([]);
  const [warnings, setWarnings] = useState<Issue[]>([]);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    const file = data.get("file");
    setMessage(null);
    setErrors([]);
    setWarnings([]);
    if (!(file instanceof File) || file.size === 0) return setMessage({ ok: false, text: "Choose a CSV file." });
    if (file.size > MAX_BYTES) return setMessage({ ok: false, text: "File is larger than 5 MB." });
    data.set("is_synthetic", synthetic ? "true" : "false");
    setBusy(true);
    try {
      const out = await clientFetch("/datasets", importSchema, { method: "POST", body: data });
      setWarnings(out.warnings);
      setMessage({ ok: true, text: `Imported ${out.dataset.name} v${out.dataset.version} (${out.dataset.row_count} bars).` });
      form.reset();
      setSynthetic(false);
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        const body = errorBodySchema.safeParse(err.body);
        if (body.success) {
          setErrors(body.data.errors ?? []);
          setWarnings(body.data.warnings ?? []);
        }
        setMessage({ ok: false, text: err.message });
      } else {
        setMessage({ ok: false, text: "Upload failed." });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <p className="text-xs text-slate-600">
        Columns: Date, Open, High, Low, Close, Volume (one row per trading day, ISO dates). Max 5 MB. The same rules run
        in <code>scripts/validate-dataset.mjs</code>.
      </p>
      <div>
        <label htmlFor="file" className="label">CSV file</label>
        <input id="file" name="file" type="file" accept=".csv,text/csv" required className="mt-1 block w-full text-sm" />
      </div>
      <div>
        <label htmlFor="ds-name" className="label">Name</label>
        <input id="ds-name" name="name" required maxLength={80} pattern="[A-Za-z0-9 ._\-]+" className="input mt-1" placeholder="SPY-yfinance" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="ds-symbol" className="label">Symbol</label>
          <input id="ds-symbol" name="symbol" required maxLength={20} className="input mt-1" placeholder="SPY" />
        </div>
        <div>
          <label htmlFor="ds-adj" className="label">Price adjustment</label>
          <select id="ds-adj" name="adjustment" className="input mt-1" defaultValue={synthetic ? "synthetic" : "adjusted"} key={String(synthetic)}>
            {synthetic ? (
              <option value="synthetic">synthetic</option>
            ) : (
              <>
                <option value="adjusted">adjusted (splits + dividends)</option>
                <option value="split_adjusted">split-adjusted only</option>
                <option value="unadjusted">unadjusted</option>
              </>
            )}
          </select>
        </div>
      </div>
      <div>
        <label htmlFor="ds-source" className="label">Source / provenance</label>
        <input id="ds-source" name="source" required minLength={3} maxLength={300} className="input mt-1" placeholder="Where the data came from and when" />
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={synthetic} onChange={(e) => setSynthetic(e.target.checked)} />
        This is generated (synthetic) data — name must contain DEMO
      </label>
      {message && (
        <p role={message.ok ? "status" : "alert"} className={`text-sm ${message.ok ? "text-emerald-700" : "text-rose-700"}`}>{message.text}</p>
      )}
      <IssueList title="Errors" items={errors} tone="error" />
      <IssueList title="Warnings" items={warnings} tone="warning" />
      <button className="btn-primary" disabled={busy}>{busy ? "Validating…" : "Validate and import"}</button>
    </form>
  );
}
