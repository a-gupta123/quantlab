// Dataset validation rules shared by the CLI and its tests.
// Keep these in sync with backend/src/quantlab/engine/data.py (the backend
// re-validates every import; this tool gives fast, actionable feedback first).
import { createHash } from "node:crypto";
import { parse } from "csv-parse/sync";

export const REQUIRED = ["date", "open", "high", "low", "close"];
export const OPTIONAL = ["volume"];
export const CANONICAL_HEADER = "date,open,high,low,close,volume";
export const ADJUSTMENTS = ["adjusted", "split_adjusted", "unadjusted", "synthetic"];
export const MAX_ROWS = 20000;
const MAX_ISSUES = 50;
const MIN_PRICE = 0.0001;
const MAX_PRICE = 1e9;
const MAX_VOLUME = 1e15;
const SUSPICIOUS_MOVE = 0.4;
// Relative slack for floating-point noise in adjusted data (e.g. high 1e-14 below close).
const OHLC_TOLERANCE = 1e-9;
const NUMBER_RE = /^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$/;
const DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

const normaliseHeader = (h) => h.trim().toLowerCase().replace(/\s+/g, "_");

function parseDate(text) {
  const m = DATE_RE.exec(text);
  if (!m) return null;
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const t = Date.UTC(y, mo - 1, d);
  const back = new Date(t);
  if (back.getUTCFullYear() !== y || back.getUTCMonth() !== mo - 1 || back.getUTCDate() !== d) {
    return null;
  }
  return t;
}

function parseNumber(text) {
  return NUMBER_RE.test(text) ? Number(text) : NaN;
}

/** Shortest round-trip text; matches Python's canonical_number for accepted ranges. */
export function canonicalNumber(x) {
  if (Number.isNaN(x)) return "";
  return String(x);
}

export function sha256(data) {
  return createHash("sha256").update(data).digest("hex");
}

/**
 * Validate CSV text. Returns { errors, warnings, rows } where rows are normalised
 * objects (only when there are no errors). Row numbers are 1-based data rows,
 * matching the backend (header excluded).
 */
