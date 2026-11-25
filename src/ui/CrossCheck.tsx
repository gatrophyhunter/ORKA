// Safety cross-checks shown next to every prediction:
//  1. Published maker data for the same cartridge + powder (+ bullet weight) — the maker's maximum wins.
//  2. Calibration scope — warns when the prediction extrapolates beyond the data the powder model was fitted to.

import type { Database, ValidationLoad } from '../data/schema';
import * as U from '../engine/units';
import type { DerivedLoad } from './useLoad';
import { fmtNum } from './format';
import { usePublished } from './published';
import { useApp, type PressureStandard } from './state';

export function publishedMatches(db: Database, cartridgeId: string | null, powderId: string | null, bulletWeightGr: number, published?: ValidationLoad[] | null): ValidationLoad[] {
  if (!cartridgeId || !powderId) return [];
  return [...db.validationLoads, ...(published ?? [])]
    .filter((l) => l.cartridgeId === cartridgeId && l.powderId === powderId)
    .filter((l) => !(bulletWeightGr > 0) || Math.abs(l.bulletWeightGr - bulletWeightGr) <= 1)
    .sort((a, b) => a.bulletWeightGr - b.bulletWeightGr || a.chargeGr - b.chargeGr);
}

// ---- Published pressure against the limit being applied ----

/** The maximum the user applies (before the safety margin), as the cross-check needs it. */
export interface LimitContext {
  standard: PressureStandard;
  /** Standard maximum (SAAMI MAP psi, C.I.P. Pmax bar, or the custom limit), Pa; null when none is set. */
  mapPa: number | null;
  /** SAAMI MAP in CUP for this cartridge, when on record (only CUP data is compared with it). */
  saamiMapCup: number | null;
  /** True for a cartridge the user entered (its maximum is the user's, not the standard's). */
  userCartridge?: boolean;
}

export interface PressureComparison {
  row: ValidationLoad;
  status: 'above' | 'within' | 'not-comparable' | 'no-pressure';
  /** Published pressure / applied maximum, when comparable. */
  ratio: number | null;
  /** The maximum compared against, in its own unit. */
  limitText: string | null;
  /** Published pressure converted to the limit's unit, when the units differ (CUP is never converted). */
  convertedText: string | null;
}

/** Unit the applied limit is stated in: SAAMI MAP and custom limits in psi, C.I.P. Pmax in bar. */
export const limitUnit = (standard: PressureStandard): 'psi' | 'bar' => (standard === 'CIP' ? 'bar' : 'psi');

const fmtInUnit = (pa: number, unit: 'psi' | 'bar') => `${fmtNum(unit === 'psi' ? U.paToPsi(pa) : U.paToBar(pa), 0)} ${unit}`;

/** Compares a published load's own pressure with the applied maximum. Psi and bar are converted; CUP only meets a SAAMI CUP MAP. */
export function comparePublishedPressure(row: ValidationLoad, ctx: LimitContext): PressureComparison {
  const base = { row, ratio: null, limitText: null, convertedText: null };
  if (row.pressure === null || !(row.pressure > 0) || !row.pressureUnit) return { ...base, status: 'no-pressure' };
  if (row.pressureUnit === 'CUP') {
    if (ctx.standard !== 'SAAMI' || !(ctx.saamiMapCup && ctx.saamiMapCup > 0)) return { ...base, status: 'not-comparable' };
    const ratio = row.pressure / ctx.saamiMapCup;
    return { ...base, status: ratio > 1 ? 'above' : 'within', ratio, limitText: `${fmtNum(ctx.saamiMapCup, 0)} CUP` };
  }
  if (ctx.mapPa === null || !(ctx.mapPa > 0)) return { ...base, status: 'not-comparable' };
  const pa = row.pressureUnit === 'psi' ? U.psiToPa(row.pressure) : U.barToPa(row.pressure);
  const unit = limitUnit(ctx.standard);
  const ratio = pa / ctx.mapPa;
  return {
    ...base,
    status: ratio > 1 ? 'above' : 'within',
    ratio,
    limitText: fmtInUnit(ctx.mapPa, unit),
    convertedText: row.pressureUnit !== unit ? `about ${fmtInUnit(pa, unit)}` : null,
  };
}

const RANK: Record<PressureComparison['status'], number> = { above: 0, within: 1, 'not-comparable': 2, 'no-pressure': 3 };

/**
 * Checks the rows that set the published reference against the applied maximum. The reference charge itself is not
 * changed; `withinCharge` is the highest published charge below the reference whose own published pressure is at or
 * below that maximum (never at or above the reference, which stays the ceiling).
 */
