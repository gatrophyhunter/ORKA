// Single-load prediction: results, charts, uncertainty band, sensitivities, temperature sweep.

import { useMemo, useState } from 'react';
import { simulate } from '../engine/model';
import { monteCarlo, sensitivities, temperatureSweep, specForPowderModel, type MonteCarloResult, type UncertaintySpec } from '../engine/uncertainty';
import * as U from '../engine/units';
import { FitGrade, ErrorList, EstimateWarning, PlainNumber, StatusChip, Tile, useDebounced } from './components';
import { fmtChargeKg, fmtE, fmtLen, fmtMs, fmtNum, fmtP, fmtPct, fmtTempC, fmtV, lenUnit, lenVal, pUnit, pVal, vUnit, vVal } from './format';
import { LineChart } from './LineChart';
import { useApp } from './state';
import { PublishedCrossCheck, ScopeWarnings } from './CrossCheck';
import { modelValidation } from '../engine/defaults';
import { encodeBuilder } from './share';
import { useLoad } from './useLoad';

export function pressureState(peakPa: number, limitPa: number | null): 'ok' | 'warn' | 'danger' | undefined {
  if (limitPa === null) return undefined;
  if (peakPa === Infinity) return 'danger'; // runaway ('diverged') result
  if (!Number.isFinite(peakPa)) return undefined;
  const r = peakPa / limitPa;
  if (r > 1) return 'danger';
  if (r > 0.95) return 'warn';
  return 'ok';
}

