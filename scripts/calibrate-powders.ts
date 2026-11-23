// Calibrate powder models against published, pressure-tested load data and measure accuracy honestly.
//
//   npx tsx scripts/calibrate-powders.ts      (after scripts/build-data.ts has produced src/data/db.json)
//
// For every powder with usable published loads:
//   1. Build each load's setup from the database (cartridge bore/groove, case capacity for the stated case brand,
//      bullet length from the maker's catalog, COAL and barrel length from the load data).
//   2. Fit the burn-rate coefficient (beta), progressivity (lambda, ≥3 loads) and energy (force, ≥4 loads with
//      ≥2 pressures) to measured velocity and peak pressure. Model breech pressure is fitted to transducer readings.
//   3. Cross-validate: refit without one cartridge at a time and predict that cartridge's loads (held-out error).
// Outputs src/data/powder-models.json and src/data/validation-report.json.

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';
import { calibrate, type FitParam, type Observation } from '../src/engine/calibrate';
import { simulate } from '../src/engine/model';
import { propellantFromParams, paramsFromPropellant, toSetup, type LoadInputs } from '../src/engine/adapter';
import { defaultShotStartPsi, priorParams } from '../src/engine/defaults';
import * as U from '../src/engine/units';
import type { Bullet, Cartridge, Database, Powder, PowderModelEntry, ValidationLoad } from '../src/data/schema';
import { estimateFromCharts } from './estimate';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const db: Database = JSON.parse(fs.readFileSync(path.join(ROOT, 'src/data/db.json'), 'utf8'));
db.validationLoads = JSON.parse(fs.readFileSync(path.join(ROOT, 'research/build/validation-loads.json'), 'utf8'));

const SIGMA_V_MS = U.fpsToMs(25); // published velocities are rounded / lot-dependent
const SIGMA_P_REL = 0.05;

const skipped: Record<string, number> = {};
const skip = (why: string) => (skipped[why] = (skipped[why] ?? 0) + 1);

const words = (s: string) => new Set(s.toLowerCase().replace(/[^a-z0-9 ]/g, ' ').split(/\s+/).filter((w) => w.length > 1));

function findBullet(l: ValidationLoad, diameterIn: number): { bullet: Bullet | null; note: string } {
  const mk = l.bulletMfr.toLowerCase().split(/\s+/)[0];
  const cands = db.bullets.filter(
    (b) => b.manufacturer.toLowerCase().includes(mk) && Math.abs(b.diameterIn - diameterIn) <= 0.003 && Math.abs(b.weightGr - l.bulletWeightGr) <= 0.5 && b.lengthIn,
  );
  if (!cands.length) return { bullet: null, note: 'no catalog bullet with length' };
  const want = words(l.bulletModel);
  const scored = cands.map((b) => ({ b, s: [...words(`${b.line} ${b.name}`)].filter((w) => want.has(w)).length })).sort((a, b) => b.s - a.s);
  const best = scored.filter((x) => x.s === scored[0].s).map((x) => x.b);
  const lens = best.map((b) => b.lengthIn as number);
  if (Math.max(...lens) - Math.min(...lens) > 0.02) return { bullet: null, note: 'ambiguous bullet match' };
  return { bullet: best[0], note: scored[0].s > 0 ? 'matched by maker/weight/model words' : 'matched by maker/weight only' };
}

function capacityFor(l: ValidationLoad, c: Cartridge): { cap: number; basis: string } | null {
  const brand = (l.caseBrand ?? '').toLowerCase();
  const byBrand = c.caseCapacityGrH2O.filter((e) => brand && e.brand && (brand.includes(e.brand.toLowerCase()) || e.brand.toLowerCase().includes(brand)));
  if (byBrand.length) {
    const v = byBrand.map((e) => e.value).sort((a, b) => a - b);
    return { cap: v[Math.floor(v.length / 2)], basis: `${byBrand[0].brand} (${byBrand[0].basis})` };
  }
  if (c.caseCapacityGrH2O.length) {
    const v = c.caseCapacityGrH2O.map((e) => e.value).sort((a, b) => a - b);
    return { cap: v[Math.floor(v.length / 2)], basis: `median of ${v.length} published capacities (case brand ${l.caseBrand ?? 'unstated'} not matched)` };
  }
  return null;
}

