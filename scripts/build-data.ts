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
import { cartridgeKey, makerKey, powderKey, slug } from './names';
import { estimateFromCharts } from './estimate';

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
const drop = (k: string) => (dropped[k] = (dropped[k] ?? 0) + 1);

// ---------------------------------------------------------------- cartridges
export function buildCartridges(files: { key: string; data: any }[]): Cartridge[] {
  const byKey = new Map<string, Cartridge>();
  for (const f of files) {
    for (const r of arr<any>(f.data.cartridges)) {
      if (!shippable(r) || !r.name) {
        drop('cartridge (no source/evidence)');
        continue;
      }
      const key = cartridgeKey(r.name);
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
        cipPmaxBar: num(r.cipPmaxBar),
        saamiTwist: str(r.saamiTwist),
        primerSize: str(r.primerSize),
        caseCapacityGrH2O: [],
        sources: sourcesOf(r),
        conflicts: arr(r.conflicts),
        notes: [str(r.notes), r.transducerLocation ? `Transducer: ${r.transducerLocation}` : null, `Evidence: ${r.evidence}`].filter(Boolean).join(' | '),
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
      if (!shippable(r) || !r.name || !r.manufacturer) {
        drop('powder (no source/evidence)');
        continue;
      }
      const id = `${makerKey(r.manufacturer)}-${slug(r.name)}`;
      const p: Powder = {
        id,
        manufacturer: r.manufacturer,
        brand: str(r.brand),
        name: r.name,
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
        notes: [str(r.notes), r.grainDimensions ? `Grain: ${r.grainDimensions}` : null, `Evidence: ${r.evidence}`].filter(Boolean).join(' | '),
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
  const powders = applyFixes([...byKey.values()]);
  // Index for chart-name matching: powderKey(name) and powderKey(maker + name).
  const index = new Map<string, string[]>();
  const addIdx = (k: string, id: string) => index.set(k, [...new Set([...(index.get(k) ?? []), id])]);
  for (const p of powders) {
    addIdx(powderKey(p.name), p.id);
    addIdx(powderKey(`${p.manufacturer} ${p.name}`), p.id);
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
      const len = num(r.lengthIn);
      const b: Bullet & { boatTailLengthIn?: number | null; baseToOgiveIn?: number | null } = {
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
        notes: [str(r.notes), `Evidence: ${r.evidence}`].filter(Boolean).join(' | '),
        boatTailLengthIn: num(r.boatTailLengthIn),
        baseToOgiveIn: num(r.baseToOgiveIn),
      };
      if (!byId.has(id)) byId.set(id, b);
    }
  }
  return applyFixes([...byId.values()]).sort((a, b) => a.diameterIn - b.diameterIn || a.weightGr - b.weightGr || a.manufacturer.localeCompare(b.manufacturer));
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
        brands.push({ id: r.id ?? slug(r.name), name: r.name, country: str(r.country), parent: str(r.parent), productLines: arr(r.productLines), notes: str(r.notes) ?? undefined, sources: sourcesOf(r) });
      }
    }
    for (const r of arr<any>(f.data.cases)) {
      if (!shippable(r) || !r.cartridge) {
        drop('case (no source/evidence)');
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
        notes: [str(r.notes), r.capacityTo ? `Capacity measured to: ${r.capacityTo}` : null, `Evidence: ${r.evidence}`].filter(Boolean).join(' | '),
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
      const ck = cartridgeKey(r.cartridge);
      const cart = cartridges.find((c) => c.id === ck || c.aliases.some((a) => cartridgeKey(a) === ck));
      const pk = powderKey(r.powder);
      const mk = r.powderMfr ? makerKey(r.powderMfr) : null;
      const pw = powders.filter((p) => powderKey(p.name) === pk || powderKey(`${p.manufacturer} ${p.name}`) === pk).filter((p) => !mk || makerKey(p.manufacturer) === mk);
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
        loadType: r.loadType ?? 'other',
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
  const cartridges = buildCartridges(files);
  const { powders, charts } = buildPowders(files);
  const bullets = buildBullets(files);
  const { brands, cases } = buildBrass(files, cartridges);
  const validationLoads = buildLoads(files, cartridges, powders);

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
  for (const p of powders) if (models[p.id]) p.model = models[p.id];
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
    }));
  fs.writeFileSync(PUBLISHED, JSON.stringify(SHIP_PUBLISHED ? compact : []));
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
