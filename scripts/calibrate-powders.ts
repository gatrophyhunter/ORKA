// Calibrate powder models against published, pressure-tested load data and measure accuracy honestly.
//
//   npx tsx scripts/calibrate-powders.ts      (after scripts/build-data.ts)
//   env: ORKA_POWDERS=id1,id2 (subset)  ORKA_PROCS=n (parallel processes)
//
// Each published load needs: cartridge bore/groove (standards), bullet length (maker catalog), COAL/barrel/charge/
// velocity/pressure (the load data) and the capacity of the case brand the publisher tested with. Capacity tiers:
//   A  capacity published for that case brand (maker or measured)        → used as is; only tier A is validated
//   B  capacity published only for other brands of the cartridge         → median used as a prior (σ 3 %)
//   C  no published capacity                                             → inferred ("effective capacity")
// Stages:
//   1. fit each powder on tier-A rows (plus tier-B rows when tier A is thin)
//   2. with those powders fixed, infer an effective capacity per (cartridge, case brand) for tier B/C groups
//   3. refit every powder on all rows; leave-one-cartridge-out validation on tier-A cartridges, training only on
//      rows whose capacity is published (A/B with prior), so no inferred quantity leaks into the held-out test.
// Outputs: src/data/powder-models.json, src/data/validation-report.json, src/data/inferred-capacities.json

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';
import { calibrate, type FitParam, type Observation } from '../src/engine/calibrate';
import { simulate, bulletVolumeBelow } from '../src/engine/model';
import { propellantFromParams, paramsFromPropellant, toSetup, type LoadInputs } from '../src/engine/adapter';
import { priorParams, shotStartClass, shotStartMPa } from '../src/engine/defaults';
import * as U from '../src/engine/units';
import type { Bullet, Cartridge, Database, Powder, PowderModelEntry, PowderModelParams, ValidationLoad } from '../src/data/schema';
import { estimateFromCharts } from './estimate';
import { featuresFromText, fitLengthModel } from './bullet-length';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const db: Database = JSON.parse(fs.readFileSync(path.join(ROOT, 'src/data/db.json'), 'utf8'));
db.validationLoads = JSON.parse(fs.readFileSync(path.join(ROOT, 'research/build/validation-loads.json'), 'utf8'));

const SIGMA_V_MS = U.fpsToMs(25); // published velocities are rounded and lot-dependent
const LENGTH_MODEL = fitLengthModel(db.bullets);
const SIGMA_P_REL = 0.05;
const CAP_PRIOR_SIGMA = 0.03;
const MAX_LOCO = 6;
const RTOL = 1e-6;

const skipped: Record<string, number> = {};
const skip = (why: string) => (skipped[why] = (skipped[why] ?? 0) + 1);
const words = (s: string) => new Set(s.toLowerCase().replace(/[^a-z0-9 ]/g, ' ').split(/\s+/).filter((w) => w.length > 1));
const median = (v: number[]) => {
  const s = v.slice().sort((a, b) => a - b);
  return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2;
};

function findBullet(l: ValidationLoad, diameterIn: number): { bullet: Bullet | null; note: string } {
  const mk = (l.bulletMfr ?? '').toLowerCase().split(/\s+/)[0];
  if (!mk) return { bullet: null, note: 'bullet maker not stated' };
  const cands = db.bullets.filter(
    (b) => b.manufacturer.toLowerCase().includes(mk) && Math.abs(b.diameterIn - diameterIn) <= 0.003 && Math.abs(b.weightGr - l.bulletWeightGr) <= 0.5 && b.lengthIn,
  );
  if (!cands.length) return { bullet: null, note: 'no catalog bullet with length' };
  const want = words(l.bulletModel ?? '');
  const scored = cands.map((b) => ({ b, s: [...words(`${b.line} ${b.name}`)].filter((w) => want.has(w)).length })).sort((a, b) => b.s - a.s);
  const best = scored.filter((x) => x.s === scored[0].s).map((x) => x.b);
  const lens = best.map((b) => b.lengthIn as number);
  if (Math.max(...lens) - Math.min(...lens) > 0.02) return { bullet: null, note: 'ambiguous bullet match' };
  return { bullet: best[0], note: scored[0].s > 0 ? 'matched by maker/weight/model words' : 'matched by maker/weight only' };
}

type Tier = 'A' | 'B' | 'C';

function shotClassOf(construction: string | null, catalogConstruction: string | null, model: string): 'jacketed' | 'monolithic' | 'lead' {
  const c = catalogConstruction ?? construction;
  if (c) return shotStartClass(c);
  if (/\b(tsx|ttsx|lrx|cx|gmx|e-tip|etip|tac-x|xpb|mono|monolithic|solid copper|all copper|lead free)\b/i.test(model)) return 'monolithic';
  if (/\b(lead|cast|lswc|lrn|swc|lwc|wc|lfp|lrnfp|hard cast)\b/i.test(model)) return 'lead';
  return 'jacketed';
}

