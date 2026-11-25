// Summarise held-out validation into src/data/model-constants.json (small file the Predict view can show).
import fs from 'node:fs';
import path from 'node:path';
import { findCartridge } from './build-data';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const rep = JSON.parse(fs.readFileSync(path.join(ROOT, 'src/data/validation-report.json'), 'utf8'));
const db = JSON.parse(fs.readFileSync(path.join(ROOT, 'src/data/db.json'), 'utf8'));
const PSI_PER_BAR = 14.503773773020923;
const signed: number[] = [];
const byClass = new Map<string, number[]>();
const heldCarts = new Map<string, string>();
for (const r of rep.rows as any[]) {
  if (!r.heldOut || r.pObs === null || r.pPredPsi === null) continue;
  const o = r.pObsUnit === 'psi' ? r.pObs : r.pObsUnit === 'bar' ? r.pObs * PSI_PER_BAR : null;
  if (o) {
    const e = (r.pPredPsi - o) / o;
    signed.push(e);
    if (typeof r.shotClass === 'string') (byClass.get(r.shotClass) ?? byClass.set(r.shotClass, []).get(r.shotClass)!).push(e);
    const c = findCartridge(db.cartridges, r.cartridge);
    if (c) heldCarts.set(c.id, c.name);
  }
}
const pct = (v: number) => Math.round(v * 1000) / 10;
/** n, median and 90th-percentile absolute error, mean signed error (bias), in percent. */
function stats(es: number[]) {
  const abs = es.map(Math.abs).sort((a, b) => a - b);
  const q = (f: number) => abs[Math.min(abs.length - 1, Math.floor(f * abs.length))];
  return { n: abs.length, p50: pct(q(0.5)), p90: pct(q(0.9)), bias: pct(es.reduce((s, v) => s + v, 0) / es.length), within10: Math.round((abs.filter((v) => v <= 0.1).length / abs.length) * 100) };
}
const all = stats(signed);
const summary = {
  heldOutPressureN: all.n,
  heldOutPressureP50Pct: all.p50,
  heldOutPressureP90Pct: all.p90,
  heldOutPressureBiasPct: all.bias,
  heldOutWithin10Pct: all.within10,
  // Per shot-start construction class (jacketed / monolithic / lead) of the bullet in each held-out row.
  byShotClass: Object.fromEntries([...byClass.entries()].sort().map(([k, es]) => {
    const s = stats(es);
    return [k, { n: s.n, p50Pct: s.p50, p90Pct: s.p90, biasPct: s.bias }];
  })),
  scope: `held-out pressure comparisons exist only for: ${[...new Set(heldCarts.values())].join(', ')}`,
  heldOutCartridgeIds: [...heldCarts.keys()],
  heldOutPowders: new Set((rep.rows as any[]).filter((r) => r.heldOut && r.pObs !== null && r.pObsUnit !== 'CUP').map((r) => r.powder)).size,
  generated: rep.generated,
};
const p = path.join(ROOT, 'src/data/model-constants.json');
const c = JSON.parse(fs.readFileSync(p, 'utf8'));
c.validation = summary;
fs.writeFileSync(p, JSON.stringify(c, null, 2));
console.log(summary);
