"use client";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div role="alert" className="card mx-auto mt-10 max-w-xl border-rose-200">
      <h1 className="text-lg font-semibold text-rose-900">Something went wrong</h1>
      <p className="mt-2 text-sm text-slate-700">
        The page could not be rendered. If the API or database was restarting, trying again usually works.
      </p>
      {error.digest && <p className="mt-2 font-mono text-xs text-slate-500">Reference: {error.digest}</p>}
      <button className="btn-primary mt-4" onClick={reset}>Try again</button>
    </div>
  );
}
