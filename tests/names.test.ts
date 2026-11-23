import { describe, it, expect } from 'vitest';
import { cartridgeKey, powderKey } from '../scripts/names';

describe('cartridgeKey', () => {
  it('joins common spellings', () => {
    expect(cartridgeKey('.308 Win')).toBe(cartridgeKey('308 Winchester'));
    expect(cartridgeKey('6.5 Creedmoor')).toBe(cartridgeKey('6.5mm Creedmoor'.replace('6.5mm', '6.5')));
    expect(cartridgeKey('.30-06 Springfield')).toBe(cartridgeKey('30-06 Sprg'));
    expect(cartridgeKey('.300 Win Mag')).toBe(cartridgeKey('300 Winchester Magnum'));
    expect(cartridgeKey('9mm Luger')).toBe(cartridgeKey('9mm Parabellum'));
    expect(cartridgeKey('.45 ACP')).toBe(cartridgeKey('45 Auto'));
    expect(cartridgeKey('.40 S&W')).toBe(cartridgeKey('40 SW'));
    expect(cartridgeKey('.223 Rem')).toBe(cartridgeKey('223 Remington'));
  });
  it('keeps distinct cartridges distinct', () => {
    expect(cartridgeKey('.300 WSM')).not.toBe(cartridgeKey('.300 Win Mag'));
    expect(cartridgeKey('.38 Special')).not.toBe(cartridgeKey('.38 Super'));
    expect(cartridgeKey('6.5 PRC')).not.toBe(cartridgeKey('6.5 Creedmoor'));
  });
});

describe('powderKey', () => {
  it('normalises spacing and Reloder variants', () => {
    expect(powderKey('IMR 4064')).toBe(powderKey('IMR4064'));
    expect(powderKey('Reloder 16')).toBe(powderKey('RL-16'));
    expect(powderKey('Varget®')).toBe('varget');
  });
});
