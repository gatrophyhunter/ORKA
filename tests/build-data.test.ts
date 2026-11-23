import { describe, it, expect } from 'vitest';
import { applyCatalogCrossChecks, isHigherPressureSection, buildBullets, buildCartridges, buildPowders, buildLoads } from '../scripts/build-data';

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
  it('applies a maker catalog cross-check: fills exact-match gaps, keeps both values on disagreement, skips flagged and suffix matches', () => {
    const web = { key: 'web', data: { bullets: [
      { id: 'mk-1', manufacturer: 'MakerCo', line: 'CX', diameterIn: 0.277, weightGr: 120, bcG1: 0.4, bcG7: null, construction: 'monolithic-copper', tip: 'polymer tip', sources: src, evidence: 'a | b' },
      { id: 'mk-2', manufacturer: 'MakerCo', line: 'CX', diameterIn: 0.257, weightGr: 90, bcG1: 0.273, bcG7: null, construction: 'monolithic-copper', sources: src, evidence: 'c' },
      { id: 'mk-3-75', manufacturer: 'MakerCo', line: 'SP', diameterIn: 0.308, weightGr: 150, bcG1: null, sources: src, evidence: 'd' },
    ] } };
    const cat = { key: 'cat', data: {
      meta: { documents: [{ url: 'https://example.invalid/2027.pdf', title: 'MakerCo 2027 Catalog' }] },
      bullets: [{ id: 'mk-9', manufacturer: 'MakerCo', line: 'CX®', diameterIn: 0.277, weightGr: 100, bcG1: 0.262, sources: src, evidence: 'CX | .277 | 100' }],
      crossCheck: [
        { id: 'mk-1', field: 'bcG7', web: null, catalog: 0.2, page: 7, evidence: 'row | 1', kind: 'web-missing', match: 'exact (web sku 1)' },
        { id: 'mk-1', field: 'bcG1', web: 0.4, catalog: 0.41, page: 7, evidence: 'row | 1', kind: 'value-mismatch', match: 'exact (web sku 1)' },
        { id: 'mk-2', field: 'bcG7', web: null, catalog: 0.246, page: 8, evidence: 'row | 2', kind: 'web-missing', match: 'exact (web sku 2)', catalogCheck: 'ratio implausible' },
        { id: 'mk-3-75', field: 'bcG1', web: null, catalog: 0.338, page: 9, evidence: 'row | 3', kind: 'web-missing', match: 'suffix (web sku 3-75)' },
      ],
    } };
    const bullets = buildBullets([web, cat]);
    const counts = applyCatalogCrossChecks(bullets, [web, cat]);
    expect(counts).toEqual({ filled: 1, disagreements: 1, skippedFlagged: 1, skippedSuffix: 1, constructionFromLine: 1 });
    const by = (id: string) => bullets.find((b) => b.id === id)!;
    expect(by('mk-1').bcG7).toBe(0.2);
    expect(by('mk-1').sources.some((s) => s.url === 'https://example.invalid/2027.pdf' && s.page === 7)).toBe(true);
    expect(by('mk-1').bcG1).toBe(0.4); // web value kept on disagreement
    expect(by('mk-1').bcNotes).toContain('.410');
    expect(by('mk-2').bcG7).toBeNull(); // flagged printed values are never adopted
    expect(by('mk-2').bcNotes).toMatch(/misprint/);
    expect(by('mk-3-75').bcG1).toBeNull(); // suffix matches are not filled
    expect(by('mk-9').construction).toBe('monolithic-copper');
    expect(by('mk-9').tip).toBe('polymer tip');
    // Evidence keeps its inner separators out of the note-part separator.
    expect(by('mk-1').notes).toContain('Evidence: a · b');
  });
  it('demotes only higher-pressure firearm sections, never aliases or the standard-level section', () => {
    expect(isHigherPressureSection('45-70 Government (Lever Actions)')).toBe(true);
    expect(isHigherPressureSection('45-70 Government (Modern Rifles)')).toBe(true);
    expect(isHigherPressureSection('45-70 Government (Trapdoor Rifles)')).toBe(false);
    expect(isHigherPressureSection('7,62 x 53R (7,62 Russian)')).toBe(false);
    expect(isHigherPressureSection('8 x 57 IS (8 mm Mauser)')).toBe(false);
    expect(isHigherPressureSection('308 Winchester')).toBe(false);
  });
});