interface Prepared {
  load: ValidationLoad;
  cartridgeId: string;
  inputs: LoadInputs;
  peakPa?: number;
  label: string;
  notes: string[];
}

function prepare(l: ValidationLoad): Prepared | null {
  const c = db.cartridges.find((x) => x.id === l.cartridgeId);
  if (!c) return skip('cartridge not in database'), null;
  if (!c.boreDiameterIn || !c.grooveDiameterIn) return skip('cartridge bore/groove unknown'), null;
  const caseLen = l.caseTrimLengthIn ?? c.trimLengthIn ?? c.caseLengthMaxIn;
  if (!caseLen) return skip('case length unknown'), null;
  if (!Number.isFinite(l.coalIn) || !Number.isFinite(l.barrelLengthIn)) return skip('COAL or barrel length missing'), null;
  const cap = capacityFor(l, c);
  if (!cap) return skip('no published case capacity for cartridge'), null;
  const d = l.bulletDiameterIn ?? c.bulletDiameterIn;
  if (!d) return skip('bullet diameter unknown'), null;
  let len = l.bulletLengthIn ?? null;
  let bt = 0;
  let construction: string | null = null;
  const notes: string[] = [`capacity ${cap.cap} gr H2O: ${cap.basis}`];
  const fb = findBullet(l, d);
  if (fb.bullet) {
    len = len ?? fb.bullet.lengthIn;
    bt = fb.bullet.boatTailLengthIn ?? 0;
    construction = fb.bullet.construction ?? null;
    notes.push(`bullet ${fb.bullet.manufacturer} ${fb.bullet.name} (${fb.note})`);
  }
  if (!len) return skip(`bullet length unknown (${fb.note})`), null;
  let peakPa: number | undefined;
  if (l.pressure !== null && l.pressureUnit === 'psi' && (l.pressureMethod ?? '').toLowerCase() !== 'cup') peakPa = U.psiToPa(l.pressure);
  else if (l.pressure !== null && l.pressureUnit === 'bar') peakPa = U.barToPa(l.pressure);
  // CUP readings are never converted; such loads contribute velocity only.
  return {
    load: l,
    cartridgeId: c.id,
    inputs: {
      boreDiameterIn: c.boreDiameterIn,
      grooveDiameterIn: c.grooveDiameterIn,
      caseLengthIn: caseLen,
      caseCapacityGrH2O: cap.cap,
      barrelLengthIn: l.barrelLengthIn,
      bulletWeightGr: l.bulletWeightGr,
      bulletDiameterIn: d,
      bulletLengthIn: len,
      boatTailLengthIn: bt,
      bulletBaseDiameterIn: bt > 0 ? d * 0.8 : d,
      coalIn: l.coalIn,
      chargeGr: l.chargeGr,
      powderTempF: 70,
      shotStartPsi: defaultShotStartPsi(construction, c.type),
    },
    peakPa,
    label: `${c.name} · ${l.bulletMfr} ${l.bulletWeightGr} gr ${l.bulletModel} · ${l.chargeGr} gr (${l.loadType})`,
    notes,
  };
}

