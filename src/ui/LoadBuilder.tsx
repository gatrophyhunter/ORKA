// Shared load builder (left column). Writes into the persisted builder state.

import { useMemo, useState } from 'react';
import { defaultShotStartPsi } from '../engine/defaults';
import type { Bullet, Cartridge, Powder } from '../data/schema';
import { NumberField, PlainNumber, SearchPicker, StatusChip, EstimateWarning, type PickerItem } from './components';
import { fmtInput, fmtP } from './format';
import { useApp, type PressureStandard } from './state';
import { capacityOptions, modelStatus, useLoad } from './useLoad';

export function cartridgeItems(cs: Cartridge[]): PickerItem[] {
  return cs.map((c) => ({
    id: c.id,
    label: c.name,
    sub: [c.type, c.standards.join('/'), c.bulletDiameterIn ? `${c.bulletDiameterIn}"` : null, c.user ? 'my entry' : null].filter(Boolean).join(' · '),
    keywords: c.aliases.join(' '),
  }));
}

export function powderItems(ps: Powder[]): PickerItem[] {
  return ps.map((p) => {
    const rank = p.burnRateCharts?.[0];
    return {
      id: p.id,
      label: p.name,
      sub: [p.manufacturer, p.form, p.base ? `${p.base}-base` : null, rank ? `#${rank.rank} on ${rank.chart}` : null, p.user ? 'my entry' : null].filter(Boolean).join(' · '),
      right: <StatusChip status={modelStatus(p)} />,
      keywords: `${p.brand ?? ''} ${p.manufacturer}`,
    };
  });
}

export function bulletItems(bs: Bullet[]): PickerItem[] {
  return bs.map((b) => ({
    id: b.id,
    label: `${b.manufacturer} ${b.line} ${b.weightGr} gr`,
    sub: [`${b.diameterIn}"`, b.lengthIn ? `L ${b.lengthIn}"` : 'length not published', b.bcG1 ? `G1 ${b.bcG1}` : null, b.bcG7 ? `G7 ${b.bcG7}` : null, b.construction, b.user ? 'my entry' : null]
      .filter(Boolean)
      .join(' · '),
    keywords: `${b.name} ${b.sku ?? ''} ${b.caliberLabel ?? ''}`,
  }));
}

