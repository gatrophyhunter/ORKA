import { describe, it, expect } from 'vitest';
import { simulate, DEFAULT_OPTIONS, boreArea, bulletVolumeBelow, formFunction } from '../src/engine/model';
import { solveChargeForPressure, solveChargeForVelocity, ladder, parametricSearch } from '../src/engine/search';
import { calibrate } from '../src/engine/calibrate';
import { monteCarlo, sensitivities, DEFAULT_SPEC_CALIBRATED } from '../src/engine/uncertainty';
import * as U from '../src/engine/units';
import type { LoadSetup, PropellantModel } from '../src/engine/types';

const powder: PropellantModel = {
  thermo: { forceJkg: 1.0e6, flameTempK: 2900, gamma: 1.24, covolumeM3kg: 1.0e-3, solidDensityKgM3: 1600 },
  burn: { beta: 5, n: 1, lambda: 0, mu: 0, tempCoeffPerK: 0.001, refTempC: 21 },
  bulkDensityKgM3: 900,
};

const base = (over: Partial<LoadSetup> = {}): LoadSetup => ({
  caseCapacityM3: U.grH2OToM3(56),
  caseLengthM: U.inToM(2.005),
  boreDiameterM: U.inToM(0.3),
  grooveDiameterM: U.inToM(0.308),
  barrelLengthM: U.inToM(24),
  coalM: U.inToM(2.8),
  chargeKg: U.grToKg(44),
  propellantTempC: 21,
  bullet: { massKg: U.grToKg(168), diameterM: U.inToM(0.308), lengthM: U.inToM(1.215), boatTailLengthM: U.inToM(0.15), baseDiameterM: U.inToM(0.25) },
  propellant: powder,
  options: { ...DEFAULT_OPTIONS },
  ...over,
});

describe('units', () => {
  it('uses exact definitions', () => {
    expect(U.grToG(7000)).toBeCloseTo(453.59237, 6); // 7000 gr = 1 lb avoirdupois exactly
    expect(U.psiToPa(1)).toBeCloseTo(6894.757293168, 6);
    expect(U.inToMm(1)).toBe(25.4);
    expect(U.fpsToMs(1000)).toBeCloseTo(304.8, 9);
  });
  it('round-trips grains of water and volume', () => {
    expect(U.m3ToGrH2O(U.grH2OToM3(56.3))).toBeCloseTo(56.3, 9);
    // 1 gr of water at 0.9982 g/cm3 is 0.064916 cm3
    expect(U.grH2OToCm3(1)).toBeCloseTo(0.0649158, 6);
  });
  it('energy in ft-lbf matches the classic reloader formula within 0.05 %', () => {
    const e = U.energyFtLbf(168, 2700);
    const classic = (168 * 2700 * 2700) / 450240; // common shortcut constant (g ≈ 32.16 ft/s²)
    expect(Math.abs(e - classic) / classic).toBeLessThan(0.0005);
  });
});

describe('geometry', () => {
  it('bore area averages bore and groove circles', () => {
    const a = boreArea(0.00762, 0.00782);
    expect(a).toBeCloseTo((Math.PI / 8) * (0.00762 ** 2 + 0.00782 ** 2), 12);
  });
  it('boat-tail intrusion volume is less than a cylinder', () => {
    const b = { massKg: 0.01, diameterM: 0.00782, lengthM: 0.03, boatTailLengthM: 0.004, baseDiameterM: 0.0064 };
    const cyl = Math.PI * (0.00782 / 2) ** 2 * 0.01;
    const v = bulletVolumeBelow(b, 0.01);
    expect(v).toBeLessThan(cyl);
    expect(v).toBeGreaterThan(cyl * 0.9);
    expect(bulletVolumeBelow(b, 0)).toBe(0);
  });
  it('form function is normalised: psi(1) = 1 and monotonic', () => {
    for (const lambda of [-0.4, 0, 0.5, 1.5]) {
      const f = formFunction({ beta: 1, n: 1, lambda, mu: 0, tempCoeffPerK: 0, refTempC: 21 });
      expect(f.psi(1)).toBeCloseTo(1, 12);
      let prev = -1;
      for (let z = 0; z <= 1.0001; z += 0.05) {
        const p = f.psi(z);
        expect(p).toBeGreaterThanOrEqual(prev);
        prev = p;
      }
    }
  });
});

