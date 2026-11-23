// Bullet-length estimator. Used inside powder calibration for published loads whose bullet maker publishes no length,
// and shown in the app only as a clearly labelled starting estimate (never stored as data); the user enters a measured length.
//
// Model (log-linear, separate fits for pointed rifle bullets and blunt handgun-style bullets), fitted on bullets whose
// maker publishes the length:   ln L = a0 + a1·ln(weight) + a2·ln(diameter) + a3·mono + a4·flatBase + a5·tipped + a6·roundNose
// Its leave-one-out error is reported in the validation report.

import type { Bullet } from '../data/schema';

export interface LengthFeatures {
  diameterIn: number;
  weightGr: number;
  mono: boolean;
  flatBase: boolean;
  tipped: boolean;
  roundNose: boolean;
  /** Handgun-style blunt bullet (JHP/JSP/XTP/FMJ RN/wadcutter/straight-wall flat nose): modelled separately. */
  blunt: boolean;
}

// ln L = a0 + a1·ln(weight) + a2·ln(diameter) + offsets (a cylinder would have a1 = 1, a2 = −2; shape bends both).
const row = (f: LengthFeatures) => [1, Math.log(f.weightGr), Math.log(f.diameterIn), f.mono ? 1 : 0, f.flatBase ? 1 : 0, f.tipped ? 1 : 0, f.roundNose ? 1 : 0];

export function featuresFromText(diameterIn: number, weightGr: number, text: string, construction?: string | null, handgunCartridge = false): LengthFeatures {
  const t = `${text} ${construction ?? ''}`.toLowerCase();
  const blunt =
    handgunCartridge ||
    /handgun|\basp\b|jhp|jsp|wadcutter|\bwc\b|swc|straight[- ]wall|xtp|\bhap\b|\brn\b|round nose|flat nose|\bfn\b|\bfp\b|lrn|pistol|revolver|hollow cavity|jhc|sub-?x|ftx|flex ?tip|dgx|dgs|gold dot/.test(t);
  const mono = /monolithic|tsx|ttsx|lrx|\bcx\b|gmx|e-tip|etip|all[- ]copper|solid copper|lead[- ]free|tac-x|xpb|varmint grenade|hht|cutting edge|mono/.test(t);
  const tipped = /tip|eld|a-tip|sst|v-max|vmax|ballistic|tmk|tipped|accubond|ftx|ntx|scirocco|gamechanger|hybrid hunter|\btt/.test(t);
  const flatBase = /\bfb\b|flat[- ]?base|\bfn\b|flat nose|\brn\b|round nose|\bsp\b(?!.*bt)|interlock sp|jsp|jhp|xtp|fmj(?!.*bt)|lswc|swc|wc|lrn|cast|hp(?!bt)|jfp|rnfp|plinker/.test(t) && !/\bbt\b|boat[- ]?tail|hpbt|bthp|sbt|btsp|vld|eld|hybrid|scenar/.test(t);
  const roundNose = /\brn\b|round nose|rnfp|lrn|fmj rn/.test(t);
  return { diameterIn, weightGr, mono, flatBase, tipped, roundNose, blunt };
}

export function bulletFeatures(b: Bullet): LengthFeatures {
  return featuresFromText(b.diameterIn, b.weightGr, `${b.line} ${b.name} ${b.profile ?? ''} ${b.tip ?? ''}`, b.construction);
}

function solve(A: number[][], y: number[], ridge = 1e-6): number[] | null {
  const p = A[0].length;
  const M = Array.from({ length: p }, (_, i) => Array.from({ length: p }, (_, j) => A.reduce((s, r) => s + r[i] * r[j], 0) + (i === j ? ridge : 0)));
  const v = Array.from({ length: p }, (_, i) => A.reduce((s, r, k) => s + r[i] * y[k], 0));
  for (let c = 0; c < p; c++) {
    let piv = c;
    for (let r = c + 1; r < p; r++) if (Math.abs(M[r][c]) > Math.abs(M[piv][c])) piv = r;
    if (Math.abs(M[piv][c]) < 1e-12) return null;
    [M[c], M[piv]] = [M[piv], M[c]];
    [v[c], v[piv]] = [v[piv], v[c]];
    for (let r = c + 1; r < p; r++) {
      const f = M[r][c] / M[c][c];
      for (let k = c; k < p; k++) M[r][k] -= f * M[c][k];
      v[r] -= f * v[c];
    }
  }
  const x = new Array(p).fill(0);
  for (let r = p - 1; r >= 0; r--) {
    let s = v[r];
    for (let k = r + 1; k < p; k++) s -= M[r][k] * x[k];
    x[r] = s / M[r][r];
  }
  return x;
}

export interface LengthModel {
  n: number;
  /** Leave-one-out RMS relative error per class (pointed rifle bullets / blunt handgun-style bullets). */
  looRelRms: number;
  looRelRmsPointed: number | null;
  looRelRmsBlunt: number | null;
  /** Predicted length, or null when the bullet's class has no adequately accurate model. */
  predict: (f: LengthFeatures) => number | null;
}

interface ClassModel {
  coef: number[];
  n: number;
  loo: number;
}

function fitClass(bullets: Bullet[], feats: LengthFeatures[]): ClassModel | null {
  if (bullets.length < 15) return null;
  const A = feats.map(row);
  const y = bullets.map((b) => Math.log(b.lengthIn as number));
  const coef = solve(A, y, 1e-4);
  if (!coef) return null;
  let se = 0;
  for (let i = 0; i < bullets.length; i++) {
    const c = solve(A.filter((_, j) => j !== i), y.filter((_, j) => j !== i), 1e-4);
    if (!c) continue;
    const pred = Math.exp(A[i].reduce((s, v, k) => s + v * c[k], 0));
    se += ((pred - (bullets[i].lengthIn as number)) / (bullets[i].lengthIn as number)) ** 2;
  }
  return { coef, n: bullets.length, loo: Math.sqrt(se / bullets.length) };
}

/** Maximum leave-one-out error for a class model to be used at all. */
export const MAX_LENGTH_LOO = 0.08;

export function fitLengthModel(bullets: Bullet[]): LengthModel | null {
  const train = bullets.filter((b) => b.lengthIn && b.lengthIn > b.diameterIn && b.weightGr > 0);
  if (train.length < 20) return null;
  const feats = train.map(bulletFeatures);
  const pIdx = feats.map((f, i) => (f.blunt ? -1 : i)).filter((i) => i >= 0);
  const bIdx = feats.map((f, i) => (f.blunt ? i : -1)).filter((i) => i >= 0);
  const pointed = fitClass(pIdx.map((i) => train[i]), pIdx.map((i) => feats[i]));
  const blunt = fitClass(bIdx.map((i) => train[i]), bIdx.map((i) => feats[i]));
  const usable = (m: ClassModel | null) => (m && m.loo <= MAX_LENGTH_LOO ? m : null);
  const pick = (f: LengthFeatures) => usable(f.blunt ? blunt : pointed);
  const nTot = (pointed?.n ?? 0) + (blunt?.n ?? 0);
  const loo = Math.sqrt((((pointed?.loo ?? 0) ** 2) * (pointed?.n ?? 0) + ((blunt?.loo ?? 0) ** 2) * (blunt?.n ?? 0)) / Math.max(1, nTot));
  return {
    n: nTot,
    looRelRms: loo,
    looRelRmsPointed: pointed?.loo ?? null,
    looRelRmsBlunt: blunt?.loo ?? null,
    predict: (f) => {
      const m = pick(f);
      return m ? Math.exp(row(f).reduce((s, v, k) => s + v * m.coef[k], 0)) : null;
    },
  };
}
