// Input-uncertainty propagation: Monte Carlo bands and one-at-a-time sensitivities.
// The spreads are ASSUMPTIONS the user can edit; the output is a sensitivity band under those
// assumptions, not a statistical confidence interval on real-world pressure.

import { simulate } from './model';
import type { LoadSetup } from './types';

export interface UncertaintySpec {
  /** 1-sigma relative spread of case capacity (brass lot / brand variation). */
  caseCapacityRel: number;
  /** 1-sigma relative spread of the powder burn-rate coefficient (lot-to-lot + model). */
  betaRel: number;
  /** 1-sigma relative spread of the powder energy (force). */
  forceRel: number;
  /** 1-sigma relative spread of shot-start pressure (neck tension, crimp, bullet construction). */
  shotStartRel: number;
  /** 1-sigma spread of seating depth, m. */
  seatingDepthM: number;
  /** 1-sigma spread of the thrown charge, kg. */
  chargeKg: number;
}

export const DEFAULT_SPEC_CALIBRATED: UncertaintySpec = {
  caseCapacityRel: 0.01,
  betaRel: 0.03,
  forceRel: 0.01,
  shotStartRel: 0.2,
  seatingDepthM: 0.0005,
  chargeKg: 0.1 * 64.79891e-6,
};

export const DEFAULT_SPEC_ESTIMATED: UncertaintySpec = {
  ...DEFAULT_SPEC_CALIBRATED,
  betaRel: 0.25,
  forceRel: 0.04,
};

function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function normalSampler(seed: number) {
  const rnd = mulberry32(seed);
  return () => {
    let u = 0;
    while (u === 0) u = rnd();
    const v = rnd();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  };
}

export function perturb(s: LoadSetup, d: { cap: number; beta: number; force: number; shot: number; seat: number; charge: number }): LoadSetup {
  return {
    ...s,
    caseCapacityM3: s.caseCapacityM3 * (1 + d.cap),
    coalM: s.coalM - d.seat, // deeper seating = shorter COAL
    chargeKg: Math.max(s.chargeKg + d.charge, 1e-7),
    propellant: {
      ...s.propellant,
      thermo: { ...s.propellant.thermo, forceJkg: s.propellant.thermo.forceJkg * (1 + d.force) },
      burn: { ...s.propellant.burn, // burn-rate spread is log-normal: model errors are multiplicative (review finding)
      beta: s.propellant.burn.beta * Math.exp(d.beta) },
    },
    options: {
      ...s.options,
      recordTrace: false,
      shotStartPressurePa: s.options.shotStartPressurePa * Math.max(0.05, 1 + d.shot),
    },
  };
}

export interface Band {
  p05: number;
  p50: number;
  p95: number;
}

export interface MonteCarloResult {
  peak: Band;
  velocity: Band;
  samples: number;
  failed: number;
}

const quantile = (sorted: number[], q: number) => {
  if (!sorted.length) return NaN;
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
};

export function monteCarlo(s: LoadSetup, spec: UncertaintySpec, n = 200, seed = 12345): MonteCarloResult {
  const z = normalSampler(seed);
  const peaks: number[] = [];
  const vels: number[] = [];
  let failed = 0;
  for (let i = 0; i < n; i++) {
    const r = simulate(
      perturb(s, {
        cap: z() * spec.caseCapacityRel,
        beta: z() * spec.betaRel,
        force: z() * spec.forceRel,
        shot: z() * spec.shotStartRel,
        seat: z() * spec.seatingDepthM,
        charge: z() * spec.chargeKg,
      }),
    );
    if (r.status !== 'muzzle') {
      failed++;
      if (Number.isFinite(r.peakBreechPa)) peaks.push(r.peakBreechPa);
      continue;
    }
    peaks.push(r.peakBreechPa);
    vels.push(r.muzzleVelocityMs);
  }
  peaks.sort((a, b) => a - b);
  vels.sort((a, b) => a - b);
  return {
    peak: { p05: quantile(peaks, 0.05), p50: quantile(peaks, 0.5), p95: quantile(peaks, 0.95) },
    velocity: { p05: quantile(vels, 0.05), p50: quantile(vels, 0.5), p95: quantile(vels, 0.95) },
    samples: n,
    failed,
  };
}

export interface Sensitivity {
  key: string;
  label: string;
  /** Change applied, in display terms. */
  change: string;
  peakPct: number;
  velocityPct: number;
}

