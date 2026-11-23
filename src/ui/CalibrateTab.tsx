// Fit a powder's burn model to the user's own chronograph data (and/or published pressures).

import { useEffect, useMemo, useRef, useState } from 'react';
import type { CalibrationInput, CalibrationResult, FitParam } from '../engine/calibrate';
import { paramsFromPropellant, propellantFromParams, toSetup } from '../engine/adapter';
import * as U from '../engine/units';
import type { PowderModelEntry, PowderModelParams } from '../data/schema';
import type { CalibrateMessage } from '../workers/calibrate.worker';
import { ErrorList, NumberField, PlainNumber, SearchPicker, StatusChip, TextField } from './components';
import { fmtNum, fmtP, fmtV } from './format';
import { powderItems } from './LoadBuilder';
import { useApp } from './state';
import { geometryErrors, modelStatus } from './useLoad';

/**
 * Generic starting point when a powder has no model at all. These are the plausible single-base values used in
 * the engine's own tests — they are NOT sourced data for any real powder. Only the parameters you tick are fitted.
 */
export const PLACEHOLDER_START: PowderModelParams = {
  forceJg: 1000,
  flameTempK: 2900,
  gamma: 1.24,
  covolumeCm3g: 1.0,
  solidDensityGcc: 1.6,
  beta: 5,
  n: 1,
  lambda: 0,
  mu: 0,
  tempCoeffPerK: 0,
  refTempC: 21,
  heatScale: 1,
};

interface Row {
  chargeGr: number;
  velFps: number;
  pPsi: number;
  label: string;
}

const emptyRow = (): Row => ({ chargeGr: NaN, velFps: NaN, pPsi: NaN, label: '' });

const PARAM_FIELDS: { key: keyof PowderModelParams; label: string; unit: string }[] = [
  { key: 'forceJg', label: 'Impetus (force)', unit: 'J/g' },
  { key: 'flameTempK', label: 'Flame temperature', unit: 'K' },
  { key: 'gamma', label: 'Ratio of specific heats γ', unit: '' },
  { key: 'covolumeCm3g', label: 'Covolume', unit: 'cm³/g' },
  { key: 'solidDensityGcc', label: 'Solid density', unit: 'g/cm³' },
  { key: 'beta', label: 'Burn-rate coefficient β', unit: '1/s @1 MPa' },
  { key: 'n', label: 'Pressure exponent n', unit: '' },
  { key: 'lambda', label: 'Progressivity λ', unit: '' },
  { key: 'mu', label: 'Form coefficient μ', unit: '' },
  { key: 'tempCoeffPerK', label: 'Temperature coefficient', unit: '1/K' },
  { key: 'refTempC', label: 'Reference temperature', unit: '°C' },
  { key: 'heatScale', label: 'Heat-loss scale', unit: '×' },
];

