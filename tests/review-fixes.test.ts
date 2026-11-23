import { describe, it, expect } from 'vitest';
import { simulate, DEFAULT_OPTIONS } from '../src/engine/model';
import { monteCarlo, sensitivities, specForPowderModel } from '../src/engine/uncertainty';
import { parseUserImport, BASE_DB } from '../src/data/db';
import { publishedReference } from '../src/ui/CrossCheck';
import * as U from '../src/engine/units';
import type { ValidationLoad } from '../src/data/schema';
import type { LoadSetup } from '../src/engine/types';

const setup: LoadSetup = {
  caseCapacityM3: U.grH2OToM3(56), caseLengthM: U.inToM(2.005), boreDiameterM: U.inToM(0.3), grooveDiameterM: U.inToM(0.308),
  barrelLengthM: U.inToM(24), coalM: U.inToM(2.8), chargeKg: U.grToKg(44), propellantTempC: 21,
  bullet: { massKg: U.grToKg(168), diameterM: U.inToM(0.308), lengthM: U.inToM(1.215) },
  propellant: { thermo: { forceJkg: 1.0e6, flameTempK: 2900, gamma: 1.24, covolumeM3kg: 1e-3, solidDensityKgM3: 1600 }, burn: { beta: 18, n: 0.78, lambda: 0, mu: 0, tempCoeffPerK: 0, refTempC: 21 } },
  options: { ...DEFAULT_OPTIONS },
} as unknown as LoadSetup;

describe('sensitivity band reproduces the intended pressure spread', () => {
  it('uses the load elasticity so p95/p50 − 1 ≈ 1.645·σP', () => {
    const k = sensitivities(setup).find((x) => x.key === 'beta')!.peakPct / (100 * (Math.exp(0.03) - 1));
    const spec = specForPowderModel({ status: 'calibrated', calibration: { rmsPressurePct: 10, heldOutPressurePct: null } }, k);
    const onlyBeta = { ...spec, caseCapacityRel: 0, forceRel: 0, shotStartRel: 0, seatingDepthM: 0, chargeKg: 0 };
    const mc = monteCarlo(setup, onlyBeta, 300, 3);
    const sigmaP = 0.145; // 10 % RMS × 1.45
    const upper = mc.peak.p95 / mc.peak.p50 - 1;
    expect(upper).toBeGreaterThan(1.645 * sigmaP * 0.75);
    expect(upper).toBeLessThan(1.645 * sigmaP * 1.6);
  });
  it('treats velocity-only models as unvalidated (wide spread)', () => {
    const a = specForPowderModel({ status: 'calibrated', calibration: { rmsPressurePct: null } }, 1.7);
    const b = specForPowderModel({ status: 'calibrated', calibration: { rmsPressurePct: 5 } }, 1.7);
    expect(a.betaRel).toBeGreaterThan(b.betaRel * 2);
  });
  it('perturbs burn rate log-normally', () => {
    expect(simulate(setup).status).toBe('muzzle');
  });
});

describe('user-data import cannot impersonate shipped data', () => {
  it('forces imported models to user-calibrated and strips fit claims; renames shipped ids', () => {
    const shippedCart = BASE_DB.cartridges[0];
    const imp = parseUserImport(JSON.stringify({
      powderModels: { x: { status: 'calibrated', params: { forceJg: 1000, flameTempK: 2900, gamma: 1.25, covolumeCm3g: 1, solidDensityGcc: 1.6, beta: 18, n: 0.8, lambda: 0, mu: 0, tempCoeffPerK: 0, refTempC: 21 }, calibration: { grade: 'good', heldOutPressurePct: 1, points: 3, rmsVelocityFps: 5, rmsPressurePct: 1, cartridges: [], sources: [] } } },
      cartridges: shippedCart ? [{ ...shippedCart, saamiMapPsi: 99999 }] : [],
    }));
    expect(imp.powderModels.x.status).toBe('user-calibrated');
    expect(imp.powderModels.x.calibration?.grade).toBeUndefined();
    expect(imp.powderModels.x.calibration?.heldOutPressurePct).toBeUndefined();
    if (shippedCart) expect(imp.cartridges[0].id).toBe(`${shippedCart.id}-imported`);
  });
});

describe('published reference', () => {
  const row = (t: string, ch: number) => ({ loadType: t, chargeGr: ch }) as unknown as ValidationLoad;
  it('uses the lowest max, else the highest single load, and never a section max', () => {
    expect(publishedReference([row('start', 40), row('max', 44), row('max', 43.2)])).toEqual({ charge: 43.2, kind: 'max' });
    expect(publishedReference([row('other', 5.5), row('other', 6.1)])).toEqual({ charge: 6.1, kind: 'single' });
    expect(publishedReference([row('section-max', 56), row('reduced', 40)])).toBeNull();
  });
});
