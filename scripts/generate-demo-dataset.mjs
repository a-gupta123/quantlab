#!/usr/bin/env node
// Generate the SYNTHETIC demo dataset data/demo/DEMO-SYNTH.csv.
//
// These are random numbers from a seeded regime-switching random walk. They are
// NOT historical prices of SPY or any other security. The fixed seed makes the
// file byte-for-byte reproducible.
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const SEED = 20240101;
const START = Date.UTC(2015, 0, 2);
const N_DAYS = 2300;

// mulberry32: tiny deterministic PRNG (do not use for anything security related).
function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function normal(rand) {
  const u = Math.max(rand(), 1e-12);
  const v = rand();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

const round = (x, d) => Math.round(x * 10 ** d) / 10 ** d;

export function generate() {
  const rand = mulberry32(SEED);
  // Regimes: calm uptrend, volatile downtrend, sideways.
  const regimes = [
    { drift: 0.0006, vol: 0.008 },
    { drift: -0.0009, vol: 0.02 },
    { drift: 0.0, vol: 0.011 },
  ];
  let regime = 0;
  let close = 100;
  const lines = ["date,open,high,low,close,volume"];
  let t = START;
  let made = 0;
  while (made < N_DAYS) {
    const dow = new Date(t).getUTCDay();
    if (dow !== 0 && dow !== 6) {
      if (rand() < 0.008) regime = Math.floor(rand() * regimes.length);
      const { drift, vol } = regimes[regime];
      const open = close * Math.exp(normal(rand) * vol * 0.3);
      const next = open * Math.exp(drift + normal(rand) * vol);
      const hi = Math.max(open, next) * (1 + Math.abs(normal(rand)) * vol * 0.5);
      const lo = Math.min(open, next) * (1 - Math.abs(normal(rand)) * vol * 0.5);
      const volume = Math.round(1_000_000 * (1 + 0.5 * rand()) * (1 + vol * 20));
      const date = new Date(t).toISOString().slice(0, 10);
      lines.push([date, round(open, 4), round(hi, 4), round(lo, 4), round(next, 4), volume].join(","));
      close = next;
      made++;
    }
    t += 86400000;
  }
  return lines.join("\n") + "\n";
}

const here = dirname(fileURLToPath(import.meta.url));
const out = resolve(here, "../data/demo/DEMO-SYNTH.csv");
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, generate());
  console.log(`wrote ${out} (SYNTHETIC demo data, seed ${SEED})`);
}