export function CalibrateTab() {
  const { db, builder, updateUser, user, prefs } = useApp();
  const sys = prefs.units;
  const [powderId, setPowderId] = useState<string | null>(builder.powderId);
  const powder = powderId ? db.powders.find((p) => p.id === powderId) ?? null : null;
  const [rows, setRows] = useState<Row[]>([emptyRow(), emptyRow(), emptyRow()]);
  const [fitLambda, setFitLambda] = useState(false);
  const [fitForce, setFitForce] = useState(false);
  const [fitHeat, setFitHeat] = useState(false);
  const [sigmaV, setSigmaV] = useState(15);
  const [sigmaP, setSigmaP] = useState(4);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CalibrationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const workerRef = useRef<Worker | null>(null);
  useEffect(() => () => workerRef.current?.terminate(), []);

  const items = useMemo(() => powderItems(db.powders), [db.powders]);
  const startParams: PowderModelParams = powder?.model && powder.model.status !== 'none' ? powder.model.params : PLACEHOLDER_START;
  const usingPlaceholder = !(powder?.model && powder.model.status !== 'none');
  const valid = rows.filter((r) => r.chargeGr > 0 && (r.velFps > 0 || r.pPsi > 0));
  const nPressure = valid.filter((r) => r.pPsi > 0).length;
  const geoErr = geometryErrors(builder);
  const errors = [...geoErr, ...(powder ? [] : ['Choose the powder to calibrate.']), ...(valid.length ? [] : ['Enter at least one charge with a measured velocity (or pressure).'])];

  const params: FitParam[] = ['beta', ...(fitLambda && valid.length >= 3 ? (['lambda'] as FitParam[]) : []), ...(fitForce && nPressure >= 1 ? (['force'] as FitParam[]) : []), ...(fitHeat && valid.length >= 4 ? (['heat'] as FitParam[]) : [])];

  const run = () => {
    if (!powder || errors.length) return;
    const start = propellantFromParams(startParams, powder.bulkDensityGcc ?? null);
    const heat = startParams.heatScale ?? 1;
    const observations = valid.map((r) => ({
      setup: toSetup({ ...builder.inputs, chargeGr: r.chargeGr }, start, {}, heat),
      velocityMs: r.velFps > 0 ? U.fpsToMs(r.velFps) : undefined,
      peakPa: r.pPsi > 0 ? U.psiToPa(r.pPsi) : undefined,
      label: r.label || undefined,
    }));
    const input: CalibrationInput = { start, startHeatScale: heat, observations, params, sigmaVelocityMs: U.fpsToMs(sigmaV || 15), sigmaPressureRel: (sigmaP || 4) / 100 };
    workerRef.current?.terminate();
    const w = new Worker(new URL('../workers/calibrate.worker.ts', import.meta.url), { type: 'module' });
    workerRef.current = w;
    setBusy(true);
    setError(null);
    setResult(null);
    setSaved(null);
    w.onmessage = (e: MessageEvent<CalibrateMessage>) => {
      if (e.data.type === 'done') setResult(e.data.result);
      else setError(e.data.message);
      setBusy(false);
      w.terminate();
      workerRef.current = null;
    };
    w.onerror = (e) => {
      setError(e.message || 'Calibration worker failed');
      setBusy(false);
      w.terminate();
      workerRef.current = null;
    };
    w.postMessage(input);
  };

  const save = () => {
    if (!powder || !result) return;
    const today = new Date().toISOString().slice(0, 10);
    const inp = builder.inputs;
    const cart = builder.cartridgeId ? db.cartridges.find((c) => c.id === builder.cartridgeId)?.name : 'custom chamber';
    const entry: PowderModelEntry = {
      status: 'user-calibrated',
      params: paramsFromPropellant(result.model, result.heatScale),
      derivation: `Fitted by you on ${today} to ${valid.length} point(s) (${params.join(', ')}) in ${cart}, ${inp.caseCapacityGrH2O} gr H2O case, ${inp.bulletWeightGr} gr bullet, ${inp.barrelLengthIn} in barrel, COAL ${inp.coalIn} in.${usingPlaceholder ? ' Started from generic placeholder thermochemistry.' : ''}`,
      calibration: {
        points: valid.length,
        rmsVelocityFps: result.rmsVelocityMs === null ? null : U.msToFps(result.rmsVelocityMs),
        rmsPressurePct: result.rmsPressureRel === null ? null : result.rmsPressureRel * 100,
        cartridges: [cart ?? 'custom'],
        sources: ['user measurements'],
      },
    };
    updateUser((u) => ({ ...u, powderModels: { ...u.powderModels, [powder.id]: entry } }));
    setSaved(`Saved as your calibration for ${powder.name}. It now overrides the shipped model on this device.`);
  };

  const hasUserModel = powder ? !!user.powderModels[powder.id] : false;

  return (
    <>
      <div className="card">
        <h2>Calibrate a powder</h2>
        <p className="small muted">
          Enter what you measured with the load builder's current cartridge, case capacity, bullet, COAL and barrel. ORKA fits the powder's burn-rate coefficient (and optionally progressivity, energy and heat loss) so the model reproduces your data. A calibration is only as good as the data and is most trustworthy near the conditions it was fitted on.
        </p>
        <SearchPicker label="Powder" items={items} value={powderId} onChange={(id) => { setPowderId(id); setResult(null); }} placeholder="Search powders…" testId="cal-powder" emptyText={db.powders.length ? 'No matches.' : 'No powders — add one in the Database tab.'} />
        {powder && (
          <div className="small" style={{ marginTop: 6 }}>
            Current model: <StatusChip status={modelStatus(powder)} /> {powder.model?.derivation}
            {usingPlaceholder && (
              <div className="alert warn" style={{ marginTop: 6 }}>
                This powder has no model, so fitting starts from generic placeholder thermochemistry (impetus {PLACEHOLDER_START.forceJg} J/g, γ {PLACEHOLDER_START.gamma}, covolume {PLACEHOLDER_START.covolumeCm3g} cm³/g, density {PLACEHOLDER_START.solidDensityGcc} g/cm³). These are not measured values for this powder. Tick “energy” with pressure data to fit it, or enter known values under Advanced.
              </div>
            )}
          </div>
        )}
        <div style={{ marginTop: 10 }}>
          <ErrorList errors={errors} title="Before fitting:" />
        </div>
      </div>

      <div className="card">
        <h3>Measurements</h3>
        <div className="table-wrap">
          <table className="data" data-testid="cal-rows">
            <thead>
              <tr>
                <th>Charge</th>
                <th>Velocity (avg)</th>
                <th>Peak pressure (piezo, optional)</th>
                <th>Label</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td style={{ minWidth: 120 }}>
                    <NumberField label={`Charge row ${i + 1}`} qty="charge" value={r.chargeGr} onChange={(v) => setRows((rs) => rs.map((x, j) => (j === i ? { ...x, chargeGr: v } : x)))} testId={`cal-charge-${i}`} />
                  </td>
                  <td style={{ minWidth: 120 }}>
                    <NumberField label={`Velocity row ${i + 1}`} qty="vel" value={r.velFps} onChange={(v) => setRows((rs) => rs.map((x, j) => (j === i ? { ...x, velFps: v } : x)))} testId={`cal-vel-${i}`} />
                  </td>
                  <td style={{ minWidth: 130 }}>
                    <NumberField label={`Pressure row ${i + 1}`} qty="press" value={r.pPsi} onChange={(v) => setRows((rs) => rs.map((x, j) => (j === i ? { ...x, pPsi: v } : x)))} />
                  </td>
                  <td style={{ minWidth: 110 }}>
                    <TextField label={`Label row ${i + 1}`} value={r.label} onChange={(v) => setRows((rs) => rs.map((x, j) => (j === i ? { ...x, label: v } : x)))} />
                  </td>
                  <td>
                    <button className="btn small danger" onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))} aria-label={`Remove row ${i + 1}`}>
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <button className="btn small" onClick={() => setRows((rs) => [...rs, emptyRow()])}>
            + row
          </button>
          <span className="small muted">Pressure must be piezo (psi / MPa), never CUP.</span>
        </div>
        <div className="section">
          <div className="section-title">Fit</div>
          <div className="row">
            <label className="check">
              <input type="checkbox" checked disabled /> burn rate β
            </label>
            <label className="check" title="needs ≥ 3 points">
              <input type="checkbox" checked={fitLambda} disabled={valid.length < 3} onChange={(e) => setFitLambda(e.target.checked)} /> progressivity λ (≥3 pts)
            </label>
            <label className="check" title="needs ≥ 1 pressure value">
              <input type="checkbox" checked={fitForce} disabled={nPressure < 1} onChange={(e) => setFitForce(e.target.checked)} /> energy (needs pressure)
            </label>
            <label className="check" title="needs ≥ 4 points">
              <input type="checkbox" checked={fitHeat} disabled={valid.length < 4} onChange={(e) => setFitHeat(e.target.checked)} /> heat loss (≥4 pts)
            </label>
          </div>
          <div className="grid-3" style={{ marginTop: 8 }}>
            <PlainNumber label="Velocity scatter (1σ)" unit="fps" value={sigmaV} onChange={setSigmaV} />
            <PlainNumber label="Pressure scatter (1σ)" unit="%" value={sigmaP} onChange={setSigmaP} />
            <div className="field" style={{ justifyContent: 'flex-end' }}>
              <button className="btn primary" disabled={busy || errors.length > 0} onClick={run} data-testid="run-cal">
                {busy ? 'Fitting…' : `Fit ${params.length} parameter${params.length > 1 ? 's' : ''}`}
              </button>
            </div>
          </div>
        </div>
        {error && <div className="alert danger" style={{ marginTop: 8 }}>{error}</div>}
      </div>

      {result && powder && (
        <div className="card" data-testid="cal-result">
          <h3>Fit result</h3>
          {result.warnings.length > 0 && (
            <div className="alert warn">
              <ul>
                {result.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="tiles" style={{ marginTop: 8 }}>
            <div className="tile">
              <div className="k">RMS velocity error</div>
              <div className="v">{result.rmsVelocityMs === null ? '—' : fmtV(result.rmsVelocityMs, sys)}</div>
            </div>
            <div className="tile">
              <div className="k">RMS pressure error</div>
              <div className="v">{result.rmsPressureRel === null ? '—' : `${fmtNum(result.rmsPressureRel * 100, 1)} %`}</div>
            </div>
            <div className="tile">
              <div className="k">Degrees of freedom</div>
              <div className="v">{result.degreesOfFreedom}</div>
            </div>
            <div className="tile">
              <div className="k">Converged</div>
              <div className="v">{result.converged ? 'yes' : 'no'}</div>
              <div className="s">{result.iterations} iterations</div>
            </div>
          </div>
          <div className="table-wrap" style={{ marginTop: 10 }}>
            <table className="data">
              <thead>
                <tr>
                  <th>Point</th>
                  <th className="num">Velocity meas.</th>
                  <th className="num">Velocity model</th>
                  <th className="num">Pressure meas.</th>
                  <th className="num">Pressure model</th>
                </tr>
              </thead>
              <tbody>
                {result.fits.map((f, i) => (
                  <tr key={i}>
                    <td>{f.label ?? `#${i + 1} (${valid[i] ? valid[i].chargeGr : '?'} gr)`}</td>
                    <td className="num">{f.velocityObsMs !== undefined ? fmtV(f.velocityObsMs, sys) : '—'}</td>
                    <td className="num">{fmtV(f.velocityPredMs, sys)}</td>
                    <td className="num">{f.peakObsPa !== undefined ? fmtP(f.peakObsPa, sys) : '—'}</td>
                    <td className="num">{fmtP(f.peakPredPa, sys)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="table-wrap" style={{ marginTop: 10 }}>
            <table className="data">
              <thead>
                <tr>
                  <th>Parameter</th>
                  <th className="num">Start</th>
                  <th className="num">Fitted</th>
                  <th className="num">± (1σ, rel.)</th>
                </tr>
              </thead>
              <tbody>
                {(
                  [
                    ['beta', 'β', startParams.beta, result.model.burn.beta],
                    ['lambda', 'λ', startParams.lambda, result.model.burn.lambda],
                    ['force', 'impetus J/g', startParams.forceJg, result.model.thermo.forceJkg / 1000],
                    ['heat', 'heat-loss scale', startParams.heatScale ?? 1, result.heatScale],
                  ] as [FitParam, string, number, number][]
                )
                  .filter(([k]) => params.includes(k))
                  .map(([k, label, a, b]) => {
                    const se = result.paramRelStdErr[k];
                    return (
                      <tr key={k}>
                        <td>{label}</td>
                        <td className="num">{fmtNum(a, 4)}</td>
                        <td className="num">{fmtNum(b, 4)}</td>
                        <td className="num">{se === null || se === undefined ? 'unknown' : k === 'lambda' ? `±${fmtNum(se, 3)}` : `±${fmtNum(se * 100, 1)} %`}</td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
          <div className="row" style={{ marginTop: 10 }}>
            <button className="btn primary" onClick={save} data-testid="save-cal">
              Save as my calibration
            </button>
            {saved && <span className="small" style={{ color: 'var(--ok)' }}>{saved}</span>}
          </div>
        </div>
      )}

      {powder && hasUserModel && (
        <div className="card">
          <div className="row">
            <span className="small">You have your own model for {powder.name}.</span>
            <button
              className="btn small danger"
              onClick={() =>
                updateUser((u) => {
                  const m = { ...u.powderModels };
                  delete m[powder.id];
                  return { ...u, powderModels: m };
                })
              }
            >
              Remove my model
            </button>
          </div>
        </div>
      )}

      {powder && <ManualParams powderId={powder.id} powderName={powder.name} start={startParams} />}
    </>
  );
}

function ManualParams({ powderId, powderName, start }: { powderId: string; powderName: string; start: PowderModelParams }) {
  const { updateUser } = useApp();
  const [p, setP] = useState<PowderModelParams>({ ...start, heatScale: start.heatScale ?? 1 });
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    setP({ ...start, heatScale: start.heatScale ?? 1 });
    setMsg(null);
  }, [powderId]); // eslint-disable-line react-hooks/exhaustive-deps
  const ok = PARAM_FIELDS.every((f) => Number.isFinite(p[f.key] as number)) && p.forceJg > 0 && p.gamma > 1 && p.solidDensityGcc > 0 && p.beta > 0 && p.n > 0 && p.lambda > -0.5;
  return (
    <details className="card collapsible" data-testid="manual-params">
      <summary>Advanced: enter model parameters manually for {powderName}</summary>
      <p className="small muted" style={{ marginTop: 8 }}>
        For users who have measured or published parameters for this exact powder lot. Values are stored on this device as your model and override the shipped model.
      </p>
      <div className="grid-3">
        {PARAM_FIELDS.map((f) => (
          <PlainNumber
            key={f.key}
            label={f.label}
            unit={f.unit}
            value={p[f.key] as number}
            onChange={(v) => setP((cur) => ({ ...cur, [f.key]: v }))}
            testId={`mp-${f.key}`}
          />
        ))}
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <button
          className="btn primary"
          disabled={!ok}
          data-testid="save-manual"
          onClick={() => {
            const entry: PowderModelEntry = { status: 'user-calibrated', params: { ...p }, derivation: 'entered manually by user' };
            updateUser((u) => ({ ...u, powderModels: { ...u.powderModels, [powderId]: entry } }));
            setMsg('Saved.');
          }}
        >
          Save parameters
        </button>
        {!ok && <span className="small" style={{ color: 'var(--danger)' }}>Check values: impetus, density, β, n &gt; 0; γ &gt; 1; λ &gt; −0.5.</span>}
        {msg && <span className="small" style={{ color: 'var(--ok)' }}>{msg}</span>}
      </div>
    </details>
  );
}