interface Prepared {
  load: ValidationLoad;
  cartridgeId: string;
  groupKey: string;
  tier: Tier;
  lengthEstimated: boolean;
  shotClass: 'jacketed' | 'monolithic' | 'lead';
  capPrior: number | null;
  capBasis: string;
  inputs: LoadInputs;
  peakPa?: number;
  label: string;
  notes: string[];
}

const normBrand = (s: string | null | undefined) =>
  (s ?? '').toLowerCase().replace(/\(.*?\)/g, ' ').replace(/[^a-z0-9 ]/g, ' ').replace(/\b(brass|cases?|commercial|new|unprimed|match)\b/g, ' ').replace(/\s+/g, ' ').trim();
function capacityFor(l: ValidationLoad, c: Cartridge): { tier: Tier; cap: number | null; basis: string } {
  const brand = normBrand(l.caseBrand);
  const published = c.caseCapacityGrH2O.filter((e) => !/inferred/i.test(e.basis));
  // Exact brand match only: "Winchester" commercial brass must not match "WCC (Winchester military headstamp)".
  const byBrand = published.filter((e) => brand && e.brand && normBrand(e.brand) === brand);
  if (byBrand.length) return { tier: 'A', cap: median(byBrand.map((e) => e.value)), basis: `${byBrand[0].brand} (${byBrand[0].basis}, ${byBrand.length} value(s))` };
  if (published.length) return { tier: 'B', cap: median(published.map((e) => e.value)), basis: `median of ${published.length} published capacities of other brands (test case: ${l.caseBrand ?? 'unstated'})` };
  return { tier: 'C', cap: null, basis: 'no published capacity' };
}

function prepare(l: ValidationLoad): Prepared | null {
  const c = db.cartridges.find((x) => x.id === l.cartridgeId);
  if (!c) return skip('cartridge not in database'), null;
  if (!c.boreDiameterIn || !c.grooveDiameterIn) return skip('cartridge bore/groove unknown'), null;
  const caseLen = l.caseTrimLengthIn ?? c.trimLengthIn ?? c.caseLengthMaxIn;
  if (!caseLen) return skip('case length unknown'), null;
  if (!Number.isFinite(l.coalIn) || !Number.isFinite(l.barrelLengthIn)) return skip('COAL or barrel length missing'), null;
  if (!(l.velocityFps > 0) || !(l.chargeGr > 0) || !(l.bulletWeightGr > 0)) return skip('incomplete load'), null;
  const d = l.bulletDiameterIn ?? c.bulletDiameterIn;
  if (!d) return skip('bullet diameter unknown'), null;
  const cap = capacityFor(l, c);
  let len = l.bulletLengthIn ?? null;
  let lengthEstimated = false;
  let bt = 0;
  let construction: string | null = null;
  const notes: string[] = [`capacity: ${cap.basis}`];
  const fb = findBullet(l, d);
  if (fb.bullet) {
    len = len ?? fb.bullet.lengthIn;
    bt = fb.bullet.boatTailLengthIn ?? 0;
    construction = fb.bullet.construction ?? null;
    notes.push(`bullet ${fb.bullet.manufacturer} ${fb.bullet.name} (${fb.note})`);
  }
  if (!len && LENGTH_MODEL) {
    // Maker publishes no length: estimate it (calibration only; error measured by leave-one-out, see report).
    const text = `${l.bulletModel ?? ''} ${fb.bullet ? `${fb.bullet.line} ${fb.bullet.name} ${fb.bullet.profile ?? ''}` : ''}`;
    const est = LENGTH_MODEL.predict(featuresFromText(d, l.bulletWeightGr, text, fb.bullet?.construction ?? construction, c.type === 'handgun'));
    if (est !== null && est > d && est < 3) {
      len = Math.round(est * 1000) / 1000;
      lengthEstimated = true;
      notes.push(`bullet length ${len} in ESTIMATED (maker publishes none; estimator leave-one-out error ${(LENGTH_MODEL.looRelRms * 100).toFixed(1)} %)`);
    }
  }
  if (!len) return skip(`bullet length unknown (${fb.note})`), null;
  let peakPa: number | undefined;
  if (l.pressure !== null && l.pressureUnit === 'psi') peakPa = U.psiToPa(l.pressure);
  else if (l.pressure !== null && l.pressureUnit === 'bar') peakPa = U.barToPa(l.pressure);
  // CUP readings are never converted: such loads contribute velocity only.
  return {
    load: l,
    cartridgeId: c.id,
    groupKey: `${c.id}|${(l.caseBrand ?? 'unstated').toLowerCase()}`,
    tier: cap.tier,
    lengthEstimated,
    shotClass: shotClassOf(construction, fb.bullet?.construction ?? null, l.bulletModel ?? ''),
    capPrior: cap.cap,
    capBasis: cap.basis,
    inputs: {
      boreDiameterIn: c.boreDiameterIn,
      grooveDiameterIn: c.grooveDiameterIn,
      caseLengthIn: caseLen,
      caseCapacityGrH2O: cap.cap ?? NaN,
      barrelLengthIn: l.barrelLengthIn,
      bulletWeightGr: l.bulletWeightGr,
      bulletDiameterIn: d,
      bulletLengthIn: len,
      boatTailLengthIn: bt,
      bulletBaseDiameterIn: bt > 0 ? d * 0.8 : d,
      coalIn: l.coalIn,
      chargeGr: l.chargeGr,
      powderTempF: 70,
      shotStartPsi: U.mpaToPsi(shotStartMPa(shotClassOf(construction, fb.bullet?.construction ?? null, l.bulletModel ?? ''))),
    },
    peakPa,
    label: `${c.name} · ${l.bulletMfr ?? ''} ${l.bulletWeightGr} gr ${l.bulletModel ?? ''} · ${l.chargeGr} gr (${l.loadType})`,
    notes,
  };
}

