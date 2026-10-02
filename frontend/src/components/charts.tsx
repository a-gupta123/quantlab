"use client";

// Charts render arrays computed by the backend engine; nothing is derived here
// except picking which series to draw.
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const COLORS = ["#0369a1", "#b45309", "#7c3aed", "#475569"];

type Series = { key: string; label: string; values: (number | null)[]; dashed?: boolean };

function rows(dates: string[], series: Series[]) {
  return dates.map((d, i) => {
    const row: Record<string, string | number | null> = { date: d };
    for (const s of series) row[s.key] = s.values[i] ?? null;
    return row;
  });
}

const money = (v: number) =>
  v >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `$${(v / 1e3).toFixed(0)}k` : `$${v}`;

export function EquityChart({
  dates,
  series,
  title,
}: {
  dates: string[];
  series: Series[];
  title: string;
}) {
  return (
    <figure>
      <figcaption className="mb-2 text-sm font-medium text-slate-700">{title}</figcaption>
      <div role="img" aria-label={`${title}. ${series.map((s) => s.label).join(" versus ")}.`} className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows(dates, series)} margin={{ top: 5, right: 16, bottom: 5, left: 8 }}>
            <CartesianGrid stroke="#e2e8f0" />
            <XAxis dataKey="date" minTickGap={60} tick={{ fontSize: 12 }} />
            <YAxis tickFormatter={money} width={60} tick={{ fontSize: 12 }} domain={["auto", "auto"]} />
            <Tooltip
              formatter={(v) => (typeof v === "number" ? `$${v.toLocaleString("en-US", { maximumFractionDigits: 2 })}` : v)}
            />
            <Legend />
            {series.map((s, i) => (
              <Line
                key={s.key}
                dataKey={s.key}
                name={s.label}
                stroke={COLORS[i % COLORS.length]}
                strokeDasharray={s.dashed ? "5 4" : undefined}
                dot={false}
                strokeWidth={1.75}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

export function DrawdownChart({ dates, series, title }: { dates: string[]; series: Series[]; title: string }) {
  return (
    <figure>
      <figcaption className="mb-2 text-sm font-medium text-slate-700">{title}</figcaption>
      <div role="img" aria-label={`${title}. Percentage below the running peak.`} className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={rows(dates, series)} margin={{ top: 5, right: 16, bottom: 5, left: 8 }}>
            <CartesianGrid stroke="#e2e8f0" />
            <XAxis dataKey="date" minTickGap={60} tick={{ fontSize: 12 }} />
            <YAxis tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`} width={48} tick={{ fontSize: 12 }} />
            <Tooltip formatter={(v) => (typeof v === "number" ? `${(v * 100).toFixed(2)}%` : v)} />
            <Legend />
            {series.map((s, i) => (
              <Area
                key={s.key}
                dataKey={s.key}
                name={s.label}
                stroke={COLORS[i % COLORS.length]}
                fill={COLORS[i % COLORS.length]}
                fillOpacity={0.12}
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
