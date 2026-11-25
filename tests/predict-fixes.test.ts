import { describe, it, expect } from 'vitest';
import { specForPowderModel, isVelocityOnly, DEFAULT_SPEC_ESTIMATED, UNVALIDATED_PRESSURE_SIGMA } from '../src/engine/uncertainty';
import { classValidation, modelValidation, type ModelValidationSummary } from '../src/engine/defaults';
import { estimateFromCharts } from '../scripts/estimate';
import { mergedDb, parseUserImport, sanitizeImportedModel, shippedModel, EMPTY_USER, BASE_DB } from '../src/data/db';
import { modelErrorView, bulletShotClass } from '../src/ui/PredictTab';
import { recallLoad } from '../src/ui/LoadBookTab';
import { customLimitWarning, limitForCartridge, pressureLimit, standardForCartridge } from '../src/ui/useLoad';
import { EMPTY_BUILDER, type BuilderState } from '../src/ui/state';
import type { SavedLoad } from '../src/data/db';
import type { BurnRateChart, Cartridge, Powder, PowderModelEntry, PowderModelParams } from '../src/data/schema';
import * as U from '../src/engine/units';

// Fictional test fixtures only.
const params: PowderModelParams = { forceJg: 1000, flameTempK: 2900, gamma: 1.24, covolumeCm3g: 1, solidDensityGcc: 1.6, beta: 5, n: 1, lambda: 0, mu: 0, tempCoeffPerK: 0, refTempC: 21 };
const fitted = (rms: number | null, held: number | null = null, grade?: 'good' | 'fair' | 'poor' | 'unvalidated'): PowderModelEntry => ({
  status: 'calibrated',
  params,
  derivation: 'test',
  calibration: { points: 10, rmsVelocityFps: 20, rmsPressurePct: rms, heldOutPressurePct: held, cartridges: [], sources: [], ...(grade ? { grade } : {}) },
});
const velocityOnlyUser: PowderModelEntry = {
  status: 'user-calibrated',
  params,
  derivation: 'Fitted by you to 1 point',
  calibration: { points: 1, rmsVelocityFps: 0, rmsPressurePct: null, cartridges: ['x'], sources: ['user measurements'] },
};

const cart = (over: Partial<Cartridge>): Cartridge => ({
  id: 'test-cart',
  name: 'Test Cartridge A',
  aliases: [],
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
  saamiTwist: null,
  primerSize: null,
  caseCapacityGrH2O: [],
  sources: [],
  ...over,
});

const mv: ModelValidationSummary = {
  heldOutPressureN: 375,
  heldOutPressureP50Pct: 12.7,
  heldOutPressureP90Pct: 30.9,
  heldOutPressureBiasPct: -4.4,
  heldOutWithin10Pct: 39,
  byShotClass: { jacketed: { n: 297, p50Pct: 12.4, p90Pct: 30.8, biasPct: -8.2 }, monolithic: { n: 78, p50Pct: 17, p90Pct: 36.9, biasPct: 9.7 } },
  scope: 'held-out pressure comparisons exist only for: Test A',
  heldOutCartridgeIds: ['test-cart'],
};
const view = (over: Partial<Parameters<typeof modelErrorView>[0]>) =>
  modelErrorView({
    peakPa: U.psiToPa(50000),
    mapPa: U.psiToPa(62000),
    standard: 'SAAMI',
    status: 'calibrated',
    model: fitted(8),
    mv,
    shotClass: null,
    cartridgeId: 'test-cart',
    estimateBetaRel: 0.423,
    elasticity: 1.7,
    fmt: (pa) => `${Math.round(U.paToPsi(pa))} psi`,
    ...over,
  });

