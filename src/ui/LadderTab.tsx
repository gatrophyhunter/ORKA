// Charge ladder and charge solvers.

import { useEffect, useState } from 'react';
import { ladder, solveChargeForPressure, solveChargeForVelocity, type ChargeSolution, type LadderRow } from '../engine/search';
import { DEFAULT_MAX_FILL } from '../engine/defaults';
import * as U from '../engine/units';
import { ErrorList, EstimateWarning, NumberField, PlainNumber, StatusChip } from './components';
import { fmtChargeKg, fmtP, fmtPct, fmtV, fmtMs } from './format';
import { useApp } from './state';
import { useLoad } from './useLoad';
import { publishedMatches, publishedReference, ScopeWarnings } from './CrossCheck';
import { usePublishedLoads } from './published';

export function LadderTab() {
  const { prefs, patchInputs, db, builder } = useApp();
  const sys = prefs.units;
  const d = useLoad();
  const base = d.setup;
  const [startGr, setStartGr] = useState<number>(NaN);
  const [endGr, setEndGr] = useState<number>(NaN);
  const [steps, setSteps] = useState<number>(10);
  const [rows, setRows] = useState<LadderRow[] | null>(null);
  const [maxFillPct, setMaxFillPct] = useState<number>(Math.round(DEFAULT_MAX_FILL * 1000) / 10);
  const [maxSol, setMaxSol] = useState<ChargeSolution | null>(null);
  const [targetFps, setTargetFps] = useState<number>(NaN);
  const [velSol, setVelSol] = useState<ChargeSolution | null | 'unreachable'>(null);
  const [busy, setBusy] = useState(false);
  const limit = d.limit.limitPa;
  // Results belong to the setup they were computed for: clear them when the load or its geometry changes (review finding).
  useEffect(() => {
    setRows(null);
    setMaxSol(null);
    setVelSol(null);
  }, [base]);
  // A solved maximum belongs to the limit it was solved for.
  useEffect(() => {
    setMaxSol(null);
    setVelSol(null);
  }, [limit]);
  // Over-limit state is evaluated against the CURRENT limit at render time; non-finite peaks count as over.
  const overNow = (peakPa: number) => limit !== null && !(peakPa <= limit);
  const published = usePublishedLoads();
  const pubMax = (() => {
    const ref = publishedReference(publishedMatches(db, d.cartridge?.id ?? null, d.powder?.id ?? null, builder.inputs.bulletWeightGr, published));
    return ref ? ref.charge : null;
  })();

  if (!base) {
    return (
      <div className="card">
        <h2>Charge ladder</h2>
        <ErrorList errors={d.errors} title="To build a ladder, complete the load builder:" />
      </div>
    );
  }

  const later = (fn: () => void) => {
    setBusy(true);
    setTimeout(() => {
      try {
        fn();
      } finally {
        setBusy(false);
      }
    }, 20);
  };

  const s0 = Number.isFinite(startGr) ? startGr : Math.max(0.1, +(base.chargeKg / U.KG_PER_GRAIN * 0.9).toFixed(1));
  const s1 = Number.isFinite(endGr) ? endGr : +(base.chargeKg / U.KG_PER_GRAIN * 1.05).toFixed(1);
  const opt = { maxFillRatio: (Number.isFinite(maxFillPct) ? maxFillPct : DEFAULT_MAX_FILL * 100) / 100, tolKg: 1e-6 };
  const applyCharge = (kg: number) => patchInputs({ chargeGr: +U.kgToGr(kg).toFixed(2) });

  return (
    <>
      <div className="card">
        <div className="card-head">
          <h2 style={{ margin: 0 }}>Charge ladder</h2>
          {d.powder && (
            <span className="row small">
              {d.powder.name} <StatusChip status={d.status} />
            </span>
          )}
        </div>
        <EstimateWarning status={d.status} />
        <ScopeWarnings d={d} chargeGr={builder.inputs.chargeGr} />
        {pubMax !== null && (
          <div className="alert info small">Maker's published maximum for these components: <strong>{pubMax.toFixed(1)} gr</strong>. Rows above it are marked “pub max”.</div>
        )}
        {limit === null && <div className="alert warn">No pressure limit set — rows cannot be flagged. {d.limit.note}</div>}
        <div className="grid-4" style={{ marginTop: 8 }}>
          <NumberField label="Start charge" qty="charge" value={s0} onChange={setStartGr} testId="ladder-start" />
          <NumberField label="End charge" qty="charge" value={s1} onChange={setEndGr} testId="ladder-end" />
          <PlainNumber label="Steps" value={steps} onChange={(v) => setSteps(Math.max(1, Math.min(60, Math.round(v || 1))))} testId="ladder-steps" />
          <div className="field" style={{ justifyContent: 'flex-end' }}>
            <button className="btn primary" disabled={busy || !(s1 > s0)} onClick={() => later(() => setRows(ladder(base, U.grToKg(s0), U.grToKg(s1), steps, limit ?? Infinity)))} data-testid="run-ladder">
              Run ladder
            </button>
          </div>
        </div>
        {rows && (
          <div className="table-wrap" style={{ marginTop: 10 }}>
            <table className="data" data-testid="ladder-table">
              <thead>
                <tr>
                  <th>Charge</th>
                  <th className="num">Peak pressure</th>
                  <th className="num">% of limit</th>
                  <th className="num">Velocity</th>
                  <th className="num">Fill</th>
                  <th className="num">Burnt</th>
                  <th className="num">Barrel time</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const overPub = pubMax !== null && U.kgToGr(r.chargeKg) > pubMax + 1e-9;
                  const over = overNow(r.result.peakBreechPa) || overPub;
                  return (
                    <tr key={r.chargeKg} className={over ? 'over' : ''}>
                      <td className="nowrap">
                        {over && (
                          <span className="stop" aria-label="over the pressure limit" title="Over the working pressure limit">
                            !
                          </span>
                        )}
                        {fmtChargeKg(r.chargeKg, sys)}
                        {overPub && <span className="small" style={{ marginLeft: 6, color: 'var(--danger)' }}>pub max</span>}
                      </td>
                      <td className="num">{fmtP(r.result.peakBreechPa, sys)}</td>
                      <td className="num">{limit !== null ? fmtPct(r.result.peakBreechPa / limit, 0) : '—'}</td>
                      <td className="num">{r.result.status === 'muzzle' ? fmtV(r.result.muzzleVelocityMs, sys) : r.result.status}</td>
                      <td className="num">{r.result.fillRatio === null ? '—' : fmtPct(r.result.fillRatio, 0)}</td>
                      <td className="num">{fmtPct(r.result.burntAtMuzzle, 0)}</td>
                      <td className="num">{fmtMs(r.result.barrelTime10S)}</td>
                      <td>
                        <button className="btn small" onClick={() => applyCharge(r.chargeKg)} disabled={over}>
                          use
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {rows && limit !== null && rows.some((r) => overNow(r.result.peakBreechPa)) && (
          <p className="small" style={{ marginTop: 6, color: 'var(--danger)' }}>
            Red rows exceed the working limit. Do not load them.
          </p>
        )}
      </div>

      <div className="card">
        <h3>Solvers</h3>
        <div className="grid-3">
          <PlainNumber label="Max fill (compression limit)" unit="%" value={maxFillPct} onChange={setMaxFillPct} hint="bulk powder volume / space under the bullet" />
          <div className="field" style={{ justifyContent: 'flex-end' }}>
            <button className="btn primary" disabled={busy || limit === null} onClick={() => later(() => setMaxSol(solveChargeForPressure(base, limit as number, opt)))} data-testid="solve-max">
              Max charge at limit
            </button>
          </div>
        </div>
        {maxSol && (
          <div className="alert info" style={{ marginTop: 8 }} data-testid="solve-max-result">
            <strong>{fmtChargeKg(maxSol.chargeKg, sys)}</strong> →{' '}
            {fmtP(maxSol.result.peakBreechPa, sys)}, {fmtV(maxSol.result.muzzleVelocityMs, sys)}, fill {maxSol.result.fillRatio === null ? 'unknown' : fmtPct(maxSol.result.fillRatio, 0)}, burnt {fmtPct(maxSol.result.burntAtMuzzle, 0)}. Limited by <strong>{maxSol.limitedBy}</strong>
            {maxSol.limitedBy !== 'pressure' ? ' (the pressure limit was not reached within the case volume)' : ''}.{' '}
            <button className="btn small" onClick={() => applyCharge(maxSol.chargeKg)}>
              use as charge
            </button>
            <div className="small muted" style={{ marginTop: 4 }}>
              This is a model maximum, not a load recommendation. Published maximums for your components take precedence.
            </div>
          </div>
        )}
        <div className="grid-3" style={{ marginTop: 12 }}>
          <NumberField label="Target velocity" qty="vel" value={targetFps} onChange={setTargetFps} testId="target-vel" />
          <div className="field" style={{ justifyContent: 'flex-end' }}>
            <button
              className="btn"
              disabled={busy || !(targetFps > 0)}
              onClick={() => later(() => setVelSol(solveChargeForVelocity(base, U.fpsToMs(targetFps), opt) ?? 'unreachable'))}
              data-testid="solve-vel"
            >
              Charge for target velocity
            </button>
          </div>
        </div>
        {velSol === 'unreachable' && <div className="alert warn" style={{ marginTop: 8 }}>Target velocity not reachable with this powder within the case volume.</div>}
        {velSol && velSol !== 'unreachable' && (
          <div className={`alert ${limit !== null && velSol.result.peakBreechPa > limit ? 'danger' : 'info'}`} style={{ marginTop: 8 }} data-testid="solve-vel-result">
            <strong>{fmtChargeKg(velSol.chargeKg, sys)}</strong> → {fmtV(velSol.result.muzzleVelocityMs, sys)} at {fmtP(velSol.result.peakBreechPa, sys)}
            {limit !== null && ` (${fmtPct(velSol.result.peakBreechPa / limit, 0)} of limit)`}
            {limit !== null && velSol.result.peakBreechPa > limit ? ' — OVER the limit: not achievable safely with this powder.' : '.'}{' '}
            {(limit === null || velSol.result.peakBreechPa <= limit) && (
              <button className="btn small" onClick={() => applyCharge(velSol.chargeKg)}>
                use as charge
              </button>
            )}
          </div>
        )}
      </div>
    </>
  );
}
