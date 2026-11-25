// Burn-rate-chart interpolation for powders that have no calibration.
// Charts are ordinal approximations, so these estimates carry a large uncertainty and are labelled
// "estimated — not for load development" everywhere in the app.

import type { BurnRateChart, Powder, PowderModelEntry } from '../src/data/schema';
import { priorParams } from '../src/engine/defaults';

/** Default 1-sigma relative uncertainty of an interpolated beta; replaced by the measured leave-one-out error when available. */
export const DEFAULT_ESTIMATE_BETA_SIGMA = 0.25;
const MAX_GAP = 15;

export function estimateFromCharts(
  powders: Powder[],
  charts: (BurnRateChart & { orderedNames?: string[] })[],
  betaRelSigma = DEFAULT_ESTIMATE_BETA_SIGMA,
): Record<string, PowderModelEntry> {
  const byId = new Map(powders.map((p) => [p.id, p]));
  const calibrated = (id: string) => {
    const m = byId.get(id)?.model;
    return m && m.status === 'calibrated' ? m : null;
  };
  const acc: Record<string, { logBeta: number[]; lambda: number[]; n: number[]; notes: string[] }> = {};
  for (const c of charts) {
    const ids = c.orderedPowderIds;
    ids.forEach((id, i) => {
      const p = byId.get(id);
      if (!p || calibrated(id)) return;
      let a = -1;
      let b = -1;
      for (let j = i - 1; j >= 0; j--) if (calibrated(ids[j])) { a = j; break; }
      for (let j = i + 1; j < ids.length; j++) if (calibrated(ids[j])) { b = j; break; }
      if (a < 0 || b < 0 || b - a > MAX_GAP) return;
      const ma = calibrated(ids[a])!;
      const mb = calibrated(ids[b])!;
      const t = (i - a) / (b - a);
      // Interpolate the burn rate at 100 MPa (beta·100^n), which is comparable across powders with different n.
      const r100 = (m: typeof ma) => Math.log(m.params.beta) + m.params.n * Math.log(100);
      const lb = r100(ma) * (1 - t) + r100(mb) * t;
      const nn = ma.params.n * (1 - t) + mb.params.n * t;
      const lam = ma.params.lambda * (1 - t) + mb.params.lambda * t;
      (acc[id] ??= { logBeta: [], lambda: [], n: [], notes: [] }).logBeta.push(lb);
      acc[id].lambda.push(lam);
      acc[id].n.push(nn);
      acc[id].notes.push(`between ${byId.get(ids[a])!.name} (#${a + 1}) and ${byId.get(ids[b])!.name} (#${b + 1}) on ${c.publisher} ${c.edition}`.trim());
    });
  }
  const out: Record<string, PowderModelEntry> = {};
  for (const [id, e] of Object.entries(acc)) {
    const p = byId.get(id)!;
    const logRate100 = e.logBeta.reduce((s, v) => s + v, 0) / e.logBeta.length;
    const lambda = e.lambda.reduce((s, v) => s + v, 0) / e.lambda.length;
    const n = e.n.reduce((s, v) => s + v, 0) / e.n.length;
    const logBeta = logRate100 - n * Math.log(100);
    out[id] = {
      status: 'estimated',
      params: { ...priorParams({ heatOfExplosionJg: p.heatOfExplosionJg ?? null, base: p.base, beta: Math.exp(logBeta), lambda }), n },
      betaRelSigma,
      derivation:
        `Burn rate interpolated by chart position ${e.notes.join('; ')}. Thermochemistry from class priors` +
        `${p.heatOfExplosionJg ? ` and the maker's published heat of explosion (${p.heatOfExplosionJg} J/g)` : ''}. ` +
        `Burn-rate charts are ordinal approximations: this estimate is NOT suitable for load development.`,
    };
  }
  return out;
}