export function PredictTab() {
  const { prefs, db, builder } = useApp();
  const sys = prefs.units;
  const d = useLoad();
  const setup = useDebounced(d.setup, 150);

  const res = useMemo(() => (setup ? simulate({ ...setup, options: { ...setup.options, recordTrace: true } }) : null), [setup]);
  const sens = useMemo(() => (setup && res?.status === 'muzzle' ? sensitivities(setup) : null), [setup, res]);
  const sweep = useMemo(() => (setup && res?.status === 'muzzle' ? temperatureSweep(setup, [-20, -10, 0, 10, 20, 30, 40, 50]) : null), [setup, res]);

  // Elasticity of peak pressure to burn rate for THIS load (sensitivities() perturbs beta by a factor e^0.03).
  const betaSens = sens?.find((x) => x.key === 'beta');
  const elasticity = betaSens ? betaSens.peakPct / (100 * (Math.exp(0.03) - 1)) : undefined;
  const defaultSpec = specForPowderModel(d.powder?.model, elasticity);
  const [spec, setSpec] = useState<UncertaintySpec | null>(null);
  const activeSpec = spec ?? defaultSpec;
  const [mc, setMc] = useState<{ r: MonteCarloResult; key: unknown } | null>(null);
  const [mcBusy, setMcBusy] = useState(false);
  const [shareMsg, setShareMsg] = useState<string | null>(null);

  if (!d.setup && !setup) {
    return (
      <div className="card">
        <h2>Prediction</h2>
        <ErrorList errors={d.errors} title="To predict, complete the load builder:" />
      </div>
    );
  }

  const limit = d.limit.limitPa;
  const ke = res && res.status === 'muzzle' ? 0.5 * (setup?.bullet.massKg ?? 0) * res.muzzleVelocityMs ** 2 : NaN;
  const pState = res ? pressureState(res.peakBreechPa, limit) : undefined;
  const ratio = res && limit ? res.peakBreechPa / limit : null;

  const runMc = () => {
    if (!setup) return;
    setMcBusy(true);
    setTimeout(() => {
      const r = monteCarlo(setup, activeSpec, 200, 12345);
      setMc({ r, key: setup });
      setMcBusy(false);
    }, 20);
  };
  const mcCurrent = mc && mc.key === setup ? mc.r : null;

  const tr = res?.trace;
  const travelPts = tr ? tr.x.map((x, i) => ({ x: lenVal(x, sys), y: pVal(tr.pBreech[i], sys) })) : [];
  const basePts = tr ? tr.x.map((x, i) => ({ x: lenVal(x, sys), y: pVal(tr.pBase[i], sys) })) : [];
  const velPts = tr ? tr.x.map((x, i) => ({ x: lenVal(x, sys), y: vVal(tr.v[i], sys) })) : [];
  const timePts = tr ? tr.t.map((t, i) => ({ x: t * 1000, y: pVal(tr.pBreech[i], sys) })) : [];
  const psiPts = tr ? tr.t.map((t, i) => ({ x: t * 1000, y: tr.psi[i] * 100 })) : [];
  const refLines = limit ? [{ y: pVal(limit, sys), label: 'working limit', color: 'var(--danger)' }] : [];
  const stale = d.setup !== setup;
  const mv = modelValidation();
  const shareUrl = () => `${window.location.origin}${window.location.pathname}${encodeBuilder(builder, db.version)}`;
  const copyLink = async () => {
    const url = shareUrl();
    try {
      await navigator.clipboard.writeText(url);
      setShareMsg('Link copied. It contains only this load’s inputs, in the link itself.');
    } catch {
      setShareMsg(url);
    }
  };

  return (
    <>
      {d.errors.length > 0 && <ErrorList errors={d.errors} title="Inputs changed — showing the last valid prediction. Fix:" />}
      <div className="card" data-testid="predict-results" style={{ opacity: stale ? 0.85 : 1 }}>
        <div className="card-head">
          <h2 style={{ margin: 0 }}>Prediction</h2>
          <span className="row small">
            {d.powder && (
              <>
                {d.powder.name} <StatusChip status={d.status} /> <FitGrade model={d.powder.model} />
              </>
            )}
            <button className="btn small no-print" onClick={copyLink} data-testid="share-link">
              Copy link
            </button>
            <button className="btn small no-print" onClick={() => window.print()}>
              Print
            </button>
          </span>
        </div>
        {shareMsg && (
          <div className="alert info small no-print" style={{ wordBreak: 'break-all' }}>
            {shareMsg}
          </div>
        )}
        <div className="print-only small" data-testid="print-summary">
          <strong>Inputs:</strong> {d.cartridge?.name ?? 'custom chamber'} · case capacity {builder.inputs.caseCapacityGrH2O} gr H₂O ({builder.capacityBasis || 'entered'}) · case length {builder.inputs.caseLengthIn} in · bore/groove {builder.inputs.boreDiameterIn}/{builder.inputs.grooveDiameterIn} in · barrel {builder.inputs.barrelLengthIn} in · bullet {d.bullet ? `${d.bullet.manufacturer} ${d.bullet.name}` : 'custom'} {builder.inputs.bulletWeightGr} gr, {builder.inputs.bulletLengthIn} in long · COAL {builder.inputs.coalIn} in · {d.powder?.manufacturer} {d.powder?.name} ({d.status}) {builder.inputs.chargeGr} gr at {builder.inputs.powderTempF} °F · shot-start {builder.inputs.shotStartPsi} psi · limit {d.limit.label}.
          <br />
          ORKA database {db.version}. Printed {new Date().toLocaleString()}. A prediction, not load data.
        </div>
        <EstimateWarning status={d.status} />
        <ScopeWarnings d={d} chargeGr={builder.inputs.chargeGr} />
        {res && res.messages.length > 0 && (
          <div className={`alert ${res.status === 'muzzle' ? 'info' : 'danger'}`} style={{ marginBottom: 10 }}>
            <strong>{res.status === 'muzzle' ? 'Notes' : `Result: ${res.status}`}</strong>
            <ul>
              {res.messages.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          </div>
        )}
        {res && (
          <div className="tiles">
            <Tile k="Peak chamber pressure" big state={pState} v={fmtP(res.peakBreechPa, sys)} s={limit ? `${fmtPct(ratio, 1)} of working limit (${fmtP(limit, sys)})` : 'no limit set'} testId="tile-peak">
              {ratio !== null && Number.isFinite(ratio) && (
                <div className={`meter ${pState === 'danger' ? 'danger' : pState === 'warn' ? 'warn' : ''}`} aria-hidden="true">
                  <div style={{ width: `${Math.min(ratio, 1) * 100}%` }} />
                </div>
              )}
              {mv && (d.status === 'calibrated' || d.status === 'estimated') && !d.powder?.user && !(d.powder && d.powder.model?.status === 'user-calibrated') && (
                <div className={`small ${d.limit.mapPa !== null && res.peakBreechPa * (1 + mv.heldOutPressureP90Pct / 100) > d.limit.mapPa ? 'warn-text' : 'muted'}`} data-testid="model-error">
                  {d.powder?.model?.calibration?.grade === 'unvalidated' && <strong>This powder's model was fitted to velocities only — its pressure has never been checked against a measurement. </strong>}
                  Model error on held-out published data ({mv.heldOutCartridgeIds?.length ? `measured on ${mv.scope.replace(/^held-out pressure comparisons exist only for: /, '')} only` : 'see Validation'}
                  {mv.heldOutCartridgeIds?.length && d.cartridge && !mv.heldOutCartridgeIds.includes(d.cartridge.id) ? '; this cartridge is outside the validated set' : ''}): median ±{mv.heldOutPressureP50Pct} %, 1 in 10 worse than ±{mv.heldOutPressureP90Pct} %
                  {mv.heldOutPressureBiasPct < 0 ? ` (on average ${Math.abs(mv.heldOutPressureBiasPct)} % low)` : ''}
                  {typeof d.powder?.model?.calibration?.heldOutPressurePct === 'number' ? `; this powder: median ±${d.powder.model.calibration.heldOutPressurePct} %` : ''}.
                  {' '}Upper estimate {fmtP(res.peakBreechPa * (1 + mv.heldOutPressureP90Pct / 100), sys)}
                  {d.limit.mapPa !== null && res.peakBreechPa * (1 + mv.heldOutPressureP90Pct / 100) > d.limit.mapPa ? ' — above the maximum.' : '.'}
                </div>
              )}
              {d.limit.mapPa !== null && (
                <div className="small muted" data-testid="pressure-bands">
                  {res.peakBreechPa > d.limit.mapPa
                    ? `ABOVE the standard's maximum (${fmtP(d.limit.mapPa, sys)})`
                    : res.peakBreechPa > d.limit.mapPa * 0.85
                      ? `within 15 % of the maximum (${fmtP(d.limit.mapPa, sys)})`
                      : res.peakBreechPa > d.limit.mapPa * 0.75
                        ? 'between 75 % and 85 % of the maximum'
                        : 'below 75 % of the maximum'}
                  {' · '}gauge-station estimate {fmtP(res.peakGaugePa, sys)}
                </div>
              )}
            </Tile>
            <Tile k="Muzzle velocity" big v={fmtV(res.muzzleVelocityMs, sys)} s={mcCurrent ? `band ${fmtV(mcCurrent.velocity.p05, sys, false)}–${fmtV(mcCurrent.velocity.p95, sys)}` : undefined} testId="tile-velocity" />
            <Tile k="Muzzle energy" v={fmtE(ke, sys)} />
            <Tile k="Burnt at muzzle" v={fmtPct(res.burntAtMuzzle, 1)} state={res.burntAtMuzzle < 0.85 ? 'warn' : undefined} s={res.burnoutTravelM !== null ? `all burnt at ${fmtLen(res.burnoutTravelM, sys, sys === 'imperial' ? 2 : 0)} travel` : 'not all burnt'} />
            <Tile k="Fill ratio" v={res.fillRatio === null ? '—' : fmtPct(res.fillRatio, 0)} s={res.fillRatio === null ? 'bulk density unknown' : res.fillRatio > 1 ? 'compressed' : undefined} state={res.fillRatio !== null && res.fillRatio > 1.1 ? 'warn' : undefined} />
            <Tile k="Muzzle pressure" v={fmtP(res.muzzleBreechPa, sys)} />
            <Tile k="Barrel time" v={fmtMs(res.barrelTime10S)} s={`from 10 % of peak pressure · ${fmtMs(res.barrelTimeS)} from ignition`} />
            <Tile k="Ballistic efficiency" v={fmtPct(res.ballisticEfficiency, 1)} />
            <Tile k="Load density" v={`${fmtNum(res.loadDensityKgM3 / 1000, 3)} g/cm³`} />
            <Tile k="Seating depth" v={fmtLen(res.seatingDepthM, sys)} />
            <Tile k="Bullet travel" v={fmtLen(res.travelM, sys, sys === 'imperial' ? 2 : 0)} />
            <Tile k="Chamber volume" v={sys === 'imperial' ? `${fmtNum(U.m3ToGrH2O(res.chamberVolumeM3), 2)} gr H₂O` : `${fmtNum(res.chamberVolumeM3 * 1e6, 3)} cm³`} s="below seated bullet" />
          </div>
        )}
      </div>

      <PublishedCrossCheck db={db} d={d} chargeGr={builder.inputs.chargeGr} bulletWeightGr={builder.inputs.bulletWeightGr} />

      {res && tr && (
        <div className="card">
          <h3>Curves</h3>
          <div className="charts">
            <LineChart
              title="Pressure vs bullet travel"
              series={[
                { name: 'chamber (breech)', color: 'var(--chart-1)', points: travelPts },
                { name: 'bullet base', color: 'var(--chart-2)', points: basePts, dashed: true },
              ]}
              xLabel={`travel (${lenUnit(sys)})`}
              yLabel={`pressure (${pUnit(sys)})`}
              refLines={refLines}
              testId="chart-pressure-travel"
            />
            <LineChart title="Velocity vs bullet travel" series={[{ name: 'velocity', color: 'var(--chart-3)', points: velPts }]} xLabel={`travel (${lenUnit(sys)})`} yLabel={`velocity (${vUnit(sys)})`} />
            <LineChart title="Pressure vs time" series={[{ name: 'chamber', color: 'var(--chart-1)', points: timePts }]} xLabel="time (ms)" yLabel={`pressure (${pUnit(sys)})`} refLines={refLines} />
            <LineChart title="Powder burnt vs time" series={[{ name: 'burnt', color: 'var(--chart-2)', points: psiPts }]} xLabel="time (ms)" yLabel="burnt (%)" />
          </div>
        </div>
      )}

      {res && res.status === 'muzzle' && (
        <div className="card">
          <div className="card-head">
            <h3 style={{ margin: 0 }}>Sensitivity band</h3>
            <button className="btn primary" onClick={runMc} disabled={mcBusy || !setup} data-testid="run-mc">
              {mcBusy ? 'Running 200 simulations…' : 'Run band (200 sims)'}
            </button>
          </div>
          <p className="small muted">
            A sensitivity band under these assumed spreads (1σ), not a confidence interval on real pressure. Defaults depend on the powder model status ({d.status}). Edit them to match what you know about your components.
          </p>
          <div className="grid-3">
            <PlainNumber label="Case capacity σ" unit="%" value={+(activeSpec.caseCapacityRel * 100).toFixed(3)} onChange={(v) => setSpec({ ...activeSpec, caseCapacityRel: (v || 0) / 100 })} />
            <PlainNumber label="Burn rate σ" unit="%" value={+(activeSpec.betaRel * 100).toFixed(3)} onChange={(v) => setSpec({ ...activeSpec, betaRel: (v || 0) / 100 })} />
            <PlainNumber label="Powder energy σ" unit="%" value={+(activeSpec.forceRel * 100).toFixed(3)} onChange={(v) => setSpec({ ...activeSpec, forceRel: (v || 0) / 100 })} />
            <PlainNumber label="Shot-start σ" unit="%" value={+(activeSpec.shotStartRel * 100).toFixed(3)} onChange={(v) => setSpec({ ...activeSpec, shotStartRel: (v || 0) / 100 })} />
            <PlainNumber label="Seating depth σ" unit="in" value={+U.mToIn(activeSpec.seatingDepthM).toFixed(4)} onChange={(v) => setSpec({ ...activeSpec, seatingDepthM: U.inToM(v || 0) })} />
            <PlainNumber label="Charge σ" unit="gr" value={+U.kgToGr(activeSpec.chargeKg).toFixed(3)} onChange={(v) => setSpec({ ...activeSpec, chargeKg: U.grToKg(v || 0) })} />
          </div>
          {spec && (
            <button className="btn small" style={{ marginTop: 6 }} onClick={() => setSpec(null)}>
              Reset to defaults
            </button>
          )}
          {mcCurrent && (
            <div className="tiles" style={{ marginTop: 10 }} data-testid="mc-results">
              <Tile k="Peak pressure 5–95 %" big v={`${fmtP(mcCurrent.peak.p05, sys, false)} – ${fmtP(mcCurrent.peak.p95, sys)}`} s={`median ${fmtP(mcCurrent.peak.p50, sys)}${limit ? ` · upper end is ${fmtPct(mcCurrent.peak.p95 / limit, 0)} of limit` : ''}`} state={limit ? pressureState(mcCurrent.peak.p95, limit) : undefined} />
              <Tile k="Velocity 5–95 %" big v={`${fmtV(mcCurrent.velocity.p05, sys, false)} – ${fmtV(mcCurrent.velocity.p95, sys)}`} s={`median ${fmtV(mcCurrent.velocity.p50, sys)}${mcCurrent.failed ? ` · ${mcCurrent.failed} runs failed` : ''}`} />
            </div>
          )}
        </div>
      )}

      {sens && (
        <div className="card">
          <h3>What moves the result</h3>
          <p className="small muted">One input changed at a time around this load.</p>
          <div className="table-wrap">
            <table className="data" data-testid="sens-table">
              <thead>
                <tr>
                  <th>Input</th>
                  <th>Change</th>
                  <th className="num">Peak pressure</th>
                  <th className="num">Velocity</th>
                </tr>
              </thead>
              <tbody>
                {sens.map((s) => (
                  <tr key={s.key}>
                    <td>{s.label}</td>
                    <td>{s.change}</td>
                    <td className="num">{s.peakPct >= 0 ? '+' : ''}{fmtNum(s.peakPct, 1)} %</td>
                    <td className="num">{s.velocityPct >= 0 ? '+' : ''}{fmtNum(s.velocityPct, 2)} %</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {sweep && (
        <div className="card">
          <h3>Powder temperature</h3>
          <p className="small muted">
            Uses the powder model's temperature coefficient ({setup ? fmtNum(setup.propellant.burn.tempCoeffPerK * 100, 3) : '—'} %/K of burn rate). If the coefficient was not measured for this powder, this sweep only shows the model's assumption.
          </p>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Powder temp</th>
                  <th className="num">Peak pressure</th>
                  <th className="num">% of limit</th>
                  <th className="num">Velocity</th>
                </tr>
              </thead>
              <tbody>
                {sweep.map((r) => {
                  const over = limit ? r.peakPa > limit : false;
                  return (
                    <tr key={r.tempC} className={over ? 'over' : ''}>
                      <td>
                        {over && <span className="stop" aria-label="over limit">!</span>}
                        {fmtTempC(r.tempC, sys)}
                      </td>
                      <td className="num">{fmtP(r.peakPa, sys)}</td>
                      <td className="num">{limit ? fmtPct(r.peakPa / limit, 0) : '—'}</td>
                      <td className="num">{r.status === 'muzzle' ? fmtV(r.velocityMs, sys) : r.status}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {res && (
        <p className="small muted" style={{ margin: 0 }}>
          Charge {fmtChargeKg(setup?.chargeKg, sys)} · shot-start {fmtP(setup?.options.shotStartPressurePa, sys)} · model heat-loss scale {fmtNum(d.heatScale, 2)}
        </p>
      )}
    </>
  );
}
