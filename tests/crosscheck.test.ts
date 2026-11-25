import { describe, it, expect, vi } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  comparePublishedPressure,
  loadsAboveReference,
  publishedReference,
  ReferencePressureNote,
  referencePressureCheck,
  scopeWarnings,
  type LimitContext,
} from '../src/ui/CrossCheck';
import { createPublishedStore, type Packed } from '../src/ui/published';
import { searchRunKey } from '../src/ui/SearchTab';
import { ladderFieldRange, ladderRunKey, PublishedRefBanner } from '../src/ui/LadderTab';
import { EMPTY_BUILDER, type BuilderState } from '../src/ui/state';
import type { DerivedLoad } from '../src/ui/useLoad';
import type { Cartridge, Powder, ValidationLoad } from '../src/data/schema';
import * as U from '../src/engine/units';

// Fictional test fixtures only.
const builder: BuilderState = {
  ...EMPTY_BUILDER,
  cartridgeId: 'test-cart',
  bulletId: 'test-bullet',
  powderId: 'test-powder',
  inputs: {
    ...EMPTY_BUILDER.inputs,
    boreDiameterIn: 0.3,
    grooveDiameterIn: 0.308,
    caseLengthIn: 2.0,
    caseCapacityGrH2O: 56,
    barrelLengthIn: 24,
    bulletWeightGr: 150,
    bulletDiameterIn: 0.308,
    bulletLengthIn: 1.1,
    coalIn: 2.8,
    chargeGr: 40,
  },
};
const withInputs = (b: BuilderState, p: Partial<BuilderState['inputs']>): BuilderState => ({ ...b, inputs: { ...b.inputs, ...p } });

describe('search results are not cleared by loading a result row', () => {
  const k = searchRunKey(builder);
  it('ignores the builder charge and powder, which the search does not use', () => {
    expect(searchRunKey(withInputs(builder, { chargeGr: 45.78 }))).toBe(k);
    expect(searchRunKey({ ...builder, powderId: 'other-powder' })).toBe(k);
  });
  it('changes with geometry, cartridge, standard, limit and margin', () => {
    expect(searchRunKey(withInputs(builder, { caseCapacityGrH2O: 55 }))).not.toBe(k);
    expect(searchRunKey(withInputs(builder, { coalIn: 2.75 }))).not.toBe(k);
    expect(searchRunKey(withInputs(builder, { powderTempF: 20 }))).not.toBe(k);
    expect(searchRunKey({ ...builder, cartridgeId: 'other-cart' })).not.toBe(k);
    expect(searchRunKey({ ...builder, standard: 'CIP' })).not.toBe(k);
    expect(searchRunKey({ ...builder, standard: 'custom', customLimitPsi: 50000 })).not.toBe(k);
    expect(searchRunKey({ ...builder, marginPct: 10 })).not.toBe(k);
  });
});

describe('ladder results are not cleared by the ladder\'s own "use" button', () => {
  const prop = { propellant: null, heatScale: 1 };
  const k = ladderRunKey(builder, prop);
  it('ignores the builder charge', () => {
    expect(ladderRunKey(withInputs(builder, { chargeGr: 38 }), prop)).toBe(k);
  });
  it('changes with geometry, powder, powder model, temperature and shot-start', () => {
    expect(ladderRunKey(withInputs(builder, { barrelLengthIn: 20 }), prop)).not.toBe(k);
    expect(ladderRunKey({ ...builder, powderId: 'other-powder' }, prop)).not.toBe(k);
    expect(ladderRunKey(builder, { propellant: null, heatScale: 1.1 })).not.toBe(k);
    expect(ladderRunKey(withInputs(builder, { powderTempF: 100 }), prop)).not.toBe(k);
    expect(ladderRunKey(withInputs(builder, { shotStartPsi: 5000 }), prop)).not.toBe(k);
  });
  it('keeps untyped start/end fields on the range of the rows shown after "use" changes the builder charge', () => {
    const untyped: [number, number] = [NaN, NaN];
    const first = ladderFieldRange(untyped, null, 44);
    expect(first).toEqual([39.6, 46.2]);
    expect(ladderFieldRange(untyped, first, 39.6)).toEqual([39.6, 46.2]);
    // No rows on screen: the defaults follow the builder charge again.
    expect(ladderFieldRange(untyped, null, 39.6)).toEqual([35.6, 41.6]);
    // Typed values always win.
    expect(ladderFieldRange([38, NaN], first, 39.6)).toEqual([38, 46.2]);
  });
});

