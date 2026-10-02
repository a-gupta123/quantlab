import Link from "next/link";

export default function NotFound() {
  return (
    <div className="card mx-auto mt-10 max-w-xl">
      <h1 className="text-lg font-semibold">Not found</h1>
      <p className="mt-2 text-sm text-slate-700">That experiment, workflow, or page does not exist (it may have been deleted).</p>
      <Link href="/" className="btn-secondary mt-4">Back to dashboard</Link>
    </div>
  );
}
