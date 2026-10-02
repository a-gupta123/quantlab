import { EmptyState, ErrorState, PageHeader, SyntheticBadge } from "@/components/ui";
import { apiTry } from "@/lib/api-server";
import { dateTime } from "@/lib/format";
import { datasetSchema, pageOf } from "@/lib/schemas";
import { requireSession } from "@/lib/session";
import { UploadForm } from "./upload-form";

export const metadata = { title: "Datasets · QuantLab" };

export default async function DatasetsPage() {
  await requireSession();
  const res = await apiTry("/api/datasets?limit=100", pageOf(datasetSchema));
  return (
    <>
      <PageHeader title="Datasets" />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <section aria-labelledby="ds-list">
          <h2 id="ds-list" className="sr-only">Imported datasets</h2>
          {res.error ? (
            <ErrorState title="Could not load datasets" message={res.error.message} />
          ) : res.data.items.length === 0 ? (
            <EmptyState title="No datasets yet">
              Import the synthetic DEMO dataset with the commands in the README, or upload a CSV here.
            </EmptyState>
          ) : (
            <div className="card overflow-x-auto p-0">
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">Name</th><th scope="col">Symbol</th><th scope="col">Range</th>
                    <th scope="col" className="num">Bars</th><th scope="col">Adjustment</th><th scope="col">SHA-256</th><th scope="col">Imported</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {res.data.items.map((d) => (
                    <tr key={d.id}>
                      <td>
                        <span className="font-medium">{d.name}</span> <span className="text-xs text-slate-500">v{d.version}</span>{" "}
                        {d.is_synthetic && <SyntheticBadge />}
                        <div className="max-w-xs truncate text-xs text-slate-500" title={d.source}>{d.source}</div>
                      </td>
                      <td>{d.symbol}</td>
                      <td className="text-xs">{d.start_date} → {d.end_date}</td>
                      <td className="num">{d.row_count.toLocaleString()}</td>
                      <td className="text-xs">{d.adjustment}</td>
                      <td className="font-mono text-xs" title={d.content_sha256}>{d.content_sha256.slice(0, 12)}…</td>
                      <td className="text-xs">{dateTime(d.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
        <section aria-labelledby="upload-h" className="card">
          <h2 id="upload-h" className="mb-3 text-lg font-semibold">Import a CSV</h2>
          <UploadForm />
        </section>
      </div>
    </>
  );
}
