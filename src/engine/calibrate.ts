// Fit propellant model parameters to measured data (chronograph velocities and/or published pressures).
// Levenberg–Marquardt on transformed parameters with a forward-difference Jacobian.

import { simulate } from './model';
import type { LoadSetup, PropellantModel } from './types';

export type FitParam = 'beta' | 'lambda' | 'force' | 'heat' | 'n';

export interface Observation {
  /** Full setup of the measured load (its `propellant` is replaced by the trial model during fitting). */
  setup: LoadSetup;
  velocityMs?: number;
  /** Peak chamber pressure (piezo), Pa. */
  peakPa?: number;
  label?: string;
}

export interface CalibrationInput {
  start: PropellantModel;
  /** Starting multiplier on the heat-loss coefficient. */
  startHeatScale?: number;
  observations: Observation[];
  params: FitParam[];
  /** Velocity residual scale (≈ expected measurement scatter), m/s. */
  sigmaVelocityMs: number;
  /** Pressure residual scale as a fraction (e.g. 0.04 = 4 %). */
  sigmaPressureRel: number;
  maxIterations?: number;
  /**
   * Weak priors (in the fitted, transformed space) that keep weakly identified parameters physical:
   * force/heat/n are log-scale relative to the start model, lambda is additive. Each adds a residual (x − center)/sigma.
   */
  priors?: Partial<Record<FitParam, { center: number; sigma: number }>>;
}

export interface ObservationFit {
  label?: string;
  velocityObsMs?: number;
  velocityPredMs: number;
  peakObsPa?: number;
  peakPredPa: number;
}

export interface CalibrationResult {
  model: PropellantModel;
  heatScale: number;
  fits: ObservationFit[];
  rmsVelocityMs: number | null;
  rmsPressureRel: number | null;
  iterations: number;
  converged: boolean;
  /** 1-sigma relative standard errors of fitted parameters (null when under-determined). */
  paramRelStdErr: Partial<Record<FitParam, number | null>>;
  degreesOfFreedom: number;
  warnings: string[];
}

const LAMBDA_MIN = -0.45;
const LAMBDA_MAX = 3;
const N_MIN = 0.3;
const N_MAX = 1.5;
/** Reference pressure (MPa) used to decorrelate beta and n while fitting: the burn rate at 100 MPa is held by beta. */
const P_REF_MPA = 100;

interface Decoded {
  model: PropellantModel;
  heatScale: number;
}

function decode(start: PropellantModel, startHeat: number, params: FitParam[], x: number[]): Decoded {
  const model: PropellantModel = {
    ...start,
    thermo: { ...start.thermo },
    burn: { ...start.burn },
  };
  let heatScale = startHeat;
  const iN = params.indexOf('n');
  const iB = params.indexOf('beta');
  if (iN >= 0) {
    // Fit n with the burn rate at P_REF held by beta: beta·P_REF^n is the decorrelated rate parameter.
    const n = Math.min(N_MAX, Math.max(N_MIN, start.burn.n * Math.exp(x[iN])));
    const rateRef = start.burn.beta * Math.pow(P_REF_MPA, start.burn.n) * (iB >= 0 ? Math.exp(x[iB]) : 1);
    model.burn.n = n;
    model.burn.beta = rateRef / Math.pow(P_REF_MPA, n);
  }
  params.forEach((p, i) => {
    switch (p) {
      case 'n':
        break;
      case 'beta':
        if (iN < 0) model.burn.beta = start.burn.beta * Math.exp(x[i]);
        break;
      case 'lambda':
        model.burn.lambda = Math.min(LAMBDA_MAX, Math.max(LAMBDA_MIN, start.burn.lambda + x[i]));
        break;
      case 'force':
        model.thermo.forceJkg = start.thermo.forceJkg * Math.exp(x[i]);
        break;
      case 'heat':
        heatScale = startHeat * Math.exp(x[i]);
        break;
    }
  });
  return { model, heatScale };
}