describe('simulate', () => {
  it('reproduces the Noble-Abel closed-vessel pressure when the bullet cannot move', () => {
    const s = base({ chargeKg: U.grToKg(20), options: { ...DEFAULT_OPTIONS, shotStartPressurePa: 1e12, heatLoss: { ...DEFAULT_OPTIONS.heatLoss, enabled: false } } });
    const r = simulate(s);
    expect(r.status).toBe('stuck');
    const V0 = r.chamberVolumeM3;
    const C = s.chargeKg;
    const Vf0 = V0 - C / powder.thermo.solidDensityKgM3;
    const expected = (powder.thermo.forceJkg * C + DEFAULT_OPTIONS.ignitionPressurePa * Vf0) / (V0 - powder.thermo.covolumeM3kg * C);
    expect(r.peakBreechPa / expected).toBeCloseTo(1, 6);
  });

  it('work done on the projectile equals its (Lagrange-augmented) kinetic energy', () => {
    const s = base({ options: { ...DEFAULT_OPTIONS, recordTrace: true, heatLoss: { ...DEFAULT_OPTIONS.heatLoss, enabled: false } } });
    const r = simulate(s);
    expect(r.status).toBe('muzzle');
    const tr = r.trace!;
    const S = boreArea(s.boreDiameterM, s.grooveDiameterM);
    const phi1 = DEFAULT_OPTIONS.secondaryWorkCoeff;
    const m = s.bullet.massKg;
    const C = s.chargeKg;
    // mean pressure = base pressure * (1 + C/(3 phi1 m))
    let work = 0;
    for (let i = 1; i < tr.t.length; i++) {
      const pm0 = tr.pBase[i - 1] * (tr.x[i - 1] > 0 || tr.v[i - 1] > 0 ? 1 + C / (3 * phi1 * m) : 1);
      const pm1 = tr.pBase[i] * (1 + C / (3 * phi1 * m));
      work += 0.5 * (pm0 + pm1) * S * (tr.x[i] - tr.x[i - 1]);
    }
    const ke = 0.5 * (phi1 * m + C / 3) * r.muzzleVelocityMs ** 2;
    expect(Math.abs(work - ke) / ke).toBeLessThan(2e-3);
  });

  it('converges: tighter tolerances change peak pressure and velocity by < 0.1 %', () => {
    const a = simulate(base());
    const b = simulate(base({ options: { ...DEFAULT_OPTIONS, rtol: 1e-10, atol: 1e-12 } }));
    expect(Math.abs(a.peakBreechPa - b.peakBreechPa) / b.peakBreechPa).toBeLessThan(1e-3);
    expect(Math.abs(a.muzzleVelocityMs - b.muzzleVelocityMs) / b.muzzleVelocityMs).toBeLessThan(1e-3);
  });

  it('pressure and velocity rise with charge; pressure falls with more case capacity', () => {
    const p = [40, 42, 44, 46].map((gr) => simulate(base({ chargeKg: U.grToKg(gr) })));
    for (let i = 1; i < p.length; i++) {
      expect(p[i].peakBreechPa).toBeGreaterThan(p[i - 1].peakBreechPa);
      expect(p[i].muzzleVelocityMs).toBeGreaterThan(p[i - 1].muzzleVelocityMs);
    }
    const small = simulate(base({ caseCapacityM3: U.grH2OToM3(54) }));
    const big = simulate(base({ caseCapacityM3: U.grH2OToM3(58) }));
    expect(small.peakBreechPa).toBeGreaterThan(big.peakBreechPa);
  });

  it('longer barrels give more velocity, same peak pressure', () => {
    const s20 = simulate(base({ barrelLengthM: U.inToM(20) }));
    const s26 = simulate(base({ barrelLengthM: U.inToM(26) }));
    expect(s26.muzzleVelocityMs).toBeGreaterThan(s20.muzzleVelocityMs);
    expect(Math.abs(s26.peakBreechPa - s20.peakBreechPa) / s20.peakBreechPa).toBeLessThan(0.002);
  });

  it('deeper seating raises pressure', () => {
    const long = simulate(base({ coalM: U.inToM(2.82) }));
    const short = simulate(base({ coalM: U.inToM(2.78) }));
    expect(short.peakBreechPa).toBeGreaterThan(long.peakBreechPa);
  });

  it('warmer powder raises pressure when the temperature coefficient is positive', () => {
    const cold = simulate(base({ propellantTempC: -10 }));
    const hot = simulate(base({ propellantTempC: 45 }));
    expect(hot.peakBreechPa).toBeGreaterThan(cold.peakBreechPa);
  });

  it('heat loss lowers velocity', () => {
    const on = simulate(base());
    const off = simulate(base({ options: { ...DEFAULT_OPTIONS, heatLoss: { ...DEFAULT_OPTIONS.heatLoss, enabled: false } } }));
    expect(off.muzzleVelocityMs).toBeGreaterThan(on.muzzleVelocityMs);
    expect(on.heatLossJ).toBeGreaterThan(0);
  });

  it('rejects a charge that cannot fit', () => {
    const r = simulate(base({ chargeKg: U.grToKg(200) }));
    expect(r.status).toBe('invalid');
  });

  it('reports fill ratio from bulk density', () => {
    const r = simulate(base());
    expect(r.fillRatio).not.toBeNull();
    expect(r.fillRatio!).toBeCloseTo(base().chargeKg / 900 / r.chamberVolumeM3, 9);
  });
});

