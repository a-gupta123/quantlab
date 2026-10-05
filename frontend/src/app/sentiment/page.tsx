import { ErrorState, PageHeader } from "@/components/ui";
import { apiTry } from "@/lib/api-server";
import { pageOf, sentimentBatchSchema, systemSchema } from "@/lib/schemas";
import { requireSession } from "@/lib/session";
import { z } from "zod";
import { SentimentPanel } from "./sentiment-panel";

export const metadata = { title: "Headline sentiment · QuantLab" };

export default async function SentimentPage() {
  await requireSession();
  const [samples, batches, system] = await Promise.all([
    apiTry("/api/sentiment/samples", z.array(z.string())),
    apiTry("/api/sentiment/batches?limit=5", pageOf(sentimentBatchSchema)),
    apiTry("/api/system", systemSchema),
  ]);
  const hosted = system.data?.sentiment_backend === "hf_api";
  const online = system.data?.workers.filter((w) => w.online) ?? [];
  const modelStatus = hosted
    ? ["served by Hugging Face Inference"]
    : online.length
      ? online.map((w) => w.sentiment_model_status)
      : ["no worker online"];

  return (
    <>
      <PageHeader title="Headline sentiment" />
      <div className="mb-6 max-w-3xl space-y-2 text-sm text-slate-600">
        <p>
          Classifies financial headlines with FinBERT (ProsusAI/finbert),{" "}
          {hosted ? "called through Hugging Face's hosted inference" : "running locally inside the worker"}. Results are
          stored with the model name and revision.
        </p>
        <p className="rounded-md border border-amber-200 bg-amber-50 p-3 text-amber-900">
          Sentiment here is an annotation for reading news. It is not used by, and does not feed into, any backtest or
          trading signal.
        </p>
        <p className="text-xs">Model status: {modelStatus.join(", ")}</p>
      </div>
      {samples.error ? (
        <ErrorState title="Could not load the sentiment service" message={samples.error.message} />
      ) : (
        <SentimentPanel samples={samples.data} recent={batches.data?.items ?? []} />
      )}
    </>
  );
}
