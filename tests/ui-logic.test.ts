import { describe, it, expect } from 'vitest';
import { fromDisplay, toDisplay, fmtP, friendlyError, slug, toCsv, type InputQty } from '../src/ui/format';
import { niceTicks } from '../src/ui/LineChart';
import { capacityOptions, deriveLoad, pressureLimit } from '../src/ui/useLoad';
import { EMPTY_BUILDER, reviveInputs, type BuilderState } from '../src/ui/state';
import type { Cartridge, Database, Powder } from '../src/data/schema';
import * as U from '../src/engine/units';

// Fictional test fixtures only.
const cart: Cartridge = {
  id: 'test-cart',
  name: 'Test Cartridge A',
  aliases: ['TCA'],
  type: 'rifle',
  standards: ['SAAMI'],
  bulletDiameterIn: 0.308,
  boreDiameterIn: 0.3,
  grooveDiameterIn: 0.308,
  caseLengthMaxIn: 2.015,
  trimLengthIn: 2.005,
  maxCoalIn: 2.8,
  saamiMapPsi: 62000,
  saamiMapCup: null,
  cipPmaxBar: 4150,
  saamiTwist: '1:12',
  primerSize: null,
  caseCapacityGrH2O: [{ value: 56, brand: 'Test Brass', basis: 'third-party measured', source: null }],
  sources: [],
};

const powder: Powder = {
  id: 'test-powder-a',
  manufacturer: 'Test Co',
  name: 'Test Powder A',
  form: 'extruded',
  base: 'single',
  applications: [],
  bulkDensityGcc: 0.9,
  burnRateCharts: [],
  status: 'unknown',
  sources: [],
  model: {
    status: 'user-calibrated',
    derivation: 'test',
    params: { forceJg: 1000, flameTempK: 2900, gamma: 1.24, covolumeCm3g: 1.0, solidDensityGcc: 1.6, beta: 5, n: 1, lambda: 0, mu: 0, tempCoeffPerK: 0, refTempC: 21 },
  },
};

const db: Database = {
  version: 'test',
  generated: '',
  cartridges: [cart],
  powders: [powder],
  burnRateCharts: [],
  bullets: [],
  brassBrands: [{ id: 'tb', name: 'Test Brass Co', sources: [] }],
  brassCases: [{ brandId: 'tb', cartridge: 'TCA', waterCapacityGrH2O: 55.5, capacityCondition: 'fired', basis: 'manufacturer', sources: [] }],
  validationLoads: [],
};

const builder: BuilderState = {
  ...EMPTY_BUILDER,
  cartridgeId: 'test-cart',
  powderId: 'test-powder-a',
  inputs: {
    boreDiameterIn: 0.3,
    grooveDiameterIn: 0.308,
    caseLengthIn: 2.005,
    caseCapacityGrH2O: 56,
    barrelLengthIn: 24,
    bulletWeightGr: 168,
    bulletDiameterIn: 0.308,
    bulletLengthIn: 1.215,
    boatTailLengthIn: 0,
    bulletBaseDiameterIn: 0,
    coalIn: 2.8,
    chargeGr: 44,
    powderTempF: 70,
    shotStartPsi: 3626,
  },
};

describe('display units', () => {
  it('round-trips every input quantity through metric display', () => {
    const samples: [InputQty, number][] = [['len', 2.8], ['barrel', 24], ['bulletMass', 168], ['charge', 44.3], ['cap', 56.2], ['vel', 2700], ['press', 62000], ['temp', 70]];
    for (const [q, v] of samples) {
      expect(fromDisplay(q, 'metric', toDisplay(q, 'metric', v))).toBeCloseTo(v, 9);
      expect(toDisplay(q, 'imperial', v)).toBe(v);
    }
    expect(toDisplay('len', 'metric', 1)).toBeCloseTo(25.4, 12);
    expect(toDisplay('temp', 'metric', 32)).toBeCloseTo(0, 12);
  });
  it('formats pressure in psi and MPa', () => {
    expect(fmtP(U.psiToPa(62000), 'imperial')).toBe('62,000 psi');
    expect(fmtP(U.psiToPa(62000), 'metric')).toBe('427.5 MPa');
    expect(fmtP(NaN, 'imperial')).toBe('—');
  });
  it('rewrites engine validation messages', () => {
    expect(friendlyError('coalIn must be a positive number')).toBe('COAL is required (positive number).');
  });
  it('slugs and CSV-escapes', () => {
    expect(slug('Test Powder A (lot #3)')).toBe('test-powder-a-lot-3');
    expect(toCsv([{ a: 'x,y', b: 1 }, { a: 'q"q', c: null }])).toBe('a,b,c\n"x,y",1,\n"q""q",,');
  });
});

describe('chart ticks', () => {
  it('produces round, ascending ticks covering the range', () => {
    const t = niceTicks(0, 63000, 5);
    expect(t[0]).toBe(0);
    expect(t[t.length - 1]).toBeLessThanOrEqual(63000);
    for (let i = 1; i < t.length; i++) expect(t[i]).toBeGreaterThan(t[i - 1]);
    expect(t).toContain(10000);
  });
});

describe('builder derivation', () => {
  it('uses SAAMI piezo psi with margin and never converts CUP', () => {
    const l = pressureLimit({ ...builder, marginPct: 5 }, cart);
    expect(l.limitPa! / U.psiToPa(62000)).toBeCloseTo(0.95, 9);
    const cupOnly = { ...cart, saamiMapPsi: null, saamiMapCup: 52000 };
    const l2 = pressureLimit(builder, cupOnly);
    expect(l2.limitPa).toBeNull();
    expect(l2.note).toMatch(/CUP/);
    const l3 = pressureLimit({ ...builder, standard: 'CIP', marginPct: 0 }, cart);
    expect(l3.limitPa).toBeCloseTo(U.barToPa(4150), 3);
  });
  it('builds a valid engine setup when inputs are complete', () => {
    const d = deriveLoad(db, builder);
    expect(d.errors).toEqual([]);
    expect(d.setup).not.toBeNull();
    expect(d.setup!.chargeKg).toBeCloseTo(U.grToKg(44), 12);
  });
  it('refuses to simulate a powder without a model', () => {
    const noModel = { ...db, powders: [{ ...powder, model: undefined }] };
    const d = deriveLoad(noModel, builder);
    expect(d.setup).toBeNull();
    expect(d.errors.join(' ')).toMatch(/no burn model/);
  });
  it('lists capacity options from brass cases (alias match) and cartridge records', () => {
    const opts = capacityOptions(db, cart);
    expect(opts.map((o) => o.value)).toEqual([55.5, 56]);
    expect(opts[0].label).toContain('Test Brass Co');
  });
  it('revives NaN inputs after a JSON round trip', () => {
    const r = reviveInputs(JSON.parse(JSON.stringify({ ...builder.inputs, coalIn: NaN })));
    expect(Number.isNaN(r.coalIn)).toBe(true);
    expect(r.chargeGr).toBe(44);
  });
});
