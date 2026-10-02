import Link from "next/link";
import { EmptyState, ErrorState, PageHeader } from "@/components/ui";
import { apiTry } from "@/lib/api-server";
import { datasetSchema, pageOf } from "@/lib/schemas";
import { requireSession } from "@/lib/session";
import { ExperimentForm } from "./experiment-form";

export const metadata = { title: "New experiment · QuantLab" };

export default async function NewExperimentPage() {
  await requireSession();
  const datasets = await apiTry("/api/datasets?limit=100", pageOf(datasetSchema));
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
        <ExperimentForm datasets={datasets.data.items} />
      )}
    </>
  );
}
