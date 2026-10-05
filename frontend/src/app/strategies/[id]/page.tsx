import { notFound } from "next/navigation";
import { ErrorState, PageHeader } from "@/components/ui";
import { apiTry } from "@/lib/api-server";
import { pageOf, strategyDetailSchema, strategyStatusSchema, strategySummarySchema } from "@/lib/schemas";
import { requireSession } from "@/lib/session";
import { StrategyWorkspace } from "../strategy-workspace";

export const metadata = { title: "Strategy builder · QuantLab" };

export default async function StrategyPage({ params }: PageProps<"/strategies/[id]">) {
  await requireSession();
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const [detail, status, saved] = await Promise.all([
    apiTry(`/api/strategies/${id}`, strategyDetailSchema),
    apiTry("/api/strategies/status", strategyStatusSchema),
    apiTry("/api/strategies?limit=50", pageOf(strategySummarySchema)),
  ]);
  if (detail.error?.status === 404) notFound();
  if (detail.error) return <ErrorState title="Could not load the strategy" message={detail.error.message} />;
  return (
    <>
      <PageHeader title="Strategy builder" />
      <StrategyWorkspace
        key={detail.data.id}
        initial={detail.data}
        available={status.data?.available ?? false}
        model={status.data?.model ?? "LLM"}
        saved={saved.data?.items ?? []}
      />
    </>
  );
}