/** One-at-a-time sensitivities around the nominal load (central differences). */
export function sensitivities(s: LoadSetup): Sensitivity[] {
  const base = simulate({ ...s, options: { ...s.options, recordTrace: false } });
  const zero = { cap: 0, beta: 0, force: 0, shot: 0, seat: 0, charge: 0 };
  const cases: { key: keyof typeof zero; label: string; change: string; delta: number }[] = [
    { key: 'charge', label: 'Charge', change: '+0.1 gr', delta: 0.1 * 64.79891e-6 },
    { key: 'cap', label: 'Case capacity', change: '−1 %', delta: -0.01 },
    { key: 'seat', label: 'Seating depth', change: '+0.010 in deeper', delta: 0.000254 },
    { key: 'beta', label: 'Powder burn rate', change: '+3 %', delta: 0.03 },
    { key: 'force', label: 'Powder energy', change: '+1 %', delta: 0.01 },
    { key: 'shot', label: 'Shot-start pressure', change: '+20 %', delta: 0.2 },
  ];
  return cases.map((c) => {
    const r = simulate(perturb(s, { ...zero, [c.key]: c.delta }));
    return {
      key: c.key,
      label: c.label,
      change: c.change,
      peakPct: ((r.peakBreechPa - base.peakBreechPa) / base.peakBreechPa) * 100,
      velocityPct: ((r.muzzleVelocityMs - base.muzzleVelocityMs) / base.muzzleVelocityMs) * 100,
    };
  });
}

/** Propellant-temperature sweep (uses the powder's temperature coefficient). */
export function temperatureSweep(s: LoadSetup, tempsC: number[]) {
  return tempsC.map((tc) => {
    const r = simulate({ ...s, propellantTempC: tc, options: { ...s.options, recordTrace: false } });
    return { tempC: tc, peakPa: r.peakBreechPa, velocityMs: r.muzzleVelocityMs, status: r.status };
  });
}

/** Typical elasticity of peak pressure to the burn-rate coefficient (median over shipped models at ~95 % of MAP, measured
 * in code review: 1.68, IQR 1.34–1.88). Used only when the caller cannot supply the load's own elasticity. */
export const DEFAULT_PRESSURE_PER_BETA = 1.7;
/** Pressure spread (1σ, relative) assumed when a model's pressure was never validated against measurements. */
export const UNVALIDATED_PRESSURE_SIGMA = 0.25;

/**
 * Default spreads for a powder model, sized from its measured error:
 *  - calibrated with pressure data: σP = max(in-sample RMS × 1.45, held-out median × 1.48);
 *  - calibrated or user-calibrated WITHOUT pressure data (velocity-only): σP = UNVALIDATED_PRESSURE_SIGMA;
 *  - estimated: the measured chart-interpolation error (already a burn-rate spread).
 * σP is converted to a burn-rate spread with the load's own elasticity d ln p / d ln β (from sensitivities()),
 * so the Monte Carlo band reproduces the intended pressure spread.
 */
export function specForPowderModel(
  m?: {
    status: string;
    betaRelSigma?: number;
    calibration?: { rmsPressurePct?: number | null; heldOutPressurePct?: number | null };
  } | null,
  pressurePerBeta: number = DEFAULT_PRESSURE_PER_BETA,
): UncertaintySpec {
  const k = Number.isFinite(pressurePerBeta) && pressurePerBeta > 0.2 ? pressurePerBeta : DEFAULT_PRESSURE_PER_BETA;
  if (!m) return DEFAULT_SPEC_ESTIMATED;
  if (m.status === 'estimated') return { ...DEFAULT_SPEC_ESTIMATED, betaRel: m.betaRelSigma && m.betaRelSigma > 0 ? m.betaRelSigma : DEFAULT_SPEC_ESTIMATED.betaRel };
  const rms = m.calibration?.rmsPressurePct;
  const held = m.calibration?.heldOutPressurePct;
  let sigmaP = UNVALIDATED_PRESSURE_SIGMA;
  if (typeof rms === 'number' && rms > 0) {
    sigmaP = Math.max((rms * 1.45) / 100, typeof held === 'number' && held > 0 ? (held * 1.48) / 100 : 0);
  }
  return { ...DEFAULT_SPEC_CALIBRATED, betaRel: Math.min(0.6, Math.max(0.03, sigmaP / k)) };
}
