import type { RunStatus } from "@/lib/schemas";

const STATUS_STYLE: Record<string, string> = {
  queued: "bg-slate-100 text-slate-700 ring-slate-300",
  running: "bg-sky-50 text-sky-800 ring-sky-300",
  completed: "bg-emerald-50 text-emerald-800 ring-emerald-300",
  failed: "bg-rose-50 text-rose-800 ring-rose-300",
  pending: "bg-slate-50 text-slate-500 ring-slate-200",
  started: "bg-sky-50 text-sky-800 ring-sky-300",
  retrying: "bg-amber-50 text-amber-800 ring-amber-300",
};

export function StatusBadge({ status }: { status: RunStatus | string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${
        STATUS_STYLE[status] ?? STATUS_STYLE.pending
      }`}
    >
      {(status === "running" || status === "started") && (
        <span aria-hidden className="h-1.5 w-1.5 animate-pulse rounded-full bg-sky-600" />
      )}
      {status}
    </span>
  );
}

export function SyntheticBadge() {
  return (
    <span
      title="Generated random data, not historical market prices"
      className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-900"
    >
      SYNTHETIC
    </span>
  );
}

export function ErrorState({ title, message }: { title: string; message: string }) {
  return (
    <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm">
      <p className="font-medium text-rose-900">{title}</p>
      <p className="mt-1 text-rose-800">{message}</p>
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center">
      <p className="font-medium text-slate-800">{title}</p>
      {children && <div className="mt-2 text-sm text-slate-600">{children}</div>}
    </div>
  );
}

export function Metric({
  label,
  value,
  hint,
  className = "",
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  className?: string;
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <dt className="text-xs font-medium tracking-wide text-slate-500 uppercase">{label}</dt>
      <dd className={`mt-1 font-mono text-lg tabular-nums ${className}`}>{value}</dd>
      {hint && <p className="mt-0.5 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

export function PageHeader({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      {children}
    </div>
  );
}
