import { describe, it, expect } from 'vitest';
import { buildBullets, buildCartridges, buildPowders, buildLoads } from '../scripts/build-data';

const src = [{ url: 'https://example.invalid/catalog.pdf', type: 'manufacturer', page: 3 }];

describe('data build policy', () => {
  it('drops records without a source URL or evidence line', () => {
    const files = [{ key: 'x', data: { bullets: [
      { manufacturer: 'TestCo', line: 'T', diameterIn: 0.308, weightGr: 168, sources: src, evidence: 'T 168 .308' },
      { manufacturer: 'TestCo', line: 'T', diameterIn: 0.308, weightGr: 175, sources: src },
      { manufacturer: 'TestCo', line: 'T', diameterIn: 0.308, weightGr: 180, sources: [], evidence: 'x' },
    ] } }];
    const b = buildBullets(files);
    expect(b.length).toBe(1);
    expect(b[0].weightGr).toBe(168);
    expect(b[0].sources[0].url).toBe(src[0].url);
  });
  it('rejects physically implausible bullet values and lengths', () => {
    const b = buildBullets([{ key: 'x', data: { bullets: [
      { manufacturer: 'TestCo', diameterIn: 3.08, weightGr: 168, sources: src, evidence: 'e' },
      { manufacturer: 'TestCo', diameterIn: 0.308, weightGr: 168, lengthIn: 12.15, sources: src, evidence: 'e', id: 'ok' },
    ] } }]);
    expect(b.length).toBe(1);
    expect(b[0].lengthIn).toBeNull();
  });
  it('merges SAAMI and CIP records of one cartridge and keeps conflicts', () => {
    const c = buildCartridges([{ key: 'x', data: { cartridges: [
      { name: '.308 Win', type: 'rifle', standards: ['SAAMI'], saamiMapPsi: 62000, maxCoalIn: 2.81, sources: src, evidence: 'a' },
      { name: '308 Winchester', type: 'rifle', standards: ['CIP'], cipPmaxBar: 4150, maxCoalIn: 2.795, sources: [{ url: 'https://example.invalid/cip.pdf', type: 'standard' }], evidence: 'b' },
    ] } }]);
    expect(c.length).toBe(1);
    expect(c[0].saamiMapPsi).toBe(62000);
    expect(c[0].cipPmaxBar).toBe(4150);
    expect(c[0].conflicts?.some((k) => k.field === 'maxCoalIn')).toBe(true);
    expect(c[0].standards.sort()).toEqual(['CIP', 'SAAMI']);
  });
  it('matches chart names to powders and loads to powders/cartridges', () => {
    const files = [{ key: 'x', data: {
      powders: [
        { manufacturer: 'Hodgdon', name: 'Test Varget', sources: src, evidence: 'e' },
        { manufacturer: 'IMR', name: 'IMR 9999', sources: src, evidence: 'e' },
      ],
      charts: [{ publisher: 'Hodgdon', edition: 'test', url: src[0].url, orderedNames: ['IMR 9999', 'Test Varget', 'Unknown Powder'] }],
      cartridges: [{ name: '.308 Win', type: 'rifle', sources: src, evidence: 'e' }],
      loads: [{ cartridge: '308 Winchester', powder: 'IMR9999', powderMfr: 'IMR', chargeGr: 40, velocityFps: 2500, pressure: 50000, pressureUnit: 'psi', sources: src, evidence: 'e' }],
    } }];
    const { powders, charts } = buildPowders(files);
    expect(charts[0].orderedPowderIds[0]).toBe('imr-imr-9999');
    expect(charts[0].orderedPowderIds[2]).toBe('name:Unknown Powder');
    expect(powders.find((p) => p.id === 'imr-imr-9999')!.burnRateCharts[0].rank).toBe(1);
    const carts = buildCartridges(files);
    const loads = buildLoads(files, carts, powders);
    expect(loads[0].powderId).toBe('imr-imr-9999');
    expect(loads[0].cartridgeId).toBe(carts[0].id);
  });
  it('never converts CUP into psi', () => {
    const files = [{ key: 'x', data: { loads: [{ cartridge: 'x', powder: 'p', chargeGr: 1, velocityFps: 1, pressure: 40000, pressureUnit: 'CUP', sources: src, evidence: 'e' }] } }];
    const loads = buildLoads(files, [], []);
    expect(loads[0].pressureUnit).toBe('CUP');
    expect(loads[0].pressure).toBe(40000);
  });
});