// ---------------------------------------------------------------- fitting helpers

interface FittedModel {
  params: PowderModelParams;
}

function startModel(p: Powder) {
  return propellantFromParams(priorParams({ heatOfExplosionJg: p.heatOfExplosionJg ?? null, base: p.base, beta: 5 }), p.bulkDensityGcc ?? null);
}

function fitPowder(p: Powder, rows: Prepared[]) {
  const start = startModel(p);
  const obs: Observation[] = rows.map((r) => ({ setup: toSetup(r.inputs, start, { rtol: RTOL }), velocityMs: U.fpsToMs(r.load.velocityFps), peakPa: r.peakPa, label: r.label }));
  const nP = rows.filter((r) => r.peakPa !== undefined).length;
  const barrels = new Set(rows.map((r) => r.inputs.barrelLengthIn)).size;
  const params: FitParam[] = ['beta'];
  if (rows.length >= 3) params.push('lambda');
  if (rows.length >= 4 && nP >= 2) params.push('force');
  if (rows.length >= 12 && barrels >= 3) params.push('heat');
  // Pressure exponent of the burn law: identifiable when a powder spans several bullet weights with measured pressures.
  if (rows.length >= 10 && nP >= 6 && new Set(rows.map((r) => Math.round(r.load.bulletWeightGr / 10))).size >= 3) params.push('n');
  const fit = calibrate({
    start,
    observations: obs,
    params,
    sigmaVelocityMs: SIGMA_V_MS,
    sigmaPressureRel: SIGMA_P_REL,
    // Weak physical priors (transformed space): energy ±10 % of the class prior, heat-loss scale ±40 %,
    // pressure exponent near 0.8 (±25 %), burn shape near neutral (±0.6). Data dominate where they are informative.
    priors: { force: { center: 0, sigma: 0.1 }, heat: { center: 0, sigma: 0.4 }, n: { center: Math.log(0.8), sigma: 0.25 }, lambda: { center: 0, sigma: 0.6 } },
  });
  return { fit, params };
}

function simulateRow(m: FittedModel, r: Prepared, bulk: number | null | undefined, capOverride?: number) {
  const prop = propellantFromParams(m.params, bulk ?? null);
  const inputs = capOverride !== undefined ? { ...r.inputs, caseCapacityGrH2O: capOverride } : r.inputs;
  return simulate(toSetup(inputs, prop, { rtol: RTOL }, m.params.heatScale ?? 1));
}

/** Deterministic, cartridge-stratified subsample. */
function subsample(rows: Prepared[], perCart = 6, cap = 48): Prepared[] {
  const byCart = new Map<string, Prepared[]>();
  for (const r of rows) byCart.set(r.cartridgeId, [...(byCart.get(r.cartridgeId) ?? []), r]);
  const lists = [...byCart.values()].map((l) => {
    const sorted = l.slice().sort((a, b) => a.load.bulletWeightGr - b.load.bulletWeightGr || a.load.chargeGr - b.load.chargeGr);
    if (sorted.length <= perCart) return sorted;
    const out: Prepared[] = [];
    for (let i = 0; i < perCart; i++) out.push(sorted[Math.round((i * (sorted.length - 1)) / (perCart - 1))]);
    return [...new Set(out)];
  });
  lists.sort((a, b) => b.length - a.length);
  const picked: Prepared[] = [];
  for (let i = 0; picked.length < cap; i++) {
    let any = false;
    for (const l of lists) {
      if (i < l.length && picked.length < cap) {
        picked.push(l[i]);
        any = true;
      }
    }
    if (!any) break;
  }
  return picked;
}

// ---------------------------------------------------------------- worker jobs

type Job =
  | { kind: 'powder'; stage: 1 | 3; powderId: string; rows: Prepared[]; locoRows?: Prepared[]; locoCartridges?: string[] }
  | { kind: 'capacity'; groupKey: string; rows: Prepared[]; models: Record<string, FittedModel> };

interface PowderOut {
  kind: 'powder';
  powderId: string;
  params: PowderModelParams;
  fitted: FitParam[];
  points: number;
  rmsVelocityFps: number | null;
  rmsPressurePct: number | null;
  warnings: string[];
  rows: any[];
  heldOutV: number[];
  heldOutP: number[];
  inSampleV: number[];
  inSampleP: number[];
}
interface CapacityOut {
  kind: 'capacity';
  groupKey: string;
  capGrH2O: number | null;
  n: number;
  powders: number;
  prior: number | null;
  rmsPressurePct: number | null;
}

