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
import { calibrate, type FitParam, type Observation } from '../src/engine/calibrate';
import { simulate } from '../src/engine/model';
import { propellantFromParams, paramsFromPropellant, toSetup, type LoadInputs } from '../src/engine/adapter';
import { defaultShotStartPsi, priorParams } from '../src/engine/defaults';
import * as U from '../src/engine/units';
import type { Bullet, Cartridge, Database, Powder, PowderModelEntry, ValidationLoad } from '../src/data/schema';
import { estimateFromCharts } from './estimate';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const db: Database = JSON.parse(fs.readFileSync(path.join(ROOT, 'src/data/db.json'), 'utf8'));

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
    setup: toSetup(r.inputs, start),
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
  return simulate(toSetup(r.inputs, prop, {}, model.heatScale));
}

function main() {
  const prepared = db.validationLoads.map(prepare).filter((x): x is Prepared => x !== null);
  const byPowder = new Map<string, Prepared[]>();
  for (const r of prepared) {
    if (!r.load.powderId) {
      skip('powder not matched to database');
      continue;
    }
    byPowder.set(r.load.powderId, [...(byPowder.get(r.load.powderId) ?? []), r]);
  }

  const models: Record<string, PowderModelEntry> = {};
  const rows: any[] = [];
  const heldOutV: number[] = [];
  const heldOutP: number[] = [];
  const inSampleV: number[] = [];
  const inSampleP: number[] = [];

  for (const [pid, prs] of byPowder) {
    const p = db.powders.find((x) => x.id === pid)!;
    const fit = fitPowder(p, prs);
    const cartridges = [...new Set(prs.map((r) => r.cartridgeId))];
    models[pid] = {
      status: 'calibrated',
      params: paramsFromPropellant(fit.model, fit.heatScale),
      derivation:
        `Fitted to ${prs.length} published pressure-tested load(s) (${cartridges.join(', ')}). ` +
        `Fitted: ${['beta', prs.length >= 3 ? 'lambda' : null, prs.length >= 4 && prs.filter((r) => r.peakPa !== undefined).length >= 2 ? 'force' : null].filter(Boolean).join(', ')}; ` +
        `other thermochemistry from class priors${p.heatOfExplosionJg ? ` and the maker's heat of explosion (${p.heatOfExplosionJg} J/g)` : ''}. ` +
        `${fit.warnings.join(' ')}`.trim(),
      calibration: {
        points: prs.length,
        rmsVelocityFps: fit.rmsVelocityMs === null ? null : U.msToFps(fit.rmsVelocityMs),
        rmsPressurePct: fit.rmsPressureRel === null ? null : fit.rmsPressureRel * 100,
        cartridges,
        sources: [...new Set(prs.flatMap((r) => r.load.sources.map((s) => s.url)))],
        chargeRangeGr: [Math.min(...prs.map((r) => r.load.chargeGr)), Math.max(...prs.map((r) => r.load.chargeGr))],
      },
    };
    // In-sample rows
    for (const r of prs) {
      const res = predict(fit, r, p.bulkDensityGcc);
      inSampleV.push(U.msToFps(res.muzzleVelocityMs) - r.load.velocityFps);
      if (r.peakPa) inSampleP.push((res.peakBreechPa - r.peakPa) / r.peakPa);
    }
    // Leave-one-cartridge-out
    if (cartridges.length >= 2) {
      for (const cid of cartridges) {
        const train = prs.filter((r) => r.cartridgeId !== cid);
        const test = prs.filter((r) => r.cartridgeId === cid);
        const f2 = fitPowder(p, train);
        for (const r of test) {
          const res = predict(f2, r, p.bulkDensityGcc);
          const vPred = U.msToFps(res.muzzleVelocityMs);
          heldOutV.push(vPred - r.load.velocityFps);
          if (r.peakPa) heldOutP.push((res.peakBreechPa - r.peakPa) / r.peakPa);
          rows.push({
            label: r.label,
            cartridge: r.load.cartridge,
            powder: p.name,
            chargeGr: r.load.chargeGr,
            velObsFps: r.load.velocityFps,
            velPredFps: Math.round(vPred),
            pObs: r.load.pressure,
            pObsUnit: r.load.pressureUnit,
            pPredPsi: Number.isFinite(res.peakBreechPa) ? Math.round(U.paToPsi(res.peakBreechPa)) : null,
            heldOut: true,
            notes: r.notes.join('; '),
          });
        }
      }
    }
    for (const r of prs) {
      const res = predict(fit, r, p.bulkDensityGcc);
      rows.push({
        label: r.label,
        cartridge: r.load.cartridge,
        powder: p.name,
        chargeGr: r.load.chargeGr,
        velObsFps: r.load.velocityFps,
        velPredFps: Math.round(U.msToFps(res.muzzleVelocityMs)),
        pObs: r.load.pressure,
        pObsUnit: r.load.pressureUnit,
        pPredPsi: Number.isFinite(res.peakBreechPa) ? Math.round(U.paToPsi(res.peakBreechPa)) : null,
        heldOut: false,
        notes: r.notes.join('; '),
      });
    }
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
  const report = {
    generated: new Date().toISOString(),
    metrics: {
      points: rows.filter((r) => r.heldOut).length,
      velocityMaeFps: mae(heldOutV),
      velocityMapePct: null as number | null,
      pressureMapePct: heldOutP.length ? (mae(heldOutP) as number) * 100 : null,
      notes:
        `Held-out = leave-one-cartridge-out: the powder is refitted without that cartridge's loads and then predicts them. ` +
        `${heldOutV.length} held-out velocity and ${heldOutP.length} held-out pressure comparisons over ${[...byPowder.keys()].length} powders. ` +
        `In-sample (all data fitted): velocity MAE ${mae(inSampleV)?.toFixed(0) ?? '—'} fps, pressure MAPE ${inSampleP.length ? ((mae(inSampleP) as number) * 100).toFixed(1) : '—'} %. ` +
        `Chart-interpolation check (calibrated powders re-estimated from chart neighbours): ${rmsLog === null ? 'too few powders to measure' : `RMS burn-rate error ${(rmsLog * 100).toFixed(0)} % over ${interpErr.length} powders`}. ` +
        `Loads skipped: ${JSON.stringify(skipped)}.`,
      interpolationBetaRelSigma: rmsLog,
    },
    rows,
  };
  fs.writeFileSync(path.join(ROOT, 'src/data/powder-models.json'), JSON.stringify({ generated: report.generated, models }, null, 1));
  fs.writeFileSync(path.join(ROOT, 'src/data/validation-report.json'), JSON.stringify(report, null, 1));
  console.log(JSON.stringify({ powdersCalibrated: Object.keys(models).length, prepared: prepared.length, skipped, metrics: report.metrics }, null, 2));
}

main();
