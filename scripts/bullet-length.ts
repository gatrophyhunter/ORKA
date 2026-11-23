// Bullet-length estimator used ONLY inside powder calibration, for published loads whose bullet maker does not
// publish lengths (e.g. Hornady, Sierra product pages). Never shipped as data: the app asks the user to measure.
//
// Model (log-linear in sectional density, with construction / profile offsets), fitted on bullets whose maker
// publishes the length:   ln(L/d) = a0 + a1·ln(SD) + a2·mono + a3·flatBase + a4·tipped + a5·roundNose
// Its leave-one-out error is reported in the validation report.

import type { Bullet } from '../src/data/schema';

export interface LengthFeatures {
  diameterIn: number;
  weightGr: number;
  mono: boolean;
  flatBase: boolean;
  tipped: boolean;
  roundNose: boolean;
}

const sd = (f: LengthFeatures) => f.weightGr / 7000 / (f.diameterIn * f.diameterIn);
const row = (f: LengthFeatures) => [1, Math.log(sd(f)), f.mono ? 1 : 0, f.flatBase ? 1 : 0, f.tipped ? 1 : 0, f.roundNose ? 1 : 0];

export function featuresFromText(diameterIn: number, weightGr: number, text: string, construction?: string | null): LengthFeatures {
  const t = `${text} ${construction ?? ''}`.toLowerCase();
  const mono = /monolithic|tsx|ttsx|lrx|\bcx\b|gmx|e-tip|etip|all[- ]copper|solid copper|lead[- ]free|tac-x|xpb|varmint grenade|hht|cutting edge|mono/.test(t);
  const tipped = /tip|eld|a-tip|sst|v-max|vmax|ballistic|tmk|tipped|accubond|ftx|ntx|scirocco|gamechanger|hybrid hunter|\btt/.test(t);
  const flatBase = /\bfb\b|flat[- ]?base|\bfn\b|flat nose|\brn\b|round nose|\bsp\b(?!.*bt)|interlock sp|jsp|jhp|xtp|fmj(?!.*bt)|lswc|swc|wc|lrn|cast|hp(?!bt)|jfp|rnfp|plinker/.test(t) && !/\bbt\b|boat[- ]?tail|hpbt|bthp|sbt|btsp|vld|eld|hybrid|scenar/.test(t);
  const roundNose = /\brn\b|round nose|rnfp|lrn|fmj rn/.test(t);
  return { diameterIn, weightGr, mono, flatBase, tipped, roundNose };
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
  coef: number[];
  n: number;
  /** Leave-one-out RMS relative error of length. */
  looRelRms: number;
  predict: (f: LengthFeatures) => number;
}

export function fitLengthModel(bullets: Bullet[]): LengthModel | null {
  const train = bullets.filter((b) => b.lengthIn && b.lengthIn > b.diameterIn && b.weightGr > 0);
  if (train.length < 20) return null;
  const feats = train.map(bulletFeatures);
  const A = feats.map(row);
  const y = train.map((b) => Math.log((b.lengthIn as number) / b.diameterIn));
  const coef = solve(A, y);
  if (!coef) return null;
  // Leave-one-out via refits (n is small enough).
  let se = 0;
  for (let i = 0; i < train.length; i++) {
    const c = solve(A.filter((_, j) => j !== i), y.filter((_, j) => j !== i));
    if (!c) continue;
    const pred = Math.exp(A[i].reduce((s, v, k) => s + v * c[k], 0)) * train[i].diameterIn;
    se += ((pred - (train[i].lengthIn as number)) / (train[i].lengthIn as number)) ** 2;
  }
  const predict = (f: LengthFeatures) => Math.exp(row(f).reduce((s, v, k) => s + v * coef[k], 0)) * f.diameterIn;
  return { coef, n: train.length, looRelRms: Math.sqrt(se / train.length), predict };
}