describe('velocity-only models never narrow the pressure band (findings 3, 4a)', () => {
  it('gives shipped velocity-only models at least the estimated-powder spread', () => {
    const s = specForPowderModel(fitted(null, null, 'unvalidated'), 1.7);
    expect(s.betaRel).toBeGreaterThanOrEqual(DEFAULT_SPEC_ESTIMATED.betaRel);
    expect(s.betaRel).toBeGreaterThanOrEqual(UNVALIDATED_PRESSURE_SIGMA / 1.7);
    expect(s.forceRel).toBeGreaterThanOrEqual(DEFAULT_SPEC_ESTIMATED.forceRel);
  });
  it('keeps a velocity-only user calibration at least as wide as the model it replaced', () => {
    // A poorly fitted parent (σP = 67.8 × 1.48 % ⇒ capped burn-rate spread 0.6 at k = 1.48).
    const parent = fitted(27.6, 67.8, 'poor');
    const p = specForPowderModel(parent, 1.48);
    const u = specForPowderModel(velocityOnlyUser, 1.48, parent);
    expect(p.betaRel).toBeCloseTo(0.6, 9);
    expect(u.betaRel).toBeGreaterThanOrEqual(p.betaRel);
    // An estimated parent passes on its chart-interpolation spread.
    const est: PowderModelEntry = { status: 'estimated', params, derivation: 'test', betaRelSigma: 0.423 };
    expect(specForPowderModel(velocityOnlyUser, 1.7, est).betaRel).toBeGreaterThanOrEqual(0.423);
    // Without a parent the unvalidated floor still applies.
    expect(specForPowderModel(velocityOnlyUser, 1.7).betaRel).toBeGreaterThanOrEqual(DEFAULT_SPEC_ESTIMATED.betaRel);
  });
  it('lets a user calibration with pressure data set its own spread', () => {
    const withP = { ...velocityOnlyUser, calibration: { ...velocityOnlyUser.calibration!, rmsPressurePct: 5 } };
    expect(specForPowderModel(withP, 1.7, fitted(27.6, 67.8)).betaRel).toBeCloseTo((5 * 1.45) / 100 / 1.7, 9);
  });
  it('flags velocity-only models', () => {
    expect(isVelocityOnly(velocityOnlyUser)).toBe(true);
    expect(isVelocityOnly(fitted(null, null, 'unvalidated'))).toBe(true);
    expect(isVelocityOnly(fitted(8))).toBe(false);
    expect(isVelocityOnly({ status: 'estimated' })).toBe(false);
  });
  it('looks up the shipped model a calibration replaces', () => {
    const p = BASE_DB.powders.find((x) => x.model);
    if (p) expect(shippedModel(p.id)).toBe(p.model);
    expect(shippedModel('no-such-powder')).toBeNull();
    expect(shippedModel(null)).toBeNull();
  });
  it('shows the model-error statement for a user calibration, marked velocity-only', () => {
    const v = view({ status: 'user-calibrated', model: velocityOnlyUser, peakPa: U.psiToPa(50000) })!;
    expect(v).not.toBeNull();
    expect(v.lead).toMatch(/velocity-only/i);
    expect(v.text).toMatch(/held-out published data/);
    expect(v.upperPa).toBeCloseTo(U.psiToPa(50000) * 1.309, 3);
    expect(v.over).toBe(true); // 65,450 psi > 62,000 psi
    const imp = view({ status: 'user-calibrated', model: { ...velocityOnlyUser, derivation: 'Imported from a file. x' } })!;
    expect(imp.lead).toMatch(/Imported model/);
  });
});

