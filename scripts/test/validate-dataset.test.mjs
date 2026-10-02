import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { test } from "node:test";
import { generate } from "../generate-demo-dataset.mjs";
import { normalisedCsv, sha256, validateCsv } from "../lib/validate.mjs";

const CLI = resolve(import.meta.dirname, "../validate-dataset.mjs");
const HEADER = "Date,Open,High,Low,Close,Volume";
const csv = (...rows) => [HEADER, ...rows].join("\n") + "\n";
const GOOD = ["2024-01-02,10,11,9,10.5,100", "2024-01-03,10.5,11,10,10.8,120"];

test("valid file normalises headers and numbers", () => {
  const { errors, rows } = validateCsv(csv(...GOOD));
  assert.deepEqual(errors, []);
  assert.equal(normalisedCsv(rows),
    "date,open,high,low,close,volume\n2024-01-02,10,11,9,10.5,100\n2024-01-03,10.5,11,10,10.8,120\n");
});

const cases = [
  ["missing column", "Date,Open,High,Close\n2024-01-02,1,1,1\n", "Missing required column(s): low"],
  ["duplicate date", csv(GOOD[0], GOOD[0]), "Duplicate date 2024-01-02"],
  ["unsorted", csv(GOOD[1], GOOD[0]), "sorted ascending"],
  ["negative price", csv("2024-01-02,-1,11,9,10,1"), "finite, positive"],
  ["blank price", csv("2024-01-02,10,11,9,,1"), "finite, positive"],
  ["NaN text", csv("2024-01-02,10,11,9,NaN,1"), "finite, positive"],
  ["hex number", csv("2024-01-02,0x10,11,9,10,1"), "finite, positive"],
  ["bad OHLC", csv("2024-01-02,10,9,8,10,1"), "OHLC inconsistent"],
  ["bad date", csv("01/02/2024,10,11,9,10,1"), "YYYY-MM-DD"],
  ["impossible date", csv("2024-02-30,10,11,9,10,1"), "YYYY-MM-DD"],
  ["adj close", "Date,Open,High,Low,Close,Adj Close\n2024-01-02,1,1,1,1,1\n", "Adj Close"],
  ["header only", `${HEADER}\n`, "no data rows"],
  ["tiny price", csv("2024-01-02,0.00001,0.00001,0.00001,0.00001,1"), "supported price range"],
];
for (const [name, text, fragment] of cases) {
  test(`rejects ${name}`, () => {
    const { errors, rows } = validateCsv(text);
    assert.equal(rows, null);
    assert.ok(errors.some((e) => e.message.includes(fragment)), JSON.stringify(errors));
  });
}

test("quoted fields are parsed by the CSV parser", () => {
  const { errors } = validateCsv(csv('"2024-01-02","10","11","9","10.5","1,000"'));
  assert.ok(errors.some((e) => e.column === "volume"), "1,000 is not a plain number");
});

test("large one-day move is a warning", () => {
  const { errors, warnings } = validateCsv(csv(GOOD[0], "2024-01-03,5,5.5,5,5.2,1"));
  assert.deepEqual(errors, []);
  assert.ok(warnings.some((w) => w.message.includes("unadjusted split")));
});

test("demo generator is deterministic and valid", () => {
  const a = generate();
  assert.equal(a, generate());
  const { errors, rows } = validateCsv(a);
  assert.deepEqual(errors, []);
  assert.equal(rows.length, 2300);
});

test("CLI writes normalised file and manifest, and fails with actionable errors", () => {
  const dir = mkdtempSync(join(tmpdir(), "ql-"));
  const input = join(dir, "in.csv");
  writeFileSync(input, csv(...GOOD));
  execFileSync("node", [CLI, input, "--name", "UNIT-DEMO", "--symbol", "demo",
    "--adjustment", "synthetic", "--synthetic", "--source", "unit test", "--out", dir]);
  const manifest = JSON.parse(readFileSync(join(dir, "UNIT-DEMO.manifest.json"), "utf8"));
  const body = readFileSync(join(dir, manifest.file));
  assert.equal(manifest.sha256, sha256(body));
  assert.equal(manifest.symbol, "DEMO");
  assert.equal(manifest.row_count, 2);
  assert.equal(manifest.schema_version, 1);

  writeFileSync(input, csv(GOOD[1], GOOD[0]));
  const bad = spawnSync("node", [CLI, input, "--name", "UNIT-DEMO", "--symbol", "D",
    "--adjustment", "synthetic", "--synthetic", "--source", "unit test", "--out", dir]);
  assert.equal(bad.status, 1);
  assert.match(bad.stderr.toString(), /row 2 \[date\]: Dates must be sorted ascending/);

  const mislabel = spawnSync("node", [CLI, input, "--name", "SPY", "--symbol", "SPY",
    "--adjustment", "synthetic", "--synthetic", "--source", "x", "--out", dir]);
  assert.equal(mislabel.status, 2);
  assert.match(mislabel.stderr.toString(), /DEMO/);
});

test("floating-point noise in high/low is clamped with a warning", () => {
  const { errors, warnings, rows } = validateCsv(
    csv("2024-01-02,108.44,108.84165954589842,107.62,108.84165954589844,1"));
  assert.deepEqual(errors, []);
  assert.equal(rows[0].high, 108.84165954589844);
  assert.ok(warnings.some((w) => w.message.includes("Clamped")));
});
