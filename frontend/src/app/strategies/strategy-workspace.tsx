"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { postJson } from "@/lib/api-client";
import { ApiError } from "@/lib/api-errors";
import {
  type Requirement,
  type StrategyDetail,
  type StrategySummary,
  type StrategyVersion,
  strategyChatSchema,
} from "@/lib/schemas";

type ChatLine = { key: string; role: "user" | "assistant"; content: string; outcome?: string | null; versionId?: number | null };

const EXAMPLES = [
  "Buy when RSI(14) drops below 30 and sell when it rises above 70.",
  "Go long when the 20-day EMA crosses above the 50-day SMA, short when it crosses below. 5% stop-loss.",
  "Buy breakouts above the 55-day high, exit on a close below the 20-day low.",
  "Short when price closes above the upper Bollinger band, cover at the middle band.",
];

const STATUS_STYLE: Record<Requirement["status"], { label: string; cls: string; icon: string }> = {
  exact: { label: "Exact", cls: "bg-emerald-50 text-emerald-800 ring-emerald-300", icon: "✓" },
  approximated: { label: "Approximated", cls: "bg-amber-50 text-amber-900 ring-amber-300", icon: "≈" },
  unsupported: { label: "Not supported", cls: "bg-rose-50 text-rose-800 ring-rose-300", icon: "✕" },
};

function toLines(d: StrategyDetail | null): ChatLine[] {
  return (d?.messages ?? []).map((m) => ({
    key: `m${m.id}`,
    role: m.role,
    content: m.content,
    outcome: m.outcome,
    versionId: m.version_id,
  }));
}

function fidelityClass(f: number) {
  if (f >= 85) return "bg-emerald-600";
  if (f >= 60) return "bg-sky-600";
  if (f >= 35) return "bg-amber-500";
  return "bg-rose-500";
}