describe('published-load table loading', () => {
  const packed: Packed = {
    v: 1,
    s: ['test-cart', 'test-powder', 'Test Bullets', 'TB', 'max', 'bar', 'https://example.invalid/data.pdf'],
    r: [[0, 1, 150, 2, 3, 4, 46, 2700, 3000, 5, 24, 3.1, -1, -1, 6, 12, -1]],
  };
  it('does not cache a failure: the next load retries and clears the failed flag', async () => {
    const fetch = vi.fn().mockRejectedValueOnce(new Error('chunk failed')).mockResolvedValue(packed);
    const store = createPublishedStore(fetch);
    expect(await store.load()).toEqual([]);
    expect(store.failed()).toBe(true);
    expect(store.cached()).toBeNull();
    const rows = await store.load();
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(store.failed()).toBe(false);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ cartridgeId: 'test-cart', powderId: 'test-powder', chargeGr: 46, pressure: 3000, pressureUnit: 'bar', loadType: 'max' });
    await store.load();
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it('treats a missing or malformed file as a failure, not as "no published data"', async () => {
    const missing = createPublishedStore(undefined);
    await missing.load();
    expect(missing.failed()).toBe(true);
    const bad = createPublishedStore(() => Promise.resolve({ v: 1 } as unknown as Packed));
    await bad.load();
    expect(bad.failed()).toBe(true);
    expect(bad.cached()).toBeNull();
  });
});

const load = (t: string, ch: number, pressure: number | null, unit: ValidationLoad['pressureUnit']): ValidationLoad => ({
  cartridge: 'Test Cartridge',
  cartridgeId: 'test-cart',
  bulletMfr: 'Test',
  bulletModel: 'TB',
  bulletWeightGr: 150,
  coalIn: 3,
  barrelLengthIn: 24,
  powder: 'test-powder',
  powderId: 'test-powder',
  chargeGr: ch,
  velocityFps: 2600,
  pressure,
  pressureUnit: unit,
  loadType: t,
  sources: [],
});
const saami = (psi: number, cup: number | null = null): LimitContext => ({ standard: 'SAAMI', mapPa: U.psiToPa(psi), saamiMapCup: cup });
const cip = (bar: number): LimitContext => ({ standard: 'CIP', mapPa: U.barToPa(bar), saamiMapCup: null });