export function referencePressureCheck(
  rows: ValidationLoad[],
  reference: { charge: number; kind: 'max' | 'single' } | null,
  ctx: LimitContext,
): { ref: PressureComparison; withinCharge: number | null } | null {
  if (!reference) return null;
  const type = reference.kind === 'max' ? 'max' : 'other';
  const refRows = rows.filter((r) => r.loadType === type && Math.abs(r.chargeGr - reference.charge) < 1e-9);
  if (!refRows.length) return null;
  const ranked = refRows
    .map((r) => comparePublishedPressure(r, ctx))
    .sort((a, b) => RANK[a.status] - RANK[b.status] || (b.ratio ?? 0) - (a.ratio ?? 0));
  const within = rows
    .filter((r) => r.loadType !== 'section-max' && r.chargeGr < reference.charge - 1e-9)
    .filter((r) => comparePublishedPressure(r, ctx).status === 'within')
    .map((r) => r.chargeGr);
  return { ref: ranked[0], withinCharge: within.length ? Math.max(...within) : null };
}

/** Plain name of the maximum being applied. */
export function limitName(ctx: LimitContext): string {
  if (ctx.standard === 'custom') return 'your custom limit';
  if (ctx.userCartridge) return 'the maximum you entered for this cartridge';
  return ctx.standard === 'CIP' ? 'the C.I.P. Pmax' : 'the SAAMI MAP';
}

export function limitContext(d: DerivedLoad, standard: PressureStandard): LimitContext {
  return { standard, mapPa: d.limit.mapPa, saamiMapCup: d.cartridge?.saamiMapCup ?? null, userCartridge: !!d.cartridge?.user };
}

/** Note on how the maker's reference load's own published pressure compares with the maximum being applied. */
export function ReferencePressureNote({
  rows,
  reference,
  ctx,
  chargeGr,
}: {
  rows: ValidationLoad[];
  reference: { charge: number; kind: 'max' | 'single' } | null;
  ctx: LimitContext;
  chargeGr?: number;
}) {
  const chk = referencePressureCheck(rows, reference, ctx);
  if (!chk || !reference) return null;
  const { ref, withinCharge } = chk;
  const what = reference.kind === 'max' ? 'maximum' : 'highest published load';
  const name = limitName(ctx);
  if (ref.status === 'above') {
    const pub = `${ref.row.pressure!.toLocaleString('en-US')} ${ref.row.pressureUnit}${ref.convertedText ? ` (${ref.convertedText})` : ''}`;
    return (
      <div className="alert warn small" data-testid="published-above-limit">
        <strong>
          The maker's {what} for these components ({fmtNum(reference.charge, 1)} gr) was published at {pub}, above {name} you are applying ({ref.limitText}).
        </strong>{' '}
        Do not use it as your ceiling under this limit.{' '}
        {withinCharge !== null
          ? `The highest charge below it that the maker publishes at or below ${ref.limitText} is ${fmtNum(withinCharge, 1)} gr.`
          : `None of the maker's lower loads for these components is published at or below ${ref.limitText}.`}
        {chargeGr !== undefined && chargeGr > 0 && withinCharge !== null && chargeGr > withinCharge + 1e-9 && ` Your charge (${fmtNum(chargeGr, 1)} gr) is above it.`}
      </div>
    );
  }
  if (ref.status === 'within' && ref.convertedText) {
    return (
      <p className="small muted" data-testid="published-unit-note">
        The maker's {what} was published in {ref.row.pressureUnit}; {name} you are applying is in {limitUnit(ctx.standard)}. Converted, its published pressure ({ref.convertedText}) is within {ref.limitText}. The maker's test method may differ from the standard's, so this comparison is approximate.
      </p>
    );
  }
  if (ref.status === 'not-comparable' && ref.row.pressureUnit === 'CUP' && ctx.mapPa !== null) {
    return (
      <p className="small muted" data-testid="published-unit-note">
        The maker's {what} was published in CUP, which ORKA does not convert to psi or bar, so its pressure is not checked against {name} you are applying.
      </p>
    );
  }
  if (ref.status === 'no-pressure') {
    return (
      <p className="small muted" data-testid="published-unit-note">
        The maker publishes no pressure for this {what}, so ORKA cannot check it against {name} you are applying.
      </p>
    );
  }
  return null;
}

/** Shown when the published table failed to load: no cross-check is possible. */
export function PublishedFailed({ retry, what }: { retry: () => void; what: string }) {
  return (
    <div className="alert warn small" data-testid="published-failed">
      Published maker data could not be loaded, so {what}. Try again or reload the page, and check the powder maker's current load data before loading.{' '}
      <button className="btn small" onClick={retry}>
        Try again
      </button>
    </div>
  );
}

