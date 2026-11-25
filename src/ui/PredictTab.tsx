// Single-load prediction: results, charts, uncertainty band, sensitivities, temperature sweep.

import { useMemo, useState } from 'react';
import { simulate } from '../engine/model';
import { monteCarlo, sensitivities, temperatureSweep, specForPowderModel, isVelocityOnly, DEFAULT_PRESSURE_PER_BETA, type MonteCarloResult, type UncertaintySpec } from '../engine/uncertainty';
import * as U from '../engine/units';
import { FitGrade, ErrorList, EstimateWarning, PlainNumber, StatusChip, Tile, useDebounced } from './components';
import { fmtChargeKg, fmtE, fmtLen, fmtMs, fmtNum, fmtP, fmtPct, fmtTempC, fmtV, lenUnit, lenVal, pUnit, pVal, vUnit, vVal } from './format';
import { LineChart } from './LineChart';
import { useApp } from './state';
import { PublishedCrossCheck, ScopeWarnings } from './CrossCheck';
import { classValidation, modelValidation, shotStartClass, type ModelValidationSummary, type ShotClass } from '../engine/defaults';
import { shippedModel } from '../data/db';
import type { ModelStatus, PowderModelEntry } from '../data/schema';
import type { PressureStandard } from './state';
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

export interface ModelErrorView {
  /** Caveat shown first, in bold (velocity-only, imported or user fit); empty when none. */
  lead: string;
  /** Plain-language statement of how far off this prediction may be. */
  text: string;
  /** Upper estimate of peak pressure, Pa. */
  upperPa: number;
  /** True when the upper estimate is above the maximum in use. */
  over: boolean;
}

/**
 * Model-error statement for the peak-pressure tile.
 *  - calibrated / user-calibrated: held-out error measured on the shipped pressure-fitted models, for the bullet's
 *    construction class when that class has enough comparisons; velocity-only fits are flagged.
 *  - estimated: no held-out validation exists; the powder's own chart-interpolation spread is shown instead.
 */
export function modelErrorView(a: {
  peakPa: number;
  mapPa: number | null;
  standard: PressureStandard;
  status: ModelStatus;
  model: PowderModelEntry | null | undefined;
  mv: ModelValidationSummary | null;
  shotClass: ShotClass | null;
  cartridgeId: string | null;
  /** Burn-rate spread (1σ, relative) of an estimated powder. */
  estimateBetaRel: number;
  /** d ln p / d ln β at this load. */
  elasticity: number | undefined;
  fmt: (pa: number) => string;
}): ModelErrorView | null {
  const maxWord = a.standard === 'custom' ? 'your custom limit' : 'the maximum';
  const tail = (upper: number) => (a.mapPa !== null && upper > a.mapPa ? ` — above ${maxWord}.` : '.');
  if (a.status === 'estimated') {
    const k = a.elasticity !== undefined && Number.isFinite(a.elasticity) && a.elasticity > 0.2 ? a.elasticity : DEFAULT_PRESSURE_PER_BETA;
    const s = a.estimateBetaRel;
    const upper = a.peakPa * Math.exp(1.645 * k * s);
    return {
      lead: 'No held-out validation exists for estimated powders. ',
      upperPa: upper,
      over: a.mapPa !== null && upper > a.mapPa,
      text:
        `This burn rate is interpolated from burn-rate charts, with a spread of ±${Math.round(s * 100)} % (1σ). ` +
        `At this load that alone moves peak pressure by a factor of about ${(Math.exp(k * s)).toFixed(1)} either way (1σ). ` +
        `Rough upper estimate (burn-rate spread only, about 1 in 20 higher) ${a.fmt(upper)}${tail(upper)}`,
    };
  }
  if ((a.status !== 'calibrated' && a.status !== 'user-calibrated') || !a.mv) return null;
  const mv = a.mv;
  const cls = classValidation(mv, a.shotClass);
  const p50 = cls?.p50Pct ?? mv.heldOutPressureP50Pct;
  const p90 = cls?.p90Pct ?? mv.heldOutPressureP90Pct;
  const bias = cls?.biasPct ?? mv.heldOutPressureBiasPct;
  // Never use a smaller error than the all-bullets figure for the upper estimate.
  const p90Upper = Math.max(p90, mv.heldOutPressureP90Pct);
  const upper = a.peakPa * (1 + p90Upper / 100);
  const user = a.status === 'user-calibrated';
  const imported = user && typeof a.model?.derivation === 'string' && a.model.derivation.startsWith('Imported from a file.');
  const velOnly = isVelocityOnly(a.model);
  const rms = a.model?.calibration?.rmsPressurePct;
  let lead = '';
  let note = '';
  if (imported) {
    lead = 'Imported model: its pressure fit is not on record, so it is treated as velocity-only. ';
    note = 'The error below was measured on the shipped pressure-fitted models, not on this one. ';
  } else if (user && velOnly) {
    lead = 'Velocity-only calibration: your calibration was fitted to velocities only and does not check pressure. ';
    note = 'The error below was measured on the shipped pressure-fitted models, not on your calibration. ';
  } else if (user && typeof rms === 'number') {
    note = `Your calibration fits your pressure data to ±${rms.toFixed(1)} % (in-sample). The error below was measured on the shipped pressure-fitted models. `;
  } else if (velOnly) lead = "This powder's model was fitted to velocities only — its pressure has never been checked against a measurement. ";
  const where = mv.heldOutCartridgeIds?.length ? `measured on ${mv.scope.replace(/^held-out pressure comparisons exist only for: /, '')} only` : 'see Validation';
  const outside = mv.heldOutCartridgeIds?.length && a.cartridgeId && !mv.heldOutCartridgeIds.includes(a.cartridgeId) ? '; this cartridge is outside the validated set' : '';
  const group = cls && a.shotClass ? `${a.shotClass} bullets, ${cls.n} published loads; ` : '';
  const own = !user && typeof a.model?.calibration?.heldOutPressurePct === 'number' ? `; this powder: median ±${a.model.calibration.heldOutPressurePct} %` : '';
  return {
    lead,
    upperPa: upper,
    over: a.mapPa !== null && upper > a.mapPa,
    text:
      `${note}Model error on held-out published data (${group}${where}${outside}): median ±${p50} %, 1 in 10 worse than ±${p90} %` +
      `${bias < 0 ? ` (on average ${Math.abs(bias)} % low: real pressure tends to be higher than shown)` : ''}${own}. ` +
      `Upper estimate (+${p90Upper} %) ${a.fmt(upper)}${tail(upper)}`,
  };
}

