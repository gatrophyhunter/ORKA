// Summarise held-out validation into src/data/model-constants.json (small file the Predict view can show).
import fs from 'node:fs';
import path from 'node:path';
import { findCartridge } from './build-data';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const rep = JSON.parse(fs.readFileSync(path.join(ROOT, 'src/data/validation-report.json'), 'utf8'));
const db = JSON.parse(fs.readFileSync(path.join(ROOT, 'src/data/db.json'), 'utf8'));
const PSI_PER_BAR = 14.503773773020923;
const signed: number[] = [];
const heldCarts = new Map<string, string>();
for (const r of rep.rows as any[]) {
  if (!r.heldOut || r.pObs === null || r.pPredPsi === null) continue;
  const o = r.pObsUnit === 'psi' ? r.pObs : r.pObsUnit === 'bar' ? r.pObs * PSI_PER_BAR : null;
  if (o) {
    signed.push((r.pPredPsi - o) / o);
    const c = findCartridge(db.cartridges, r.cartridge);
    if (c) heldCarts.set(c.id, c.name);
  }
}
const abs = signed.map(Math.abs).sort((a, b) => a - b);
const q = (f: number) => abs[Math.min(abs.length - 1, Math.floor(f * abs.length))];
const summary = {
  heldOutPressureN: abs.length,
  heldOutPressureP50Pct: Math.round(q(0.5) * 1000) / 10,
  heldOutPressureP90Pct: Math.round(q(0.9) * 1000) / 10,
  heldOutPressureBiasPct: Math.round((signed.reduce((s, v) => s + v, 0) / signed.length) * 1000) / 10,
  heldOutWithin10Pct: Math.round((abs.filter((v) => v <= 0.1).length / abs.length) * 100),
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
