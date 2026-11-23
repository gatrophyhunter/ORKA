import { describe, it, expect } from 'vitest';
import { encodeBuilder, decodeBuilder } from '../src/ui/share';
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
});
