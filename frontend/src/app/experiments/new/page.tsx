import Link from "next/link";
import { EmptyState, ErrorState, PageHeader } from "@/components/ui";
import { apiTry } from "@/lib/api-server";
import { datasetSchema, pageOf, strategySummarySchema } from "@/lib/schemas";
import { requireSession } from "@/lib/session";
import { ExperimentForm, type StrategyOption } from "./experiment-form";

export const metadata = { title: "New experiment · QuantLab" };

export default async function NewExperimentPage({ searchParams }: PageProps<"/experiments/new">) {
  await requireSession();
  const sp = await searchParams;
  const raw = typeof sp.strategy_version === "string" ? sp.strategy_version : "";
  const requested = /^\d+$/.test(raw) ? Number(raw) : null;
  const [datasets, saved] = await Promise.all([
    apiTry("/api/datasets?limit=100", pageOf(datasetSchema)),
    apiTry("/api/strategies?limit=100", pageOf(strategySummarySchema)),
  ]);
  const strategies: StrategyOption[] = (saved.data?.items ?? []).map((s) => ({
    versionId: s.latest_version_id,
    label: `${s.name} (v${s.latest_version})`,
  }));
  // Older versions are not in the list (it shows the latest per strategy); keep a requested one selectable.
  if (requested !== null && !strategies.some((s) => s.versionId === requested)) {
    strategies.unshift({ versionId: requested, label: `Strategy version #${requested}` });
  }
  return (
    <>
      <PageHeader title="New experiment" />
      {datasets.error ? (
        <ErrorState title="Could not load datasets" message={datasets.error.message} />
      ) : datasets.data.items.length === 0 ? (
        <EmptyState title="No datasets imported">
          Import the DEMO dataset first (see the README), or{" "}
          <Link href="/datasets" className="text-sky-800 underline">upload a CSV</Link>.
        </EmptyState>
      ) : (
        <ExperimentForm datasets={datasets.data.items} strategies={strategies} initialStrategy={requested} />
      )}
    </>
  );
}