function fitPowder(p: Powder, rows: Prepared[]) {
  const start = propellantFromParams(priorParams({ heatOfExplosionJg: p.heatOfExplosionJg ?? null, base: p.base, beta: 5 }), p.bulkDensityGcc ?? null);
  const obs: Observation[] = rows.map((r) => ({
    setup: toSetup(r.inputs, start, { rtol: 1e-6 }),
    velocityMs: U.fpsToMs(r.load.velocityFps),
    peakPa: r.peakPa,
    label: r.label,
  }));
  const nP = rows.filter((r) => r.peakPa !== undefined).length;
  const params: FitParam[] = ['beta'];
  if (rows.length >= 3) params.push('lambda');
  if (rows.length >= 4 && nP >= 2) params.push('force');
  return calibrate({ start, observations: obs, params, sigmaVelocityMs: SIGMA_V_MS, sigmaPressureRel: SIGMA_P_REL });
}

function predict(model: ReturnType<typeof fitPowder>, r: Prepared, bulk: number | null | undefined) {
  const prop = { ...model.model, bulkDensityKgM3: bulk ? bulk * 1000 : undefined };
  return simulate(toSetup(r.inputs, prop, { rtol: 1e-6 }, model.heatScale));
}

/** Deterministic, cartridge-stratified subsample: up to `perCart` rows per cartridge (spread over bullet weights,
 * both start and max loads), at most `cap` rows in total (cartridges taken round-robin). */
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

interface PowderJob {
  powderId: string;
  rows: Prepared[];
}

interface PowderResult {
  powderId: string;
  entry: PowderModelEntry;
  rows: any[];
  heldOutV: number[];
  heldOutP: number[];
  inSampleV: number[];
  inSampleP: number[];
}

const MAX_LOCO = 6;

function runPowder(job: PowderJob): PowderResult {
  const p = db.powders.find((x) => x.id === job.powderId)!;
  const prs = job.rows;
  const fitRows = subsample(prs);
  const fit = fitPowder(p, fitRows);
  const cartridges = [...new Set(prs.map((r) => r.cartridgeId))];
  const nP = fitRows.filter((r) => r.peakPa !== undefined).length;
  const entry: PowderModelEntry = {
    status: 'calibrated',
    params: paramsFromPropellant(fit.model, fit.heatScale),
    derivation:
      `Fitted to ${fitRows.length} of ${prs.length} usable published pressure-tested loads (cartridge-stratified sample) across ${cartridges.length} cartridge(s). ` +
      `Fitted: ${['beta', fitRows.length >= 3 ? 'lambda' : null, fitRows.length >= 4 && nP >= 2 ? 'force' : null].filter(Boolean).join(', ')}; ` +
      `other thermochemistry from class priors${p.heatOfExplosionJg ? ` and the maker's heat of explosion (${p.heatOfExplosionJg} J/g)` : ''}. ` +
      `${fit.warnings.join(' ')}`.trim(),
    calibration: {
      points: fitRows.length,
      rmsVelocityFps: fit.rmsVelocityMs === null ? null : U.msToFps(fit.rmsVelocityMs),
      rmsPressurePct: fit.rmsPressureRel === null ? null : fit.rmsPressureRel * 100,
      cartridges,
      sources: [...new Set(prs.flatMap((r) => r.load.sources.map((s) => s.url)))],
      chargeRangeGr: [Math.min(...prs.map((r) => r.load.chargeGr)), Math.max(...prs.map((r) => r.load.chargeGr))],
    },
  };
  const out: PowderResult = { powderId: p.id, entry, rows: [], heldOutV: [], heldOutP: [], inSampleV: [], inSampleP: [] };
  const row = (r: Prepared, res: ReturnType<typeof simulate>, heldOut: boolean) => ({
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
    page: r.load.sources[0]?.page ?? null,
    notes: r.notes.join('; '),
  });
  for (const r of fitRows) {
    const res = predict(fit, r, p.bulkDensityGcc);
    out.inSampleV.push(U.msToFps(res.muzzleVelocityMs) - r.load.velocityFps);
    if (r.peakPa) out.inSampleP.push((res.peakBreechPa - r.peakPa) / r.peakPa);
    out.rows.push(row(r, res, false));
  }
  // Leave-one-cartridge-out on the cartridges with the most data.
  if (cartridges.length >= 2) {
    const counts = cartridges.map((c) => [c, prs.filter((r) => r.cartridgeId === c).length] as const).sort((a, b) => b[1] - a[1]);
    for (const [cid] of counts.slice(0, MAX_LOCO)) {
      const train = subsample(prs.filter((r) => r.cartridgeId !== cid));
      const test = subsample(prs.filter((r) => r.cartridgeId === cid), 8, 8);
      const f2 = fitPowder(p, train);
      for (const r of test) {
        const res = predict(f2, r, p.bulkDensityGcc);
        if (Number.isFinite(res.muzzleVelocityMs)) out.heldOutV.push(U.msToFps(res.muzzleVelocityMs) - r.load.velocityFps);
        if (r.peakPa && Number.isFinite(res.peakBreechPa)) out.heldOutP.push((res.peakBreechPa - r.peakPa) / r.peakPa);
        out.rows.push(row(r, res, true));
      }
    }
  }
  return out;
}