function rowReport(p: Powder, r: Prepared, res: ReturnType<typeof simulate>, heldOut: boolean) {
  return {
    label: r.label,
    cartridge: r.load.cartridge,
    powder: p.name,
    chargeGr: r.load.chargeGr,
    velObsFps: r.load.velocityFps,
    velPredFps: Number.isFinite(res.muzzleVelocityMs) ? Math.round(U.msToFps(res.muzzleVelocityMs)) : null,
    pObs: r.load.pressure,
    pObsUnit: r.load.pressureUnit,
    pPredPsi: Number.isFinite(res.peakBreechPa) ? Math.round(U.paToPsi(res.peakBreechPa)) : null,
    heldOut,
    cartType: db.cartridges.find((c) => c.id === r.cartridgeId)?.type ?? null,
    shotClass: r.shotClass,
    loadType: r.load.loadType ?? null,
    capacityTier: r.tier,
    lengthEstimated: r.lengthEstimated,
    page: r.load.sources[0]?.page ?? null,
    notes: r.notes.join('; '),
  };
}

function runPowder(job: Extract<Job, { kind: 'powder' }>): PowderOut {
  const p = db.powders.find((x) => x.id === job.powderId)!;
  const fitRows = subsample(job.rows);
  const { fit, params } = fitPowder(p, fitRows);
  const model: FittedModel = { params: paramsFromPropellant(fit.model, fit.heatScale) };
  const out: PowderOut = {
    kind: 'powder',
    powderId: p.id,
    params: model.params,
    fitted: params,
    points: fitRows.length,
    rmsVelocityFps: fit.rmsVelocityMs === null ? null : U.msToFps(fit.rmsVelocityMs),
    rmsPressurePct: fit.rmsPressureRel === null ? null : fit.rmsPressureRel * 100,
    warnings: fit.warnings,
    rows: [],
    heldOutV: [],
    heldOutP: [],
    inSampleV: [],
    inSampleP: [],
  };
  if (job.stage === 3) {
    for (const r of fitRows) {
      const res = simulateRow(model, r, p.bulkDensityGcc);
      out.inSampleV.push(U.msToFps(res.muzzleVelocityMs) - r.load.velocityFps);
      if (r.peakPa) out.inSampleP.push((res.peakBreechPa - r.peakPa) / r.peakPa);
      out.rows.push(rowReport(p, r, res, false));
    }
    // Leave-one-cartridge-out on tier-A cartridges; training uses only rows with published capacity.
    const pool = job.locoRows ?? [];
    for (const cid of job.locoCartridges ?? []) {
      const train = subsample(pool.filter((r) => r.cartridgeId !== cid));
      const test = subsample(pool.filter((r) => r.cartridgeId === cid && r.tier === 'A'), 8, 8);
      if (train.length < 3 || !test.length) continue;
      const f2 = fitPowder(p, train).fit;
      const m2: FittedModel = { params: paramsFromPropellant(f2.model, f2.heatScale) };
      for (const r of test) {
        const res = simulateRow(m2, r, p.bulkDensityGcc);
        if (Number.isFinite(res.muzzleVelocityMs)) out.heldOutV.push(U.msToFps(res.muzzleVelocityMs) - r.load.velocityFps);
        if (r.peakPa && Number.isFinite(res.peakBreechPa)) out.heldOutP.push((res.peakBreechPa - r.peakPa) / r.peakPa);
        out.rows.push(rowReport(p, r, res, true));
      }
    }
  }
  return out;
}

