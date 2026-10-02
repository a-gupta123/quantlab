// Pure OHLC validation + canonical formatting, shared by the CLI and its tests.
// Mirrors backend/src/quantlab/engine/data.py; the backend re-validates on import.
import { createHash } from "node:crypto";
import { parse } from "csv-parse/sync";

export const REQUIRED = ["date", "open", "high", "low", "close"];
export const CANONICAL_HEADER = "date,open,high,low,close,volume";
export const ADJUSTMENTS = ["adjusted", "split_adjusted", "unadjusted", "synthetic"];
export const MAX_ROWS = 20000;
export const MIN_PRICE = 0.0001;
export const MAX_PRICE = 1e9;
export const MAX_VOLUME = 1e15;
const MAX_ISSUES = 50;
const NUMBER_RE = /^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$/;
const DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

const normaliseHeader = (h) => h.trim().toLowerCase().replace(/\s+/g, "_");

function parseDate(text) {
  const m = DATE_RE.exec(text);
  if (!m) return null;
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const t = Date.UTC(y, mo - 1, d);
  const back = new Date(t);
  // Reject impossible dates such as 2024-02-30 that Date would silently roll over.
  if (back.getUTCFullYear() !== y || back.getUTCMonth() !== mo - 1 || back.getUTCDate() !== d) {
    return null;
  }
  return t;
}

function parseNumber(text) {
  return NUMBER_RE.test(text) ? Number(text) : NaN;
}

// Shortest round-trip text; matches Python's canonical_number in datasets.py
// for the accepted ranges (integers print without ".0").
export function canonicalNumber(x) {
  if (x === null || Number.isNaN(x)) return "";
  return String(x);
}

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
    return { errors, warnings, rows: [] };
  }
  if (records.length === 0) {
    err(null, null, "The file is empty.");
    return { errors, warnings, rows: [] };
  }

  const header = records[0].map(normaliseHeader);
  const dataRows = records.slice(1);
  if (header.includes("adj_close")) {
    err(null, "adj_close",
      "Found an 'Adj Close' column. Provide one consistently adjusted OHLC set (all of " +
      "open/high/low/close adjusted the same way) and drop 'Adj Close'.");
  }
  const missing = REQUIRED.filter((c) => !header.includes(c));
  if (missing.length) err(null, null, `Missing required column(s): ${missing.join(", ")}`);
  if (new Set(header).size !== header.length) {
    err(null, null, "Duplicate column names after normalising headers.");
  }
  if (errors.length) return { errors, warnings, rows: [] };
  if (dataRows.length === 0) {
    err(null, null, "The file has a header but no data rows.");
    return { errors, warnings, rows: [] };
  }
  if (dataRows.length > MAX_ROWS) {
    err(null, null, `Too many rows (${dataRows.length}); the limit is ${MAX_ROWS}.`);
    return { errors, warnings, rows: [] };
  }

  const idx = Object.fromEntries(header.map((h, i) => [h, i]));
  const hasVolume = "volume" in idx;
  const rows = [];
  dataRows.forEach((rec, i) => {
    const rowNo = i + 1;
    if (rec.length !== header.length) {
      err(rowNo, null, `Expected ${header.length} fields, found ${rec.length}.`);
      return;
    }
    const dateText = rec[idx.date];
    const t = parseDate(dateText);
    if (t === null) err(rowNo, "date", `'${dateText}' is not a valid YYYY-MM-DD date.`);
    const row = { date: dateText, t };
    for (const col of ["open", "high", "low", "close"]) {
      const v = parseNumber(rec[idx[col]]);
      if (!Number.isFinite(v) || v <= 0) {
        err(rowNo, col, `'${rec[idx[col]]}' must be a finite, positive number.`);
      } else if (v < MIN_PRICE || v > MAX_PRICE) {
        err(rowNo, col, `${v} is outside the supported price range ${MIN_PRICE}..${MAX_PRICE}.`);
      }
      row[col] = v;
    }
    row.volume = null;
    if (hasVolume && rec[idx.volume] !== "") {
      const v = parseNumber(rec[idx.volume]);
      if (!Number.isFinite(v) || v < 0 || v >= MAX_VOLUME) {
        err(rowNo, "volume", `'${rec[idx.volume]}' must be a finite, non-negative number below 1e15.`);
      }
      row.volume = v;
    }
    rows.push({ rowNo, ...row });
  });
  if (errors.length) return { errors, warnings, rows: [] };

  for (const r of rows) {
    const { open: o, high: h, low: l, close: c } = r;
    if (h < l || h < o || h < c || l > o || l > c) {
      err(r.rowNo, null,
        `OHLC inconsistent: open=${o}, high=${h}, low=${l}, close=${c} (need low <= open, close <= high).`);
    }
  }
  const seen = new Set();
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    if (seen.has(r.t)) err(r.rowNo, "date", `Duplicate date ${r.date}.`);
    seen.add(r.t);
    if (i > 0 && r.t < rows[i - 1].t) {
      err(r.rowNo, "date", `Dates must be sorted ascending: ${r.date} comes after ${rows[i - 1].date}.`);
    }
  }
  if (errors.length) return { errors, warnings, rows: [] };

  const weekend = rows.filter((r) => [0, 6].includes(new Date(r.t).getUTCDay())).length;
  if (weekend) warn(null, "date", `${weekend} row(s) fall on a weekend.`);
  let maxGap = 0, gapAt = -1;
  for (let i = 1; i < rows.length; i++) {
    const gap = (rows[i].t - rows[i - 1].t) / 86400000;
    if (gap > maxGap) { maxGap = gap; gapAt = i; }
  }
  if (maxGap > 7) {
    warn(rows[gapAt].rowNo, "date",
      `Gap of ${maxGap} calendar days between ${rows[gapAt - 1].date} and ${rows[gapAt].date}; missing dates are not filled.`);
  }
  let moves = 0;
  for (let i = 1; i < rows.length && moves < 5; i++) {
    const move = Math.abs(rows[i].close / rows[i - 1].close - 1);
    if (move > 0.4) {
      moves++;
      warn(rows[i].rowNo, "close", `Close moved ${Math.round(move * 100)}% in one day; check for an unadjusted split.`);
    }
  }
  return { errors, warnings, rows };
}

export function toCanonicalCsv(rows) {
  const lines = [CANONICAL_HEADER];
  for (const r of rows) {
    lines.push([r.date, r.open, r.high, r.low, r.close, r.volume].map((v, i) =>
      i === 0 ? v : canonicalNumber(v)).join(","));
  }
  return lines.join("\n") + "\n";
}

export const sha256 = (data) => createHash("sha256").update(data).digest("hex");