const SHARD_DIR = path.join(os.tmpdir(), 'orka-calib');

async function runWorkers(jobs: PowderJob[], nProc: number): Promise<PowderResult[]> {
  fs.mkdirSync(SHARD_DIR, { recursive: true });
  // Largest jobs first, dealt round-robin so shards finish at similar times.
  const sorted = jobs.slice().sort((a, b) => b.rows.length - a.rows.length);
  const shards: PowderJob[][] = Array.from({ length: nProc }, () => []);
  sorted.forEach((j, i) => shards[i % nProc].push(j));
  const procs = shards.map(
    (shard, i) =>
      new Promise<PowderResult[]>((resolve, reject) => {
        const inF = path.join(SHARD_DIR, `in-${i}.json`);
        const outF = path.join(SHARD_DIR, `out-${i}.json`);
        fs.writeFileSync(inF, JSON.stringify(shard));
        const child = spawn(process.execPath, [...process.execArgv, new URL(import.meta.url).pathname, '--worker', inF, outF], { stdio: ['ignore', 'inherit', 'inherit'] });
        child.on('exit', (code) => (code === 0 ? resolve(JSON.parse(fs.readFileSync(outF, 'utf8'))) : reject(new Error(`worker ${i} exited ${code}`))));
      }),
  );
  return (await Promise.all(procs)).flat();
}

