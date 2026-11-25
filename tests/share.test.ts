import { describe, it, expect } from 'vitest';
import { encodeBuilder, decodeBuilder, reviewSharedLimit } from '../src/ui/share';
import type { Cartridge } from '../src/data/schema';
import { EMPTY_BUILDER } from '../src/ui/state';

describe('share links', () => {
  it('round-trips the builder state, keeping NaN fields empty', () => {
    const b = { ...EMPTY_BUILDER, cartridgeId: 'x-test', powderId: 'test-powder-a', inputs: { ...EMPTY_BUILDER.inputs, chargeGr: 44.3, coalIn: 2.8 }, standard: 'CIP' as const };
    const h = encodeBuilder(b, '0.1.0');
    const d = decodeBuilder(h)!;
    expect(d.dbVersion).toBe('0.1.0');
    expect(d.builder.cartridgeId).toBe('x-test');
    expect(d.builder.inputs.chargeGr).toBe(44.3);
    expect(Number.isNaN(d.builder.inputs.bulletLengthIn)).toBe(true);
    expect(d.builder.standard).toBe('CIP');
  });
  it('rejects garbage', () => {
    expect(decodeBuilder('#load=%%%')).toBeNull();
    expect(decodeBuilder('#other')).toBeNull();
  });
  // Fictional cartridge: SAAMI 62,000 psi, C.I.P. 4,150 bar.
  const cart = {
    id: 'test-cart', name: 'Test Cartridge A', aliases: [], type: 'rifle', standards: ['SAAMI'], bulletDiameterIn: 0.308, boreDiameterIn: 0.3, grooveDiameterIn: 0.308,
    caseLengthMaxIn: 2.015, trimLengthIn: 2.005, maxCoalIn: 2.8, saamiMapPsi: 62000, saamiMapCup: null, cipPmaxBar: 4150, saamiTwist: null, primerSize: null, caseCapacityGrH2O: [], sources: [],
  } as Cartridge;
  const link = (over: object) => decodeBuilder(encodeBuilder({ ...EMPTY_BUILDER, cartridgeId: 'test-cart', ...over }, '0.1.0'))!.builder;
  it('lists the link\'s standard, limit and margin', () => {
    expect(reviewSharedLimit(link({ standard: 'SAAMI', marginPct: 5 }), cart).summary).toBe('SAAMI MAP 62,000 psi (piezo) − 5 % margin');
    expect(reviewSharedLimit(link({ standard: 'custom', customLimitPsi: 58000, marginPct: 3 }), cart).summary).toBe('Custom limit 58,000 psi − 3 % margin');
    expect(reviewSharedLimit(link({ standard: 'custom', customLimitPsi: 58000, marginPct: -20 }), cart).summary).toMatch(/Safety margin -20 % is outside 0–50 %: 0 % applied\)$/);
    expect(reviewSharedLimit(link({ standard: 'custom' }), cart).summary).toMatch(/^custom standard, no limit set/);
  });
  it('offers the cartridge standard instead of a custom limit above its maximum', () => {
    const r = reviewSharedLimit(link({ standard: 'custom', customLimitPsi: 90000, marginPct: 0 }), cart);
    expect(r.warning).toMatch(/90,000 psi\) is above this cartridge's SAAMI MAP/);
    expect(r.safeBuilder.standard).toBe('SAAMI');
    expect(Number.isNaN(r.safeBuilder.customLimitPsi)).toBe(true);
    const ok = reviewSharedLimit(link({ standard: 'custom', customLimitPsi: 58000 }), cart);
    expect(ok.warning).toBeNull();
    expect(ok.safeBuilder.customLimitPsi).toBe(58000);
  });
  it('drops non-positive custom limits and non-finite margins', () => {
    expect(Number.isNaN(link({ standard: 'custom', customLimitPsi: -5 }).customLimitPsi)).toBe(true);
    expect(link({ marginPct: NaN }).marginPct).toBe(EMPTY_BUILDER.marginPct);
  });
});
