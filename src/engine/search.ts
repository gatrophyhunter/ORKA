// Charge solvers, ladders and the parametric powder search.

import { simulate } from './model';
import type { LoadSetup, PropellantModel, SimResult } from './types';

export interface ChargeSolveOptions {
  /** Largest fill ratio (bulk powder volume / chamber volume) allowed; 1.0 = full to bullet base. */
  maxFillRatio: number;
  /** Absolute charge tolerance, kg. */
  tolKg: number;
}

export const DEFAULT_SOLVE: ChargeSolveOptions = { maxFillRatio: 1.1, tolKg: 1e-6 };

export type LimitReason = 'pressure' | 'fill' | 'fit' | 'velocity' | 'no-solution';

export interface ChargeSolution {
  chargeKg: number;
  result: SimResult;
  limitedBy: LimitReason;
  /** Iterations used by the bisection. */
  iterations: number;
}

const withCharge = (s: LoadSetup, chargeKg: number): LoadSetup => ({ ...s, chargeKg });

/** Upper bound on charge from physical fit (solid volume) and the fill-ratio limit. */
export function maxChargeByVolume(s: LoadSetup, maxFillRatio: number): { kg: number; reason: 'fill' | 'fit' } {
  const probe = simulate({ ...withCharge(s, 1e-6), options: { ...s.options, recordTrace: false } });
  const V0 = probe.chamberVolumeM3;
  // Physical fit: solid grains must fit, and the burnt gas's covolume must leave free volume (Noble-Abel).
  const eta = s.propellant.thermo.covolumeM3kg;
  const solidLimit = Math.min(0.98 * V0 * s.propellant.thermo.solidDensityKgM3, eta > 0 ? (0.95 * V0) / eta : Infinity);
  const bulk = s.propellant.bulkDensityKgM3;
  if (bulk && bulk > 0) {
    const fillLimit = maxFillRatio * V0 * bulk;
    if (fillLimit < solidLimit) return { kg: fillLimit, reason: 'fill' };
  }
  return { kg: solidLimit, reason: 'fit' };
}

/** Peak used by the solvers. Anything that is not a finite, trustworthy peak counts as over the limit (conservative). */
const peakOf = (r: SimResult) => {
  if (r.status === 'muzzle' || r.status === 'stuck') return Number.isFinite(r.peakBreechPa) ? r.peakBreechPa : Infinity;
  return Infinity;
};

/**
 * Find the charge whose predicted peak breech pressure equals `targetPa`.
 * Peak pressure rises monotonically with charge in this model, so bisection is safe.
 */
export function solveChargeForPressure(
  s: LoadSetup,
  targetPa: number,
  opt: ChargeSolveOptions = DEFAULT_SOLVE,
): ChargeSolution {
  const cap = maxChargeByVolume(s, opt.maxFillRatio);
  const quiet = { ...s.options, recordTrace: false };
  const hiRes = simulate({ ...s, chargeKg: cap.kg, options: quiet });
  if (peakOf(hiRes) <= targetPa) {
    return { chargeKg: cap.kg, result: simulate(withCharge(s, cap.kg)), limitedBy: cap.reason, iterations: 0 };
  }
  let lo = cap.kg * 0.02;
  let hi = cap.kg;
  const loRes = simulate({ ...s, chargeKg: lo, options: quiet });
  if (peakOf(loRes) > targetPa) {
    // Even the smallest charge searched exceeds the target (e.g. a limit below the shot-start pressure).
    return { chargeKg: 0, result: simulate(withCharge(s, lo)), limitedBy: 'no-solution', iterations: 0 };
  }
  let it = 0;
  while (hi - lo > opt.tolKg && it < 60) {
    it++;
    const mid = 0.5 * (lo + hi);
    const r = simulate({ ...s, chargeKg: mid, options: quiet });
    if (peakOf(r) > targetPa) hi = mid;
    else lo = mid;
  }
  return { chargeKg: lo, result: simulate(withCharge(s, lo)), limitedBy: 'pressure', iterations: it };
}

/** Find the charge that gives `targetMs` muzzle velocity (ignores pressure; caller must check). */
export function solveChargeForVelocity(
  s: LoadSetup,
  targetMs: number,
  opt: ChargeSolveOptions = DEFAULT_SOLVE,
): ChargeSolution | null {
  const cap = maxChargeByVolume(s, opt.maxFillRatio);
  const quiet = { ...s.options, recordTrace: false };
  let top = cap.kg;
  let topRes = simulate({ ...s, chargeKg: top, options: quiet });
  if (topRes.status !== 'muzzle') {
    // Find the largest charge that still gives a valid muzzle exit (velocity is only defined there).
    let a = cap.kg * 0.02;
    let b = cap.kg;
    for (let i = 0; i < 40 && b - a > opt.tolKg; i++) {
      const mid = 0.5 * (a + b);
      if (simulate({ ...s, chargeKg: mid, options: quiet }).status === 'muzzle') a = mid;
      else b = mid;
    }
    top = a;
    topRes = simulate({ ...s, chargeKg: top, options: quiet });
  }
  if (!(topRes.muzzleVelocityMs >= targetMs)) return null;
  let lo = cap.kg * 0.02;
  let hi = top;
  let it = 0;
  while (hi - lo > opt.tolKg && it < 60) {
    it++;
    const mid = 0.5 * (lo + hi);
    const r = simulate({ ...s, chargeKg: mid, options: quiet });
    const v = r.status === 'muzzle' ? r.muzzleVelocityMs : 0;
    if (v > targetMs) hi = mid;
    else lo = mid;
  }
  return { chargeKg: hi, result: simulate(withCharge(s, hi)), limitedBy: 'velocity', iterations: it };
}