describe('published pressure against the applied limit', () => {
  const rows = [load('start', 40, 2000, 'bar'), load('max', 46, 3000, 'bar'), load('max', 47, 3100, 'bar')];
  it('flags a reference published above the SAAMI MAP being applied, and finds the highest load within it', () => {
    const ref = publishedReference(rows);
    expect(ref).toEqual({ charge: 46, kind: 'max' });
    const chk = referencePressureCheck(rows, ref, saami(40000));
    expect(chk?.ref.status).toBe('above');
    expect(chk?.ref.limitText).toBe('40,000 psi');
    expect(chk?.ref.convertedText).toBe(`about ${Math.round(U.paToPsi(U.barToPa(3000))).toLocaleString('en-US')} psi`);
    expect(chk?.withinCharge).toBe(40);
    const html = renderToStaticMarkup(createElement(ReferencePressureNote, { rows, reference: ref, ctx: saami(40000), chargeGr: 44 }));
    expect(html).toContain('published-above-limit');
    expect(html).toContain('above the SAAMI MAP you are applying (40,000 psi)');
    expect(html).toContain('at or below 40,000 psi is 40.0 gr');
    expect(html).toContain('at or below 40,000 psi is 40.0 gr. Your charge (44.0 gr) is above it.');
    expect(renderToStaticMarkup(createElement(ReferencePressureNote, { rows, reference: ref, ctx: saami(40000), chargeGr: 39 }))).not.toContain('Your charge');
  });
  it('never points below-limit guidance above the reference (lowest max)', () => {
    // Two bullets of the same weight: A's max (46 gr) is published above the limit, B's higher max (47.5 gr) within it.
    const r = [load('start', 42, 35000, 'psi'), load('max', 46, 41000, 'psi'), load('max', 47.5, 39000, 'psi')];
    const ref = publishedReference(r);
    expect(ref).toEqual({ charge: 46, kind: 'max' });
    const chk = referencePressureCheck(r, ref, saami(40000));
    expect(chk?.ref.status).toBe('above');
    expect(chk?.withinCharge).toBe(42);
    const html = renderToStaticMarkup(createElement(ReferencePressureNote, { rows: r, reference: ref, ctx: saami(40000), chargeGr: 47 }));
    expect(html).not.toContain('47.5 gr');
    expect(html).toContain('below it that the maker publishes at or below 40,000 psi is 42.0 gr');
    expect(html).toContain('Your charge (47.0 gr) is above it.');
    // A row at the reference charge that is within the limit is not offered either.
    const same = [load('max', 46, 41000, 'psi'), load('max', 46, 39000, 'psi')];
    expect(referencePressureCheck(same, publishedReference(same), saami(40000))?.withinCharge).toBeNull();
  });
  it('keeps the reference charge (lowest max) unchanged', () => {
    expect(publishedReference(rows)?.charge).toBe(46);
  });
  it('compares bar with a C.I.P. Pmax without conversion, and psi with it after conversion', () => {
    expect(comparePublishedPressure(load('max', 46, 3000, 'bar'), cip(3500))).toMatchObject({ status: 'within', convertedText: null, limitText: '3,500 bar' });
    const psiRow = comparePublishedPressure(load('max', 46, 52000, 'psi'), cip(3500));
    expect(psiRow.status).toBe('above');
    expect(psiRow.convertedText).toBe(`about ${Math.round(U.paToBar(U.psiToPa(52000))).toLocaleString('en-US')} bar`);
  });
  it('notes a converted pressure that is within the limit, without a warning', () => {
    const r = [load('max', 46, 2500, 'bar')];
    const html = renderToStaticMarkup(createElement(ReferencePressureNote, { rows: r, reference: publishedReference(r), ctx: saami(40000) }));
    expect(html).toContain('published-unit-note');
    expect(html).not.toContain('published-above-limit');
  });
  it('never converts CUP: compared only with a SAAMI CUP MAP', () => {
    expect(comparePublishedPressure(load('max', 46, 47000, 'CUP'), saami(50000, 46000)).status).toBe('above');
    expect(comparePublishedPressure(load('max', 46, 45000, 'CUP'), saami(50000, 46000)).status).toBe('within');
    expect(comparePublishedPressure(load('max', 46, 47000, 'CUP'), saami(50000)).status).toBe('not-comparable');
    expect(comparePublishedPressure(load('max', 46, 47000, 'CUP'), cip(3500)).status).toBe('not-comparable');
  });
  it('does not guess for loads published without a pressure', () => {
    const r = [load('start', 40, null, null), load('max', 46, null, null)];
    const chk = referencePressureCheck(r, publishedReference(r), saami(40000));
    expect(chk?.ref.status).toBe('no-pressure');
    expect(chk?.withinCharge).toBeNull();
    const html = renderToStaticMarkup(createElement(ReferencePressureNote, { rows: r, reference: publishedReference(r), ctx: saami(40000) }));
    expect(html).toContain('publishes no pressure for this maximum');
  });
  it('ignores section maxima when finding the highest load within the limit', () => {
    const r = [load('section-max', 45, 2300, 'bar'), load('start', 40, 2000, 'bar'), load('max', 46, 3000, 'bar')];
    expect(referencePressureCheck(r, publishedReference(r), saami(40000))?.withinCharge).toBe(40);
  });
  it('checks single-load references against their own rows', () => {
    const r = [load('other', 8, 30000, 'psi')];
    const ref = publishedReference(r);
    expect(ref).toEqual({ charge: 8, kind: 'single' });
    expect(referencePressureCheck(r, ref, saami(25000))?.ref.status).toBe('above');
  });
  it('says nothing when no limit is set', () => {
    const r = [load('max', 46, 3000, 'bar')];
    const html = renderToStaticMarkup(createElement(ReferencePressureNote, { rows: r, reference: publishedReference(r), ctx: { standard: 'SAAMI', mapPa: null, saamiMapCup: null } }));
    expect(html).toBe('');
  });
});