export function StrategyWorkspace({
  initial,
  available,
  model,
  saved,
}: {
  initial: StrategyDetail | null;
  available: boolean;
  model: string;
  saved: StrategySummary[];
}) {
  const router = useRouter();
  const [detail, setDetail] = useState<StrategyDetail | null>(initial);
  const [lines, setLines] = useState<ChatLine[]>(toLines(initial));
  const [selectedId, setSelectedId] = useState<number | null>(initial?.versions.at(-1)?.id ?? null);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const localKey = useRef(0);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [lines, pending]);

  const selected = detail?.versions.find((v) => v.id === selectedId) ?? detail?.versions.at(-1) ?? null;

  async function send(text: string) {
    const message = text.trim();
    if (!message || pending) return;
    setError(null);
    setPending(true);
    const userLine: ChatLine = { key: `u${++localKey.current}`, role: "user", content: message };
    setLines((prev) => [...prev, userLine]);
    setDraft("");
    try {
      const path = detail ? `/strategies/${detail.id}/messages` : "/strategies";
      const res = await postJson(path, strategyChatSchema, { message });
      if (res.strategy) {
        const isNew = !detail;
        setDetail(res.strategy);
        setLines(toLines(res.strategy));
        setSelectedId(res.strategy.versions.at(-1)?.id ?? null);
        if (isNew) router.replace(`/strategies/${res.strategy.id}`, { scroll: false });
        router.refresh();
      } else {
        setLines((prev) => [...prev, { key: `a${++localKey.current}`, role: "assistant", content: res.reply, outcome: res.outcome }]);
      }
    } catch (err) {
      setLines((prev) => prev.filter((l) => l !== userLine));
      setDraft(message);
      setError(err instanceof ApiError ? err.message : "The strategy builder did not respond.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <section aria-labelledby="chat-h" className="card flex min-h-[28rem] flex-col">
        <div className="flex items-baseline justify-between gap-2">
          <h2 id="chat-h" className="text-lg font-semibold">{detail ? detail.name : "Describe a strategy"}</h2>
          {detail && (
            <Link href="/strategies" className="text-sm text-sky-800 underline">New strategy</Link>
          )}
        </div>
        <p className="mt-1 text-xs text-slate-500">
          Describe your idea in plain English. The assistant ({model}) turns it into rules the backtester can run, then you can
          refine it by replying. It only produces rules from a fixed set of indicators — never code.
        </p>

        <div className="mt-4 flex-1 space-y-3 overflow-y-auto pr-1" aria-live="polite" style={{ maxHeight: "32rem" }}>
          {lines.length === 0 && (
            <div className="space-y-2">
              <p className="text-sm text-slate-600">Try one of these, or write your own:</p>
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  type="button"
                  disabled={!available || pending}
                  onClick={() => send(ex)}
                  className="block w-full rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-left text-sm text-slate-700 hover:border-sky-300 hover:bg-sky-50 disabled:opacity-60"
                >
                  {ex}
                </button>
              ))}
            </div>
          )}
          {lines.map((l) => (
            <ChatBubble
              key={l.key}
              line={l}
              version={detail?.versions.find((v) => v.id === l.versionId)}
              onSelect={setSelectedId}
              active={l.versionId != null && l.versionId === selected?.id}
            />
          ))}
          {pending && (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <span aria-hidden className="h-2 w-2 animate-pulse rounded-full bg-sky-600" />
              Building your strategy… this can take up to 30 seconds.
            </div>
          )}
          <div ref={endRef} />
        </div>

        {error && (
          <p role="alert" className="mt-3 rounded-md bg-rose-50 p-3 text-sm text-rose-800">{error}</p>
        )}
        {!available ? (
          <p role="status" className="mt-4 rounded-md bg-amber-50 p-3 text-sm text-amber-900">
            The strategy builder is turned off because no OpenAI API key is configured on the server
            (set <code>OPENAI_API_KEY</code>). Saved strategies can still be backtested.
          </p>
        ) : (
          <form
            className="mt-4 flex flex-col gap-2 sm:flex-row"
            onSubmit={(e) => {
              e.preventDefault();
              send(draft);
            }}
          >
            <label htmlFor="strategy-message" className="sr-only">Message</label>
            <textarea
              id="strategy-message"
              className="input min-h-[4.5rem] flex-1 resize-y"
              placeholder={detail ? "Refine it, e.g. “add a 5% stop-loss” or “only short when below the 200-day SMA”" : "e.g. Buy when the 10-day SMA crosses above the 50-day SMA…"}
              value={draft}
              maxLength={2000}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(draft);
                }
              }}
            />
            <button type="submit" className="btn-primary sm:self-end" disabled={pending || !draft.trim()}>
              {pending ? "Building…" : detail ? "Refine" : "Build"}
            </button>
          </form>
        )}
      </section>

      <div className="space-y-6">
        {selected && detail ? (
          <BuildPanel detail={detail} version={selected} onSelect={setSelectedId} />
        ) : (
          <section className="card text-sm text-slate-600">
            <h2 className="text-lg font-semibold text-slate-900">How it works</h2>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              <li>Daily bars only: open, high, low, close, volume of the chosen dataset.</li>
              <li>Indicators: SMA, EMA, RSI, MACD, Bollinger bands, N-day highs/lows, % return, volatility.</li>
              <li>Long, short, or long/short; stop-loss, take-profit, and maximum holding period.</li>
              <li>Decisions at each close, filled at the next open — no look-ahead.</li>
              <li>Anything the rules can&apos;t express is approximated or marked unsupported, and the match percentage reflects that.</li>
            </ul>
          </section>
        )}
        <SavedList saved={saved} currentId={detail?.id ?? null} />
      </div>
    </div>
  );
}

function ChatBubble({
  line,
  version,
  onSelect,
  active,
}: {
  line: ChatLine;
  version?: StrategyVersion;
  onSelect: (id: number) => void;
  active: boolean;
}) {
  const mine = line.role === "user";
  return (
    <div className={`flex ${mine ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${
          mine
            ? "bg-sky-700 text-white"
            : line.outcome === "invalid"
              ? "border border-rose-200 bg-rose-50 text-rose-900"
              : "border border-slate-200 bg-slate-50 text-slate-800"
        }`}
      >
        {line.content}
        {version && (
          <button
            type="button"
            onClick={() => onSelect(version.id)}
            aria-pressed={active}
            className={`mt-2 flex items-center gap-2 rounded px-2 py-1 text-xs font-medium ring-1 ring-inset ${
              active ? "bg-sky-100 text-sky-900 ring-sky-300" : "bg-white text-slate-700 ring-slate-300 hover:bg-sky-50"
            }`}
          >
            Version {version.version} · {version.fidelity.toFixed(0)}% match
          </button>
        )}
      </div>
    </div>
  );
}