export interface LadderRow {
  chargeKg: number;
  result: SimResult;
  /** Peak pressure as a fraction of the limit. */
  pressureRatio: number;
  overLimit: boolean;
}

/** Charge ladder from startKg to endKg in `steps` equal increments. */
export function ladder(s: LoadSetup, startKg: number, endKg: number, steps: number, limitPa: number): LadderRow[] {
  const rows: LadderRow[] = [];
  const n = Math.max(1, Math.round(steps));
  for (let i = 0; i <= n; i++) {
    const c = startKg + ((endKg - startKg) * i) / n;
    const r = simulate({ ...s, chargeKg: c, options: { ...s.options, recordTrace: false } });
    const ratio = r.peakBreechPa / limitPa;
    rows.push({ chargeKg: c, result: r, pressureRatio: ratio, overLimit: !(ratio <= 1) });
  }
  return rows;
}

export interface PowderCandidate {
  id: string;
  label: string;
  model: PropellantModel;
  /** Provenance of the model parameters — surfaced in results so users see what they are trusting. */
  status: 'calibrated' | 'user-calibrated' | 'estimated';
  /** Heat-loss multiplier fitted together with this powder (default 1). */
  heatScale?: number;
}

export interface ParametricConstraints {
  /** Pressure limit, Pa (already including any safety margin). */
  pressureLimitPa: number;
  maxFillRatio: number;
  /** Minimum fraction of powder burnt at the muzzle (0..1). */
  minBurnt: number;
  /** Minimum fill ratio (very low fill ratios give erratic ignition / position sensitivity). */
  minFillRatio: number;
  /** Optional target velocity, m/s: candidates are also solved for the charge giving it. */
  targetVelocityMs?: number;
}

export interface ParametricRow {
  candidate: PowderCandidate;
  chargeKg: number;
  limitedBy: LimitReason;
  result: SimResult;
  passes: boolean;
  reasons: string[];
  /** If a target velocity was given: charge and pressure needed to reach it (null if unreachable within limits). */
  atTarget?: { chargeKg: number; peakPa: number; fillRatio: number | null } | null;
}

/**
 * GRT-style parametric search: for each powder, find the largest charge allowed by the pressure limit and
 * the fill limit, then report velocity, burn completion and fill so powders can be compared on equal terms.
 */
export function parametricSearch(
  base: LoadSetup,
  candidates: PowderCandidate[],
  c: ParametricConstraints,
  onProgress?: (done: number, total: number) => void,
): ParametricRow[] {
  const rows: ParametricRow[] = [];
  const quietBase: LoadSetup = { ...base, options: { ...base.options, recordTrace: false, rtol: Math.max(base.options.rtol, 1e-6) } };
  candidates.forEach((cand, i) => {
    const s: LoadSetup = {
      ...quietBase,
      propellant: cand.model,
      options: { ...quietBase.options, heatLoss: { ...quietBase.options.heatLoss, scale: cand.heatScale ?? quietBase.options.heatLoss.scale } },
    };
    const sol = solveChargeForPressure(s, c.pressureLimitPa, { maxFillRatio: c.maxFillRatio, tolKg: 2e-6 });
    const r = sol.result;
    const reasons: string[] = [];
    if (sol.limitedBy === 'no-solution') reasons.push('no charge satisfies the pressure limit');
    if (r.status !== 'muzzle') reasons.push(`simulation: ${r.status}`);
    if (r.burntAtMuzzle < c.minBurnt) reasons.push(`only ${(r.burntAtMuzzle * 100).toFixed(0)} % burnt at muzzle`);
    if (r.fillRatio !== null && r.fillRatio < c.minFillRatio) reasons.push(`fill ${(r.fillRatio * 100).toFixed(0)} % below minimum`);
    if (r.fillRatio === null) reasons.push('bulk density unknown — fill ratio not checked');
    let atTarget: ParametricRow['atTarget'];
    if (c.targetVelocityMs) {
      const tv = solveChargeForVelocity(s, c.targetVelocityMs, { maxFillRatio: c.maxFillRatio, tolKg: 2e-6 });
      atTarget = tv && tv.result.peakBreechPa <= c.pressureLimitPa
        ? { chargeKg: tv.chargeKg, peakPa: tv.result.peakBreechPa, fillRatio: tv.result.fillRatio }
        : null;
      if (atTarget === null) reasons.push('cannot reach target velocity within limits');
    }
    const hard = reasons.filter((x) => !x.startsWith('bulk density unknown'));
    rows.push({ candidate: cand, chargeKg: sol.chargeKg, limitedBy: sol.limitedBy, result: r, passes: hard.length === 0, reasons, atTarget });
    onProgress?.(i + 1, candidates.length);
  });
  rows.sort((a, b) => {
    if (a.passes !== b.passes) return a.passes ? -1 : 1;
    return (b.result.muzzleVelocityMs || 0) - (a.result.muzzleVelocityMs || 0);
  });
  return rows;
}
