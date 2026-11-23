// Build src/data/db.json from the extracted, verified research files in research/raw2/.
//
//   npx tsx scripts/build-data.ts
//
// Policy (docs/DATA.md):
//  - Only records that carry a source URL and an evidence line from a primary document are shipped.
//  - Sources that verification judged "unreliable" are excluded; individual records listed in
//    research/raw2/_review.json (exclude / fix) are applied.
//  - Round-1 snippet-only research (research/raw/) is never shipped.

import fs from 'node:fs';
import path from 'node:path';
import type {
  Bullet, BrassBrand, BrassCase, BurnRateChart, Cartridge, Database, Powder, PowderModelEntry, Source, ValidationLoad,
} from '../src/data/schema';
import { cartridgeKey, cartridgeKeyLoose, makerKey, powderKey, slug } from './names';
import { estimateFromCharts } from './estimate';
import { bulletFeatures, fitLengthModel } from './bullet-length';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const RAW = path.join(ROOT, 'research/raw2');
const OUT = path.join(ROOT, 'src/data/db.json');
const MODELS = path.join(ROOT, 'src/data/powder-models.json');
const PUBLISHED = path.join(ROOT, 'src/data/published-loads.json');
const BUILD_DIR = path.join(ROOT, 'research/build');
/** Set ORKA_SHIP_PUBLISHED=0 to build without the published-load cross-check table. */
const SHIP_PUBLISHED = process.env.ORKA_SHIP_PUBLISHED !== '0';

interface Review {
  excludeSources?: string[];
  excludeRecords?: Record<string, string>; // id -> reason
  fixes?: { id: string; field: string; value: unknown; reason: string }[];
}

const readJson = (p: string): any => (fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, 'utf8')) : null);
const review: Review = readJson(path.join(RAW, '_review.json')) ?? {};
const excluded = new Set(review.excludeSources ?? []);

function rawFiles(): { key: string; data: any }[] {
  if (!fs.existsSync(RAW)) return [];
  return fs
    .readdirSync(RAW)
    .filter((f) => f.endsWith('.json') && !f.startsWith('_'))
    .map((f) => ({ key: f.replace(/\.json$/, ''), data: readJson(path.join(RAW, f)) }))
    .filter((x) => x.data && !excluded.has(x.key));
}

/** One "Evidence: …" note part. Extractors join table cells / JSON fields with " | ", which is also the note-part
 * separator that later splits notes from evidence, so inner separators become " · ". */
const evidencePart = (e: unknown) => `Evidence: ${String(e ?? '').replace(/\s\|\s/g, ' · ')}`;

