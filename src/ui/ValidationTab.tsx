// Validation report: model predictions vs published pressure-tested loads.

import { DataTable, type Column } from './components';
import { fmtNum } from './format';

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
      render: (r) => (r.pObs !== null && r.pObsUnit === 'psi' && r.pPredPsi !== null ? fmtNum(((r.pPredPsi - r.pObs) / r.pObs) * 100, 1) : '—'),
      sortValue: (r) => (r.pObs !== null && r.pObsUnit === 'psi' && r.pPredPsi !== null ? (r.pPredPsi - r.pObs) / r.pObs : null),
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
            <div className="k">Velocity MAE</div>
            <div className="v">{m.velocityMaeFps === null ? '—' : `${fmtNum(m.velocityMaeFps, 0)} fps`}</div>
          </div>
          <div className="tile">
            <div className="k">Velocity MAPE</div>
            <div className="v">{m.velocityMapePct === null ? '—' : `${fmtNum(m.velocityMapePct, 1)} %`}</div>
          </div>
          <div className="tile">
            <div className="k">Pressure MAPE (psi rows)</div>
            <div className="v">{m.pressureMapePct === null ? '—' : `${fmtNum(m.pressureMapePct, 1)} %`}</div>
          </div>
        </div>
        {m.notes && <p className="small" style={{ marginTop: 8 }}>{m.notes}</p>}
      </div>
      <div className="card">
        <DataTable rows={rep.rows} columns={cols} rowKey={(r) => `${r.label}-${r.chargeGr}-${r.powder}`} rowClass={(r) => (r.heldOut ? 'heldout' : '')} testId="validation-table" />
      </div>
    </>
  );
}