describe('solvers', () => {
  it('solves the charge that hits a pressure limit', () => {
    const limit = U.psiToPa(62000);
    const sol = solveChargeForPressure(base(), limit);
    expect(sol.limitedBy).toBe('pressure');
    expect(Math.abs(sol.result.peakBreechPa - limit) / limit).toBeLessThan(0.002);
  });
  it('reports the fill limit when pressure cannot be reached', () => {
    const slow: PropellantModel = { ...powder, burn: { ...powder.burn, beta: 1 } };
    const sol = solveChargeForPressure(base({ propellant: slow }), U.psiToPa(62000), { maxFillRatio: 1.0, tolKg: 1e-6 });
    expect(sol.limitedBy).toBe('fill');
    expect(sol.result.fillRatio!).toBeCloseTo(1.0, 3);
  });
  it('solves the charge for a target velocity', () => {
    const sol = solveChargeForVelocity(base(), U.fpsToMs(2600))!;
    expect(Math.abs(U.msToFps(sol.result.muzzleVelocityMs) - 2600)).toBeLessThan(1);
  });
  it('ladder flags rows over the limit', () => {
    const rows = ladder(base(), U.grToKg(40), U.grToKg(48), 8, U.psiToPa(62000));
    expect(rows.length).toBe(9);
    expect(rows[0].overLimit).toBe(false);
    expect(rows[8].overLimit).toBe(true);
  });
  it('parametric search ranks powders and enforces the burn constraint', () => {
    const cands = [0.8, 2.5, 5, 9].map((b, i) => ({
      id: `p${i}`,
      label: `beta ${b}`,
      status: 'calibrated' as const,
      model: { ...powder, burn: { ...powder.burn, beta: b } },
    }));
    const rows = parametricSearch(base(), cands, { pressureLimitPa: U.psiToPa(62000), maxFillRatio: 1.05, minBurnt: 0.9, minFillRatio: 0.7 });
    expect(rows.length).toBe(4);
    for (const r of rows.filter((x) => x.limitedBy === 'pressure')) {
      expect(r.result.peakBreechPa).toBeLessThanOrEqual(U.psiToPa(62000) * 1.0001);
    }
    // passing rows come first and are sorted by velocity
    const passing = rows.filter((r) => r.passes);
    for (let i = 1; i < passing.length; i++) expect(passing[i - 1].result.muzzleVelocityMs).toBeGreaterThanOrEqual(passing[i].result.muzzleVelocityMs);
  });
});

describe('calibration', () => {
  it('recovers a known burn-rate coefficient and progressivity from synthetic data', () => {
    const truth: PropellantModel = { ...powder, burn: { ...powder.burn, beta: 6.3, lambda: 0.35 } };
    const obs = [41, 43, 45, 47].map((gr) => {
      const s = base({ chargeKg: U.grToKg(gr), propellant: truth });
      const r = simulate(s);
      return { setup: s, velocityMs: r.muzzleVelocityMs, peakPa: r.peakBreechPa };
    });
    const res = calibrate({
      start: { ...powder, burn: { ...powder.burn, beta: 3, lambda: 0 } },
      observations: obs,
      params: ['beta', 'lambda'],
      sigmaVelocityMs: 5,
      sigmaPressureRel: 0.02,
    });
    expect(res.model.burn.beta).toBeCloseTo(6.3, 1);
    expect(res.model.burn.lambda).toBeCloseTo(0.35, 1);
    expect(res.rmsVelocityMs!).toBeLessThan(1);
  });
});

describe('uncertainty', () => {
  it('produces an ordered band that contains the nominal result', () => {
    const s = base();
    const nominal = simulate(s);
    const mc = monteCarlo(s, DEFAULT_SPEC_CALIBRATED, 80, 7);
    expect(mc.peak.p05).toBeLessThan(mc.peak.p50);
    expect(mc.peak.p50).toBeLessThan(mc.peak.p95);
    expect(nominal.peakBreechPa).toBeGreaterThan(mc.peak.p05);
    expect(nominal.peakBreechPa).toBeLessThan(mc.peak.p95);
  });
  it('sensitivities have physically expected signs', () => {
    const sens = Object.fromEntries(sensitivities(base()).map((x) => [x.key, x]));
    expect(sens.charge.peakPct).toBeGreaterThan(0);
    expect(sens.cap.peakPct).toBeGreaterThan(0); // capacity −1 % → more pressure
    expect(sens.seat.peakPct).toBeGreaterThan(0);
    expect(sens.beta.peakPct).toBeGreaterThan(0);
  });
});