function predict(obs: Observation, d: Decoded) {
  const s = obs.setup;
  return simulate({
    ...s,
    propellant: { ...d.model, bulkDensityKgM3: s.propellant.bulkDensityKgM3 ?? d.model.bulkDensityKgM3 },
    options: { ...s.options, recordTrace: false, heatLoss: { ...s.options.heatLoss, scale: d.heatScale } },
  });
}

function residuals(inp: CalibrationInput, d: Decoded): number[] {
  const out: number[] = [];
  for (const o of inp.observations) {
    const r = predict(o, d);
    const v = r.status === 'muzzle' ? r.muzzleVelocityMs : 0;
    const p = Number.isFinite(r.peakBreechPa) ? r.peakBreechPa : 1e10;
    if (o.velocityMs !== undefined) out.push((v - o.velocityMs) / inp.sigmaVelocityMs);
    if (o.peakPa !== undefined) out.push((p - o.peakPa) / (o.peakPa * inp.sigmaPressureRel));
  }
  return out;
}

const sumSq = (r: number[]) => r.reduce((a, b) => a + b * b, 0);

function withPriors(inp: CalibrationInput, params: FitParam[], x: number[], r: number[]): number[] {
  if (!inp.priors) return r;
  const out = r.slice();
  params.forEach((p, i) => {
    const pr = inp.priors![p];
    if (pr && pr.sigma > 0) out.push((x[i] - pr.center) / pr.sigma);
  });
  return out;
}

function solveLinear(Ain: number[][], bin: number[]): number[] | null {
  const n = bin.length;
  const A = Ain.map((r) => r.slice());
  const b = bin.slice();
  for (let c = 0; c < n; c++) {
    let piv = c;
    for (let r = c + 1; r < n; r++) if (Math.abs(A[r][c]) > Math.abs(A[piv][c])) piv = r;
    if (Math.abs(A[piv][c]) < 1e-14) return null;
    [A[c], A[piv]] = [A[piv], A[c]];
    [b[c], b[piv]] = [b[piv], b[c]];
    for (let r = c + 1; r < n; r++) {
      const f = A[r][c] / A[c][c];
      for (let k = c; k < n; k++) A[r][k] -= f * A[c][k];
      b[r] -= f * b[c];
    }
  }
  const x = new Array(n).fill(0);
  for (let r = n - 1; r >= 0; r--) {
    let s = b[r];
    for (let k = r + 1; k < n; k++) s -= A[r][k] * x[k];
    x[r] = s / A[r][r];
  }
  return x;
}

function invert(A: number[][]): number[][] | null {
  const n = A.length;
  const cols: number[][] = [];
  for (let i = 0; i < n; i++) {
    const e = new Array(n).fill(0);
    e[i] = 1;
    const c = solveLinear(A, e);
    if (!c) return null;
    cols.push(c);
  }
  return A.map((_, r) => cols.map((c) => c[r]));
}

/** Coarse log-scan of beta so LM starts near the basin (pressure is very sensitive to beta). */
function presetBeta(inp: CalibrationInput, startHeat: number): PropellantModel {
  let best = inp.start;
  let bestCost = Infinity;
  for (let k = -24; k <= 24; k++) {
    const factor = Math.pow(1.15, k);
    const trial: PropellantModel = { ...inp.start, burn: { ...inp.start.burn, beta: inp.start.burn.beta * factor } };
    const cost = sumSq(residuals({ ...inp, start: trial }, { model: trial, heatScale: startHeat }));
    if (cost < bestCost) {
      bestCost = cost;
      best = trial;
    }
  }
  return best;
}

