// Validation report: model predictions vs published pressure-tested loads.

import { useEffect, useState } from 'react';
import { DataTable, StatusChip, type Column } from './components';
import { fmtNum } from './format';
import { useApp } from './state';
import type { ModelStatus } from '../data/schema';

const PSI_PER_BAR = 14.503773773020923;
/** Published pressure in psi when the unit is psi or bar (exact unit conversion; CUP is never converted). */
const obsPsi = (r: { pObs: number | null; pObsUnit: string | null }) =>
  r.pObs === null ? null : r.pObsUnit === 'psi' ? r.pObs : r.pObsUnit === 'bar' ? r.pObs * PSI_PER_BAR : null;

/** Held-out error broken down by bullet construction and by whether the bullet length was published or estimated. */
function Breakdown({ rows }: { rows: ValidationRow[] }) {
  const held = rows.filter((r) => r.heldOut);
  const groups: { label: string; f: (r: ValidationRow) => boolean }[] = [
    { label: 'All held-out', f: () => true },
    { label: 'Bullet length published by maker', f: (r) => r.lengthEstimated === false },
    { label: 'Bullet length estimated (maker publishes none)', f: (r) => r.lengthEstimated === true },
    { label: 'Jacketed bullets', f: (r) => r.shotClass === 'jacketed' },
    { label: 'Monolithic bullets', f: (r) => r.shotClass === 'monolithic' },
  ];
  const stats = (rs: ValidationRow[]) => {
    const pe = rs.map((r) => {
      const o = obsPsi(r);
      return o !== null && r.pPredPsi !== null ? Math.abs((r.pPredPsi - o) / o) : null;
    }).filter((x): x is number => x !== null).sort((a, b) => a - b);
    const ve = rs.filter((r) => r.velPredFps !== null && r.velObsFps > 0).map((r) => Math.abs((r.velPredFps as number) - r.velObsFps)).sort((a, b) => a - b);
    const signed = rs.map((r) => {
      const o = obsPsi(r);
      return o !== null && r.pPredPsi !== null ? (r.pPredPsi - o) / o : null;
    }).filter((x): x is number => x !== null);
    const q = (a: number[], f: number) => (a.length ? a[Math.min(a.length - 1, Math.floor(f * a.length))] : null);
    return { nP: pe.length, p50: q(pe, 0.5), p90: q(pe, 0.9), bias: signed.length ? signed.reduce((s, v) => s + v, 0) / signed.length : null, nV: ve.length, v50: q(ve, 0.5), v90: q(ve, 0.9) };
  };
  if (!held.length || held[0].cartType === undefined) return null;
  return (
    <div className="card" data-testid="validation-breakdown">
      <h3>Held-out error by group</h3>
      <p className="small muted">Absolute errors of held-out predictions. p50 = median, p90 = 90th percentile (one prediction in ten is worse than this). Bias is the mean signed pressure error: negative means the model predicts <strong>lower</strong> pressure than was measured — the unsafe direction. The all-held-out bias mixes jacketed and monolithic bullets: read the row for your bullet's construction (the Predict tab shows it for the selected bullet).</p>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>Group</th>
              <th className="num">Pressure n</th>
              <th className="num">Pressure p50</th>
              <th className="num">Pressure p90</th>
              <th className="num" title="Mean signed error: negative = model predicts lower pressure than published (the unsafe direction)">Pressure bias</th>
              <th className="num">Velocity n</th>
              <th className="num">Velocity p50</th>
              <th className="num">Velocity p90</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((g) => {
              const s = stats(held.filter(g.f));
              return (
                <tr key={g.label}>
                  <td>{g.label}</td>
                  <td className="num">{s.nP}</td>
                  <td className="num">{s.p50 === null ? '—' : `${fmtNum(s.p50 * 100, 1)} %`}</td>
                  <td className="num">{s.p90 === null ? '—' : `${fmtNum(s.p90 * 100, 1)} %`}</td>
                  <td className="num" style={s.bias !== null && s.bias < 0 ? { color: 'var(--danger)' } : undefined}>{s.bias === null ? '—' : `${s.bias >= 0 ? '+' : ''}${fmtNum(s.bias * 100, 1)} %`}</td>
                  <td className="num">{s.nV}</td>
                  <td className="num">{s.v50 === null ? '—' : `${fmtNum(s.v50, 0)} fps`}</td>
                  <td className="num">{s.v90 === null ? '—' : `${fmtNum(s.v90, 0)} fps`}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Which powders, per maker, have calibrated / estimated / no models in this build. */
export function CoverageCard() {
  const { db } = useApp();
  if (!db.powders.length) return null;
  const statuses: ModelStatus[] = ['calibrated', 'user-calibrated', 'estimated', 'none'];
  const byMaker = new Map<string, Record<ModelStatus, string[]>>();
  for (const p of db.powders) {
    const m = byMaker.get(p.manufacturer) ?? { calibrated: [], 'user-calibrated': [], estimated: [], none: [] };
    m[p.model?.status ?? 'none'].push(p.name);
    byMaker.set(p.manufacturer, m);
  }
  return (
    <div className="card" data-testid="coverage">
      <h3>Powder model coverage</h3>
      <p className="small muted">Every powder in the database, by maker and model status. Powders without a model cannot be simulated until you calibrate them with your own chronograph data.</p>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>Maker</th>
              {statuses.map((s) => (
                <th key={s} className="num">
                  <StatusChip status={s} />
                </th>
              ))}
              <th>Without a model</th>
            </tr>
          </thead>
          <tbody>
            {[...byMaker.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([maker, m]) => (
              <tr key={maker}>
                <td>{maker}</td>
                {statuses.map((s) => (
                  <td key={s} className="num">
                    {m[s].length}
                  </td>
                ))}
                <td className="small">{m.none.join(', ') || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export interface ValidationRow {
  cartType?: 'rifle' | 'handgun' | null;
  lengthEstimated?: boolean;
  capacityTier?: string;
  shotClass?: string;
  label: string;
  cartridge: string;
  powder: string;
  chargeGr: number;
  velObsFps: number;
  velPredFps: number;
  pObs: number | null;
  pObsUnit: string | null;
  pPredPsi: number | null;
  heldOut: boolean;
}

export interface ValidationReport {
  generated: string;
  metrics: { points: number; velocityMaeFps: number | null; velocityMapePct: number | null; pressureMapePct: number | null; notes: string };
  rows: ValidationRow[];
}

// Optional, large file: loaded lazily when this tab opens. import.meta.glob keeps the build working when it is absent.
const loaders = import.meta.glob('../data/validation-report.json', { import: 'default' }) as Record<string, () => Promise<ValidationReport>>;
let reportCache: ValidationReport | null | undefined;

function useReport(): ValidationReport | null | undefined {
  const [rep, setRep] = useState<ValidationReport | null | undefined>(reportCache);
  useEffect(() => {
    if (reportCache !== undefined) return;
    const fn = Object.values(loaders)[0];
    let live = true;
    (fn ? fn() : Promise.resolve(null))
      .then((r) => {
        reportCache = r ?? null;
        if (live) setRep(reportCache);
      })
      .catch(() => live && setRep((reportCache = null)));
    return () => {
      live = false;
    };
  }, []);
  return rep;
}

export function ValidationTab() {
  const rep = useReport();
  if (rep === undefined) return <div className="card">Loading validation report…</div>;
  if (!rep || !rep.rows?.length) {
    return (
      <div className="card" data-testid="validation-pending">
        <h2>Validation</h2>
        <p>
          This page will compare ORKA's predictions with published, pressure-tested load data (manufacturer data that states charge, velocity and piezo pressure for a stated barrel and COAL). Powders are fitted on part of that data; the rest is held out so the comparison measures prediction, not curve-fitting.
        </p>
        <div className="alert info">The validation report is not yet available in this build.</div>
        <CoverageCard />
      </div>
    );
  }
  const cols: Column<ValidationRow>[] = [
    { key: 'label', label: 'Load', render: (r) => <>{r.label} {r.heldOut && <span className="chip user-calibrated">held out</span>}</>, sortValue: (r) => r.label },
    { key: 'cart', label: 'Cartridge', render: (r) => r.cartridge, sortValue: (r) => r.cartridge },
    { key: 'powder', label: 'Powder', render: (r) => r.powder, sortValue: (r) => r.powder },
    { key: 'charge', label: 'Charge gr', num: true, render: (r) => fmtNum(r.chargeGr, 1), sortValue: (r) => r.chargeGr },
    { key: 'vo', label: 'Vel. published', num: true, render: (r) => fmtNum(r.velObsFps, 0), sortValue: (r) => r.velObsFps },
    { key: 'vp', label: 'Vel. model', num: true, render: (r) => fmtNum(r.velPredFps, 0), sortValue: (r) => r.velPredFps },
    { key: 'dv', label: 'Δ vel %', num: true, render: (r) => `${fmtNum(((r.velPredFps - r.velObsFps) / r.velObsFps) * 100, 1)}`, sortValue: (r) => (r.velPredFps - r.velObsFps) / r.velObsFps },
    { key: 'po', label: 'Pressure published', num: true, render: (r) => (r.pObs === null ? '—' : `${fmtNum(r.pObs, 0)} ${r.pObsUnit ?? ''}`), sortValue: (r) => r.pObs },
    { key: 'pp', label: 'Pressure model psi', num: true, render: (r) => fmtNum(r.pPredPsi, 0), sortValue: (r) => r.pPredPsi },
    { key: 'len', label: 'Bullet length', render: (r) => (r.lengthEstimated === undefined ? '—' : r.lengthEstimated ? 'estimated' : 'published'), sortValue: (r) => (r.lengthEstimated ? 1 : 0) },
    {
      key: 'dp',
      label: 'Δ p %',
      num: true,
      render: (r) => {
        const o = obsPsi(r);
        return o !== null && r.pPredPsi !== null ? fmtNum(((r.pPredPsi - o) / o) * 100, 1) : '—';
      },
      sortValue: (r) => {
        const o = obsPsi(r);
        return o !== null && r.pPredPsi !== null ? (r.pPredPsi - o) / o : null;
      },
    },
  ];
  const m = rep.metrics;
  return (
    <>
      <div className="card" data-testid="validation-report">
        <h2>Validation</h2>
        <p className="small muted">Generated {rep.generated}. Held-out rows (blue) were not used to fit the powder they test. CUP pressures are shown but never compared with piezo psi.</p>
        <div className="tiles">
          <div className="tile">
            <div className="k">Data points</div>
            <div className="v">{m.points}</div>
          </div>
          <div className="tile">
            <div className="k">Velocity MAE (held out)</div>
            <div className="v">{m.velocityMaeFps === null ? '—' : `${fmtNum(m.velocityMaeFps, 0)} fps`}</div>
          </div>
          <div className="tile">
            <div className="k">Velocity MAPE</div>
            <div className="v">{m.velocityMapePct === null ? '—' : `${fmtNum(m.velocityMapePct, 1)} %`}</div>
          </div>
          <div className="tile">
            <div className="k">Pressure MAPE (held out)</div>
            <div className="v">{m.pressureMapePct === null ? '—' : `${fmtNum(m.pressureMapePct, 1)} %`}</div>
          </div>
        </div>
        {m.notes && <p className="small" style={{ marginTop: 8 }}>{m.notes}</p>}
      </div>
      <Breakdown rows={rep.rows} />
      <div className="card">
        <DataTable rows={rep.rows} columns={cols} rowKey={(r) => `${r.label}-${r.chargeGr}-${r.powder}-${r.heldOut}`} rowClass={(r) => (r.heldOut ? 'heldout' : '')} testId="validation-table" />
      </div>
      <CoverageCard />
    </>
  );
}
