import { describe, it, expect } from 'vitest';
import { fitLengthModel, featuresFromText } from '../scripts/bullet-length';
import type { Bullet } from '../src/data/schema';

const mk = (d: number, w: number, mono: boolean, fb: boolean): Bullet => {
  const L = Math.exp(-1.5 + 0.45 * Math.log(w) - 0.6 * Math.log(d) + (mono ? 0.12 : 0) + (fb ? -0.08 : 0));
  return { id: `${d}-${w}-${mono}-${fb}`, manufacturer: 'TestCo', line: fb ? 'FB Target' : 'BT', name: mono ? 'TSX' : fb ? 'HP' : 'HPBT', diameterIn: d, weightGr: w, lengthIn: L, bcG1: null, bcG7: null, status: 'current', sources: [] };
};

describe('bullet length estimator', () => {
  it('recovers a synthetic log-linear relation with small leave-one-out error', () => {
    const bs: Bullet[] = [];
    for (const d of [0.224, 0.243, 0.264, 0.284, 0.308, 0.338])
      for (const sdT of [0.18, 0.22, 0.26, 0.3])
        for (const mono of [false, true]) for (const fb of [false, true]) bs.push(mk(d, sdT * 7000 * d * d, mono, fb));
    const m = fitLengthModel(bs)!;
    expect(m.looRelRmsPointed!).toBeLessThan(0.005);
    const f = featuresFromText(0.308, 168, 'HPBT', 'cup-and-core');
    expect(m.predict(f)!).toBeCloseTo(mk(0.308, 168, false, false).lengthIn!, 3);
  });
  it('reads construction and profile words', () => {
    expect(featuresFromText(0.308, 150, 'TTSX', null).mono).toBe(true);
    expect(featuresFromText(0.308, 150, 'ELD-X', 'cup-and-core').tipped).toBe(true);
    expect(featuresFromText(0.355, 115, 'FMJ RN', null).flatBase).toBe(true);
    expect(featuresFromText(0.355, 115, 'FMJ RN', null).blunt).toBe(true);
    expect(featuresFromText(0.308, 168, 'HPBT Match', null).blunt).toBe(false);
    expect(featuresFromText(0.308, 168, 'HPBT Match', null).flatBase).toBe(false);
  });
});