function runCapacity(job: Extract<Job, { kind: 'capacity' }>): CapacityOut {
  const rows = subsample(job.rows.filter((r) => job.models[r.load.powderId!]), 40, 40);
  const prior = job.rows[0].capPrior;
  if (rows.length < 3) return { kind: 'capacity', groupKey: job.groupKey, capGrH2O: null, n: rows.length, powders: 0, prior, rmsPressurePct: null };
  // Lower bound: the solid charge plus the seated bullet must fit.
  let lo = 0;
  for (const r of rows) {
    const solidCm3 = U.grToG(r.inputs.chargeGr) / 1.6;
    const seat = Math.max(0, r.inputs.bulletLengthIn - (r.inputs.coalIn - r.inputs.caseLengthIn));
    const intr = bulletVolumeBelow({ massKg: 1, diameterM: U.inToM(r.inputs.bulletDiameterIn), lengthM: U.inToM(r.inputs.bulletLengthIn) }, U.inToM(seat)) * 1e6;
    lo = Math.max(lo, U.cm3ToGrH2O((solidCm3 + intr) * 1.02));
  }
  let a = Math.log(prior ? Math.max(lo, prior * 0.85) : lo);
  let b = Math.log(prior ? prior * 1.15 : lo * 3.5);
  if (a >= b) b = a + 0.3;
  const cost = (logCap: number) => {
    const cap = Math.exp(logCap);
    let s = 0;
    for (const r of rows) {
      const m = job.models[r.load.powderId!];
      const p = db.powders.find((x) => x.id === r.load.powderId)!;
      const res = simulateRow(m, r, p.bulkDensityGcc, cap);
      const v = res.status === 'muzzle' ? res.muzzleVelocityMs : 0;
      s += ((v - U.fpsToMs(r.load.velocityFps)) / SIGMA_V_MS) ** 2;
      if (r.peakPa) s += ((Number.isFinite(res.peakBreechPa) ? res.peakBreechPa : 1e10) - r.peakPa) ** 2 / (r.peakPa * SIGMA_P_REL) ** 2;
    }
    if (prior) s += (Math.log(cap / prior) / CAP_PRIOR_SIGMA) ** 2;
    return s;
  };
  const g = (Math.sqrt(5) - 1) / 2;
  let c = b - g * (b - a);
  let d = a + g * (b - a);
  let fc = cost(c);
  let fd = cost(d);
  for (let i = 0; i < 28; i++) {
    if (fc < fd) {
      b = d;
      d = c;
      fd = fc;
      c = b - g * (b - a);
      fc = cost(c);
    } else {
      a = c;
      c = d;
      fc = fd;
      d = a + g * (b - a);
      fd = cost(d);
    }
  }
  const cap = Math.exp((a + b) / 2);
  const pErr: number[] = [];
  for (const r of rows) {
    if (!r.peakPa) continue;
    const p = db.powders.find((x) => x.id === r.load.powderId)!;
    const res = simulateRow(job.models[r.load.powderId!], r, p.bulkDensityGcc, cap);
    pErr.push((res.peakBreechPa - r.peakPa) / r.peakPa);
  }
  return {
    kind: 'capacity',
    groupKey: job.groupKey,
    capGrH2O: cap,
    n: rows.length,
    powders: new Set(rows.map((r) => r.load.powderId)).size,
    prior,
    rmsPressurePct: pErr.length ? Math.sqrt(pErr.reduce((s, v) => s + v * v, 0) / pErr.length) * 100 : null,
  };
}

const SHARD_DIR = path.join(os.tmpdir(), 'orka-calib');

async function runJobs<T>(jobs: Job[], nProc: number, tag: string): Promise<T[]> {
  if (!jobs.length) return [];
  fs.mkdirSync(SHARD_DIR, { recursive: true });
  const sorted = jobs.slice().sort((a, b) => b.rows.length - a.rows.length);
  const n = Math.max(1, Math.min(nProc, sorted.length));
  const shards: Job[][] = Array.from({ length: n }, () => []);
  sorted.forEach((j, i) => shards[i % n].push(j));
  const procs = shards.map(
    (shard, i) =>
      new Promise<T[]>((resolve, reject) => {
        const inF = path.join(SHARD_DIR, `${tag}-in-${i}.json`);
        const outF = path.join(SHARD_DIR, `${tag}-out-${i}.json`);
        fs.writeFileSync(inF, JSON.stringify(shard));
        const child = spawn(process.execPath, [...process.execArgv, new URL(import.meta.url).pathname, '--worker', inF, outF], { stdio: ['ignore', 'inherit', 'inherit'] });
        child.on('exit', (code) => (code === 0 ? resolve(JSON.parse(fs.readFileSync(outF, 'utf8'))) : reject(new Error(`worker ${tag}-${i} exited ${code}`))));
      }),
  );
  return (await Promise.all(procs)).flat();
}

// ---------------------------------------------------------------- main

