// Parametric powder search (runs in a Web Worker).

import { useEffect, useMemo, useRef, useState } from 'react';
import type { ParametricRow, PowderCandidate } from '../engine/search';
import { DEFAULT_MAX_FILL, DEFAULT_MIN_BURNT, DEFAULT_MIN_FILL } from '../engine/defaults';
import * as U from '../engine/units';
import type { Powder } from '../data/schema';
import type { SearchMessage, SearchRequest } from '../workers/search.worker';
import { DataTable, ErrorList, FitGrade, NumberField, PlainNumber, StatusChip, type Column } from './components';
import { fmtChargeKg, fmtMs, fmtP, fmtPct, fmtV } from './format';
import { useApp } from './state';
import { geometryErrors, modelStatus, powderPropellant, setupForPowder, useLoad } from './useLoad';

export function SearchTab() {
  const { db, builder, setBuilder, prefs } = useApp();
  const sys = prefs.units;
  const d = useLoad();
  const [maxFill, setMaxFill] = useState(Math.round(DEFAULT_MAX_FILL * 1000) / 10);
  const [minFill, setMinFill] = useState(Math.round(DEFAULT_MIN_FILL * 1000) / 10);
  const [minBurnt, setMinBurnt] = useState(Math.round(DEFAULT_MIN_BURNT * 1000) / 10);
  const [targetFps, setTargetFps] = useState<number>(NaN);
  const [includeEstimated, setIncludeEstimated] = useState(false);
  const [includePoor, setIncludePoor] = useState(false);
  const [mfr, setMfr] = useState('');
  const [form, setForm] = useState('');
  const [similarTo, setSimilarTo] = useState('');
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [rows, setRows] = useState<ParametricRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const workerRef = useRef<Worker | null>(null);

  useEffect(() => () => workerRef.current?.terminate(), []);
  // Results belong to the builder state and limit they were computed for: clear them on any change (review finding).
  const runKey = JSON.stringify([builder.inputs, builder.cartridgeId, builder.standard, builder.customLimitPsi, builder.marginPct]);
  useEffect(() => {
    workerRef.current?.terminate();
    workerRef.current = null;
    setRows(null);
    setProgress(null);
  }, [runKey]);

  const manufacturers = useMemo(() => [...new Set(db.powders.map((p) => p.manufacturer))].sort(), [db.powders]);
  const filtered = useMemo(
    () => db.powders.filter((p) => (!mfr || p.manufacturer === mfr) && (!form || p.form === form)),
    [db.powders, mfr, form],
  );
  const isPoor = (p: Powder) => p.model?.status === 'calibrated' && (p.model.calibration?.grade === 'poor' || p.model.calibration?.grade === 'unvalidated');
  const usable = filtered.filter((p) => {
    const s = modelStatus(p);
    if (isPoor(p) && !includePoor) return false;
    return s === 'calibrated' || s === 'user-calibrated' || (includeEstimated && s === 'estimated');
  });
  const skippedPoor = includePoor ? [] : filtered.filter(isPoor);
  const skippedNone = filtered.filter((p) => modelStatus(p) === 'none');
  const skippedEst = includeEstimated ? [] : filtered.filter((p) => modelStatus(p) === 'estimated');
  const geoErr = geometryErrors(builder);
  const limit = d.limit.limitPa;
  const errors = [...geoErr, ...(limit === null ? [d.limit.note ?? 'Set a pressure limit.'] : [])];
  const running = progress !== null && rows === null && !error;

  const run = () => {
    if (limit === null) return;
    const candidates: PowderCandidate[] = [];
    const heatScales: Record<string, number> = {};
    for (const p of usable) {
      const prop = powderPropellant(p);
      if (!prop) continue;
      candidates.push({ id: p.id, label: `${p.manufacturer} ${p.name}`, model: prop.model, status: modelStatus(p) as PowderCandidate['status'] });
      heatScales[p.id] = prop.heatScale;
    }
    const any = candidates[0];
    if (!any) {
      setError('No powders with a burn model match the filters.');
      return;
    }
    const base = setupForPowder(builder, any.model);
    if (!base) return;
    workerRef.current?.terminate();
    const w = new Worker(new URL('../workers/search.worker.ts', import.meta.url), { type: 'module' });
    workerRef.current = w;
    setRows(null);
    setError(null);
    setProgress({ done: 0, total: candidates.length });
    w.onmessage = (e: MessageEvent<SearchMessage>) => {
      const m = e.data;
      if (m.type === 'progress') setProgress({ done: m.done, total: m.total });
      else if (m.type === 'done') {
        setRows(m.rows);
        w.terminate();
        workerRef.current = null;
      } else {
        setError(m.message);
        w.terminate();
        workerRef.current = null;
      }
    };
    w.onerror = (e) => {
      setError(e.message || 'Worker failed');
      w.terminate();
      workerRef.current = null;
    };
    const req: SearchRequest = {
      type: 'run',
      base,
      candidates,
      heatScales,
      constraints: {
        pressureLimitPa: limit,
        maxFillRatio: (maxFill || 0) / 100,
        minFillRatio: (minFill || 0) / 100,
        minBurnt: (minBurnt || 0) / 100,
        targetVelocityMs: targetFps > 0 ? U.fpsToMs(targetFps) : undefined,
      },
    };
    w.postMessage(req);
  };

  const cancel = () => {
    workerRef.current?.terminate();
    workerRef.current = null;
    setProgress(null);
  };

  const powderById = useMemo(() => new Map<string, Powder>(db.powders.map((p) => [p.id, p])), [db.powders]);

  // "Similar to" mode: distance of each powder's behaviour at the limit from a chosen reference powder
  // (velocity, burn completion, fill and barrel time, each scaled by a tolerance of practical significance).
  const baseRow = rows && similarTo ? rows.find((r) => r.candidate.id === similarTo) ?? null : null;
  const similarity = (r: ParametricRow): number | null => {
    if (!baseRow || baseRow.result.status !== 'muzzle' || r.result.status !== 'muzzle') return null;
    const b = baseRow.result;
    const x = r.result;
    const terms = [
      (x.muzzleVelocityMs - b.muzzleVelocityMs) / b.muzzleVelocityMs / 0.01,
      (x.burntAtMuzzle - b.burntAtMuzzle) / 0.05,
      (x.barrelTime10S - b.barrelTime10S) / b.barrelTime10S / 0.03,
      x.fillRatio !== null && b.fillRatio !== null ? (x.fillRatio - b.fillRatio) / 0.05 : 0,
    ];
    return Math.sqrt(terms.reduce((s, t) => s + t * t, 0) / terms.length);
  };
  const shownRows = rows && baseRow ? rows.slice().sort((a, b) => (similarity(a) ?? 1e9) - (similarity(b) ?? 1e9)) : rows;

  const columns: Column<ParametricRow>[] = [
    { key: 'powder', label: 'Powder', render: (r) => r.candidate.label, sortValue: (r) => r.candidate.label },
    { key: 'status', label: 'Model', render: (r) => <><StatusChip status={r.candidate.status} /> <FitGrade model={powderById.get(r.candidate.id)?.model} /></>, sortValue: (r) => r.candidate.status },
    { key: 'charge', label: 'Charge', num: true, render: (r) => fmtChargeKg(r.chargeKg, sys), sortValue: (r) => r.chargeKg },
    { key: 'vel', label: 'Velocity', num: true, render: (r) => (r.result.status === 'muzzle' ? fmtV(r.result.muzzleVelocityMs, sys) : r.result.status), sortValue: (r) => r.result.muzzleVelocityMs || 0 },
    { key: 'p', label: 'Peak pressure', num: true, render: (r) => fmtP(r.result.peakBreechPa, sys), sortValue: (r) => r.result.peakBreechPa },
    { key: 'fill', label: 'Fill', num: true, render: (r) => (r.result.fillRatio === null ? '—' : fmtPct(r.result.fillRatio, 0)), sortValue: (r) => r.result.fillRatio },
    { key: 'burnt', label: 'Burnt', num: true, render: (r) => fmtPct(r.result.burntAtMuzzle, 0), sortValue: (r) => r.result.burntAtMuzzle },
    { key: 'pm', label: 'Muzzle p', num: true, render: (r) => fmtP(r.result.muzzleBreechPa, sys), sortValue: (r) => r.result.muzzleBreechPa },
    { key: 'bt', label: 'Barrel time', num: true, render: (r) => fmtMs(r.result.barrelTime10S), sortValue: (r) => r.result.barrelTime10S },
    ...(targetFps > 0
      ? [
          {
            key: 'tgt',
            label: 'Charge @ target',
            num: true,
            render: (r: ParametricRow) => (r.atTarget ? `${fmtChargeKg(r.atTarget.chargeKg, sys)} @ ${fmtP(r.atTarget.peakPa, sys)}` : '—'),
            sortValue: (r: ParametricRow) => (r.atTarget ? r.atTarget.peakPa : null),
          } as Column<ParametricRow>,
        ]
      : []),
    ...(baseRow
      ? [
          {
            key: 'sim',
            label: 'Distance',
            num: true,
            render: (r: ParametricRow) => {
              const s = similarity(r);
              return s === null ? '—' : r.candidate.id === similarTo ? 'reference' : s.toFixed(2);
            },
            sortValue: (r: ParametricRow) => similarity(r),
          } as Column<ParametricRow>,
        ]
      : []),
    { key: 'lim', label: 'Limited by', render: (r) => r.limitedBy, sortValue: (r) => r.limitedBy },
    { key: 'why', label: 'Notes', render: (r) => <span className="small">{r.reasons.join('; ') || 'passes'}</span> },
  ];

  return (
    <>
      <div className="card">
        <h2>Parametric powder search</h2>
        <p className="small muted">
          For every powder with a burn model, ORKA finds the largest charge allowed by the pressure limit and the fill limit for the current cartridge, case, bullet, COAL and barrel, then compares velocity, burn completion and fill on equal terms.
        </p>
        <ErrorList errors={errors} title="To search, complete the load builder (charge and powder are not needed):" />
        <div className="grid-4" style={{ marginTop: 8 }}>
          <div className="field">
            <span className="label">Pressure limit</span>
            <div className="small" data-testid="search-limit">{limit !== null ? fmtP(limit, sys) : '—'}</div>
            <span className="hint">from the load builder</span>
          </div>
          <PlainNumber label="Max fill" unit="%" value={maxFill} onChange={setMaxFill} />
          <PlainNumber label="Min fill" unit="%" value={minFill} onChange={setMinFill} />
          <PlainNumber label="Min burnt at muzzle" unit="%" value={minBurnt} onChange={setMinBurnt} />
          <NumberField label="Target velocity (optional)" qty="vel" value={targetFps} onChange={setTargetFps} />
          <div className="field">
            <label htmlFor="s-mfr">Manufacturer</label>
            <select id="s-mfr" value={mfr} onChange={(e) => setMfr(e.target.value)}>
              <option value="">All</option>
              {manufacturers.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="s-form">Form</label>
            <select id="s-form" value={form} onChange={(e) => setForm(e.target.value)}>
              <option value="">All</option>
              <option value="spherical">spherical</option>
              <option value="extruded">extruded</option>
              <option value="flake">flake</option>
              <option value="disc">disc</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="s-sim">Similar to (optional)</label>
            <select id="s-sim" value={similarTo} onChange={(e) => setSimilarTo(e.target.value)} data-testid="similar-to">
              <option value="">— rank by velocity —</option>
              {usable.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.manufacturer} {p.name}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ justifyContent: 'flex-end' }}>
            <label className="check">
              <input type="checkbox" checked={includeEstimated} onChange={(e) => setIncludeEstimated(e.target.checked)} data-testid="include-estimated" /> include estimates
            </label>
            <label className="check" title="Calibrated powders whose fit to published pressure data is worse than ±20 % RMS">
              <input type="checkbox" checked={includePoor} onChange={(e) => setIncludePoor(e.target.checked)} /> include poor / pressure-unvalidated fits
            </label>
          </div>
        </div>
        {includeEstimated && (
          <div className="alert warn" style={{ marginTop: 8 }}>
            Estimated powders are interpolated from a burn-rate chart — not for load development. They are shown for orientation only.
          </div>
        )}
        <div className="row" style={{ marginTop: 10 }}>
          <button className="btn primary" disabled={errors.length > 0 || running || usable.length === 0} onClick={run} data-testid="run-search">
            Search {usable.length} powder{usable.length === 1 ? '' : 's'}
          </button>
          {running && (
            <button className="btn" onClick={cancel}>
              Cancel
            </button>
          )}
          <span className="small muted">
            {skippedNone.length} without a model{skippedEst.length ? `, ${skippedEst.length} estimates` : ''}{skippedPoor.length ? `, ${skippedPoor.length} poor or pressure-unvalidated fits` : ''} skipped
          </span>
        </div>
        {progress && rows === null && !error && (
          <div style={{ marginTop: 8 }} aria-live="polite">
            <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={progress.total} aria-valuenow={progress.done}>
              <div style={{ width: `${(progress.done / Math.max(1, progress.total)) * 100}%` }} />
            </div>
            <div className="small muted">
              {progress.done} / {progress.total}
            </div>
          </div>
        )}
        {error && <div className="alert danger" style={{ marginTop: 8 }}>{error}</div>}
      </div>

      {rows && (
        <div className="card" data-testid="search-results">
          <h3>Results</h3>
          {baseRow && (
            <p className="small">
              Ranked by similarity to <strong>{baseRow.candidate.label}</strong> at the pressure limit (velocity ±1 %, burn ±5 points, barrel time ±3 %, fill ±5 points ≈ distance 1).
            </p>
          )}
          <p className="small muted">Passing powders first, fastest first. Click a row to load that powder and charge into the builder. These are model maxima, never load recommendations.</p>
          <DataTable
            rows={shownRows ?? []}
            columns={columns}
            rowKey={(r) => r.candidate.id}
            rowClass={(r) => (r.passes ? '' : 'fail')}
            onRowClick={(r) => {
              if (!powderById.has(r.candidate.id)) return;
              setBuilder((b) => ({ ...b, powderId: r.candidate.id, inputs: { ...b.inputs, chargeGr: +U.kgToGr(r.chargeKg).toFixed(2) } }));
            }}
            selectedKey={builder.powderId}
            testId="search-table"
          />
        </div>
      )}

      {skippedNone.length > 0 && (
        <div className="card">
          <details className="collapsible">
            <summary>
              Skipped: {skippedNone.length} powder{skippedNone.length === 1 ? '' : 's'} without a burn model
            </summary>
            <p className="small muted">These powders are in the database but have no burn model yet. Calibrate them in the Calibrate tab to include them.</p>
            <p className="small">{skippedNone.slice(0, 300).map((p) => `${p.manufacturer} ${p.name}`).join(' · ')}{skippedNone.length > 300 ? ' …' : ''}</p>
          </details>
        </div>
      )}
    </>
  );
}