export function calibrate(inp: CalibrationInput): CalibrationResult {
  const warnings: string[] = [];
  const startHeat = inp.startHeatScale ?? 1;
  const nRes = inp.observations.reduce((a, o) => a + (o.velocityMs !== undefined ? 1 : 0) + (o.peakPa !== undefined ? 1 : 0), 0);
  let params = inp.params.slice();
  if (params.length > nRes) {
    warnings.push(`Only ${nRes} measurement(s) for ${params.length} parameter(s); fitting the first ${nRes} only.`);
    params = params.slice(0, Math.max(1, nRes));
  }
  const start = params.includes('beta') ? presetBeta(inp, startHeat) : inp.start;
  const P = params.length;
  let x = new Array(P).fill(0);
  let d = decode(start, startHeat, params, x);
  let r = withPriors(inp, params, x, residuals(inp, d));
  let cost = sumSq(r);
  let mu = 1e-3;
  let it = 0;
  let converged = false;
  let JtJ: number[][] = [];
  const maxIt = inp.maxIterations ?? 40;
  for (; it < maxIt; it++) {
    // Jacobian
    const J: number[][] = r.map(() => new Array(P).fill(0));
    for (let j = 0; j < P; j++) {
      const hstep = 1e-4;
      const xp = x.slice();
      xp[j] += hstep;
      const rp = withPriors(inp, params, xp, residuals(inp, decode(start, startHeat, params, xp)));
      for (let i = 0; i < r.length; i++) J[i][j] = (rp[i] - r[i]) / hstep;
    }
    JtJ = Array.from({ length: P }, (_, a) => Array.from({ length: P }, (_, b) => J.reduce((s, row) => s + row[a] * row[b], 0)));
    const Jtr = Array.from({ length: P }, (_, a) => J.reduce((s, row, i) => s + row[a] * r[i], 0));
    let improved = false;
    for (let tries = 0; tries < 12; tries++) {
      const Aug = JtJ.map((row, a) => row.map((v, b) => (a === b ? v * (1 + mu) + 1e-12 : v)));
      const delta = solveLinear(Aug, Jtr.map((v) => -v));
      if (!delta) {
        mu *= 10;
        continue;
      }
      // limit step size in transformed space
      const maxStep = Math.max(...delta.map(Math.abs));
      const scale = maxStep > 0.7 ? 0.7 / maxStep : 1;
      const xn = x.map((v, i) => v + delta[i] * scale);
      const dn = decode(start, startHeat, params, xn);
      const rn = withPriors(inp, params, xn, residuals(inp, dn));
      const cn = sumSq(rn);
      if (cn < cost) {
        const rel = (cost - cn) / Math.max(cost, 1e-30);
        x = xn;
        d = dn;
        r = rn;
        cost = cn;
        mu = Math.max(mu / 3, 1e-9);
        improved = true;
        if (rel < 1e-9 || cost < 1e-12) converged = true;
        break;
      }
      mu *= 8;
    }
    if (!improved) {
      converged = true;
      break;
    }
    if (converged) break;
  }

  const dof = nRes - P;
  const paramRelStdErr: CalibrationResult['paramRelStdErr'] = {};
  const inv = dof > 0 ? invert(JtJ) : null;
  params.forEach((p, i) => {
    if (!inv) {
      paramRelStdErr[p] = null;
      return;
    }
    const s2 = cost / dof;
    const sd = Math.sqrt(Math.max(inv[i][i] * s2, 0));
    // log-parametrised quantities: sd in log space ≈ relative sd; lambda is additive
    paramRelStdErr[p] = p === 'lambda' ? sd : sd;
  });
  if (dof <= 0) warnings.push('No spare degrees of freedom: the fit passes through the data exactly and its uncertainty is unknown. Add more charge weights or pressure data.');

  const fits: ObservationFit[] = inp.observations.map((o) => {
    const res = predict(o, d);
    return {
      label: o.label,
      velocityObsMs: o.velocityMs,
      velocityPredMs: res.muzzleVelocityMs,
      peakObsPa: o.peakPa,
      peakPredPa: res.peakBreechPa,
    };
  });
  const vRes = fits.filter((f) => f.velocityObsMs !== undefined).map((f) => f.velocityPredMs - (f.velocityObsMs as number));
  const pRes = fits.filter((f) => f.peakObsPa !== undefined).map((f) => (f.peakPredPa - (f.peakObsPa as number)) / (f.peakObsPa as number));
  const rms = (a: number[]) => (a.length ? Math.sqrt(a.reduce((s, v) => s + v * v, 0) / a.length) : null);
  return {
    model: d.model,
    heatScale: d.heatScale,
    fits,
    rmsVelocityMs: rms(vRes),
    rmsPressureRel: rms(pRes),
    iterations: it,
    converged,
    paramRelStdErr,
    degreesOfFreedom: dof,
    warnings,
  };
}