export function PublishedCrossCheck({ db, d, chargeGr, bulletWeightGr }: { db: Database; d: DerivedLoad; chargeGr: number; bulletWeightGr: number }) {
  const { builder } = useApp();
  const { rows: published, failed, retry } = usePublished();
  const rows = publishedMatches(db, d.cartridge?.id ?? null, d.powder?.id ?? null, bulletWeightGr, published);
  if (!d.cartridge || !d.powder) return null;
  if (published === null) return <div className="small muted">Loading published maker data…</div>;
  if (failed) return <PublishedFailed retry={retry} what="ORKA cannot cross-check this load" />;
  if (!rows.length) {
    return (
      <div className="alert info small" data-testid="published-none">
        No published maker load for {d.cartridge.name} + {d.powder.name}
        {bulletWeightGr > 0 ? ` with a ${fmtNum(bulletWeightGr, 0)} gr bullet` : ''} is in ORKA's database. Check the powder maker's current load data before loading.
      </div>
    );
  }
  const ref = publishedReference(rows);
  const maxCharge = ref?.charge ?? null;
  const over = maxCharge !== null && chargeGr > maxCharge + 1e-9;
  const ctx = limitContext(d, builder.standard);
  const higher = ref?.kind === 'single' ? loadsAboveReference(rows, ref.charge) : [];
  return (
    <div className="card" data-testid="published-crosscheck">
      <h3>Published maker data for these components</h3>
      {over && (
        <div className="alert danger" role="alert" data-testid="published-over">
          {ref?.kind === 'single' ? (
            higher.length ? (
              <strong>Your charge ({fmtNum(chargeGr, 1)} gr) is above the highest single load the maker publishes ({fmtNum(maxCharge, 1)} gr)</strong>
            ) : (
              <strong>Your charge ({fmtNum(chargeGr, 1)} gr) is above every load the maker publishes ({fmtNum(maxCharge, 1)} gr is the highest)</strong>
            )
          ) : (
            <strong>Your charge ({fmtNum(chargeGr, 1)} gr) is above the maker's published maximum ({fmtNum(maxCharge, 1)} gr)</strong>
          )}{' '}
          for this cartridge, powder and bullet weight.
          {higher.length > 0 && ` The maker's loads above ${fmtNum(maxCharge, 1)} gr are ${joinAnd(higher)}, which ORKA does not use as a ceiling.`}
          {' Published pressure-tested data takes precedence over any prediction.'}
        </div>
      )}
      <ReferencePressureNote rows={rows} reference={ref} ctx={ctx} chargeGr={chargeGr} />
      <p className="small muted">
        Pressure-tested data as published. Components (case, primer, exact bullet, COAL, barrel) can differ from yours. Always use the maker's current edition.
      </p>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>Bullet</th>
              <th>Type</th>
              <th className="num">Charge (gr)</th>
              <th className="num">Velocity (fps)</th>
              <th className="num">Pressure</th>
              <th className="num">Barrel (in)</th>
              <th className="num">COAL (in)</th>
              <th>Case / primer</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const cmp = comparePublishedPressure(r, ctx);
              return (
                <tr key={i} className={r.loadType === 'max' && over ? 'over' : undefined}>
                  <td>
                    {r.bulletMfr} {fmtNum(r.bulletWeightGr, 0)} gr {r.bulletModel}
                    {/\(/.test(r.cartridge) && <div className="small muted">{r.cartridge}</div>}
                  </td>
                  <td>{TYPE_LABEL[r.loadType ?? ''] ?? r.loadType}</td>
                  <td className="num">{fmtNum(r.chargeGr, 1)}</td>
                  <td className="num">{fmtNum(r.velocityFps, 0)}</td>
                  <td className="num">
                    {r.pressure !== null ? `${r.pressure.toLocaleString('en-US')} ${r.pressureUnit ?? ''}` : '—'}
                    {cmp.convertedText && <div className="small muted">{cmp.convertedText}</div>}
                    {cmp.status === 'above' && (
                      <div className="small" style={{ color: 'var(--danger)' }}>
                        above {limitName(ctx)}
                      </div>
                    )}
                  </td>
                  <td className="num">{Number.isFinite(r.barrelLengthIn) ? fmtNum(r.barrelLengthIn, 0) : '—'}</td>
                  <td className="num">{Number.isFinite(r.coalIn) ? fmtNum(r.coalIn, 3) : '—'}</td>
                  <td>{[r.caseBrand, r.primer].filter(Boolean).join(' / ') || '—'}</td>
                  <td>
                    {r.sources[0] ? (
                      <a href={`${r.sources[0].url}${r.sources[0].page ? `#page=${r.sources[0].page}` : ''}`} target="_blank" rel="noopener noreferrer">
                        maker{r.sources[0].page ? ` p.${r.sources[0].page}` : ''}
                      </a>
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** The maker's reference maximum for these components: the lowest published 'max' charge; if the maker publishes only
 * single loads (no start/max pair), the highest published single load (exceeding every published load is flagged). */
export function publishedReference(rows: ValidationLoad[]): { charge: number; kind: 'max' | 'single' } | null {
  const max = rows.filter((r) => r.loadType === 'max');
  if (max.length) return { charge: Math.min(...max.map((r) => r.chargeGr)), kind: 'max' };
  const single = rows.filter((r) => r.loadType === 'other');
  if (single.length) return { charge: Math.max(...single.map((r) => r.chargeGr)), kind: 'single' };
  return null;
}

const HIGHER_LABEL: Record<string, string> = {
  start: 'start loads',
  reduced: 'reduced loads',
  'section-max': 'maxima for a higher-pressure firearm section (e.g. lever or modern rifles)',
};

/** Joins phrases as "a", "a and b", "a, b and c". */
export const joinAnd = (xs: string[]) => (xs.length < 2 ? xs.join('') : `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}`);

/**
 * For a single-load reference: the kinds of load the maker lists above it (start loads, section maxima, ...), which
 * are not used as a ceiling. Empty when the reference is above every published load.
 */
export function loadsAboveReference(rows: ValidationLoad[], charge: number): string[] {
  const types = new Set(rows.filter((r) => r.chargeGr > charge + 1e-9 && r.loadType !== 'max' && r.loadType !== 'other').map((r) => r.loadType ?? ''));
  const order = Object.keys(HIGHER_LABEL);
  return [...types]
    .sort((a, b) => (order.indexOf(a) + 1 || 99) - (order.indexOf(b) + 1 || 99) || a.localeCompare(b))
    .map((t) => HIGHER_LABEL[t] ?? (t ? `${t} loads` : 'loads of unstated type'));
}

const TYPE_LABEL: Record<string, string> = {
  max: 'max',
  start: 'start',
  other: 'single load',
  reduced: 'reduced (not a max)',
  'section-max': 'max for a higher-pressure firearm section (e.g. lever or modern rifles), not the cartridge standard',
};

const validRange = (r: unknown): [number, number] | null =>
  Array.isArray(r) && r.length === 2 && Number.isFinite(r[0]) && Number.isFinite(r[1]) && r[0] <= r[1] ? [r[0], r[1]] : null;

/** Warnings about how far the current prediction is from the powder model's calibration data. */
export function scopeWarnings(d: DerivedLoad, chargeGr: number): string[] {
  const out: string[] = [];
  const m = d.powder?.model;
  if (!m || !m.calibration) return out;
  const cal = m.calibration;
  const cid = d.cartridge?.id;
  if (cid && cal.cartridges.length && !cal.cartridges.includes(cid)) {
    out.push(
      `${d.powder!.name} was calibrated on ${cal.cartridges.join(', ')}, not on ${d.cartridge!.name}. This prediction transfers the model to a new cartridge; the Validation tab shows the typical error of such held-out predictions.`,
    );
  }
  if (cid && chargeGr > 0) {
    // Charge range for this cartridge; a single-cartridge model's overall range is that cartridge's range.
    const byCart = cal.chargeRangeByCartridge;
    const own = byCart && typeof byCart === 'object' ? validRange(byCart[cid]) : null;
    const range = own ?? (cal.cartridges.length === 1 && cal.cartridges[0] === cid ? validRange(cal.chargeRangeGr) : null);
    if (range && (chargeGr < range[0] - 0.05 || chargeGr > range[1] + 0.05)) {
      out.push(
        `Charge ${fmtNum(chargeGr, 1)} gr is outside the charges ${d.powder!.name} was calibrated on in ${d.cartridge!.name} (${fmtNum(range[0], 1)}–${fmtNum(range[1], 1)} gr). The prediction is an extrapolation: rely on the maker's published data here.`,
      );
    }
  }
  if (cal.points < 3) out.push(`The model for ${d.powder!.name} rests on only ${cal.points} data point(s).`);
  return out;
}

export function ScopeWarnings({ d, chargeGr }: { d: DerivedLoad; chargeGr: number }) {
  const w = scopeWarnings(d, chargeGr);
  if (!w.length) return null;
  return (
    <div className="alert warn small" data-testid="scope-warnings">
      <ul style={{ margin: 0 }}>
        {w.map((x) => (
          <li key={x}>{x}</li>
        ))}
      </ul>
    </div>
  );
}