export function LoadBuilder() {
  const { db, builder, setBuilder, patchInputs, prefs } = useApp();
  const d = useLoad();
  const sys = prefs.units;
  const inp = builder.inputs;

  const cItems = useMemo(() => cartridgeItems(db.cartridges), [db.cartridges]);
  const pItems = useMemo(() => powderItems(db.powders), [db.powders]);
  const bulletPool = useMemo(() => {
    const dia = d.cartridge?.bulletDiameterIn;
    return dia ? db.bullets.filter((b) => Math.abs(b.diameterIn - dia) <= 0.0015) : db.bullets;
  }, [db.bullets, d.cartridge]);
  const bItems = useMemo(() => bulletItems(bulletPool), [bulletPool]);
  const capOpts = useMemo(() => capacityOptions(db, d.cartridge), [db, d.cartridge]);
  const selectedCap = capOpts.find((o) => o.key === builder.brassKey) ?? null;

  const pickCartridge = (id: string | null) => {
    const c = id ? db.cartridges.find((x) => x.id === id) ?? null : null;
    setBuilder((b) => {
      if (!c) return { ...b, cartridgeId: null, brassKey: null, brassBrandId: null };
      const standard: PressureStandard = c.saamiMapPsi ? 'SAAMI' : c.cipPmaxBar ? 'CIP' : 'custom';
      const keep = (v: number | null | undefined, cur: number) => (typeof v === 'number' && v > 0 ? v : cur);
      return {
        ...b,
        cartridgeId: c.id,
        brassKey: null,
        brassBrandId: null,
        capacityBasis: '',
        standard,
        // A custom limit typed for another cartridge must not carry over (review finding).
        customLimitPsi: standard === 'custom' ? NaN : b.customLimitPsi,
        bulletId: b.bulletId && c.bulletDiameterIn && Math.abs((db.bullets.find((x) => x.id === b.bulletId)?.diameterIn ?? 0) - c.bulletDiameterIn) > 0.0015 ? null : b.bulletId,
        inputs: {
          ...b.inputs,
          boreDiameterIn: keep(c.boreDiameterIn, NaN),
          grooveDiameterIn: keep(c.grooveDiameterIn, NaN),
          caseLengthIn: keep(c.trimLengthIn ?? c.caseLengthMaxIn, NaN),
          coalIn: keep(c.maxCoalIn, b.inputs.coalIn),
          bulletDiameterIn: keep(c.bulletDiameterIn, b.inputs.bulletDiameterIn),
          caseCapacityGrH2O: NaN,
          shotStartPsi: defaultShotStartPsi(null, c.type),
        },
      };
    });
  };

  const pickCapacity = (key: string) => {
    if (key === 'measured' || key === '') {
      setBuilder((b) => ({ ...b, brassKey: key || null, brassBrandId: null, capacityBasis: key === 'measured' ? 'your measurement' : '' }));
      return;
    }
    const o = capOpts.find((x) => x.key === key);
    if (!o) return;
    setBuilder((b) => ({
      ...b,
      brassKey: key,
      brassBrandId: o.brandId,
      capacityBasis: `${o.label} — ${o.basis}`,
      inputs: { ...b.inputs, caseCapacityGrH2O: o.value ?? NaN },
    }));
  };

  const pickBullet = (id: string | null) => {
    const bl = id ? db.bullets.find((x) => x.id === id) ?? null : null;
    setBuilder((b) => ({
      ...b,
      bulletId: id,
      inputs: bl
        ? {
            ...b.inputs,
            bulletWeightGr: bl.weightGr,
            bulletDiameterIn: bl.diameterIn,
            bulletLengthIn: bl.lengthIn ?? NaN,
            boatTailLengthIn: 0,
            bulletBaseDiameterIn: 0,
            shotStartPsi: defaultShotStartPsi(bl.construction ?? null, d.cartridge?.type),
          }
        : b.inputs,
    }));
  };

  const pickPowder = (id: string | null) => setBuilder((b) => ({ ...b, powderId: id }));
  const [collapsed, setCollapsed] = useState(false);

  const head = (
    <div className="card-head">
      <h2 style={{ margin: 0 }}>Load builder</h2>
      <button type="button" className="btn small" aria-expanded={!collapsed} onClick={() => setCollapsed((c) => !c)} data-testid="builder-toggle">
        {collapsed ? 'Edit load' : 'Collapse'}
      </button>
    </div>
  );

  if (collapsed) {
    const bits = [
      d.cartridge?.name ?? 'custom chamber',
      Number.isFinite(inp.bulletWeightGr) ? fmtInput('bulletMass', sys, inp.bulletWeightGr) : null,
      d.powder?.name ?? 'no powder',
      Number.isFinite(inp.chargeGr) ? fmtInput('charge', sys, inp.chargeGr) : null,
      Number.isFinite(inp.coalIn) ? `COAL ${fmtInput('len', sys, inp.coalIn)}` : null,
      Number.isFinite(inp.barrelLengthIn) ? `${fmtInput('barrel', sys, inp.barrelLengthIn)} barrel` : null,
    ].filter(Boolean);
    return (
      <div className="card" aria-label="Load builder" data-testid="load-builder">
        {head}
        <div className="builder-summary">{bits.join(' · ')}</div>
        {d.limit.limitPa !== null && <div className="builder-summary">Working limit {fmtP(d.limit.limitPa, sys)}</div>}
      </div>
    );
  }

  return (
    <div className="card" aria-label="Load builder" data-testid="load-builder">
      {head}
      <p className="muted small" style={{ marginTop: -4 }}>Shared by all tabs.</p>

      <div className="section">
        <div className="section-title">Cartridge &amp; chamber</div>
        <SearchPicker label="Cartridge" items={cItems} value={builder.cartridgeId} onChange={pickCartridge} placeholder="Search cartridges…" emptyText={db.cartridges.length ? 'No matches.' : 'Database empty — add a custom cartridge in the Database tab.'} testId="pick-cartridge" />
        {d.cartridge?.saamiTwist && <div className="hint small muted">SAAMI twist {d.cartridge.saamiTwist}</div>}
        <div className="grid-2" style={{ marginTop: 8 }}>
          <NumberField label="Bore Ø" qty="len" value={inp.boreDiameterIn} onChange={(v) => patchInputs({ boreDiameterIn: v })} digits={sys === 'imperial' ? 4 : 3} required testId="in-bore" />
          <NumberField label="Groove Ø" qty="len" value={inp.grooveDiameterIn} onChange={(v) => patchInputs({ grooveDiameterIn: v })} digits={sys === 'imperial' ? 4 : 3} required testId="in-groove" />
          <NumberField label="Case length (trimmed)" qty="len" value={inp.caseLengthIn} onChange={(v) => patchInputs({ caseLengthIn: v })} required testId="in-caselen" />
          <NumberField label="Barrel length" qty="barrel" value={inp.barrelLengthIn} onChange={(v) => patchInputs({ barrelLengthIn: v })} hint="bolt face to muzzle" required testId="in-barrel" />
        </div>
      </div>

      <div className="section">
        <div className="section-title">Case capacity</div>
        <div className="field">
          <label htmlFor="cap-select">Brass</label>
          <select id="cap-select" value={builder.brassKey ?? ''} onChange={(e) => pickCapacity(e.target.value)} data-testid="pick-brass">
            <option value="">— choose brass or measured —</option>
            {capOpts.map((o) => (
              <option key={o.key} value={o.key} disabled={o.value === null}>
                {o.label}
                {o.value !== null ? ` — ${o.value} gr H₂O` : ' — capacity not published'}
              </option>
            ))}
            <option value="measured">My measured capacity</option>
          </select>
          {d.cartridge && capOpts.filter((o) => o.value !== null).length === 0 && (
            <span className="hint">No published capacity on record for this cartridge — measure your fired brass (water to the case mouth) and enter it below.</span>
          )}
        </div>
        <div style={{ marginTop: 6 }}>
          <NumberField
            label="Water capacity to case mouth"
            qty="cap"
            value={inp.caseCapacityGrH2O}
            onChange={(v) => {
              patchInputs({ caseCapacityGrH2O: v });
              if (builder.brassKey !== 'measured') setBuilder((b) => ({ ...b, brassKey: 'measured', brassBrandId: null, capacityBasis: 'your measurement' }));
            }}
            required
            testId="in-capacity"
            hint={
              builder.capacityBasis ? (
                <>
                  Basis: {builder.capacityBasis}
                  {selectedCap?.sourceUrl && /^https?:/.test(selectedCap.sourceUrl) ? (
                    <>
                      {' · '}
                      <a href={selectedCap.sourceUrl} target="_blank" rel="noopener noreferrer">
                        source
                      </a>
                    </>
                  ) : null}
                </>
              ) : (
                'Capacity drives pressure strongly; your own fired-case measurement is best.'
              )
            }
          />
        </div>
      </div>

      <div className="section">
        <div className="section-title">Bullet</div>
        <SearchPicker
          label={`Bullet${d.cartridge?.bulletDiameterIn ? ` (Ø ${d.cartridge.bulletDiameterIn}")` : ''}`}
          items={bItems}
          value={builder.bulletId}
          onChange={pickBullet}
          placeholder="Search bullets or enter below…"
          emptyText={db.bullets.length ? 'No bullets of this diameter.' : 'Database empty — enter the bullet below or add it in the Database tab.'}
          testId="pick-bullet"
        />
        <div className="grid-3" style={{ marginTop: 8 }}>
          <NumberField label="Weight" qty="bulletMass" value={inp.bulletWeightGr} onChange={(v) => patchInputs({ bulletWeightGr: v })} required testId="in-bweight" />
          <NumberField label="Diameter" qty="len" value={inp.bulletDiameterIn} onChange={(v) => patchInputs({ bulletDiameterIn: v })} digits={sys === 'imperial' ? 4 : 3} required testId="in-bdia" />
          <NumberField
            label="Length"
            qty="len"
            value={inp.bulletLengthIn}
            onChange={(v) => patchInputs({ bulletLengthIn: v })}
            required
            testId="in-blen"
            error={d.bullet && d.bullet.lengthIn === null && !Number.isFinite(inp.bulletLengthIn) ? 'Not published — measure it' : null}
          />
        </div>
        <details className="collapsible" style={{ marginTop: 6 }}>
          <summary className="small">Boat tail (optional)</summary>
          <div className="grid-2" style={{ marginTop: 6 }}>
            <NumberField label="Boat-tail length" qty="len" value={inp.boatTailLengthIn} onChange={(v) => patchInputs({ boatTailLengthIn: Number.isFinite(v) ? v : 0 })} hint="0 = flat base" />
            <NumberField label="Base Ø" qty="len" value={inp.bulletBaseDiameterIn} onChange={(v) => patchInputs({ bulletBaseDiameterIn: Number.isFinite(v) ? v : 0 })} digits={sys === 'imperial' ? 4 : 3} hint="0 = same as bullet" />
          </div>
        </details>
        <div className="grid-2" style={{ marginTop: 8 }}>
          <NumberField label="COAL" qty="len" value={inp.coalIn} onChange={(v) => patchInputs({ coalIn: v })} required testId="in-coal" hint={d.cartridge?.maxCoalIn ? `SAAMI/CIP max ${fmtInput('len', sys, d.cartridge.maxCoalIn)}` : undefined} />
          <NumberField label="Shot-start pressure" qty="press" value={inp.shotStartPsi} onChange={(v) => patchInputs({ shotStartPsi: v })} hint="engraving / bullet release" testId="in-shotstart" />
        </div>
      </div>

      <div className="section">
        <div className="section-title">Powder &amp; charge</div>
        <SearchPicker label="Powder" items={pItems} value={builder.powderId} onChange={pickPowder} placeholder="Search powders…" emptyText={db.powders.length ? 'No matches.' : 'Database empty — add a custom powder in the Database tab.'} testId="pick-powder" />
        <div style={{ marginTop: 6 }}>
          <EstimateWarning status={d.status} />
        </div>
        <div className="grid-2" style={{ marginTop: 8 }}>
          <NumberField label="Charge" qty="charge" value={inp.chargeGr} onChange={(v) => patchInputs({ chargeGr: v })} required testId="in-charge" />
          <NumberField label="Powder temperature" qty="temp" value={inp.powderTempF} onChange={(v) => patchInputs({ powderTempF: v })} testId="in-temp" />
        </div>
      </div>

      <div className="section">
        <div className="section-title">Pressure limit</div>
        <div className="seg" role="group" aria-label="Pressure standard">
          {(['SAAMI', 'CIP', 'custom'] as PressureStandard[]).map((s) => (
            <button key={s} type="button" aria-pressed={builder.standard === s} onClick={() => setBuilder((b) => ({ ...b, standard: s }))} data-testid={`std-${s}`}>
              {s === 'SAAMI' ? 'SAAMI (piezo psi)' : s === 'CIP' ? 'C.I.P. (bar)' : 'Custom'}
            </button>
          ))}
        </div>
        <div className="grid-2" style={{ marginTop: 8 }}>
          {builder.standard === 'custom' && (
            <PlainNumber label="Custom limit" unit="psi" value={builder.customLimitPsi} onChange={(v) => setBuilder((b) => ({ ...b, customLimitPsi: v }))} testId="in-customlimit" />
          )}
          <PlainNumber label="Safety margin below limit" unit="%" value={builder.marginPct} onChange={(v) => setBuilder((b) => ({ ...b, marginPct: v }))} testId="in-margin" />
        </div>
        <div className="small" style={{ marginTop: 6 }} data-testid="limit-summary">
          {d.limit.limitPa !== null ? (
            <>
              {d.limit.label} → working limit <strong>{fmtP(d.limit.limitPa, sys)}</strong>
            </>
          ) : (
            <span className="muted">{d.limit.note}</span>
          )}
        </div>
        {d.limit.limitPa !== null && d.limit.note && <div className="small muted">{d.limit.note}</div>}
      </div>

      {d.powder && (
        <div className="small muted" style={{ marginTop: 10 }}>
          Powder model: <StatusChip status={d.status} /> {d.powder.model?.derivation ? `— ${d.powder.model.derivation}` : ''}
        </div>
      )}
    </div>
  );
}