/** Construction class of the selected bullet, or null when no bullet is selected or its construction is not recorded. */
export function bulletShotClass(construction: string | null | undefined): ShotClass | null {
  return construction && construction.trim() ? shotStartClass(construction) : null;
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
  // A user calibration without pressure data must not narrow the band of the shipped model it replaced.
  const parentModel = d.powder?.model?.status === 'user-calibrated' ? shippedModel(d.powder.id) : null;
  const defaultSpec = specForPowderModel(d.powder?.model, elasticity, parentModel);
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
  const maxWord = builder.standard === 'custom' ? 'your custom limit' : "the standard's maximum";
  const modelErr =
    res && d.powder
      ? modelErrorView({
          peakPa: res.peakBreechPa,
          mapPa: d.limit.mapPa,
          standard: builder.standard,
          status: d.status,
          model: d.powder.model,
          mv,
          shotClass: d.bullet ? bulletShotClass(d.bullet.construction) : null,
          cartridgeId: d.cartridge?.id ?? null,
          estimateBetaRel: defaultSpec.betaRel,
          elasticity,
          fmt: (pa) => fmtP(pa, sys),
        })
      : null;
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
          <strong>Inputs:</strong> {d.cartridge?.name ?? 'custom chamber'} · case capacity {builder.inputs.caseCapacityGrH2O} gr H₂O ({builder.capacityBasis || 'entered'}) · case length {builder.inputs.caseLengthIn} in · bore/groove {builder.inputs.boreDiameterIn}/{builder.inputs.grooveDiameterIn} in · barrel {builder.inputs.barrelLengthIn} in · bullet {d.bullet ? `${d.bullet.manufacturer} ${d.bullet.name}` : 'custom'} {builder.inputs.bulletWeightGr} gr, {builder.inputs.bulletLengthIn} in long · COAL {builder.inputs.coalIn} in · {d.powder?.manufacturer} {d.powder?.name} ({d.status}) {builder.inputs.chargeGr} gr at {builder.inputs.powderTempF} °F · shot-start {builder.inputs.shotStartPsi} psi · limit {d.limit.label}.{d.limit.warning ? ` ${d.limit.warning}` : ''}
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
              {d.limit.warning && (
                <div className="small warn-text" data-testid="predict-limit-warning">
                  {d.limit.warning}
                </div>
              )}
              {modelErr && (
                <div className={`small ${modelErr.over ? 'warn-text' : 'muted'}`} data-testid="model-error">
                  {modelErr.lead && <strong>{modelErr.lead}</strong>}
                  {modelErr.text}
                </div>
              )}
              {d.limit.mapPa !== null && (
                <div className="small muted" data-testid="pressure-bands">
                  {res.peakBreechPa > d.limit.mapPa
                    ? `ABOVE ${maxWord} (${fmtP(d.limit.mapPa, sys)})`
                    : res.peakBreechPa > d.limit.mapPa * 0.85
                      ? `within 15 % of ${maxWord} (${fmtP(d.limit.mapPa, sys)})`
                      : res.peakBreechPa > d.limit.mapPa * 0.75
                        ? `between 75 % and 85 % of ${maxWord}`
                        : `below 75 % of ${maxWord}`}
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