describe('chart interpolation skips velocity-only anchors (finding 4b)', () => {
  const pw = (id: string, model?: PowderModelEntry): Powder => ({
    id, manufacturer: 'Test Co', name: id, form: 'extruded', base: 'single', applications: [], burnRateCharts: [], status: 'unknown', sources: [], model,
  });
  const withBeta = (m: PowderModelEntry, beta: number): PowderModelEntry => ({ ...m, params: { ...m.params, beta } });
  const chart: BurnRateChart = { publisher: 'Test', edition: '1', url: '', orderedPowderIds: ['a', 'x', 'u', 'b'] };
  it('interpolates between pressure-fitted anchors only and leaves velocity-only fits alone', () => {
    const powders = [pw('a', withBeta(fitted(8), 10)), pw('x'), pw('u', withBeta(fitted(null, null, 'unvalidated'), 1000)), pw('b', withBeta(fitted(9), 2))];
    const out = estimateFromCharts(powders, [chart]);
    expect(out.u).toBeUndefined();
    expect(out.x).toBeDefined();
    // x sits one third of the way from a to b (positions 0, 1, 3): log-linear in beta at equal n.
    expect(Math.log(out.x.params.beta)).toBeCloseTo(Math.log(10) * (2 / 3) + Math.log(2) * (1 / 3), 9);
    expect(out.x.derivation).toMatch(/between a \(#1\) and b \(#4\)/);
  });
  it('gives no estimate when the only neighbours are velocity-only', () => {
    const powders = [pw('a', withBeta(fitted(null, null, 'unvalidated'), 10)), pw('x'), pw('b', withBeta(fitted(9), 2))];
    expect(estimateFromCharts(powders, [{ ...chart, orderedPowderIds: ['a', 'x', 'b'] }]).x).toBeUndefined();
  });
});

describe('estimated powders show their own spread, not the calibrated held-out error (finding 16)', () => {
  it('states that no held-out validation exists and uses the chart-interpolation spread', () => {
    const v = view({ status: 'estimated', model: { status: 'estimated', params, derivation: 'test', betaRelSigma: 0.423 } })!;
    expect(v.lead).toMatch(/No held-out validation/);
    expect(v.text).not.toMatch(/held-out published data/);
    expect(v.text).not.toMatch(/30\.9/);
    expect(v.text).toMatch(/±42 %/);
    expect(v.upperPa).toBeCloseTo(U.psiToPa(50000) * Math.exp(1.645 * 1.7 * 0.423), 3);
    expect(v.over).toBe(true);
  });
  it('does not need the validation summary', () => {
    expect(view({ status: 'estimated', mv: null })).not.toBeNull();
    expect(view({ status: 'calibrated', mv: null })).toBeNull();
  });
});

describe('held-out bias per bullet construction (finding 17)', () => {
  it('uses the class figures when the class has enough comparisons', () => {
    expect(classValidation(mv, 'jacketed')?.biasPct).toBe(-8.2);
    expect(classValidation(mv, 'lead')).toBeNull();
    expect(classValidation(mv, null)).toBeNull();
    expect(classValidation({ ...mv, byShotClass: { jacketed: { n: 5, p50Pct: 1, p90Pct: 2, biasPct: -1 } } }, 'jacketed')).toBeNull();
  });
  it('shows the jacketed bias for a jacketed bullet and the overall figure when the class is unknown', () => {
    expect(view({ shotClass: 'jacketed' })!.text).toMatch(/jacketed bullets, 297 published loads.*on average 8\.2 % low/);
    expect(view({ shotClass: null })!.text).toMatch(/on average 4\.4 % low/);
    // Monolithic reads high on average: no "low" claim, and its larger p90 sets the upper estimate.
    const mono = view({ shotClass: 'monolithic' })!;
    expect(mono.text).not.toMatch(/% low/);
    expect(mono.upperPa).toBeCloseTo(U.psiToPa(50000) * 1.369, 3);
    // The upper estimate never uses less than the all-bullets p90.
    expect(view({ shotClass: 'jacketed' })!.upperPa).toBeCloseTo(U.psiToPa(50000) * 1.309, 3);
  });
  it('classifies the selected bullet only when its construction is recorded', () => {
    expect(bulletShotClass(null)).toBeNull();
    expect(bulletShotClass('  ')).toBeNull();
    expect(bulletShotClass('jacketed lead core')).toBe('jacketed');
    expect(bulletShotClass('monolithic copper')).toBe('monolithic');
  });
  it('ships per-class figures that add up to the headline count', () => {
    const v = modelValidation();
    if (!v?.byShotClass) return;
    const n = Object.values(v.byShotClass).reduce((s, c) => s + (c?.n ?? 0), 0);
    expect(n).toBe(v.heldOutPressureN);
  });
  it('says "your custom limit" when the limit is custom', () => {
    const v = view({ standard: 'custom', mapPa: U.psiToPa(60000), peakPa: U.psiToPa(55000) })!;
    expect(v.text).toMatch(/above your custom limit/);
  });
});

describe('custom limits above the cartridge maximum (finding 6)', () => {
  const b: BuilderState = { ...EMPTY_BUILDER, cartridgeId: 'test-cart', standard: 'custom', customLimitPsi: 90000, marginPct: 0 };
  it('warns in the builder whenever a custom limit is above SAAMI or C.I.P.', () => {
    expect(pressureLimit(b, cart({})).warning).toMatch(/above this cartridge's SAAMI MAP \(62,000 psi\) and C\.I\.P\. Pmax \(4,150 bar = 60,191 psi\)/);
    // Between C.I.P. (60,191 psi) and SAAMI (62,000 psi): above C.I.P. only.
    expect(customLimitWarning(61000, cart({}))).toMatch(/C\.I\.P\. Pmax/);
    expect(customLimitWarning(61000, cart({}))).not.toMatch(/SAAMI/);
    expect(customLimitWarning(60000, cart({}))).toBeNull();
    // CUP is a different measurement: never compared.
    expect(customLimitWarning(90000, cart({ saamiMapPsi: null, saamiMapCup: 52000, cipPmaxBar: null }))).toBeNull();
    // Only a custom standard can carry a custom limit.
    expect(pressureLimit({ ...b, standard: 'SAAMI' }, cart({})).warning).toBeNull();
  });
});

describe('load-book recall and cartridge changes reset the limit (finding 7)', () => {
  const load = (cartridgeId: string | null): SavedLoad => ({
    id: 'l1', name: 'Test load', createdIso: '2026-01-01T00:00:00Z', cartridgeId, powderId: null, bulletId: null, brassBrandId: null, inputs: EMPTY_BUILDER.inputs,
  });
  const lowMap = cart({ id: 'low-map', saamiMapPsi: 28000, cipPmaxBar: null });
  const wildcat: BuilderState = { ...EMPTY_BUILDER, cartridgeId: 'test-cart', standard: 'custom', customLimitPsi: 68000 };
  it('does not carry a custom limit to another cartridge', () => {
    const r = recallLoad(wildcat, load('low-map'), [cart({}), lowMap]);
    expect(r.cartridgeId).toBe('low-map');
    expect(r.standard).toBe('SAAMI');
    expect(Number.isNaN(r.customLimitPsi)).toBe(true);
    expect(pressureLimit(r, lowMap).limitPa).toBeCloseTo(U.psiToPa(28000) * 0.95, 3);
  });
  it('keeps the limit when the cartridge is unchanged, and clears it for an unknown cartridge', () => {
    expect(recallLoad(wildcat, load('test-cart'), [cart({})]).customLimitPsi).toBe(68000);
    const r = recallLoad(wildcat, load('gone'), []);
    expect(Number.isNaN(r.customLimitPsi)).toBe(true);
    expect(pressureLimit(r, null).limitPa).toBeNull();
  });
  it('keeps an explicit C.I.P. choice when the new cartridge has a C.I.P. Pmax', () => {
    expect(standardForCartridge('CIP', cart({}))).toBe('CIP');
    expect(standardForCartridge('SAAMI', cart({}))).toBe('SAAMI');
    expect(standardForCartridge('CIP', lowMap)).toBe('SAAMI');
    expect(standardForCartridge('SAAMI', cart({ saamiMapPsi: null }))).toBe('CIP');
    expect(limitForCartridge({ cartridgeId: 'a', standard: 'CIP', customLimitPsi: NaN }, 'test-cart', cart({})).standard).toBe('CIP');
  });
  it('shows the CUP-only note whatever the standard', () => {
    const cup = cart({ saamiMapPsi: null, saamiMapCup: 53500, cipPmaxBar: null });
    const base: BuilderState = { ...EMPTY_BUILDER, cartridgeId: 'test-cart' };
    expect(pressureLimit({ ...base, standard: 'custom' }, cup).note).toMatch(/CUP only \(53,500 CUP\)/);
    expect(pressureLimit({ ...base, standard: 'custom', customLimitPsi: 50000 }, cup).note).toMatch(/CUP only/);
    expect(pressureLimit({ ...base, standard: 'CIP' }, cup).note).toMatch(/CUP only/);
    expect(pressureLimit({ ...base, standard: 'SAAMI' }, cup).note).toMatch(/CUP only/);
    expect(pressureLimit({ ...base, standard: 'custom' }, cart({})).note).not.toMatch(/CUP/);
  });
});

describe('imported powder records cannot embed a shipped-looking model (finding 13)', () => {
  const fake = {
    status: 'calibrated',
    params,
    derivation: 'Fitted to 48 of 474 usable published pressure-tested loads',
    betaRelSigma: 0.001,
    calibration: { points: 48, rmsVelocityFps: 5, rmsPressurePct: 1.5, heldOutPressurePct: 2, grade: 'good', cartridges: [], sources: [] },
  };
  const rec = { id: 'my-lot', manufacturer: 'Test Co', name: 'My lot', form: 'extruded', base: 'single', applications: [], burnRateCharts: [], status: 'unknown', sources: [] };
  it('routes powders[].model through the user-calibrated sanitizer', () => {
    const imp = parseUserImport(JSON.stringify({ powders: [{ ...rec, model: fake }] }));
    const m = imp.powders[0].model!;
    expect(m.status).toBe('user-calibrated');
    expect(m.calibration?.grade).toBeUndefined();
    expect(m.calibration?.heldOutPressurePct).toBeUndefined();
    expect(m.calibration?.rmsPressurePct).toBeNull();
    expect(m.betaRelSigma).toBeUndefined();
    expect(m.derivation.startsWith('Imported from a file.')).toBe(true);
    expect(specForPowderModel(m, 1.7).betaRel).toBeGreaterThanOrEqual(DEFAULT_SPEC_ESTIMATED.betaRel);
  });
  it('drops unusable or "none" models', () => {
    const imp = parseUserImport(JSON.stringify({ powders: [{ ...rec, model: { ...fake, params: { beta: 1 } } }, { ...rec, id: 'b', model: { ...fake, status: 'none' } }] }));
    expect(imp.powders[0].model).toBeUndefined();
    expect(imp.powders[1].model).toBeUndefined();
  });
  it('re-checks models already stored by an older import, without repeating the prefix', () => {
    const db = mergedDb({ ...EMPTY_USER, powders: [{ ...(rec as unknown as Powder), model: fake as unknown as PowderModelEntry }] });
    const p = db.powders.find((x) => x.id === 'my-lot')!;
    expect(p.model?.status).toBe('user-calibrated');
    expect(p.model?.calibration?.grade).toBeUndefined();
    const once = sanitizeImportedModel(fake)!;
    expect(sanitizeImportedModel(once)!.derivation).toBe(once.derivation);
    // An older import in powderModels keeps no pressure-fit claim either.
    const db2 = mergedDb({ ...EMPTY_USER, powderModels: { 'my-lot': { ...once, calibration: { ...once.calibration!, rmsPressurePct: 1.5 } } }, powders: [rec as unknown as Powder] });
    expect(db2.powders.find((x) => x.id === 'my-lot')!.model?.calibration?.rmsPressurePct).toBeNull();
  });
});
