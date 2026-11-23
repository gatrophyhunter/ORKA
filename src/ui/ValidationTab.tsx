// Validation report: model predictions vs published pressure-tested loads.

import { DataTable, StatusChip, type Column } from './components';
import { fmtNum } from './format';
import { useApp } from './state';
import type { ModelStatus } from '../data/schema';

const PSI_PER_BAR = 14.503773773020923;
/** Published pressure in psi when the unit is psi or bar (exact unit conversion; CUP is never converted). */
const obsPsi = (r: { pObs: number | null; pObsUnit: string | null }) =>
  r.pObs === null ? null : r.pObsUnit === 'psi' ? r.pObs : r.pObsUnit === 'bar' ? r.pObs * PSI_PER_BAR : null;

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

// Optional file: absent until the calibration pipeline produces it. import.meta.glob keeps the build working either way.
const found = import.meta.glob('../data/validation-report.json', { eager: true, import: 'default' }) as Record<string, ValidationReport>;
export const VALIDATION_REPORT: ValidationReport | null = Object.values(found)[0] ?? null;

export function ValidationTab() {
  const rep = VALIDATION_REPORT;
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
      <div className="card">
        <DataTable rows={rep.rows} columns={cols} rowKey={(r) => `${r.label}-${r.chargeGr}-${r.powder}-${r.heldOut}`} rowClass={(r) => (r.heldOut ? 'heldout' : '')} testId="validation-table" />
      </div>
      <CoverageCard />
    </>
  );
}