async function main() {
  if (process.argv[2] === '--worker') {
    const jobs: PowderJob[] = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
    const res: PowderResult[] = [];
    for (const j of jobs) {
      const t0 = Date.now();
      res.push(runPowder(j));
      console.log(`  fitted ${j.powderId} (${j.rows.length} rows) in ${((Date.now() - t0) / 1000).toFixed(1)} s`);
      fs.writeFileSync(process.argv[4], JSON.stringify(res));
    }
    fs.writeFileSync(process.argv[4], JSON.stringify(res));
    return;
  }
  const only = process.env.ORKA_POWDERS ? new Set(process.env.ORKA_POWDERS.split(',')) : null;
  const prepared = db.validationLoads.map(prepare).filter((x): x is Prepared => x !== null);
  const byPowder = new Map<string, Prepared[]>();
  for (const r of prepared) {
    if (!r.load.powderId) {
      skip('powder not matched to database');
      continue;
    }
    if (only && !only.has(r.load.powderId)) continue;
    byPowder.set(r.load.powderId, [...(byPowder.get(r.load.powderId) ?? []), r]);
  }
  const jobs = [...byPowder.entries()].map(([powderId, rows]) => ({ powderId, rows }));
  const nProc = Math.max(1, Math.min(Number(process.env.ORKA_PROCS ?? os.cpus().length - 1), jobs.length));
  console.log(`Calibrating ${jobs.length} powders from ${prepared.length} prepared loads on ${nProc} processes…`);
  const results = await runWorkers(jobs, nProc);

  const models: Record<string, PowderModelEntry> = {};
  const rows: any[] = [];
  const heldOutV: number[] = [];
  const heldOutP: number[] = [];
  const inSampleV: number[] = [];
  const inSampleP: number[] = [];
  for (const r of results) {
    models[r.powderId] = r.entry;
    rows.push(...r.rows);
    heldOutV.push(...r.heldOutV);
    heldOutP.push(...r.heldOutP);
    inSampleV.push(...r.inSampleV);
    inSampleP.push(...r.inSampleP);
  }

  // How good is chart interpolation? Leave each calibrated powder out, re-estimate it from its neighbours.
  const powdersWithModels = db.powders.map((p) => (models[p.id] ? { ...p, model: models[p.id] } : { ...p, model: undefined }));
  const interpErr: number[] = [];
  for (const pid of Object.keys(models)) {
    const without = powdersWithModels.map((p) => (p.id === pid ? { ...p, model: undefined } : p));
    const est = estimateFromCharts(without, db.burnRateCharts as any)[pid];
    if (est) interpErr.push(Math.log(est.params.beta / models[pid].params.beta));
  }
  const rmsLog = interpErr.length >= 3 ? Math.sqrt(interpErr.reduce((s, v) => s + v * v, 0) / interpErr.length) : null;

  const mae = (a: number[]) => (a.length ? a.reduce((s, v) => s + Math.abs(v), 0) / a.length : null);
  const pct = (a: number[], q: number) => {
    if (!a.length) return null;
    const s = a.map(Math.abs).sort((x, y) => x - y);
    return s[Math.min(s.length - 1, Math.floor(q * s.length))];
  };
  const report = {
    generated: new Date().toISOString(),
    metrics: {
      points: rows.filter((r) => r.heldOut).length,
      velocityMaeFps: mae(heldOutV),
      velocityMapePct: null as number | null,
      pressureMapePct: heldOutP.length ? (mae(heldOutP) as number) * 100 : null,
      pressureP67Pct: heldOutP.length ? (pct(heldOutP, 0.67) as number) * 100 : null,
      pressureP95Pct: heldOutP.length ? (pct(heldOutP, 0.95) as number) * 100 : null,
      velocityP95Fps: pct(heldOutV, 0.95),
      notes:
        `Held-out = leave-one-cartridge-out: each powder is refitted without one cartridge's loads, then predicts them (up to ${MAX_LOCO} cartridges per powder). ` +
        `${heldOutV.length} held-out velocity and ${heldOutP.length} held-out pressure comparisons over ${results.length} powders. ` +
        `Held-out |pressure error|: 67th percentile ${heldOutP.length ? ((pct(heldOutP, 0.67) as number) * 100).toFixed(1) : '—'} %, 95th ${heldOutP.length ? ((pct(heldOutP, 0.95) as number) * 100).toFixed(1) : '—'} %. ` +
        `In-sample (fitted data): velocity MAE ${mae(inSampleV)?.toFixed(0) ?? '—'} fps, pressure MAPE ${inSampleP.length ? ((mae(inSampleP) as number) * 100).toFixed(1) : '—'} %. ` +
        `Chart-interpolation check (calibrated powders re-estimated from chart neighbours): ${rmsLog === null ? 'too few powders to measure' : `RMS burn-rate error ${(rmsLog * 100).toFixed(0)} % over ${interpErr.length} powders`}. ` +
        `Loads skipped while preparing: ${JSON.stringify(skipped)}.`,
      interpolationBetaRelSigma: rmsLog,
    },
    rows,
  };
  fs.writeFileSync(path.join(ROOT, 'src/data/powder-models.json'), JSON.stringify({ generated: report.generated, models }, null, 1));
  fs.writeFileSync(path.join(ROOT, 'src/data/validation-report.json'), JSON.stringify(report));
  console.log(JSON.stringify({ powdersCalibrated: Object.keys(models).length, prepared: prepared.length, skipped, metrics: { ...report.metrics, notes: undefined } }, null, 2));
}

main();
