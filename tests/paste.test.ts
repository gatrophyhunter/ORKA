import { describe, it, expect } from 'vitest';
import { parseMeasurements } from '../src/ui/CalibrateTab';

describe('chronograph paste parser', () => {
  it('parses comma-separated imperial lines and skips headers', () => {
    const r = parseMeasurements('charge,velocity\n42.0, 2610\n43.0,2655, 58000, hot day\n', 'imperial');
    expect(r.rows.length).toBe(2);
    expect(r.rows[1]).toEqual({ chargeGr: 43, velFps: 2655, pPsi: 58000, label: 'hot day' });
    expect(Number.isNaN(r.rows[0].pPsi)).toBe(true);
  });
  it('accepts decimal commas with semicolons or tabs and converts metric', () => {
    const r = parseMeasurements('2,72;795,5\n2,80\t810', 'metric');
    expect(r.rows.length).toBe(2);
    expect(r.rows[0].chargeGr).toBeCloseTo(2.72 / 0.06479891, 6);
    expect(r.rows[0].velFps).toBeCloseTo(795.5 / 0.3048, 6);
  });
});
