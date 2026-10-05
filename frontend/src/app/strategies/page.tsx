import { PageHeader } from "@/components/ui";
import { apiTry } from "@/lib/api-server";
import { pageOf, strategyStatusSchema, strategySummarySchema } from "@/lib/schemas";
import { requireSession } from "@/lib/session";
import { StrategyWorkspace } from "./strategy-workspace";

export const metadata = { title: "Strategy builder · QuantLab" };

export default async function StrategiesPage() {
  await requireSession();
  const [status, saved] = await Promise.all([
    apiTry("/api/strategies/status", strategyStatusSchema),
    apiTry("/api/strategies?limit=50", pageOf(strategySummarySchema)),
  ]);
  return (
    <>
      <PageHeader title="Strategy builder" />
      <StrategyWorkspace
        initial={null}
        available={status.data?.available ?? false}
        model={status.data?.model ?? "LLM"}
        saved={saved.data?.items ?? []}
      />
    </>
  );
}
