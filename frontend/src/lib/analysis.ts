import type { ConfidenceInterval, Metrics } from "./schemas";
import { num, pct } from "./format";

/** Plain-language observations built only from numbers the engine computed. */
export function describeRun(s: Metrics, b: Metrics, ci: ConfidenceInterval): string[] {
  const out: string[] = [];
  const diff = s.total_return - b.total_return;
  out.push(
    `The strategy returned ${pct(s.total_return)} versus ${pct(b.total_return)} for buy-and-hold over the same dates, ` +
      `a difference of ${pct(diff)} after ${pct(s.total_fees / Math.max(1, s.final_equity), 3)} of final equity paid in fees.`,
  );
  out.push(
    `Its worst peak-to-trough decline was ${pct(s.max_drawdown)} (buy-and-hold: ${pct(b.max_drawdown)}), ` +
      `and it was invested on ${pct(s.exposure, 0)} of days with ${s.n_trades} trades.`,
  );
  if (s.sharpe_ratio === null) {
    out.push("Sharpe ratio is undefined for the strategy because its daily returns have no variation.");
  } else {
    out.push(`Sharpe ratio ${num(s.sharpe_ratio)} versus ${num(b.sharpe_ratio)} for buy-and-hold.`);
  }
  if (ci.status === "ok" && ci.low !== null && ci.high !== null) {
    const straddles = ci.low <= 0 && ci.high >= 0;
    out.push(
      `The ${pct(ci.confidence_level, 0)} block-bootstrap interval for the mean daily return is ` +
        `${pct(ci.low, 3)} to ${pct(ci.high, 3)}` +
        (straddles
          ? ", which includes zero: this sample does not distinguish the average daily return from zero."
          : ", which excludes zero for this sample (this is about the past period, not a forecast)."),
    );
  } else {
    out.push(`No confidence interval: ${ci.detail}`);
  }
  if (s.n_days < 252) out.push("The evaluation period is shorter than one trading year, so annualized figures are unstable.");
  return out;
}