async function main() {
  if (process.argv[2] === '--worker') {
    const jobs: Job[] = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
    const res: (PowderOut | CapacityOut)[] = [];
    for (const j of jobs) {
      const t0 = Date.now();
      res.push(j.kind === 'powder' ? runPowder(j) : runCapacity(j));
      console.log(`  ${j.kind} ${j.kind === 'powder' ? `${j.powderId} stage ${j.stage}` : j.groupKey} (${j.rows.length} rows) ${((Date.now() - t0) / 1000).toFixed(1)} s`);
      fs.writeFileSync(process.argv[4], JSON.stringify(res));
    }
    fs.writeFileSync(process.argv[4], JSON.stringify(res));
    return;
  }
  const only = process.env.ORKA_POWDERS ? new Set(process.env.ORKA_POWDERS.split(',')) : null;
  const nProc = Math.max(1, Number(process.env.ORKA_PROCS ?? os.cpus().length - 1));
  const prepared = db.validationLoads.map(prepare).filter((x): x is Prepared => x !== null);
  const rowsOf = new Map<string, Prepared[]>();
  for (const r of prepared) {
    if (!r.load.powderId) {
      skip('powder not matched to database');
      continue;
    }
    if (only && !only.has(r.load.powderId)) continue;
    rowsOf.set(r.load.powderId, [...(rowsOf.get(r.load.powderId) ?? []), r]);
  }
  const tierCount = prepared.reduce<Record<string, number>>((a, r) => ((a[r.tier] = (a[r.tier] ?? 0) + 1), a), {});
  console.log(`Prepared ${prepared.length} loads (capacity tiers ${JSON.stringify(tierCount)}), ${rowsOf.size} powders, ${nProc} processes.`);

  // Stage 1: powders on rows with published capacity.
  const stage1Jobs: Job[] = [];
  for (const [pid, rows] of rowsOf) {
    const a = rows.filter((r) => r.tier === 'A' && r.shotClass === 'jacketed');
    const ab = rows.filter((r) => r.tier !== 'C' && r.shotClass === 'jacketed');
    const use = a.length >= 6 ? a : ab;
    if (use.length >= 3) stage1Jobs.push({ kind: 'powder', stage: 1, powderId: pid, rows: use });
  }
  console.log(`Stage 1: ${stage1Jobs.length} powders with ≥3 rows of published capacity.`);
  const s1 = await runJobs<PowderOut>(stage1Jobs, nProc, 's1');
  const models1: Record<string, FittedModel> = Object.fromEntries(s1.map((o) => [o.powderId, { params: o.params }]));

  // Stage 2a: shot-start pressure of monolithic and lead bullets relative to the jacketed reference, fitted with the
  // stage-1 powders fixed, on rows whose case capacity is published (tier A, or tier B at the prior).
  const shotFits: Record<string, { value: number; n: number; powders: number; rmsPressurePct: number | null } | null> = {};
  for (const cls of ['monolithic', 'lead'] as const) {
    const pool: Prepared[] = [];
    for (const rows of rowsOf.values()) for (const r of rows) if (r.shotClass === cls && r.tier !== 'C' && models1[r.load.powderId!]) pool.push(r);
    const sample = subsample(pool, 4, 60);
    if (sample.length < 8) {
      shotFits[cls] = null;
      continue;
    }
    const cost = (logMPa: number) => {
      let s = 0;
      for (const r of sample) {
        const p = db.powders.find((x) => x.id === r.load.powderId)!;
        const rr = { ...r, inputs: { ...r.inputs, shotStartPsi: U.mpaToPsi(Math.exp(logMPa)), caseCapacityGrH2O: r.inputs.caseCapacityGrH2O > 0 ? r.inputs.caseCapacityGrH2O : r.capPrior! } };
        const res = simulateRow(models1[r.load.powderId!], rr, p.bulkDensityGcc);
        const v = res.status === 'muzzle' ? res.muzzleVelocityMs : 0;
        s += ((v - U.fpsToMs(r.load.velocityFps)) / SIGMA_V_MS) ** 2;
        if (r.peakPa) s += ((Number.isFinite(res.peakBreechPa) ? res.peakBreechPa : 1e10) - r.peakPa) ** 2 / (r.peakPa * SIGMA_P_REL) ** 2;
      }
      return s;
    };
    let a = Math.log(10);
    let b = Math.log(250);
    const g = (Math.sqrt(5) - 1) / 2;
    let c = b - g * (b - a);
    let d = a + g * (b - a);
    let fc = cost(c);
    let fd = cost(d);
    for (let i = 0; i < 24; i++) {
      if (fc < fd) {
        b = d; d = c; fd = fc; c = b - g * (b - a); fc = cost(c);
      } else {
        a = c; c = d; fc = fd; d = a + g * (b - a); fd = cost(d);
      }
    }
    const value = Math.exp((a + b) / 2);
    shotFits[cls] = { value: Math.round(value * 10) / 10, n: sample.length, powders: new Set(sample.map((r) => r.load.powderId)).size, rmsPressurePct: null };
    for (const rows of rowsOf.values()) for (const r of rows) if (r.shotClass === cls) r.inputs = { ...r.inputs, shotStartPsi: U.mpaToPsi(value) };
    console.log(`Stage 2a: ${cls} shot-start fitted at ${value.toFixed(1)} MPa from ${sample.length} loads.`);
  }

  // Stage 2: effective capacity per (cartridge, case brand) for groups without a brand-matched capacity.
  const groups = new Map<string, Prepared[]>();
  for (const rows of rowsOf.values()) for (const r of rows) if (r.tier !== 'A') groups.set(r.groupKey, [...(groups.get(r.groupKey) ?? []), r]);
  const capJobs: Job[] = [...groups.entries()].map(([groupKey, rows]) => ({ kind: 'capacity', groupKey, rows, models: models1 }));
  console.log(`Stage 2: inferring effective capacity for ${capJobs.length} cartridge/case groups.`);
  const caps = await runJobs<CapacityOut>(capJobs, nProc, 's2');
  const capOf = new Map(caps.filter((c) => c.capGrH2O !== null).map((c) => [c.groupKey, c]));

  // Apply inferred capacities (tier C rows without one are dropped).
  for (const [pid, rows] of rowsOf) {
    const kept: Prepared[] = [];
    for (const r of rows) {
      if (r.tier === 'A') kept.push(r);
      else {
        const c = capOf.get(r.groupKey);
        if (c) {
          kept.push({ ...r, inputs: { ...r.inputs, caseCapacityGrH2O: c.capGrH2O! }, notes: [...r.notes, `effective capacity ${c.capGrH2O!.toFixed(1)} gr H2O inferred from ${c.n} loads / ${c.powders} powders`] });
        } else if (r.tier === 'B') kept.push(r);
        else skip('no capacity (could not infer)');
      }
    }
    rowsOf.set(pid, kept);
  }

  // Stage 3: final fits + validation.
  const stage3Jobs: Job[] = [];
  for (const [pid, rows] of rowsOf) {
    if (rows.length < 1) continue;
    const pool = rows.filter((r) => r.tier !== 'C').map((r) => (r.tier === 'B' ? { ...r, inputs: { ...r.inputs, caseCapacityGrH2O: r.capPrior! } } : r));
    const aCarts = [...new Set(rows.filter((r) => r.tier === 'A').map((r) => r.cartridgeId))];
    const ranked = aCarts.map((c) => [c, rows.filter((r) => r.cartridgeId === c).length] as const).sort((x, y) => y[1] - x[1]).map((x) => x[0]);
    stage3Jobs.push({ kind: 'powder', stage: 3, powderId: pid, rows, locoRows: pool, locoCartridges: new Set(pool.map((r) => r.cartridgeId)).size >= 2 ? ranked.slice(0, MAX_LOCO) : [] });
  }
  console.log(`Stage 3: final fits for ${stage3Jobs.length} powders.`);
  const s3 = await runJobs<PowderOut>(stage3Jobs, nProc, 's3');

  const models: Record<string, PowderModelEntry> = {};
  const rows: any[] = [];
  const heldOutV: number[] = [];
  const heldOutP: number[] = [];
  const inSampleV: number[] = [];
  const inSampleP: number[] = [];
  for (const o of s3) {
    const p = db.powders.find((x) => x.id === o.powderId)!;
    const all = rowsOf.get(o.powderId)!;
    const carts = [...new Set(all.map((r) => r.cartridgeId))];
    const nInferred = all.filter((r) => r.tier !== 'A').length;
    models[o.powderId] = {
      status: 'calibrated',
      params: o.params,
      derivation:
        `Fitted to ${o.points} of ${all.length} usable published pressure-tested loads (cartridge-stratified sample) across ${carts.length} cartridge(s); ` +
        `${nInferred ? `${nInferred} of those loads use an inferred or other-brand case capacity. ` : ''}` +
        `Fitted: ${o.fitted.join(', ')}; other thermochemistry from class priors${p.heatOfExplosionJg ? ` and the maker's heat of explosion (${p.heatOfExplosionJg} J/g)` : ''}. ` +
        `${o.warnings.join(' ')}`.trim(),
      calibration: {
        points: o.points,
        rmsVelocityFps: o.rmsVelocityFps,
        rmsPressurePct: o.rmsPressurePct,
        cartridges: carts,
        sources: [...new Set(all.flatMap((r) => r.load.sources.map((s) => s.url)))],
        chargeRangeGr: [Math.min(...all.map((r) => r.load.chargeGr)), Math.max(...all.map((r) => r.load.chargeGr))],
        grade: o.rmsPressurePct === null ? 'fair' : o.rmsPressurePct <= 10 ? 'good' : o.rmsPressurePct <= 20 ? 'fair' : 'poor',
        heldOutPressurePct: o.heldOutP.length >= 3 ? Math.round([...o.heldOutP].map(Math.abs).sort((a, b) => a - b)[Math.floor(o.heldOutP.length / 2)] * 1000) / 10 : null,
      },
    };
    rows.push(...o.rows);
    heldOutV.push(...o.heldOutV);
    heldOutP.push(...o.heldOutP);
    inSampleV.push(...o.inSampleV);
    inSampleP.push(...o.inSampleP);
  }

  // Inferred capacities for the app (clearly labelled, never preferred over a published value).
  const inferred = caps
    .filter((c) => c.capGrH2O !== null)
    .map((c) => {
      const [cartridgeId, caseBrand] = c.groupKey.split('|');
      return {
        cartridgeId,
        caseBrand,
        grH2O: Math.round(c.capGrH2O! * 10) / 10,
        loads: c.n,
        powders: c.powders,
        priorFromOtherBrands: c.prior,
        rmsPressurePct: c.rmsPressurePct,
        basis: `model-inferred effective capacity of the ${caseBrand} cases used in published pressure tests (${c.n} loads, ${c.powders} powders) — not a measurement`,
      };
    });

  // How good is chart interpolation? Re-estimate each calibrated powder from its chart neighbours.
  const withModels = db.powders.map((p) => (models[p.id] ? { ...p, model: models[p.id] } : { ...p, model: undefined }));
  const interpErr: number[] = [];
  for (const pid of Object.keys(models)) {
    const without = withModels.map((p) => (p.id === pid ? { ...p, model: undefined } : p));
    const est = estimateFromCharts(without, db.burnRateCharts as any)[pid];
    if (est) interpErr.push(Math.log(est.params.beta * Math.pow(100, est.params.n)) - Math.log(models[pid].params.beta * Math.pow(100, models[pid].params.n)));
  }
  const rmsLog = interpErr.length >= 3 ? Math.sqrt(interpErr.reduce((s, v) => s + v * v, 0) / interpErr.length) : null;

  const mae = (a: number[]) => (a.length ? a.reduce((s, v) => s + Math.abs(v), 0) / a.length : null);
  const q = (a: number[], f: number) => {
    if (!a.length) return null;
    const s = a.map(Math.abs).sort((x, y) => x - y);
    return s[Math.min(s.length - 1, Math.floor(f * s.length))];
  };
  const pctTxt = (v: number | null) => (v === null ? '—' : `${(v * 100).toFixed(1)} %`);
  const report = {
    generated: new Date().toISOString(),
    metrics: {
      points: rows.filter((r) => r.heldOut).length,
      velocityMaeFps: mae(heldOutV),
      velocityMapePct: null as number | null,
      pressureMapePct: heldOutP.length ? (mae(heldOutP) as number) * 100 : null,
      pressureP67Pct: heldOutP.length ? (q(heldOutP, 0.67) as number) * 100 : null,
      pressureP95Pct: heldOutP.length ? (q(heldOutP, 0.95) as number) * 100 : null,
      velocityP95Fps: q(heldOutV, 0.95),
      notes:
        `Held-out = leave-one-cartridge-out: each powder is refitted without one cartridge (only rows whose case capacity is published are used for this test), then predicts that cartridge's loads. ` +
        `${heldOutV.length} held-out velocity and ${heldOutP.length} held-out pressure comparisons over ${s3.length} powders. ` +
        `Held-out |pressure error|: median-ish MAPE ${heldOutP.length ? ((mae(heldOutP) as number) * 100).toFixed(1) : '—'} %, 67th percentile ${pctTxt(q(heldOutP, 0.67))}, 95th ${pctTxt(q(heldOutP, 0.95))}. ` +
        `In-sample (fitted rows, including inferred capacities): velocity MAE ${mae(inSampleV)?.toFixed(0) ?? '—'} fps, pressure MAPE ${inSampleP.length ? ((mae(inSampleP) as number) * 100).toFixed(1) : '—'} %. ` +
        `Chart interpolation (calibrated powders re-estimated from chart neighbours): ${rmsLog === null ? 'too few to measure' : `RMS burn-rate error ${(rmsLog * 100).toFixed(0)} % over ${interpErr.length} powders`}. ` +
        `Capacity tiers of prepared loads: ${JSON.stringify(tierCount)}. ` +
        `Shot-start fitted per bullet construction: ${Object.entries(shotFits).map(([k, v]) => `${k} ${v ? `${v.value} MPa (${v.n} loads)` : 'not enough data'}`).join(', ')}; jacketed reference 25 MPa. ` +
        `Bullet lengths: ${prepared.filter((r) => r.lengthEstimated).length} of ${prepared.length} prepared loads use an ESTIMATED length because the bullet maker publishes none ` +
        `(estimator fitted on ${LENGTH_MODEL?.n ?? 0} bullets with published lengths, leave-one-out error: pointed ${LENGTH_MODEL?.looRelRmsPointed != null ? (LENGTH_MODEL.looRelRmsPointed * 100).toFixed(1) : '—'} %, blunt ${LENGTH_MODEL?.looRelRmsBlunt != null ? (LENGTH_MODEL.looRelRmsBlunt * 100).toFixed(1) : '—'} %; a class is used only when its error is at most 8 %). ` +
        `Loads skipped: ${JSON.stringify(skipped)}.`,
      interpolationBetaRelSigma: rmsLog,
    },
    rows,
  };
  fs.writeFileSync(path.join(ROOT, 'src/data/powder-models.json'), JSON.stringify({ generated: report.generated, models }, null, 1));
  // Keep the shipped report compact: in-sample rows drop their long notes (held-out rows keep them).
  const slim = { ...report, rows: report.rows.map((r: any) => (r.heldOut ? r : { ...r, notes: undefined, label: r.label })) };
  fs.writeFileSync(path.join(ROOT, 'src/data/validation-report.json'), JSON.stringify(slim));
  fs.writeFileSync(path.join(ROOT, 'src/data/inferred-capacities.json'), JSON.stringify(inferred, null, 1));
  if (!only) {
    const constPath = path.join(ROOT, 'src/data/model-constants.json');
    const consts = JSON.parse(fs.readFileSync(constPath, 'utf8'));
    consts.generated = report.generated;
    for (const cls of ['monolithic', 'lead'] as const) {
      const f = shotFits[cls];
      if (f) consts.shotStartMPa[cls] = { value: f.value, basis: `Fitted to ${f.n} published pressure-tested loads with ${cls} bullets (${f.powders} powders), relative to the 25 MPa jacketed reference, by scripts/calibrate-powders.ts.` };
    }
    fs.writeFileSync(constPath, JSON.stringify(consts, null, 2));
  }
  console.log(JSON.stringify({ powdersCalibrated: Object.keys(models).length, inferredCapacities: inferred.length, skipped, metrics: { ...report.metrics, notes: undefined } }, null, 2));
}

main();