describe('ladder banner wording', () => {
  it('does not call a single-load reference a maximum', () => {
    const rows = [load('other', 7.5, 18000, 'psi'), load('other', 8, 20000, 'psi')];
    const single = renderToStaticMarkup(createElement(PublishedRefBanner, { reference: { charge: 8, kind: 'single' }, rows }));
    expect(single).not.toMatch(/published maximum/);
    expect(single).toContain('no maximum');
    expect(single).toContain('only single loads');
    expect(single).toContain('8.0 gr');
    expect(single).not.toContain('does not use as a ceiling');
    const maxRows = [load('max', 43.2, null, null)];
    const max = renderToStaticMarkup(createElement(PublishedRefBanner, { reference: { charge: 43.2, kind: 'max' }, rows: maxRows }));
    expect(max).toContain('published maximum');
  });
  it('names the loads listed above a single-load reference instead of calling it the highest load', () => {
    // A single load in the cartridge-standard section; start loads and maxima only in higher-pressure firearm sections.
    const rows = [load('other', 28, 19000, 'psi'), load('start', 29, 23000, 'psi'), load('section-max', 34, 27000, 'psi'), load('start', 34, 32000, 'psi')];
    const ref = publishedReference(rows);
    expect(ref).toEqual({ charge: 28, kind: 'single' });
    expect(loadsAboveReference(rows, 28)).toEqual(['start loads', 'maxima for a higher-pressure firearm section (e.g. lever or modern rifles)']);
    const html = renderToStaticMarkup(createElement(PublishedRefBanner, { reference: ref, rows }));
    expect(html).not.toContain('only single loads');
    expect(html).not.toContain('every published load');
    expect(html).toContain('no maximum for these components at the cartridge standard');
    expect(html).toContain('loads above 28.0 gr are start loads and maxima for a higher-pressure firearm section');
    expect(loadsAboveReference([load('other', 8, null, null), load('start', 7, null, null)], 8)).toEqual([]);
  });
});

describe('charge-extrapolation warning per cartridge', () => {
  const cart = { id: 'test-cart', name: 'Test Cartridge A' } as Cartridge;
  const powder = (cal: NonNullable<Powder['model']>['calibration']): Powder =>
    ({ id: 'test-powder', name: 'Test Powder A', model: { status: 'calibrated', params: {} as never, derivation: '', calibration: cal } }) as unknown as Powder;
  const derived = (p: Powder) => ({ cartridge: cart, powder: p }) as unknown as DerivedLoad;
  const base = { points: 20, rmsVelocityFps: 30, rmsPressurePct: 8, cartridges: ['test-cart', 'other-cart'], sources: [], chargeRangeGr: [20, 77] as [number, number] };
  const outside = (w: string[]) => w.some((x) => /outside the charges/.test(x));
  it('uses the current cartridge\'s range on a multi-cartridge model', () => {
    const p = powder({ ...base, chargeRangeByCartridge: { 'test-cart': [40, 46], 'other-cart': [20, 77] } });
    expect(outside(scopeWarnings(derived(p), 60))).toBe(true);
    expect(outside(scopeWarnings(derived(p), 35))).toBe(true);
    expect(outside(scopeWarnings(derived(p), 44))).toBe(false);
  });
  it('without per-cartridge ranges, keeps the single-cartridge check only', () => {
    expect(outside(scopeWarnings(derived(powder(base)), 60))).toBe(false);
    const single = powder({ ...base, cartridges: ['test-cart'], chargeRangeGr: [40, 46] });
    expect(outside(scopeWarnings(derived(single), 50))).toBe(true);
  });
  it('ignores a malformed per-cartridge range', () => {
    const p = powder({ ...base, cartridges: ['test-cart'], chargeRangeGr: [40, 46], chargeRangeByCartridge: { 'test-cart': [50] as unknown as [number, number] } });
    expect(outside(scopeWarnings(derived(p), 48))).toBe(true);
  });
});