function BuildPanel({
  detail,
  version,
  onSelect,
}: {
  detail: StrategyDetail;
  version: StrategyVersion;
  onSelect: (id: number) => void;
}) {
  const reqs = version.requirements;
  return (
    <section aria-labelledby="build-h" className="card space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="build-h" className="text-lg font-semibold">Version {version.version}</h2>
        {detail.versions.length > 1 && (
          <label className="flex items-center gap-2 text-sm text-slate-600">
            Version
            <select className="input w-auto py-1" value={version.id} onChange={(e) => onSelect(Number(e.target.value))}>
              {detail.versions.map((v) => (
                <option key={v.id} value={v.id}>
                  v{v.version} · {v.fidelity.toFixed(0)}%
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div>
        <div className="flex items-baseline justify-between">
          <span className="text-sm font-medium text-slate-700">Estimated match to your description</span>
          <span className="font-mono text-2xl font-semibold tabular-nums">{version.fidelity.toFixed(1)}%</span>
        </div>
        <div className="mt-2 h-2.5 w-full overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-valuenow={version.fidelity} aria-valuemin={0} aria-valuemax={100} aria-label="Match percentage">
          <div className={`h-full ${fidelityClass(version.fidelity)}`} style={{ width: `${version.fidelity}%` }} />
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Weighted average over the checklist below: exact = full credit, approximated = half, not supported = none, weighted by
          importance (1–3). The arithmetic is done by the app; whether each item is exact is the model&apos;s own judgement, so
          treat this as an estimate.
        </p>
      </div>

      <div>
        <h3 className="text-sm font-semibold">Your requirements</h3>
        <ul className="mt-2 space-y-2">
          {reqs.map((r, i) => {
            const s = STATUS_STYLE[r.status];
            return (
              <li key={i} className="flex gap-3 text-sm">
                <span className={`mt-0.5 inline-flex h-fit shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${s.cls}`}>
                  <span aria-hidden>{s.icon}</span>
                  {s.label}
                </span>
                <div>
                  <p className="text-slate-800">
                    {r.text} <span className="text-xs text-slate-400">(weight {r.weight})</span>
                  </p>
                  {r.note && <p className="text-xs text-slate-500">{r.note}</p>}
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      <div>
        <h3 className="text-sm font-semibold">Rules the backtester will run</h3>
        <ul className="mt-2 space-y-1 rounded-md bg-slate-50 p-3 font-mono text-xs text-slate-800">
          {version.rules_text.map((l) => <li key={l}>{l}</li>)}
        </ul>
        <p className="mt-1 text-xs text-slate-500">Needs {version.warmup_bars} trading days of history before the start date.</p>
      </div>

      {version.assumptions.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold">Assumptions filled in</h3>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-700">
            {version.assumptions.map((a) => <li key={a}>{a}</li>)}
          </ul>
        </div>
      )}

      <details className="text-xs">
        <summary className="cursor-pointer text-slate-600">Rule specification (JSON)</summary>
        <pre className="mt-2 max-h-72 overflow-auto rounded bg-slate-900 p-3 text-slate-100">{JSON.stringify(version.spec, null, 2)}</pre>
      </details>

      <div className="flex flex-wrap gap-3">
        <Link href={`/experiments/new?strategy_version=${version.id}`} className="btn-primary">
          Backtest version {version.version}
        </Link>
      </div>
    </section>
  );
}

function SavedList({ saved, currentId }: { saved: StrategySummary[]; currentId: number | null }) {
  if (!saved.length) return null;
  return (
    <section aria-labelledby="saved-h" className="card">
      <h2 id="saved-h" className="text-sm font-semibold">Your strategies</h2>
      <ul className="mt-2 divide-y divide-slate-100 text-sm">
        {saved.map((s) => (
          <li key={s.id} className="flex items-center justify-between gap-3 py-2">
            <Link
              href={`/strategies/${s.id}`}
              aria-current={s.id === currentId ? "page" : undefined}
              className={`truncate ${s.id === currentId ? "font-semibold text-slate-900" : "text-sky-800 underline"}`}
            >
              {s.name}
            </Link>
            <span className="shrink-0 font-mono text-xs text-slate-500">
              v{s.latest_version} · {s.direction.replace("_", " ")} · {s.fidelity.toFixed(0)}%
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
