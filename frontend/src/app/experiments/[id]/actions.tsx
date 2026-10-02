"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { clientFetch, postJson } from "@/lib/api-client";
import { ApiError } from "@/lib/api-errors";
import { experimentDetailSchema, type RunStatus } from "@/lib/schemas";

export function ExperimentActions({ id, status, workflowOwned }: { id: number; status: RunStatus; workflowOwned: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Request failed.");
      setBusy(false);
    }
  }

  const rerun = () =>
    run(async () => {
      const created = await postJson(`/experiments/${id}/rerun`, experimentDetailSchema, {});
      router.push(`/experiments/${created.id}`);
      router.refresh();
    });

  const remove = () => {
    if (!window.confirm("Delete this experiment and its results? This cannot be undone.")) return;
    return run(async () => {
      await clientFetch(`/experiments/${id}`, null, { method: "DELETE" });
      router.push("/");
      router.refresh();
    });
  };

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex gap-2">
        <button className="btn-secondary" onClick={rerun} disabled={busy || status === "queued" || status === "running"}>
          Re-run
        </button>
        {!workflowOwned && (
          <button className="btn-danger" onClick={remove} disabled={busy || status === "running"}>
            Delete
          </button>
        )}
      </div>
      {error && <p role="alert" className="text-sm text-rose-700">{error}</p>}
    </div>
  );
}
