export const pct = (x: number | null | undefined, digits = 2) =>
  x === null || x === undefined ? "—" : `${(x * 100).toFixed(digits)}%`;

export const num = (x: number | null | undefined, digits = 2) =>
  x === null || x === undefined ? "—" : x.toFixed(digits);

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
export const usd = (x: number | null | undefined) =>
  x === null || x === undefined ? "—" : money.format(x);

export const dateTime = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }) : "—";

export const signClass = (x: number | null | undefined) =>
  x === null || x === undefined ? "" : x >= 0 ? "text-emerald-700" : "text-rose-700";
