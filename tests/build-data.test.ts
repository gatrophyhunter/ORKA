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

import { applyFixes, normStatus, maxBulletDiameterFor, screenBulletLengths, matchCartridge, isGarandLoad, buildBrass } from '../scripts/build-data';
import type { Bullet, Cartridge } from '../src/data/schema';

const std = [{ url: 'https://example.invalid/standard.pdf', type: 'standard' }];

describe('review fixes (data group)', () => {
  it('adds a notes fix as its own note part and never replaces the evidence lines', () => {
    const items = [{ id: 'c1', notes: 'source note | Evidence: line A | Evidence: line B' }];
    const out = applyFixes(items, { fixes: [{ id: 'c1', field: 'notes', value: 'Two tables disagree.', reason: 'review' }, { id: 'c1', field: 'x', value: 1, reason: 'why' }] });
    const parts = out[0].notes.split(' | ');
    expect(parts).toContain('Evidence: line A');
    expect(parts).toContain('Evidence: line B');
    expect(parts).toContain('Two tables disagree. [review note — review]');
    // A field correction is its own part, so no "Evidence:" line carries non-verbatim text.
    expect(parts.filter((p) => p.startsWith('Evidence: ')).every((p) => !p.includes('[corrected'))).toBe(true);
  });

  it('merges the C.I.P. WSSM twins and the mislabelled "9 mm" row (416 Weath. Mag. sheet) into the SAAMI records', () => {
    const c = buildCartridges([{ key: 'x', data: { cartridges: [
      { name: '223 Winchester Super Short Magnum', aliases: ['223 WSSM'], type: 'rifle', standards: ['SAAMI Z299.4'], saamiMapPsi: 65000, bulletDiameterIn: 0.2245, caseLengthMaxIn: 1.67, maxCoalIn: 2.36, sources: std, evidence: 's' },
      { name: '223 Win. SS Mag.', type: 'rifle', standards: ['C.I.P.'], cipPmaxBar: 4400, bulletDiameterIn: 0.2244, caseLengthMaxIn: 1.6701, maxCoalIn: 2.3598, sources: std, evidence: 'c' },
      { name: '416 Weatherby Magnum', type: 'rifle', standards: ['SAAMI Z299.4'], saamiMapCup: 53500, bulletDiameterIn: 0.416, caseLengthMaxIn: 2.913, maxCoalIn: 3.75, sources: std, evidence: 's' },
      { name: '9 mm', type: 'rifle', standards: ['C.I.P.'], cipPmaxBar: 4400, bulletDiameterIn: 0.4161, caseLengthMaxIn: 2.913, maxCoalIn: 3.75, cip: { sheetHeader: '416 Weath. Mag.' }, sources: std, evidence: 'c' },
    ] } }]);
    expect(c.map((x) => x.id).sort()).toEqual(['223-winchester-super-short-magnum', '416-weatherby-magnum']);
    const wssm = c.find((x) => x.id === '223-winchester-super-short-magnum')!;
    expect([wssm.saamiMapPsi, wssm.cipPmaxBar]).toEqual([65000, 4400]);
    expect(wssm.conflicts ?? []).toEqual([]);
    const wby = c.find((x) => x.id === '416-weatherby-magnum')!;
    expect(wby.cipPmaxBar).toBe(4400);
    expect(wby.saamiMapCup).toBe(53500);
    expect(wby.aliases).not.toContain('9 mm');
    expect(wby.notes).toContain('printed as "9 mm"');
  });

  it('normalises annotated status text case-insensitively and never guesses current', () => {
    expect(normStatus('current (listed in Berger 2026 catalog)')).toBe('current');
    expect(normStatus('DISCONTINUED')).toBe('discontinued');
    expect(normStatus('discontinued (bergerbullets.com product page titled "DISCONTINUED")')).toBe('discontinued');
    expect(normStatus('listed on bergerbullets.com Bullet Reference Charts but not in the 2026 catalog')).toBe('unknown');
    expect(normStatus(null)).toBe('unknown');
    const b = buildBullets([{ key: 'x', data: { bullets: [{ id: 's1', manufacturer: 'M', diameterIn: 0.308, weightGr: 168, status: 'Current (catalog 2026)', sources: src, evidence: 'e' }] } }]);
    expect(b[0].status).toBe('current');
    expect(b[0].notes).toContain('Status as published: Current (catalog 2026)');
  });

  it('widens the bullet range only to the largest shipped cartridge diameter', () => {
    const big = { key: 'x', data: { bullets: [
      { id: 'b577', manufacturer: 'M', diameterIn: 0.583, weightGr: 750, sources: src, evidence: 'e' },
      { id: 'b600', manufacturer: 'M', diameterIn: 0.618, weightGr: 900, sources: src, evidence: 'e' },
      { id: 'bad', manufacturer: 'M', diameterIn: 3.08, weightGr: 168, sources: src, evidence: 'e' },
      { id: 'heavy', manufacturer: 'M', diameterIn: 0.308, weightGr: 900, sources: src, evidence: 'e' },
    ] } };
    expect(buildBullets([big]).map((b) => b.id)).toEqual([]);
    const max = maxBulletDiameterFor([{ bulletDiameterIn: 0.5839 }, { bulletDiameterIn: 0.6201 }, { bulletDiameterIn: null }] as Cartridge[]);
    expect(max).toBeCloseTo(0.6251, 4);
    expect(buildBullets([big], max).map((b) => b.id).sort()).toEqual(['b577', 'b600']);
  });

  it('ships the longest length when the sources disagree, and keeps both values in the notes', () => {
    const b = buildBullets([{ key: 'x', data: { bullets: [
      { id: 'n1', manufacturer: 'M', diameterIn: 0.224, weightGr: 70, lengthIn: 0.965, conflicts: [{ field: 'lengthIn', values: [{ value: 0.965, source: 'web' }, { value: 0.985, source: 'catalog p.5' }] }], sources: src, evidence: 'e' },
      { id: 'n2', manufacturer: 'M', diameterIn: 0.264, weightGr: 120, lengthIn: null, conflicts: [{ field: 'lengthIn', values: [{ value: 1.145, source: 'a' }, { value: 1.252, source: 'b' }] }], sources: src, evidence: 'e' },
      { id: 'n3', manufacturer: 'M', diameterIn: 0.308, weightGr: 168, lengthIn: 1.2, lengthConfidence: 'low', conflicts: [{ field: 'lengthIn', values: [{ value: 1.2 }, { value: 1.3 }] }], sources: src, evidence: 'e' },
    ] } }]);
    const by = (id: string) => b.find((x) => x.id === id)!;
    expect(by('n1').lengthIn).toBe(0.985);
    expect(by('n1').notes).toMatch(/0\.965 and 0\.985 in; the longest \(0\.985 in\)/);
    expect(by('n2').lengthIn).toBe(1.252);
    expect(by('n3').lengthIn).toBeNull(); // low-confidence lengths never ship
  });

  it('withholds only lengths that are too dense or much SHORTER than the model, never longer ones', () => {
    const lenAt = (d: number, w: number, rho: number) => (w * 0.06479891) / (rho * (Math.PI / 4) * (d * 2.54) ** 2) / 2.54;
    const train: Bullet[] = [];
    let k = 0;
    for (const d of [0.204, 0.224, 0.243, 0.257, 0.264, 0.277, 0.284, 0.308, 0.338, 0.375]) {
      for (const w of [50, 60, 70, 80, 90, 100, 120, 140, 160, 180]) {
        const wt = w * (d / 0.264) ** 2;
        train.push({ id: `t${k}`, manufacturer: 'M', line: 'X', name: 'X HPBT', diameterIn: d, weightGr: wt, lengthIn: lenAt(d, wt, 6.5) * (1 + 0.01 * Math.sin(k++)), sources: [] } as unknown as Bullet);
      }
    }
    const mk = (id: string, L: number) => ({ id, manufacturer: 'M', line: 'X', name: 'X HPBT', diameterIn: 0.308, weightGr: 150, lengthIn: L, notes: 'Evidence: e', sources: [] }) as unknown as Bullet;
    const base = lenAt(0.308, 150, 6.5);
    const long = mk('long', base * 1.3); // low density (all-copper, powdered core): kept
    const short = mk('short', base * 0.7); // 30 % short, still under 9.5 g/cm³: withheld by the model test
    const dense = mk('dense', lenAt(0.308, 150, 10)); // denser than 9.5 g/cm³ as a cylinder: withheld
    const all = [...train, long, short, dense];
    expect(screenBulletLengths(all)).toBe(2);
    expect(long.lengthIn).toBeCloseTo(base * 1.3, 6);
    expect(short.lengthIn).toBeNull();
    expect(short.notes).toMatch(/much shorter than similar bullets/);
    expect(dense.lengthIn).toBeNull();
    expect(dense.notes).toMatch(/denser than a solid cylinder/);
  });

  it('matches brass and load labels through aliases and loose keys, but never an improved or "- Long" case to its parent', () => {
    const carts = buildCartridges([{ key: 'x', data: { cartridges: [
      { name: '375 Chey Tac', type: 'rifle', sources: std, evidence: 'e' },
      { name: '7mm Remington Ultra Magnum', aliases: ['7mm REM ULTRA MAG'], type: 'rifle', sources: std, evidence: 'e' },
      { name: '300 Winchester Short Magnum', aliases: ['300 WSM'], type: 'rifle', sources: std, evidence: 'e' },
      { name: '223 Remington', type: 'rifle', sources: std, evidence: 'e' },
      { name: '300 Winchester Magnum', type: 'rifle', sources: std, evidence: 'e' },
      { name: '32 Smith &Wesson Long (32 Colt New Police)', type: 'handgun', sources: std, evidence: 'e' },
    ] } }]);
    const id = (label: string) => matchCartridge(carts, label)?.id ?? null;
    expect(id('375 CheyTac (9.5x77)')).toBe('375-chey-tac');
    expect(id('.375 CheyTac')).toBe('375-chey-tac');
    expect(id('7 mm RUM')).toBe('7mm-remington-ultra-magnum');
    expect(id('7mm RUM (Remington Ultra Magnum)')).toBe('7mm-remington-ultra-magnum');
    expect(id('300 WSM (Winchester Short Magnum)')).toBe('300-winchester-short-magnum');
    expect(id('.223 Remington Ackley Improved')).toBeNull();
    expect(id('300 Winchester Magnum - Long')).toBeNull();
    expect(matchCartridge(carts, '.32 S.&W. Long')?.type ?? 'handgun').toBe('handgun');
  });

  it('keeps matched brass and screens gross capacity errors', () => {
    const carts = buildCartridges([{ key: 'x', data: { cartridges: [{ name: '375 Chey Tac', type: 'rifle', sources: std, evidence: 'e' }] } }]);
    const caps = [160.9, 159.9, 160.3, 59.4];
    const { cases } = buildBrass([{ key: 'b', data: { cases: caps.map((v) => ({ brandId: 'p', cartridge: '375 CheyTac (9.5x77)', waterCapacityGrH2O: v, sources: src, evidence: 'e' })) } }], carts);
    expect(cases.every((c) => c.cartridgeId === '375-chey-tac')).toBe(true);
    expect(cases[3].waterCapacityGrH2O).toBeNull();
    expect(cases[3].notes).toMatch(/59\.4 gr H2O withheld/);
    expect(carts[0].caseCapacityGrH2O.map((e) => e.value)).toEqual([160.9, 159.9, 160.3]);
  });

  it('labels only rows printed as "Garand Load" as reduced, not rows marked "Safe in Garand"', () => {
    expect(isGarandLoad({ notes: "Garand load (caliber/start cells mention Garand). Start-load cells read 'Garand Load' / 'N/A'." })).toBe(true);
    expect(isGarandLoad({ notes: "Garand load (caliber/start cells mention Garand). Start-load cells read 'Safe in Garand' / 'N/A'." })).toBe(false);
    const files = [{ key: 'x', data: {
      cartridges: [{ name: '30-06 Springfield', type: 'rifle', sources: std, evidence: 'e' }],
      loads: [
        { cartridge: '30-06 Springfield', powder: 'P', chargeGr: 40.8, velocityFps: 2785, loadType: 'max', notes: "Start-load cells read 'Safe in Garand' / 'N/A'.", sources: src, evidence: 'e' },
        { cartridge: '30-06 Springfield', powder: 'P', chargeGr: 46.5, velocityFps: 2720, loadType: 'max', notes: "Start-load cells read 'Garand Load' / 'N/A'.", sources: src, evidence: 'e' },
      ],
    } }];
    const loads = buildLoads(files, buildCartridges(files), []);
    expect(loads.map((l) => l.loadType)).toEqual(['max', 'reduced']);
  });

  it('builds a chart-sourced Vihtavuori record only when Vihtavuori\'s own data sheet names it', () => {
    const sds = 'https://example.invalid/N-Powder-High-Energy-N500-series-RELO-en.pdf';
    const { powders } = buildPowders([{ key: 'x', data: {
      powders: [{ manufacturer: 'Nammo Vihtavuori Oy', brand: 'Vihtavuori', name: 'N540', sources: [{ url: sds, type: 'manufacturer', page: 1 }], evidence: 'N540 page | 1.1 Product identifier: N-Powder High Energy, N500-series (RELO) N515, N530, N540 | CAS: 55-63-0 Nitroglycerin Self-classified' }],
      charts: [{ publisher: 'Hodgdon Powder Company', edition: 'test', url: 'https://example.invalid/chart.pdf', orderedNames: ['VIHTAVUORI N530', 'VIHTAVUORI N540', 'VIHTAVUORI N32C - TIN STAR', 'VIHTAVUORI N999'] }],
    } }]);
    const ids = powders.map((p) => p.id).sort();
    expect(ids).toEqual(['vihtavuori-n530', 'vihtavuori-n540']);
    const n530 = powders.find((p) => p.id === 'vihtavuori-n530')!;
    expect(n530.base).toBe('double');
    expect(n530.burnRateCharts[0].rank).toBe(1);
    expect(n530.sources.map((s) => s.url)).toContain(sds);
    expect(n530.notes).toContain('Evidence: 1.1 Product identifier');
  });
});
