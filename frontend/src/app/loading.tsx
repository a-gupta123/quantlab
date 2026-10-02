export default function Loading() {
  return (
    <div role="status" className="animate-pulse space-y-4" aria-label="Loading">
      <div className="h-8 w-64 rounded bg-slate-200" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {Array.from({ length: 5 }, (_, i) => <div key={i} className="h-20 rounded bg-slate-200" />)}
      </div>
      <div className="h-72 rounded bg-slate-200" />
    </div>
  );
}
