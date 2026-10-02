#!/usr/bin/env node
// Validate an OHLC CSV and write a normalised copy plus a manifest that the
// backend importer consumes:
//
//   node scripts/validate-dataset.mjs data/demo/DEMO-SYNTH.csv \
//     --name DEMO-SYNTH --symbol DEMO --adjustment synthetic --synthetic \
//     --source "Synthetic ..." --out data/normalized
//
//   cd backend && uv run quantlab import-manifest ../data/normalized/DEMO-SYNTH.manifest.json
//
// Exit codes: 0 valid, 1 validation errors, 2 usage error.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { ADJUSTMENTS, normalisedCsv, sha256, validateCsv } from "./lib/validate.mjs";

const USAGE = `Usage: node validate-dataset.mjs <input.csv> --name NAME --symbol SYMBOL
       --source "where the data came from" --adjustment ${ADJUSTMENTS.join("|")}
       [--synthetic] [--out DIR]`;

function fail(message, code = 2) {
  console.error(message);
  process.exit(code);
}

export function buildManifest({ name, symbol, source, adjustment, synthetic }, inputPath, input,
  rows, warnings, fileName, normalised) {
  return {
    schema_version: 1,
    name,
    symbol: symbol.toUpperCase(),
    source,
    adjustment,
    is_synthetic: synthetic,
    file: fileName,
    sha256: sha256(normalised),
    row_count: rows.length,
    start_date: rows[0].date,
    end_date: rows[rows.length - 1].date,
    columns: ["date", "open", "high", "low", "close", "volume"],
    warnings,
    input_file: basename(inputPath),
    input_sha256: sha256(input),
    validated_by: "scripts/validate-dataset.mjs",
    validated_at: new Date().toISOString(),
  };
}

function main() {
  let parsed;
  try {
    parsed = parseArgs({
      allowPositionals: true,
      options: {
        name: { type: "string" },
        symbol: { type: "string" },
        source: { type: "string" },
        adjustment: { type: "string" },
        synthetic: { type: "boolean", default: false },
        out: { type: "string", default: "data/normalized" },
      },
    });
  } catch (e) {
    fail(`${e.message}\n${USAGE}`);
  }
  const { values, positionals } = parsed;
  if (positionals.length !== 1) fail(USAGE);
  for (const k of ["name", "symbol", "source", "adjustment"]) {
    if (!values[k]) fail(`Missing --${k}.\n${USAGE}`);
  }
  if (!/^[A-Za-z0-9._-]{1,80}$/.test(values.name)) {
    fail("--name may only contain letters, digits, '.', '_' and '-' (max 80).");
  }
  if (!ADJUSTMENTS.includes(values.adjustment)) {
    fail(`--adjustment must be one of: ${ADJUSTMENTS.join(", ")}`);
  }
  if (values.synthetic !== (values.adjustment === "synthetic")) {
    fail("Use --synthetic together with --adjustment synthetic (and only then).");
  }
  if (values.synthetic && !values.name.toUpperCase().includes("DEMO")) {
    fail("Synthetic datasets must have 'DEMO' in their name so they are never mistaken for real data.");
  }

  const inputPath = resolve(positionals[0]);
  let input;
  try {
    input = readFileSync(inputPath);
  } catch (e) {
    fail(`Cannot read ${inputPath}: ${e.message}`);
  }
  const { errors, warnings, rows } = validateCsv(input.toString("utf8"));
  for (const w of warnings) {
    console.warn(`warning${w.row ? ` row ${w.row}` : ""}${w.column ? ` [${w.column}]` : ""}: ${w.message}`);
  }
  if (errors.length) {
    console.error(`${basename(inputPath)}: ${errors.length} error(s)`);
    for (const e of errors) {
      console.error(`  ${e.row ? `row ${e.row}` : "file"}${e.column ? ` [${e.column}]` : ""}: ${e.message}`);
    }
    process.exit(1);
  }

  const outDir = resolve(values.out);
  mkdirSync(outDir, { recursive: true });
  const fileName = `${values.name}.csv`;
  const normalised = normalisedCsv(rows);
  writeFileSync(join(outDir, fileName), normalised);
  const manifest = buildManifest(values, inputPath, input, rows, warnings, fileName, normalised);
  const manifestPath = join(outDir, `${values.name}.manifest.json`);
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + "\n");
  console.log(`ok: ${rows.length} rows ${manifest.start_date}..${manifest.end_date}, ` +
    `sha256 ${manifest.sha256.slice(0, 12)}`);
  console.log(`wrote ${join(outDir, fileName)}`);
  console.log(`wrote ${manifestPath}`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}
