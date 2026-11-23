// Runs the parametric powder search off the main thread.
// Each powder is searched with its own fitted heat-loss scale (PowderCandidate does not carry one),
// so candidates are run one at a time and merged with the engine's ordering.
import { parametricSearch, type ParametricConstraints, type ParametricRow, type PowderCandidate } from '../engine/search';
import type { LoadSetup } from '../engine/types';

export interface SearchRequest {
  type: 'run';
  base: LoadSetup;
  candidates: PowderCandidate[];
  /** Heat-loss multiplier per candidate id (defaults to the base setup's). */
  heatScales: Record<string, number>;
  constraints: ParametricConstraints;
}

export type SearchMessage =
  | { type: 'progress'; done: number; total: number }
  | { type: 'done'; rows: ParametricRow[] }
  | { type: 'error'; message: string };

const post = (m: SearchMessage) => (self as unknown as Worker).postMessage(m);

self.onmessage = (e: MessageEvent<SearchRequest>) => {
  const req = e.data;
  if (req?.type !== 'run') return;
  try {
    const rows: ParametricRow[] = [];
    req.candidates.forEach((c, i) => {
      const scale = req.heatScales[c.id] ?? req.base.options.heatLoss.scale;
      const base: LoadSetup = { ...req.base, options: { ...req.base.options, heatLoss: { ...req.base.options.heatLoss, scale } } };
      rows.push(...parametricSearch(base, [c], req.constraints));
      post({ type: 'progress', done: i + 1, total: req.candidates.length });
    });
    rows.sort((a, b) => {
      if (a.passes !== b.passes) return a.passes ? -1 : 1;
      return (b.result.muzzleVelocityMs || 0) - (a.result.muzzleVelocityMs || 0);
    });
    post({ type: 'done', rows });
  } catch (err) {
    post({ type: 'error', message: err instanceof Error ? err.message : String(err) });
  }
};