export function validateCsv(text) {
  const errors = [];
  const warnings = [];
  const err = (row, column, message) => {
    if (errors.length < MAX_ISSUES) errors.push({ row, column, message });
  };
  const warn = (row, column, message) => {
    if (warnings.length < MAX_ISSUES) warnings.push({ row, column, message });
  };

  let records;
  try {
    records = parse(text, { bom: true, skip_empty_lines: true, trim: true });
  } catch (e) {
    err(null, null, `File is not a readable CSV: ${e.message}`);
    return { errors, warnings, rows: null };
  }
  if (records.length === 0) {
    err(null, null, "File is empty.");
    return { errors, warnings, rows: null };
  }

  const header = records[0].map(normaliseHeader);
  const dataRows = records.slice(1);
  if (header.includes("adj_close")) {
    err(null, "adj_close",
      "Found an 'Adj Close' column. Provide one consistently adjusted OHLC set " +
      "(all of open/high/low/close adjusted the same way) and drop 'Adj Close'.");
  }
  const missing = REQUIRED.filter((c) => !header.includes(c));
  if (missing.length) err(null, null, `Missing required column(s): ${missing.join(", ")}`);
  if (new Set(header).size !== header.length) {
    err(null, null, "Duplicate column names after normalising headers.");
  }
  if (errors.length) return { errors, warnings, rows: null };
  if (dataRows.length === 0) {
    err(null, null, "The file has a header but no data rows.");
    return { errors, warnings, rows: null };
  }
  if (dataRows.length > MAX_ROWS) {
    err(null, null, `Too many rows (${dataRows.length}); the limit is ${MAX_ROWS}.`);
    return { errors, warnings, rows: null };
  }

  const idx = Object.fromEntries(header.map((h, i) => [h, i]));
  const hasVolume = "volume" in idx;
  const rows = [];
  dataRows.forEach((rec, i) => {
    const rowNo = i + 1;
    const get = (c) => (rec[idx[c]] ?? "").trim();
    const t = parseDate(get("date"));
    if (t === null) err(rowNo, "date", `'${get("date")}' is not a YYYY-MM-DD date.`);
    const out = { t, date: get("date") };
    for (const c of ["open", "high", "low", "close"]) {
      const v = parseNumber(get(c));
      if (!Number.isFinite(v) || v <= 0) {
        err(rowNo, c, `'${get(c)}' must be a finite, positive number.`);
      } else if (v < MIN_PRICE || v > MAX_PRICE) {
        err(rowNo, c, `${v} is outside the supported price range ${MIN_PRICE} to ${MAX_PRICE}.`);
      }
      out[c] = v;
    }
    if (hasVolume) {
      const raw = get("volume");
      const v = raw === "" ? NaN : parseNumber(raw);
      if (raw !== "" && (!Number.isFinite(v) || v < 0 || v >= MAX_VOLUME)) {
        err(rowNo, "volume", `'${raw}' must be a finite, non-negative number below 1e15.`);
      }
      out.volume = v;
    } else {
      out.volume = NaN;
    }
    rows.push(out);
  });
  if (errors.length) return { errors, warnings, rows: null };

  rows.forEach((r, i) => {
    const { open: o, high: h, low: l, close: c } = r;
    const top = Math.max(o, c);
    const bottom = Math.min(o, c);
    const slack = OHLC_TOLERANCE * top;
    if (h < l || h < top - slack || l > bottom + slack) {
      err(i + 1, null,
        `OHLC inconsistent: open=${o}, high=${h}, low=${l}, close=${c} ` +
        "(need low <= open, close <= high).");
    } else if (h < top || l > bottom) {
      r.high = Math.max(h, top);
      r.low = Math.min(l, bottom);
      warn(i + 1, null, "Clamped high/low by a floating-point rounding difference " +
        `(high ${h} -> ${r.high}, low ${l} -> ${r.low}).`);
    }
  });
  const seen = new Set();
  rows.forEach((r, i) => {
    if (seen.has(r.t)) err(i + 1, "date", `Duplicate date ${r.date}.`);
    seen.add(r.t);
    if (i > 0 && r.t < rows[i - 1].t) {
      err(i + 1, "date",
        `Dates must be sorted ascending: ${r.date} comes after ${rows[i - 1].date}.`);
    }
  });
  if (errors.length) return { errors, warnings, rows: null };

  const weekend = rows.filter((r) => [0, 6].includes(new Date(r.t).getUTCDay())).length;
  if (weekend) warn(null, "date", `${weekend} row(s) fall on a weekend.`);
  let maxGap = 0;
  let gapAt = -1;
  for (let i = 1; i < rows.length; i++) {
    const gap = (rows[i].t - rows[i - 1].t) / 86400000;
    if (gap > maxGap) [maxGap, gapAt] = [gap, i];
  }
  if (maxGap > 7) {
    warn(gapAt + 1, "date",
      `Gap of ${maxGap} calendar days between ${rows[gapAt - 1].date} and ${rows[gapAt].date}; ` +
      "missing dates are not filled.");
  }
  let flagged = 0;
  for (let i = 1; i < rows.length && flagged < 5; i++) {
    const move = Math.abs(rows[i].close / rows[i - 1].close - 1);
    if (move > SUSPICIOUS_MOVE) {
      flagged++;
      warn(i + 1, "close",
        `Close moved ${Math.round(move * 100)}% in one day; check for an unadjusted split.`);
    }
  }
  return { errors, warnings, rows };
}

export function normalisedCsv(rows) {
  const lines = [CANONICAL_HEADER];
  for (const r of rows) {
    lines.push([r.date, r.open, r.high, r.low, r.close, r.volume].map((v) =>
      typeof v === "string" ? v : canonicalNumber(v)).join(","));
  }
  return lines.join("\n") + "\n";
}