const num = (v: unknown): number | null => {
  if (v === null || v === undefined || v === '') return null;
  const n = typeof v === 'number' ? v : Number(String(v).replace(/[,"”]/g, ''));
  return Number.isFinite(n) ? n : null;
};
const str = (v: unknown): string | null => (v === null || v === undefined || v === '' ? null : String(v));
const arr = <T>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);

function sourcesOf(r: any): Source[] {
  return arr<any>(r.sources)
    .filter((s) => s && typeof s.url === 'string' && /^https?:\/\//.test(s.url))
    .map((s) => ({ url: s.url, type: s.type ?? 'manufacturer', fields: s.fields, ...(s.page != null ? { page: s.page } : {}), ...(s.retrieved ? { retrieved: s.retrieved } : {}) } as Source));
}

function shippable(r: any): boolean {
  return sourcesOf(r).length > 0 && typeof r.evidence === 'string' && r.evidence.trim().length > 0;
}

function applyFixes<T extends { id: string }>(items: T[]): T[] {
  const ex = review.excludeRecords ?? {};
  const out = items.filter((x) => !(x.id in ex));
  for (const f of review.fixes ?? []) {
    const it = out.find((x) => x.id === f.id) as any;
    if (it) {
      it[f.field] = f.value;
      it.notes = `${it.notes ? it.notes + ' ' : ''}[corrected: ${f.field} — ${f.reason}]`;
    }
  }
  return out;
}

const dropped: Record<string, number> = {};
const SCOPE = process.env.ORKA_SCOPE ?? 'rifle';
/** Fit grade from the worse of in-sample RMS and held-out median pressure error; no pressure data = 'unvalidated'. */
function gradeModel(m: PowderModelEntry): PowderModelEntry {
  const c = m.calibration;
  if (!c) return m;
  const rms = typeof c.rmsPressurePct === 'number' ? c.rmsPressurePct : null;
  const held = typeof c.heldOutPressurePct === 'number' ? c.heldOutPressurePct : null;
  const eff = rms === null && held === null ? null : Math.max(rms ?? 0, held ?? 0);
  const grade = eff === null ? 'unvalidated' : eff <= 10 ? 'good' : eff <= 20 ? 'fair' : 'poor';
  return { ...m, calibration: { ...c, grade } };
}
const LOAD_POWDER_ALIASES: Record<string, string> = {
  'accurate|2015': '2015br',
  'shooters-world|precisionrifle': 'precision',
  'shooters-world|sbr-socom': 'socom',
  'shooters-world|sbrsocom': 'socom',
};
/** Handgun and muzzleloader projectiles (by the maker's own category, or by product-line name where none is given). */
function isNonRifleBullet(b: Bullet & { use?: string | null }): boolean {
  if (b.use && /handgun|pistol|muzzle/i.test(b.use)) return true;
  return /handgun|personal protection|\bxpb\b|tac-xp\b|\bcprn\b|\bcpfn\b|\bmz\b|spit-?fire|muzzle ?loader|sabot/i.test(`${b.line} ${b.name}`);
}
const CANISTER_BRANDS = new Set(['hodgdon', 'imr', 'winchester', 'alliant', 'vihtavuori', 'norma', 'reload-swiss', 'shooters-world', 'accurate', 'ramshot', 'adi']);
const cleanName = (s: string) => s.replace(/[®™]/g, '').replace(/\s+/g, ' ').trim();
const drop = (k: string) => (dropped[k] = (dropped[k] ?? 0) + 1);

// ---------------------------------------------------------------- cartridges
/** C.I.P. names of cartridges that SAAMI lists under another name (same cartridge; found by the verifier). */
const CIP_SAAMI_TWINS: Record<string, string> = {
  '9 mm Browning court': '380 Automatic',
  '7,65 mm Browning': '32 Automatic',
  '6,35 Browning': '25 Automatic',
  '7,65 Parabellum': '30 Luger (7.65mm)',
  '9 mm Makarov': '9x18 Makarov',
  '8 x 57 IS': '8mm Mauser (8x57)',
  '32 S&W Long': '32 Smith &Wesson Long (32 Colt New Police)',
  '38 S&W': '38 Smith &Wesson (38 Colt New Police)',
  '9,3 x 66 Sako': '370 Sako Magnum',
};
export function buildCartridges(files: { key: string; data: any }[]): Cartridge[] {
  const byKey = new Map<string, Cartridge>();
  for (const f of files) {
    for (const r of arr<any>(f.data.cartridges)) {
      if (!shippable(r) || !r.name) {
        drop('cartridge (no source/evidence)');
        continue;
      }
      const key = cartridgeKey(CIP_SAAMI_TWINS[r.name] ?? r.name);
      // C.I.P. Pmax measured by the crusher method is not comparable with piezo limits: never ship it as Pmax.
      const crusher = /crusher/i.test(String(r.cip?.sheetMethod ?? r.cip?.method ?? ''));
      const c: Cartridge = {
        id: key,
        name: r.name,
        aliases: arr<string>(r.aliases),
        type: r.type === 'handgun' ? 'handgun' : 'rifle',
        standards: arr<string>(r.standards),
        bulletDiameterIn: num(r.bulletDiameterIn),
        boreDiameterIn: num(r.boreDiameterIn),
        grooveDiameterIn: num(r.grooveDiameterIn),
        caseLengthMaxIn: num(r.caseLengthMaxIn),
        trimLengthIn: num(r.trimLengthIn),
        maxCoalIn: num(r.maxCoalIn),
        saamiMapPsi: num(r.saamiMapPsi),
        saamiMapCup: num(r.saamiMapCup),
        cipPmaxBar: crusher ? null : num(r.cipPmaxBar),
        saamiTwist: str(r.saamiTwist),
        primerSize: str(r.primerSize),
        caseCapacityGrH2O: [],
        sources: sourcesOf(r),
        conflicts: arr(r.conflicts),
        notes: [
          str(r.notes),
          crusher && r.cipPmaxBar ? `C.I.P. Pmax ${r.cipPmaxBar} bar was measured by the crusher method and is not used as a piezo limit.` : null,
          r.transducerLocation ? `Transducer: ${typeof r.transducerLocation === 'string' ? r.transducerLocation : JSON.stringify(r.transducerLocation)}` : null,
          evidencePart(r.evidence),
        ].filter(Boolean).join(' | '),
      };
      const prev = byKey.get(key);
      if (!prev) {
        byKey.set(key, c);
        continue;
      }
      // Merge (e.g. SAAMI + CIP records of the same cartridge): keep non-null values, record disagreements.
      const fields: (keyof Cartridge)[] = ['bulletDiameterIn', 'boreDiameterIn', 'grooveDiameterIn', 'caseLengthMaxIn', 'trimLengthIn', 'maxCoalIn', 'saamiMapPsi', 'saamiMapCup', 'cipPmaxBar', 'saamiTwist', 'primerSize'];
      for (const k of fields) {
        const a = prev[k] as any;
        const b = c[k] as any;
        if (a == null && b != null) (prev as any)[k] = b;
        else if (a != null && b != null && a !== b && !(typeof a === 'number' && Math.abs(a - b) <= 0.0005)) {
          prev.conflicts = [...(prev.conflicts ?? []), { field: String(k), values: [{ value: a, source: prev.sources[0]?.url ?? '' }, { value: b, source: c.sources[0]?.url ?? '' }] }];
        }
      }
      prev.aliases = [...new Set([...prev.aliases, c.name, ...c.aliases])].filter((x) => x !== prev.name);
      prev.standards = [...new Set([...prev.standards, ...c.standards])];
      prev.sources = [...prev.sources, ...c.sources];
      prev.notes = [prev.notes, c.notes].filter(Boolean).join(' | ');
    }
  }
  return applyFixes([...byKey.values()]).sort((a, b) => a.name.localeCompare(b.name));
}

// ---------------------------------------------------------------- powders + charts
export function buildPowders(files: { key: string; data: any }[]): { powders: Powder[]; charts: (BurnRateChart & { orderedNames: string[] })[] } {
  const byKey = new Map<string, Powder>();
  for (const f of files) {
    for (const r of arr<any>(f.data.powders)) {
      // Some sources name only the brand, not the maker (e.g. Norma, Vectan): fall back to the brand.
      const maker = str(r.manufacturer) ?? str(r.brand);
      if (!shippable(r) || !r.name || !maker) {
        drop('powder (no source/evidence)');
        continue;
      }
      // Show powders under their canister brand (IMR 4064, Winchester 760), keep the parent company in notes.
      const brand = str(r.brand);
      const shownMaker = brand && CANISTER_BRANDS.has(makerKey(brand)) ? brand : maker;
      const name = cleanName(r.name);
      const id = `${makerKey(shownMaker)}-${slug(name)}`;
      const p: Powder = {
        id,
        manufacturer: shownMaker,
        brand: brand && brand !== shownMaker ? brand : maker !== shownMaker ? maker : null,
        name,
        form: (['spherical', 'extruded', 'flake', 'disc'].includes(r.form) ? r.form : null) as Powder['form'],
        base: (['single', 'double', 'triple'].includes(r.base) ? r.base : null) as Powder['base'],
        nitroglycerinPct: num(r.nitroglycerinPct),
        applications: arr<string>(r.applications),
        temperatureStableClaim: str(r.temperatureStableClaim),
        bulkDensityGcc: num(r.bulkDensityGcc),
        heatOfExplosionJg: num(r.heatOfExplosionJg),
        burnRateCharts: [],
        status: r.status === 'discontinued' ? 'discontinued' : r.status === 'current' ? 'current' : 'unknown',
        sources: sourcesOf(r),
        notes: [str(r.notes), r.grainDimensions ? `Grain: ${typeof r.grainDimensions === 'string' ? r.grainDimensions : JSON.stringify(r.grainDimensions)}` : null, evidencePart(r.evidence)].filter(Boolean).join(' | '),
      };
      if (p.bulkDensityGcc != null && (p.bulkDensityGcc < 0.3 || p.bulkDensityGcc > 1.3)) {
        p.notes += ` | bulk density ${p.bulkDensityGcc} outside 0.3–1.3 g/cm³ rejected`;
        p.bulkDensityGcc = null;
      }
      const prev = byKey.get(id);
      if (!prev) byKey.set(id, p);
      else {
        for (const k of ['form', 'base', 'nitroglycerinPct', 'bulkDensityGcc', 'heatOfExplosionJg', 'temperatureStableClaim'] as const) {
          if ((prev as any)[k] == null && (p as any)[k] != null) (prev as any)[k] = (p as any)[k];
        }
        prev.sources = [...prev.sources, ...p.sources];
        prev.applications = [...new Set([...prev.applications, ...p.applications])];
      }
    }
  }
  // Merge duplicate spellings of one product (verifier finding): chart "7828SC" is the product "7828 SSC".
  const POWDER_MERGE: Record<string, string> = { 'imr-7828sc': 'imr-7828-ssc', 'accurate-11-fs': 'accurate-no-11-fs' };
  const mergedAliases: { name: string; maker: string; to: string }[] = [];
  for (const [from, to] of Object.entries(POWDER_MERGE)) {
    const a = byKey.get(from);
    const b = byKey.get(to);
    if (a && b) {
      b.sources = [...b.sources, ...a.sources];
      b.notes = `${b.notes ?? ''} | Also printed as "${a.name}" on burn-rate charts.`;
      mergedAliases.push({ name: a.name, maker: a.manufacturer, to });
      byKey.delete(from);
    }
  }
  // Powders printed on the Hodgdon burn-rate chart whose own maker pages could not be reached (Accurate and Ramshot
  // are Hodgdon brands; Western Powders' site reset every connection): minimal records sourced from the chart line.
  const CHART_BRANDS: Record<string, string> = { ACCURATE: 'Accurate', RAMSHOT: 'Ramshot' };
  for (const f of files) {
    for (const c of arr<any>(f.data.charts)) {
      if (!/hodgdon/i.test(String(c.publisher ?? '')) || !c.url) continue;
      for (const raw of arr<string>(c.orderedNames)) {
        const m = /^(ACCURATE|RAMSHOT)\s+(.+)$/i.exec(String(raw).trim());
        if (!m) continue;
        const maker = CHART_BRANDS[m[1].toUpperCase()];
        const name = cleanName(m[2]).replace(/\b([A-Z])([A-Z]+)\b/g, (_s, a: string, b: string) => a + b.toLowerCase());
        const id = `${makerKey(maker)}-${slug(name)}`;
        if (byKey.has(id)) continue;
        byKey.set(id, {
          id,
          manufacturer: maker,
          brand: 'Hodgdon Powder Company',
          name,
          form: null,
          base: null,
          applications: [],
          burnRateCharts: [],
          status: 'unknown',
          sources: [{ url: c.url, type: 'manufacturer', fields: ['name', 'burnRateCharts'] }],
          notes: `Name and burn-rate position from the ${c.publisher} ${c.edition ?? ''} chart; ${maker}'s own product pages could not be reached, so form, base and density are not stated. | ${evidencePart(raw)}`,
        });
      }
    }
  }
  // Apply merges again: chart-sourced records (created above) can also be duplicate spellings (e.g. "#11 FS" / "No. 11 FS").
  for (const [from, to] of Object.entries(POWDER_MERGE)) {
    const a = byKey.get(from);
    const b = byKey.get(to);
    if (a && b) {
      b.sources = [...b.sources, ...a.sources];
      b.notes = `${b.notes ?? ''} | Also printed as "${a.name}" on burn-rate charts.`;
      mergedAliases.push({ name: a.name, maker: a.manufacturer, to });
      byKey.delete(from);
    }
  }
  const powders = applyFixes([...byKey.values()]);
  // Index for chart-name matching: powderKey(name) and powderKey(maker + name).
  const index = new Map<string, string[]>();
  const addIdx = (k: string, id: string) => index.set(k, [...new Set([...(index.get(k) ?? []), id])]);
  for (const m of mergedAliases) {
    addIdx(powderKey(m.name), m.to);
    addIdx(powderKey(`${m.maker} ${m.name}`), m.to);
  }
  for (const p of powders) {
    addIdx(powderKey(p.name), p.id);
    addIdx(powderKey(`${p.manufacturer} ${p.name}`), p.id);
    addIdx(powderKey(`${makerKey(p.manufacturer)} ${p.name}`), p.id);
    if (makerKey(p.manufacturer) === 'imr' && !/^imr/i.test(p.name)) addIdx(powderKey(`IMR ${p.name}`), p.id);
    if (makerKey(p.manufacturer) === 'winchester' && !/^win/i.test(p.name)) addIdx(powderKey(`Winchester ${p.name}`), p.id);
  }
  const charts: (BurnRateChart & { orderedNames: string[] })[] = [];
  for (const f of files) {
    for (const c of arr<any>(f.data.charts)) {
      const names: string[] = arr<string>(c.orderedNames ?? c.orderedPowderIds);
      if (!names.length || !c.url) continue;
      const ids = names.map((n) => {
        const hits = index.get(powderKey(n)) ?? [];
        return hits.length === 1 ? hits[0] : `name:${n}`;
      });
      const chartLabel = `${c.publisher ?? 'unknown'} ${c.edition ?? ''}`.trim();
      ids.forEach((id, i) => {
        const p = powders.find((x) => x.id === id);
        if (p) p.burnRateCharts.push({ chart: chartLabel, rank: i + 1, chartUrl: c.url });
      });
      charts.push({ publisher: c.publisher ?? 'unknown', edition: c.edition ?? '', url: c.url, orderedPowderIds: ids, orderedNames: names });
    }
  }
  return { powders: powders.sort((a, b) => a.manufacturer.localeCompare(b.manufacturer) || a.name.localeCompare(b.name)), charts };
}

// ---------------------------------------------------------------- bullets
export function buildBullets(files: { key: string; data: any }[]): Bullet[] {
  const byId = new Map<string, Bullet>();
  for (const f of files) {
    for (const r of arr<any>(f.data.bullets)) {
      const d = num(r.diameterIn);
      const w = num(r.weightGr);
      if (!shippable(r) || d === null || w === null || !r.manufacturer) {
        drop('bullet (no source/evidence/diameter/weight)');
        continue;
      }
      if (d < 0.17 || d > 0.52 || w < 15 || w > 800) {
        drop('bullet (diameter/weight out of range)');
        continue;
      }
      const id = r.id ? slug(String(r.id)) : slug(`${r.manufacturer}-${r.sku ?? `${r.line}-${d}-${w}`}`);
      // Lengths marked low-confidence (e.g. inferred from an unlabeled data file) are not shipped (verifier finding).
      const len = r.lengthConfidence === 'low' ? null : num(r.lengthIn);
      const b = {
        id,
        manufacturer: r.manufacturer,
        line: r.line ?? '',
        name: r.name ?? `${r.line ?? ''} ${w} gr`,
        sku: str(r.sku),
        caliberLabel: str(r.caliberLabel),
        diameterIn: d,
        weightGr: w,
        lengthIn: len !== null && len > d && len < 3 ? len : null,
        bcG1: num(r.bcG1),
        bcG7: num(r.bcG7),
        bcNotes: str(r.bcNotes),
        profile: str(r.profile),
        tip: str(r.tip),
        construction: str(r.construction),
        recommendedTwist: str(r.recommendedTwist),
        status: r.status === 'discontinued' ? 'discontinued' : r.status === 'current' ? 'current' : 'unknown',
        sources: sourcesOf(r),
        notes: [str(r.notes), arr(r.conflicts).length ? `Sources disagree: ${JSON.stringify(r.conflicts)}` : null, evidencePart(r.evidence)].filter(Boolean).join(' | '),
        boatTailLengthIn: num(r.boatTailLengthIn),
        baseToOgiveIn: num(r.baseToOgiveIn),
        use: str(r.kind ?? r.firearm ?? null),
      } as Bullet & { boatTailLengthIn?: number | null; baseToOgiveIn?: number | null; use?: string | null };
      if (!byId.has(id)) byId.set(id, b);
    }
  }
  return applyFixes([...byId.values()]).sort((a, b) => a.diameterIn - b.diameterIn || a.weightGr - b.weightGr || a.manufacturer.localeCompare(b.manufacturer));
}

/**
 * A maker's catalog cross-checked against the same maker's web records (file with a `crossCheck` array, e.g.
 * bullets-hornady-catalog.json). Rules:
 *  - 'web-missing' (the web record leaves a BC empty, the catalog prints one): filled from the catalog, exact item
 *    number matches only, never when the extractor flagged the printed values as inconsistent (catalogCheck);
 *  - 'value-mismatch' (both publish a value and they differ): the web value is kept and both values are recorded,
 *    because nothing in either document says which is newer;
 *  - new catalog-only records with no construction take the construction and tip that the maker's own web records give
 *    for the same product line (labelled as such).
 * Returns counts for the build log.
 */
export function applyCatalogCrossChecks(bullets: Bullet[], files: { key: string; data: any }[]) {
  const byId = new Map(bullets.map((b) => [b.id, b]));
  const counts = { filled: 0, disagreements: 0, skippedFlagged: 0, skippedSuffix: 0, constructionFromLine: 0 };
  const fmtBc = (v: number) => v.toFixed(3).replace(/^0/, '');
  const fieldLabel: Record<string, string> = { bcG1: 'G1', bcG7: 'G7' };
  const addNote = (b: Bullet, note: string) => {
    if ((b.notes ?? '').split(' | ').includes(note)) return;
    b.notes = [b.notes, note].filter(Boolean).join(' | ');
  };
  for (const f of files) {
    const doc = f.data?.meta?.documents?.[0];
    const checks = arr<any>(f.data?.crossCheck);
    if (!checks.length || !doc?.url) continue;
    const title = String(doc.title ?? 'maker catalog');
    for (const c of checks) {
      const b = byId.get(slug(String(c.id)));
      const field = String(c.field);
      if (!b || !(field in fieldLabel)) continue;
      const label = fieldLabel[field];
      const cat = num(c.catalog);
      if (cat === null) continue;
      const where = `${title}, PDF page ${c.page}`;
      if (c.catalogCheck) {
        counts.skippedFlagged++;
        addNote(b, `${where} prints ${label} ${fmtBc(cat)}, not adopted: ${c.catalogCheck}`);
        addNote(b, evidencePart(`${where}: ${c.evidence}`));
        b.bcNotes = [b.bcNotes, `The 2027 catalog's G1/G7 pair for this bullet is inconsistent (probable misprint); treat the BC with caution.`].filter(Boolean).join('; ');
        continue;
      }
      if (!/^exact/.test(String(c.match ?? ''))) {
        counts.skippedSuffix++;
        continue;
      }
      if (c.kind === 'web-missing' && (b as any)[field] === null) {
        (b as any)[field] = cat;
        b.sources = [...b.sources, { url: doc.url, type: 'manufacturer', fields: [field], page: c.page, retrieved: '2026-11-23' }];
        addNote(b, `${label} ${fmtBc(cat)} from the ${where} (the hornady.com product page gives no ${label}).`);
        addNote(b, evidencePart(`${where}: ${c.evidence}`));
        counts.filled++;
      } else if (c.kind === 'value-mismatch') {
        const web = num(c.web);
        addNote(b, `The maker's two publications disagree on ${label}: hornady.com ${web !== null ? fmtBc(web) : '—'}, ${where} ${fmtBc(cat)}. ORKA shows the web value; neither document says which is newer.`);
        addNote(b, evidencePart(`${where}: ${c.evidence}`));
        b.bcNotes = [b.bcNotes, `${label}: hornady.com ${web !== null ? fmtBc(web) : '—'} vs 2027 catalog ${fmtBc(cat)}`].filter(Boolean).join('; ');
        counts.disagreements++;
      }
    }
    // Construction for new catalog-only records, from the same maker's web records of the same line.
    for (const r of arr<any>(f.data?.bullets)) {
      const b = byId.get(slug(String(r.id)));
      if (!b || b.construction) continue;
      const lineKey = (l: string) => l.replace(/[®™]/g, '').replace(/\b(rifle|handgun)\b/gi, '').replace(/[‐‑–]/g, '-').trim().toLowerCase();
      const peers = bullets.filter((x) => x !== b && x.manufacturer === b.manufacturer && x.construction && lineKey(x.line) === lineKey(b.line));
      const kinds = [...new Set(peers.map((x) => x.construction))];
      if (kinds.length !== 1) continue;
      b.construction = kinds[0] ?? null;
      const tips = [...new Set(peers.map((x) => x.tip).filter(Boolean))];
      if (!b.tip && tips.length === 1) b.tip = tips[0] ?? null;
      addNote(b, `Construction${!r.tip && tips.length === 1 ? ' and tip' : ''} not printed in the catalog; taken from the maker's web records for the same line (${peers.length} bullets, all "${kinds[0]}").`);
      counts.constructionFromLine++;
    }
  }
  return counts;
}

// ---------------------------------------------------------------- brass
export function buildBrass(files: { key: string; data: any }[], cartridges: Cartridge[]): { brands: BrassBrand[]; cases: BrassCase[] } {
  const brands: BrassBrand[] = [];
  const cases: BrassCase[] = [];
  const cartByKey = new Map<string, Cartridge>();
  for (const c of cartridges) {
    cartByKey.set(c.id, c);
    for (const a of c.aliases) cartByKey.set(cartridgeKey(a), c);
  }
  for (const f of files) {
    for (const r of arr<any>(f.data.brands)) {
      if (!r.name || sourcesOf(r).length === 0) continue;
      if (!brands.find((b) => b.id === (r.id ?? slug(r.name)))) {
        // Keep the source's wording: the expansion "(Winchester military headstamp)" is not in the source (verifier finding).
        const shownName = String(r.name).replace(/\s*\(Winchester military headstamp\)/i, '');
        brands.push({ id: r.id ?? slug(r.name), name: shownName, country: str(r.country), parent: str(r.parent), productLines: arr(r.productLines), notes: str(r.notes) ?? undefined, sources: sourcesOf(r) });
      }
    }
    for (const r of arr<any>(f.data.cases)) {
      if (!shippable(r) || !r.cartridge) {
        drop('case (no source/evidence)');
        continue;
      }
      if (/\\|u0026/.test(String(r.cartridge))) {
        drop('case (escape-corrupted cartridge name; verifier finding)');
        continue;
      }
      const cart = cartByKey.get(cartridgeKey(r.cartridge));
      const cap = num(r.waterCapacityGrH2O);
      const bc: BrassCase = {
        brandId: r.brandId ?? 'unknown',
        cartridge: r.cartridge,
        cartridgeId: cart?.id ?? null,
        sku: str(r.sku),
        caseWeightGr: num(r.caseWeightGr),
        waterCapacityGrH2O: cap !== null && cap > 2 && cap < 300 ? cap : null,
        capacityCondition: r.capacityCondition ?? 'unknown',
        primerSize: str(r.primerSize),
        primerPocketType: str(r.primerPocketType),
        basis: r.basis ?? 'unknown',
        sources: sourcesOf(r),
        notes: [str(r.notes), r.capacityTo ? `Capacity measured to: ${r.capacityTo}` : null, evidencePart(r.evidence)].filter(Boolean).join(' | '),
      };
      cases.push(bc);
      if (cart && bc.waterCapacityGrH2O != null && (r.capacityTo ?? 'case mouth') !== 'base of neck') {
        cart.caseCapacityGrH2O.push({ value: bc.waterCapacityGrH2O, brand: brands.find((b) => b.id === bc.brandId)?.name ?? bc.brandId, basis: `${bc.basis}${bc.capacityCondition !== 'unknown' ? `, ${bc.capacityCondition} case` : ''}`, source: bc.sources[0]?.url ?? null });
      }
    }
  }
  return { brands, cases };
}

// ---------------------------------------------------------------- validation loads
/** Match a cartridge name from load data: exact key, then key without parentheses, then a unique token-subset match. */
const keyCache = new WeakMap<Cartridge[], { keys: Set<string>[]; looseKeys: Set<string>[]; loose: string[][] }>();
const nameCache = new Map<string, Cartridge | undefined>();
export function findCartridge(cartridges: Cartridge[], name: string): Cartridge | undefined {
  let idx = keyCache.get(cartridges);
  if (!idx) {
    idx = {
      keys: cartridges.map((c) => new Set([c.id, cartridgeKey(c.name), ...c.aliases.map(cartridgeKey)])),
      looseKeys: cartridges.map((c) => new Set([cartridgeKeyLoose(c.name), ...c.aliases.map(cartridgeKeyLoose)])),
      loose: cartridges.map((c) => cartridgeKeyLoose(c.name).split('-')),
    };
    keyCache.set(cartridges, idx);
    nameCache.clear();
  }
  if (nameCache.has(name)) return nameCache.get(name);
  const I = idx;
  const pick = (): Cartridge | undefined => {
    const k = cartridgeKey(name);
    const exact = cartridges.filter((_, i) => I.keys[i].has(k));
    if (exact.length === 1) return exact[0];
    const kl = cartridgeKeyLoose(name);
    const strict2 = cartridges.filter((_, i) => I.keys[i].has(kl));
    if (strict2.length === 1) return strict2[0];
    const loose = cartridges.filter((_, i) => I.looseKeys[i].has(kl));
    if (loose.length === 1) return loose[0];
    // Token subset: every token of the cartridge key appears in the load's key (e.g. "7.62x39 russian" ⊇ "7.62x39").
    const toks = new Set(kl.split('-'));
    const sub = cartridges
      .map((c, i) => ({ c, t: I.loose[i] }))
      .filter(({ t }) => t.length >= 1 && /\d/.test(t[0]) && t.every((x) => toks.has(x)))
      .sort((a, b) => b.t.length - a.t.length);
    if (sub.length === 1 || (sub.length > 1 && sub[0].t.length > sub[1].t.length)) return sub[0].c;
    // Reverse subset (load name is an abbreviation of the cartridge name): accept the unique shortest superset.
    const lt = kl.split('-');
    const sup = cartridges
      .map((c, i) => ({ c, t: I.loose[i] }))
      .filter(({ t }) => lt.length >= 2 && lt.every((x) => t.includes(x)))
      .sort((a, b) => a.t.length - b.t.length);
    if (sup.length === 1 || (sup.length > 1 && sup[0].t.length < sup[1].t.length)) return sup[0].c;
    return undefined;
  };
  const r = pick();
  nameCache.set(name, r);
  return r;
}

export function buildLoads(files: { key: string; data: any }[], cartridges: Cartridge[], powders: Powder[]): ValidationLoad[] {
  const out: ValidationLoad[] = [];
  for (const f of files) {
    for (const r of arr<any>(f.data.loads)) {
      const charge = num(r.chargeGr);
      const vel = num(r.velocityFps);
      if (!shippable(r) || charge === null || vel === null || !r.cartridge || !r.powder) {
        drop('load (incomplete or unsourced)');
        continue;
      }
      const cart = findCartridge(cartridges, r.cartridge);
      const mk = r.powderMfr ? makerKey(r.powderMfr) : null;
      // Renamed / reprinted products (review finding): load-data name -> catalog name.
      const pk = LOAD_POWDER_ALIASES[`${mk ?? ''}|${powderKey(r.powder)}`] ?? powderKey(r.powder);
      const pw = powders
        .filter((p) => powderKey(p.name) === pk || powderKey(`${p.manufacturer} ${p.name}`) === pk || powderKey(`${makerKey(p.manufacturer)} ${p.name}`) === pk)
        .filter((p) => !mk || makerKey(p.manufacturer) === mk);
      const unit = r.pressureUnit === 'psi' || r.pressureUnit === 'CUP' || r.pressureUnit === 'bar' ? r.pressureUnit : null;
      out.push({
        cartridge: r.cartridge,
        cartridgeId: cart?.id ?? null,
        bulletMfr: r.bulletMfr ?? '',
        bulletModel: r.bulletModel ?? '',
        bulletWeightGr: num(r.bulletWeightGr) ?? NaN,
        bulletDiameterIn: num(r.bulletDiameterIn),
        bulletLengthIn: num(r.bulletLengthIn),
        caseBrand: str(r.caseBrand),
        caseTrimLengthIn: num(r.caseTrimLengthIn),
        primer: str(r.primer),
        coalIn: num(r.coalIn) ?? NaN,
        barrelLengthIn: num(r.barrelLengthIn) ?? NaN,
        twist: str(r.twist),
        powder: r.powder,
        powderId: pw.length === 1 ? pw[0].id : null,
        powderMfr: str(r.powderMfr),
        chargeGr: charge,
        velocityFps: vel,
        pressure: num(r.pressure),
        pressureUnit: unit,
        pressureMethod: r.pressureMethod ?? 'unknown',
        // Not cartridge maximums: reduced loads for gas-operated service rifles (e.g. M1 Garand), and firearm-class
        // sections such as "45-70 Government (Modern Rifles)" whose pressure level differs from the standard (review finding).
        loadType:
          r.loadType === 'max' && /garand/i.test(`${r.cartridge} ${r.notes ?? ''} ${r.dataSection ?? ''}`)
            ? 'reduced'
            : r.loadType === 'max' && /\(.+\)/.test(String(r.cartridge)) && cart && cartridgeKey(r.cartridge) !== cart.id
              ? 'section-max'
              : r.loadType ?? 'other',
        compressed: r.compressed ?? null,
        sources: sourcesOf(r),
        notes: [str(r.notes), `Evidence: ${r.evidence}`].filter(Boolean).join(' | '),
      });
    }
  }
  return out;
}

function main() {
  const files = rawFiles();
  let cartridges = buildCartridges(files);
  let { powders, charts } = buildPowders(files);
  let bullets = buildBullets(files);
  console.log('catalog cross-checks:', applyCatalogCrossChecks(bullets, files));
  let { brands, cases } = buildBrass(files, cartridges);
  let validationLoads = buildLoads(files, cartridges, powders);

  // Bullet-length plausibility screen (review finding): a published length is withheld when the bullet would be denser
  // than physically possible as a plain cylinder (real bullets have less volume than their cylinder), or when it
  // disagrees with the length model by more than 3x the model's leave-one-out error.
  {
    const lm = fitLengthModel(bullets);
    for (const b of bullets) {
      if (!b.lengthIn) continue;
      const f = bulletFeatures(b);
      const volCm3 = (Math.PI / 4) * (b.diameterIn * 2.54) ** 2 * (b.lengthIn * 2.54);
      const rhoCyl = (b.weightGr * 0.06479891) / volCm3; // g/cm³, a lower bound on the true density
      const maxRho = f.blunt ? 10.8 : 9.5; // lead is 11.34 g/cm³; pointed jacketed bullets fill far less than their cylinder
      const pred = lm?.predict(f) ?? null;
      const loo = f.blunt ? lm?.looRelRmsBlunt : lm?.looRelRmsPointed;
      const resid = pred ? (b.lengthIn - pred) / pred : 0;
      const tooFar = pred !== null && typeof loo === 'number' && Math.abs(resid) > Math.max(0.2, 3 * loo);
      if (rhoCyl > maxRho || tooFar) {
        b.notes = `${b.notes ?? ''} | Published length ${b.lengthIn} in withheld as implausible (cylinder density ${rhoCyl.toFixed(2)} g/cm³${pred ? `; length model ${pred.toFixed(3)} in` : ''}). Measure this bullet.`;
        b.lengthIn = null;
        drop('bullet length withheld as implausible');
      }
    }
  }

  // Scope: ORKA is focused on centerfire rifle reloading (ORKA_SCOPE=all keeps handgun data).
  if (SCOPE === 'rifle') {
    cartridges = cartridges.filter((c) => c.type === 'rifle');
    const rifleIds = new Set(cartridges.map((c) => c.id));
    bullets = bullets.filter((b) => !isNonRifleBullet(b));
    validationLoads = validationLoads.filter((l) => l.cartridgeId && rifleIds.has(l.cartridgeId));
    const usedInRifleLoads = new Set(validationLoads.map((l) => l.powderId).filter(Boolean));
    powders = powders.filter((p) => !p.applications.length || p.applications.some((a) => /rifle/i.test(a)) || usedInRifleLoads.has(p.id));
    const keptPowders = new Set(powders.map((p) => p.id));
    charts = charts.map((c) => ({ ...c, orderedPowderIds: c.orderedPowderIds.map((id, i) => (id.startsWith('name:') || keptPowders.has(id) ? id : `name:${c.orderedNames?.[i] ?? id}`)) }));
    cases = cases.filter((c) => c.cartridgeId && rifleIds.has(c.cartridgeId));
    const usedBrands = new Set(cases.map((c) => c.brandId));
    brands = brands.filter((b) => usedBrands.has(b.id));
  }

  // Model-inferred effective capacities of publishers' test cases (scripts/calibrate-powders.ts), labelled as such.
  const inferredCaps: any[] = readJson(path.join(ROOT, 'src/data/inferred-capacities.json')) ?? [];
  for (const ic of inferredCaps) {
    const c = cartridges.find((x) => x.id === ic.cartridgeId);
    if (!c || !(ic.grH2O > 0)) continue;
    const brand = String(ic.caseBrand ?? '').replace(/\b\w/g, (m: string) => m.toUpperCase());
    if (c.caseCapacityGrH2O.some((e) => (e.brand ?? '').toLowerCase() === brand.toLowerCase() && !/inferred/i.test(e.basis))) continue;
    c.caseCapacityGrH2O.push({ value: ic.grH2O, brand, basis: ic.basis, source: null });
  }

  // Attach powder models: calibrated (scripts/calibrate-powders.ts) then chart-interpolated estimates.
  const models: Record<string, PowderModelEntry> = readJson(MODELS)?.models ?? {};
  for (const p of powders) if (models[p.id]) p.model = gradeModel(models[p.id]);
  const report = readJson(path.join(ROOT, 'src/data/validation-report.json'));
  const sigma = report?.metrics?.interpolationBetaRelSigma;
  const estimates = estimateFromCharts(powders, charts, typeof sigma === 'number' && sigma > 0 ? Math.max(sigma, 0.1) : undefined);
  for (const p of powders) if (!p.model && estimates[p.id]) p.model = estimates[p.id];

  const db: Database = {
    version: `0.1.0+${new Date().toISOString().slice(0, 10)}`,
    generated: new Date().toISOString(),
    cartridges,
    powders,
    burnRateCharts: charts,
    bullets,
    brassBrands: brands,
    brassCases: cases,
    // Published loads are large: the full set (with evidence) goes to research/build for calibration, and a compact
    // copy is loaded lazily by the app for the published-data cross-check. db.json itself stays small.
    validationLoads: [],
  };
  // Move verbatim evidence out of the records into a lazily loaded file (keeps the main bundle small).
  const evidence: Record<string, Record<string, string>> = { cartridges: {}, powders: {}, bullets: {}, brassCases: {} };
  // Notes and verbatim evidence are shown only in the record's detail panel, so both move to the lazy file.
  const split = (col: string, key: string, rec: { notes?: string }) => {
    if (!rec.notes) return;
    const parts = rec.notes.split(' | ');
    const ev = parts.filter((x) => x.startsWith('Evidence: ')).map((x) => x.slice(10));
    const other = parts.filter((x) => !x.startsWith('Evidence: ') && x.trim());
    evidence[col][key] = [...(other.length ? [`Notes: ${other.join(' | ')}`] : []), ...ev.map((e) => `Evidence: ${e}`)].join('\n');
    delete rec.notes;
  };
  db.cartridges.forEach((c) => split('cartridges', c.id, c));
  db.powders.forEach((p) => split('powders', p.id, p));
  db.bullets.forEach((b) => split('bullets', b.id, b));
  db.brassCases.forEach((c, i) => split('brassCases', String(i), c));
  fs.writeFileSync(path.join(ROOT, 'src/data/db-evidence.json'), JSON.stringify(evidence));
  fs.writeFileSync(OUT, JSON.stringify(db));
  fs.mkdirSync(BUILD_DIR, { recursive: true });
  fs.writeFileSync(path.join(BUILD_DIR, 'validation-loads.json'), JSON.stringify(validationLoads));
  const compact = validationLoads
    .filter((l) => l.cartridgeId && l.powderId)
    .map((l) => ({
      c: l.cartridgeId,
      p: l.powderId,
      w: l.bulletWeightGr,
      bm: l.bulletMfr,
      bt: l.bulletModel,
      t: l.loadType,
      ch: l.chargeGr,
      v: l.velocityFps,
      pr: l.pressure,
      pu: l.pressureUnit,
      b: Number.isFinite(l.barrelLengthIn) ? l.barrelLengthIn : null,
      oal: Number.isFinite(l.coalIn) ? l.coalIn : null,
      cs: l.caseBrand,
      pm: l.primer,
      u: l.sources[0]?.url ?? null,
      pg: l.sources[0]?.page ?? null,
      cp: l.compressed ?? null,
      // Section label as printed (e.g. "45-70 Government (Trapdoor Rifles)"), when it differs from the cartridge name.
      cn: l.cartridge,
    }));
  // Dictionary-encode repeated strings: { s: [strings], r: [[...fields with string indices...]] }.
  const strings: string[] = [];
  const sIdx = new Map<string, number>();
  const si = (v: string | null | undefined) => {
    if (v === null || v === undefined) return -1;
    let i = sIdx.get(v);
    if (i === undefined) {
      i = strings.length;
      strings.push(v);
      sIdx.set(v, i);
    }
    return i;
  };
  const rowsOut = (SHIP_PUBLISHED ? compact : []).map((x) => [
    si(x.c), si(x.p), x.w, si(x.bm), si(x.bt), si(x.t), x.ch, x.v, x.pr, si(x.pu), x.b, x.oal, si(x.cs), si(x.pm), si(x.u), x.pg ?? null, x.cp === null ? -1 : x.cp ? 1 : 0, si(x.cn),
  ]);
  fs.writeFileSync(PUBLISHED, JSON.stringify({ v: 1, s: strings, r: rowsOut }));
  const modelCounts: Record<string, number> = {};
  for (const p of powders) modelCounts[p.model?.status ?? 'none'] = (modelCounts[p.model?.status ?? 'none'] ?? 0) + 1;
  console.log(JSON.stringify({
    sourcesUsed: files.map((f) => f.key),
    excludedSources: [...excluded],
    counts: { cartridges: cartridges.length, powders: powders.length, charts: charts.length, bullets: bullets.length, brassBrands: brands.length, brassCases: cases.length, validationLoads: validationLoads.length, publishedShipped: SHIP_PUBLISHED ? compact.length : 0 },
    bytes: { db: fs.statSync(OUT).size, published: fs.statSync(PUBLISHED).size },
    powderModels: modelCounts,
    dropped,
  }, null, 2));
}

// Run only when executed directly (the build functions are also imported by tests).
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)) main();
