// Safety cross-checks shown next to every prediction:
//  1. Published maker data for the same cartridge + powder (+ bullet weight) — the maker's maximum wins.
//  2. Calibration scope — warns when the prediction extrapolates beyond the data the powder model was fitted to.

import type { Database, ValidationLoad } from '../data/schema';
import type { DerivedLoad } from './useLoad';
import { fmtNum } from './format';
import { publishedLoadFailed, usePublishedLoads } from './published';

export function publishedMatches(db: Database, cartridgeId: string | null, powderId: string | null, bulletWeightGr: number, published?: ValidationLoad[] | null): ValidationLoad[] {
  if (!cartridgeId || !powderId) return [];
  return [...db.validationLoads, ...(published ?? [])]
    .filter((l) => l.cartridgeId === cartridgeId && l.powderId === powderId)
    .filter((l) => !(bulletWeightGr > 0) || Math.abs(l.bulletWeightGr - bulletWeightGr) <= 1)
    .sort((a, b) => a.bulletWeightGr - b.bulletWeightGr || a.chargeGr - b.chargeGr);
}

export function PublishedCrossCheck({ db, d, chargeGr, bulletWeightGr }: { db: Database; d: DerivedLoad; chargeGr: number; bulletWeightGr: number }) {
  const published = usePublishedLoads();
  const rows = publishedMatches(db, d.cartridge?.id ?? null, d.powder?.id ?? null, bulletWeightGr, published);
  if (!d.cartridge || !d.powder) return null;
  if (published === null) return <div className="small muted">Loading published maker data…</div>;
  if (publishedLoadFailed()) {
    return (
      <div className="alert warn small" data-testid="published-failed">
        Published maker data could not be loaded, so ORKA cannot cross-check this load. Reload the page, and check the powder maker's current load data before loading.
      </div>
    );
  }
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
  return (
    <div className="card" data-testid="published-crosscheck">
      <h3>Published maker data for these components</h3>
      {over && (
        <div className="alert danger" role="alert" data-testid="published-over">
          {ref?.kind === 'single' ? (
            <strong>Your charge ({fmtNum(chargeGr, 1)} gr) is above every load the maker publishes ({fmtNum(maxCharge, 1)} gr is the highest)</strong>
          ) : (
            <strong>Your charge ({fmtNum(chargeGr, 1)} gr) is above the maker's published maximum ({fmtNum(maxCharge, 1)} gr)</strong>
          )}{' '}
          for this cartridge, powder and bullet weight. Published pressure-tested data takes precedence over any prediction.
        </div>
      )}
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
            {rows.map((r, i) => (
              <tr key={i} className={r.loadType === 'max' && over ? 'over' : undefined}>
                <td>
                  {r.bulletMfr} {fmtNum(r.bulletWeightGr, 0)} gr {r.bulletModel}
                  {/\(/.test(r.cartridge) && <div className="small muted">{r.cartridge}</div>}
                </td>
                <td>{TYPE_LABEL[r.loadType ?? ''] ?? r.loadType}</td>
                <td className="num">{fmtNum(r.chargeGr, 1)}</td>
                <td className="num">{fmtNum(r.velocityFps, 0)}</td>
                <td className="num">{r.pressure !== null ? `${r.pressure.toLocaleString('en-US')} ${r.pressureUnit ?? ''}` : '—'}</td>
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
            ))}
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

const TYPE_LABEL: Record<string, string> = {
  max: 'max',
  start: 'start',
  other: 'single load',
  reduced: 'reduced (not a max)',
  'section-max': 'max for a higher-pressure firearm section (e.g. lever or modern rifles), not the cartridge standard',
};

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
  if (cal.chargeRangeGr && chargeGr > 0) {
    const [lo, hi] = cal.chargeRangeGr;
    if (cid && cal.cartridges.length === 1 && cal.cartridges[0] === cid && (chargeGr < lo - 0.05 || chargeGr > hi + 0.05)) {
      out.push(`Charge ${fmtNum(chargeGr, 1)} gr is outside the calibrated range ${fmtNum(lo, 1)}–${fmtNum(hi, 1)} gr: this is an extrapolation.`);
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
