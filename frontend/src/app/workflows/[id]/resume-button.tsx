"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { postJson } from "@/lib/api-client";
import { ApiError } from "@/lib/api-errors";
import { workflowDetailSchema } from "@/lib/schemas";

export function ResumeButton({ id, resumable }: { id: number; resumable: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!resumable) return null;
  return (
    <div className="flex flex-col items-end gap-1">
      <button
        className="btn-primary"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            await postJson(`/workflows/${id}/resume`, workflowDetailSchema, {});
            router.refresh();
          } catch (e) {
            setError(e instanceof ApiError ? e.message : "Could not resume.");
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Resuming…" : "Resume from checkpoint"}
      </button>
      {error && <p role="alert" className="text-sm text-rose-700">{error}</p>}
    </div>
  );
}
