// Database browser: sourced shipped data + user entries, with detail panels, custom entries, import/export.

import { useMemo, useRef, useState, type ReactNode } from 'react';
import { parseUserImport, type UserData } from '../data/db';
import type { BrassCase, Bullet, Cartridge, Powder } from '../data/schema';
import { Evidence } from './evidence';
import { DataTable, NumberField, PlainNumber, SelectField, SourceLinks, StatusChip, TextField, type Column } from './components';
import { downloadText, slug, toCsv } from './format';
import { useApp } from './state';
import { modelStatus } from './useLoad';

type Sub = 'cartridges' | 'powders' | 'bullets' | 'brass' | 'charts';

const has = (hay: unknown, q: string) => !q || JSON.stringify(hay).toLowerCase().includes(q.toLowerCase());

function Detail({ obj, extra, evidenceKey }: { obj: Record<string, unknown>; extra?: ReactNode; evidenceKey?: string | null }) {
  const skip = new Set(['sources', 'conflicts', 'model', 'user']);
  const entries = Object.entries(obj).filter(([k]) => !skip.has(k));
  const fmt = (v: unknown): ReactNode => {
    if (v === null || v === undefined || v === '') return <span className="muted">—</span>;
    if (Array.isArray(v)) {
      if (!v.length) return <span className="muted">—</span>;
      if (v.every((x) => typeof x !== 'object')) return v.join(', ');
      return <pre className="small" style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{JSON.stringify(v, null, 1)}</pre>;
    }
    if (typeof v === 'object') return <pre className="small" style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{JSON.stringify(v, null, 1)}</pre>;
    if (typeof v === 'string' && /^https?:\/\//.test(v))
      return (
        <a href={v} target="_blank" rel="noopener noreferrer">
          {v}
        </a>
      );
    return String(v);
  };
  const conflicts = obj.conflicts as { field: string; values: { value: unknown; source: string }[] }[] | undefined;
  return (
    <div className="card" data-testid="db-detail">
      <dl className="kv">
        {entries.map(([k, v]) => (
          <div key={k} style={{ display: 'contents' }}>
            <dt>{k}</dt>
            <dd>{fmt(v)}</dd>
          </div>
        ))}
      </dl>
      {extra}
      {conflicts && conflicts.length > 0 && (
        <div className="alert warn" style={{ marginTop: 10 }}>
          <strong>Sources disagree:</strong>
          <ul>
            {conflicts.map((c, i) => (
              <li key={i}>
                {c.field}: {c.values.map((v) => `${String(v.value)} (${v.source})`).join(' vs ')}
              </li>
            ))}
          </ul>
        </div>
      )}
      <h4 style={{ marginTop: 12 }}>Sources</h4>
      <SourceLinks sources={(obj.sources as { url: string; type: string; fields?: string[] }[]) ?? []} />
      {evidenceKey && <Evidence k={evidenceKey} />}
    </div>
  );
}

export function DatabaseTab() {
  const { db, user, updateUser } = useApp();
  const [sub, setSub] = useState<Sub>('cartridges');
  const [msg, setMsg] = useState<{ kind: 'ok' | 'danger'; text: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const importFile = async (f: File) => {
    try {
      const imp = parseUserImport(await f.text());
      updateUser((u) => mergeUser(u, imp));
      setMsg({ kind: 'ok', text: `Imported ${imp.cartridges.length} cartridges, ${imp.powders.length} powders, ${imp.bullets.length} bullets, ${imp.brassCases.length} cases, ${Object.keys(imp.powderModels).length} powder models, ${imp.loads.length} loads.` });
    } catch (e) {
      setMsg({ kind: 'danger', text: `Import failed: ${e instanceof Error ? e.message : String(e)}` });
    }
  };

  const counts: Record<Sub, number> = {
    cartridges: db.cartridges.length,
    powders: db.powders.length,
    bullets: db.bullets.length,
    brass: db.brassCases.length,
    charts: db.burnRateCharts.length,
  };

  return (
    <>
      <div className="card">
        <div className="card-head">
          <h2 style={{ margin: 0 }}>Component database</h2>
          <div className="row">
            <button className="btn small" onClick={() => downloadText('orka-my-data.json', JSON.stringify(user, null, 2))} data-testid="export-user">
              Export my data
            </button>
            <button className="btn small" onClick={() => fileRef.current?.click()}>
              Import…
            </button>
            <input ref={fileRef} type="file" accept="application/json,.json" style={{ display: 'none' }} aria-label="Import my data file" onChange={(e) => e.target.files?.[0] && importFile(e.target.files[0])} />
            <button className="btn small" onClick={() => downloadText('orka-database.json', JSON.stringify(db, null, 2))}>
              Export full DB (JSON)
            </button>
          </div>
        </div>
        <p className="small muted">
          Shipped data version {db.version || 'unknown'}{db.generated ? `, generated ${db.generated}` : ''}. Every shipped record lists its sources; values nobody could source are left empty rather than guessed. Your own entries are stored only in this browser — export them to keep a backup.
        </p>
        {msg && <div className={`alert ${msg.kind}`}>{msg.text}</div>}
        <div className="subtabs" role="tablist" aria-label="Database tables">
          {(['cartridges', 'powders', 'bullets', 'brass', 'charts'] as Sub[]).map((s) => (
            <button key={s} role="tab" aria-selected={sub === s} className={`btn small${sub === s ? ' primary' : ''}`} onClick={() => setSub(s)} data-testid={`db-sub-${s}`}>
              {s === 'charts' ? 'Burn-rate charts' : s[0].toUpperCase() + s.slice(1)} ({counts[s].toLocaleString('en-US')})
            </button>
          ))}
        </div>
      </div>
      {sub === 'cartridges' && <CartridgesTable />}
      {sub === 'powders' && <PowdersTable />}
      {sub === 'bullets' && <BulletsTable />}
      {sub === 'brass' && <BrassTable />}
      {sub === 'charts' && <ChartsView />}
    </>
  );
}

function mergeUser(u: UserData, imp: UserData): UserData {
  const byId = <T extends { id: string }>(a: T[], b: T[]) => {
    const m = new Map(a.map((x) => [x.id, x]));
    b.forEach((x) => m.set(x.id, x));
    return [...m.values()];
  };
  return {
    ...u,
    cartridges: byId(u.cartridges, imp.cartridges),
    powders: byId(u.powders, imp.powders),
    bullets: byId(u.bullets, imp.bullets),
    brassCases: [...u.brassCases, ...imp.brassCases],
    powderModels: { ...u.powderModels, ...imp.powderModels },
    loads: byId(u.loads, imp.loads),
  };
}

function TableToolbar(props: { q: string; setQ: (s: string) => void; children?: ReactNode; onAdd: () => void; onCsv: () => void; label: string }) {
  return (
    <div className="row" style={{ marginBottom: 8 }}>
      <input type="search" placeholder={`Search ${props.label}…`} aria-label={`Search ${props.label}`} value={props.q} onChange={(e) => props.setQ(e.target.value)} style={{ maxWidth: 260 }} data-testid={`db-search-${props.label}`} />
      {props.children}
      <span className="spacer" />
      <button className="btn small" onClick={props.onCsv}>
        CSV
      </button>
      <button className="btn small primary" onClick={props.onAdd} data-testid={`db-add-${props.label}`}>
        + Add custom
      </button>
    </div>
  );
}

const flat = (r: Record<string, unknown>) => {
  const o: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(r)) {
    if (k === 'sources' && Array.isArray(v)) o[k] = v.map((s: { url: string }) => s.url).join(' | ');
    else if (k === 'model' && v && typeof v === 'object') o.modelStatus = (v as { status: string }).status;
    else o[k] = v;
  }
  return o;
};

function UserActions(props: { isUser: boolean; onEdit: () => void; onDelete: () => void }) {
  if (!props.isUser) return null;
  return (
    <div className="row" style={{ marginTop: 10 }}>
      <span className="chip user">my entry</span>
      <button className="btn small" onClick={props.onEdit}>
        Edit
      </button>
      <button className="btn small danger" onClick={props.onDelete}>
        Delete
      </button>
    </div>
  );
}

// ---------------- Cartridges ----------------
function CartridgesTable() {
  const { db, updateUser } = useApp();
  const [q, setQ] = useState('');
  const type = ''; // all shipped cartridges are centerfire rifle
  const [sel, setSel] = useState<string | null>(null);
  const [editing, setEditing] = useState<Cartridge | 'new' | null>(null);
  const rows = useMemo(() => db.cartridges.filter((c) => (!type || c.type === type) && has([c.name, c.aliases, c.id], q)), [db.cartridges, q, type]);
  const cols: Column<Cartridge>[] = [
    { key: 'name', label: 'Name', render: (c) => <>{c.name} {c.user && <span className="chip user">mine</span>}</>, sortValue: (c) => c.name },
    { key: 'type', label: 'Type', render: (c) => c.type, sortValue: (c) => c.type },
    { key: 'dia', label: 'Bullet Ø in', num: true, render: (c) => c.bulletDiameterIn ?? '—', sortValue: (c) => c.bulletDiameterIn },
    { key: 'map', label: 'SAAMI psi', num: true, render: (c) => c.saamiMapPsi?.toLocaleString('en-US') ?? (c.saamiMapCup ? `${c.saamiMapCup.toLocaleString('en-US')} CUP` : '—'), sortValue: (c) => c.saamiMapPsi },
    { key: 'cip', label: 'CIP bar', num: true, render: (c) => c.cipPmaxBar?.toLocaleString('en-US') ?? '—', sortValue: (c) => c.cipPmaxBar },
    { key: 'coal', label: 'Max COAL in', num: true, render: (c) => c.maxCoalIn ?? '—', sortValue: (c) => c.maxCoalIn },
    { key: 'src', label: 'Sources', num: true, render: (c) => c.sources.length, sortValue: (c) => c.sources.length },
  ];
  const selected = rows.find((c) => c.id === sel) ?? db.cartridges.find((c) => c.id === sel) ?? null;
  return (
    <div className="card">
      <TableToolbar q={q} setQ={setQ} label="cartridges" onAdd={() => setEditing('new')} onCsv={() => downloadText('orka-cartridges.csv', toCsv(rows.map((r) => flat(r as never))), 'text/csv')}>
      </TableToolbar>
      {editing && (
        <CartridgeForm
          initial={editing === 'new' ? null : editing}
          onCancel={() => setEditing(null)}
          onSave={(c) => {
            updateUser((u) => ({ ...u, cartridges: [...u.cartridges.filter((x) => x.id !== c.id), c] }));
            setEditing(null);
            setSel(c.id);
          }}
        />
      )}
      <DataTable rows={rows} columns={cols} rowKey={(c) => c.id} onRowClick={(c) => setSel(c.id)} selectedKey={sel} testId="db-cartridges" />
      {selected && (
        <Detail
          obj={selected as never}
          evidenceKey={selected.user ? null : `cartridges:${selected.id}`}
          extra={<UserActions isUser={!!selected.user} onEdit={() => setEditing(selected)} onDelete={() => { updateUser((u) => ({ ...u, cartridges: u.cartridges.filter((x) => x.id !== selected.id) })); setSel(null); }} />}
        />
      )}
    </div>
  );
}

function CartridgeForm(props: { initial: Cartridge | null; onSave: (c: Cartridge) => void; onCancel: () => void }) {
  const i = props.initial;
  const [name, setName] = useState(i?.name ?? '');
  const type: 'rifle' | 'handgun' = i?.type ?? 'rifle';
  const [dia, setDia] = useState(i?.bulletDiameterIn ?? NaN);
  const [bore, setBore] = useState(i?.boreDiameterIn ?? NaN);
  const [groove, setGroove] = useState(i?.grooveDiameterIn ?? NaN);
  const [trim, setTrim] = useState(i?.trimLengthIn ?? NaN);
  const [coal, setCoal] = useState(i?.maxCoalIn ?? NaN);
  const [map, setMap] = useState(i?.saamiMapPsi ?? NaN);
  const [cip, setCip] = useState(i?.cipPmaxBar ?? NaN);
  const [twist, setTwist] = useState(i?.saamiTwist ?? '');
  const [notes, setNotes] = useState(i?.notes ?? '');
  const n = (v: number) => (Number.isFinite(v) && v > 0 ? v : null);
  const ok = name.trim().length > 0;
  return (
    <div className="card" style={{ marginBottom: 10, background: 'var(--surface-2)' }} data-testid="form-cartridge">
      <h3>{i ? 'Edit cartridge' : 'Add custom cartridge'}</h3>
      <div className="grid-3">
        <TextField label="Name *" value={name} onChange={setName} testId="fc-name" />

        <NumberField label="Bullet Ø" qty="len" value={dia} onChange={setDia} digits={4} testId="fc-dia" />
        <NumberField label="Bore Ø" qty="len" value={bore} onChange={setBore} digits={4} testId="fc-bore" />
        <NumberField label="Groove Ø" qty="len" value={groove} onChange={setGroove} digits={4} testId="fc-groove" />
        <NumberField label="Trim length" qty="len" value={trim} onChange={setTrim} testId="fc-trim" />
        <NumberField label="Max COAL" qty="len" value={coal} onChange={setCoal} testId="fc-coal" />
        <PlainNumber label="SAAMI MAP (piezo)" unit="psi" value={map} onChange={setMap} testId="fc-map" />
        <PlainNumber label="C.I.P. Pmax" unit="bar" value={cip} onChange={setCip} />
        <TextField label="Twist" value={twist} onChange={setTwist} placeholder="1:10" />
        <TextField label="Notes / source" value={notes} onChange={setNotes} />
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <button
          className="btn primary"
          disabled={!ok}
          data-testid="fc-save"
          onClick={() =>
            props.onSave({
              id: i?.id ?? `user-cart-${slug(name)}`,
              name: name.trim(),
              aliases: i?.aliases ?? [],
              type,
              standards: [n(map) ? 'SAAMI' : '', n(cip) ? 'CIP' : ''].filter(Boolean),
              bulletDiameterIn: n(dia),
              boreDiameterIn: n(bore),
              grooveDiameterIn: n(groove),
              caseLengthMaxIn: i?.caseLengthMaxIn ?? null,
              trimLengthIn: n(trim),
              maxCoalIn: n(coal),
              saamiMapPsi: n(map),
              saamiMapCup: i?.saamiMapCup ?? null,
              cipPmaxBar: n(cip),
              saamiTwist: twist || null,
              primerSize: i?.primerSize ?? null,
              caseCapacityGrH2O: i?.caseCapacityGrH2O ?? [],
              sources: [{ url: 'user entry', type: 'user' }],
              notes,
            })
          }
        >
          Save
        </button>
        <button className="btn" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

// ---------------- Powders ----------------
function PowdersTable() {
  const { db, updateUser } = useApp();
  const [q, setQ] = useState('');
  const [mfr, setMfr] = useState('');
  const [status, setStatus] = useState('');
  const [sel, setSel] = useState<string | null>(null);
  const [editing, setEditing] = useState<Powder | 'new' | null>(null);
  const mfrs = useMemo(() => [...new Set(db.powders.map((p) => p.manufacturer))].sort(), [db.powders]);
  const rows = useMemo(
    () => db.powders.filter((p) => (!mfr || p.manufacturer === mfr) && (!status || modelStatus(p) === status) && has([p.name, p.manufacturer, p.brand, p.id], q)),
    [db.powders, q, mfr, status],
  );
  const cols: Column<Powder>[] = [
    { key: 'name', label: 'Powder', render: (p) => <>{p.name} {p.user && <span className="chip user">mine</span>}</>, sortValue: (p) => p.name },
    { key: 'mfr', label: 'Manufacturer', render: (p) => p.manufacturer, sortValue: (p) => p.manufacturer },
    { key: 'form', label: 'Form', render: (p) => p.form ?? '—', sortValue: (p) => p.form },
    { key: 'base', label: 'Base', render: (p) => p.base ?? '—', sortValue: (p) => p.base },
    { key: 'rank', label: 'Chart rank', num: true, render: (p) => (p.burnRateCharts?.[0] ? `#${p.burnRateCharts[0].rank}` : '—'), sortValue: (p) => p.burnRateCharts?.[0]?.rank ?? null },
    { key: 'bulk', label: 'Bulk g/cm³', num: true, render: (p) => p.bulkDensityGcc ?? '—', sortValue: (p) => p.bulkDensityGcc ?? null },
    { key: 'model', label: 'Model', render: (p) => <StatusChip status={modelStatus(p)} />, sortValue: (p) => modelStatus(p) },
  ];
  const selected = db.powders.find((p) => p.id === sel) ?? null;
  return (
    <div className="card">
      <TableToolbar q={q} setQ={setQ} label="powders" onAdd={() => setEditing('new')} onCsv={() => downloadText('orka-powders.csv', toCsv(rows.map((r) => flat(r as never))), 'text/csv')}>
        <select aria-label="Manufacturer" value={mfr} onChange={(e) => setMfr(e.target.value)} style={{ maxWidth: 180 }}>
          <option value="">All manufacturers</option>
          {mfrs.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
        <select aria-label="Model status" value={status} onChange={(e) => setStatus(e.target.value)} style={{ maxWidth: 160 }}>
          <option value="">Any model status</option>
          <option value="calibrated">calibrated</option>
          <option value="user-calibrated">my calibration</option>
          <option value="estimated">estimate</option>
          <option value="none">no model</option>
        </select>
      </TableToolbar>
      {editing && (
        <PowderForm
          initial={editing === 'new' ? null : editing}
          onCancel={() => setEditing(null)}
          onSave={(p) => {
            updateUser((u) => ({ ...u, powders: [...u.powders.filter((x) => x.id !== p.id), p] }));
            setEditing(null);
            setSel(p.id);
          }}
        />
      )}
      <DataTable rows={rows} columns={cols} rowKey={(p) => p.id} onRowClick={(p) => setSel(p.id)} selectedKey={sel} testId="db-powders" />
      {selected && (
        <Detail
          obj={selected as never}
          evidenceKey={selected.user ? null : `powders:${selected.id}`}
          extra={
            <>
              <h4 style={{ marginTop: 12 }}>Burn model</h4>
              <div className="small">
                <StatusChip status={modelStatus(selected)} /> {selected.model?.derivation ?? 'No model. Calibrate it in the Calibrate tab.'}
              </div>
              {selected.model?.calibration && (
                <div className="small muted" style={{ marginTop: 4 }}>
                  {selected.model.calibration.points} points; RMS velocity {selected.model.calibration.rmsVelocityFps?.toFixed(0) ?? '—'} fps; RMS pressure {selected.model.calibration.rmsPressurePct?.toFixed(1) ?? '—'} %; cartridges: {selected.model.calibration.cartridges.join(', ')}
                </div>
              )}
              {selected.model && selected.model.status !== 'none' && (
                <pre className="small" style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(selected.model.params, null, 1)}</pre>
              )}
              <UserActions isUser={!!selected.user} onEdit={() => setEditing(selected)} onDelete={() => { updateUser((u) => ({ ...u, powders: u.powders.filter((x) => x.id !== selected.id) })); setSel(null); }} />
            </>
          }
        />
      )}
    </div>
  );
}

function PowderForm(props: { initial: Powder | null; onSave: (p: Powder) => void; onCancel: () => void }) {
  const i = props.initial;
  const [mfr, setMfr] = useState(i?.manufacturer ?? '');
  const [name, setName] = useState(i?.name ?? '');
  const [form, setForm] = useState<string>(i?.form ?? '');
  const [base, setBase] = useState<string>(i?.base ?? '');
  const [bulk, setBulk] = useState<number>(i?.bulkDensityGcc ?? NaN);
  const [notes, setNotes] = useState(i?.notes ?? '');
  const ok = mfr.trim() && name.trim();
  return (
    <div className="card" style={{ marginBottom: 10, background: 'var(--surface-2)' }} data-testid="form-powder">
      <h3>{i ? 'Edit powder' : 'Add custom powder'}</h3>
      <div className="grid-3">
        <TextField label="Manufacturer *" value={mfr} onChange={setMfr} testId="fp-mfr" />
        <TextField label="Name *" value={name} onChange={setName} testId="fp-name" />
        <SelectField label="Form" value={form} onChange={setForm} options={[{ value: '', label: 'unknown' }, { value: 'spherical', label: 'spherical' }, { value: 'extruded', label: 'extruded' }, { value: 'flake', label: 'flake' }, { value: 'disc', label: 'disc' }]} />
        <SelectField label="Base" value={base} onChange={setBase} options={[{ value: '', label: 'unknown' }, { value: 'single', label: 'single' }, { value: 'double', label: 'double' }, { value: 'triple', label: 'triple' }]} />
        <PlainNumber label="Bulk density" unit="g/cm³" value={bulk} onChange={setBulk} testId="fp-bulk" hint="for fill ratio" />
        <TextField label="Notes / source" value={notes} onChange={setNotes} />
      </div>
      <p className="small muted">After saving, give it a burn model in the Calibrate tab (fit to your chronograph data, or enter parameters under Advanced).</p>
      <div className="row">
        <button
          className="btn primary"
          disabled={!ok}
          data-testid="fp-save"
          onClick={() =>
            props.onSave({
              id: i?.id ?? `user-powder-${slug(`${mfr} ${name}`)}`,
              manufacturer: mfr.trim(),
              name: name.trim(),
              form: (form || null) as Powder['form'],
              base: (base || null) as Powder['base'],
              applications: i?.applications ?? [],
              bulkDensityGcc: Number.isFinite(bulk) && bulk > 0 ? bulk : null,
              burnRateCharts: i?.burnRateCharts ?? [],
              status: 'unknown',
              sources: [{ url: 'user entry', type: 'user' }],
              notes,
            })
          }
        >
          Save
        </button>
        <button className="btn" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

// ---------------- Bullets ----------------
function BulletsTable() {
  const { db, updateUser } = useApp();
  const [q, setQ] = useState('');
  const [mfr, setMfr] = useState('');
  const [dia, setDia] = useState('');
  const [sel, setSel] = useState<string | null>(null);
  const [editing, setEditing] = useState<Bullet | 'new' | null>(null);
  const mfrs = useMemo(() => [...new Set(db.bullets.map((p) => p.manufacturer))].sort(), [db.bullets]);
  const dias = useMemo(() => [...new Set(db.bullets.map((p) => p.diameterIn))].sort((a, b) => a - b), [db.bullets]);
  const rows = useMemo(
    () => db.bullets.filter((b) => (!mfr || b.manufacturer === mfr) && (!dia || String(b.diameterIn) === dia) && has([b.name, b.line, b.manufacturer, b.sku, b.weightGr], q)),
    [db.bullets, q, mfr, dia],
  );
  const cols: Column<Bullet>[] = [
    { key: 'mfr', label: 'Make', render: (b) => b.manufacturer, sortValue: (b) => b.manufacturer },
    { key: 'line', label: 'Line', render: (b) => <>{b.line} {b.user && <span className="chip user">mine</span>}</>, sortValue: (b) => b.line },
    { key: 'dia', label: 'Ø in', num: true, render: (b) => b.diameterIn, sortValue: (b) => b.diameterIn },
    { key: 'w', label: 'Weight gr', num: true, render: (b) => b.weightGr, sortValue: (b) => b.weightGr },
    { key: 'len', label: 'Length in', num: true, render: (b) => b.lengthIn ?? '—', sortValue: (b) => b.lengthIn },
    { key: 'g1', label: 'G1', num: true, render: (b) => b.bcG1 ?? '—', sortValue: (b) => b.bcG1 },
    { key: 'g7', label: 'G7', num: true, render: (b) => b.bcG7 ?? '—', sortValue: (b) => b.bcG7 },
    { key: 'sku', label: 'SKU', render: (b) => b.sku ?? '—', sortValue: (b) => b.sku ?? null },
  ];
  const selected = db.bullets.find((b) => b.id === sel) ?? null;
  return (
    <div className="card">
      <TableToolbar q={q} setQ={setQ} label="bullets" onAdd={() => setEditing('new')} onCsv={() => downloadText('orka-bullets.csv', toCsv(rows.map((r) => flat(r as never))), 'text/csv')}>
        <select aria-label="Manufacturer" value={mfr} onChange={(e) => setMfr(e.target.value)} style={{ maxWidth: 160 }}>
          <option value="">All makes</option>
          {mfrs.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
        <select aria-label="Diameter" value={dia} onChange={(e) => setDia(e.target.value)} style={{ maxWidth: 120 }}>
          <option value="">All Ø</option>
          {dias.map((m) => (
            <option key={m} value={String(m)}>
              {m}"
            </option>
          ))}
        </select>
      </TableToolbar>
      {editing && (
        <BulletForm
          initial={editing === 'new' ? null : editing}
          onCancel={() => setEditing(null)}
          onSave={(b) => {
            updateUser((u) => ({ ...u, bullets: [...u.bullets.filter((x) => x.id !== b.id), b] }));
            setEditing(null);
            setSel(b.id);
          }}
        />
      )}
      <DataTable rows={rows} columns={cols} rowKey={(b) => b.id} onRowClick={(b) => setSel(b.id)} selectedKey={sel} testId="db-bullets" />
      {selected && (
        <Detail obj={selected as never} evidenceKey={selected.user ? null : `bullets:${selected.id}`} extra={<UserActions isUser={!!selected.user} onEdit={() => setEditing(selected)} onDelete={() => { updateUser((u) => ({ ...u, bullets: u.bullets.filter((x) => x.id !== selected.id) })); setSel(null); }} />} />
      )}
    </div>
  );
}

function BulletForm(props: { initial: Bullet | null; onSave: (b: Bullet) => void; onCancel: () => void }) {
  const i = props.initial;
  const [mfr, setMfr] = useState(i?.manufacturer ?? '');
  const [line, setLine] = useState(i?.line ?? '');
  const [dia, setDia] = useState(i?.diameterIn ?? NaN);
  const [w, setW] = useState(i?.weightGr ?? NaN);
  const [len, setLen] = useState(i?.lengthIn ?? NaN);
  const [g1, setG1] = useState(i?.bcG1 ?? NaN);
  const [g7, setG7] = useState(i?.bcG7 ?? NaN);
  const [cons, setCons] = useState(i?.construction ?? '');
  const ok = mfr.trim() && line.trim() && dia > 0 && w > 0;
  const n = (v: number) => (Number.isFinite(v) && v > 0 ? v : null);
  return (
    <div className="card" style={{ marginBottom: 10, background: 'var(--surface-2)' }} data-testid="form-bullet">
      <h3>{i ? 'Edit bullet' : 'Add custom bullet'}</h3>
      <div className="grid-3">
        <TextField label="Manufacturer *" value={mfr} onChange={setMfr} />
        <TextField label="Line / model *" value={line} onChange={setLine} />
        <NumberField label="Diameter *" qty="len" value={dia} onChange={setDia} digits={4} />
        <NumberField label="Weight *" qty="bulletMass" value={w} onChange={setW} />
        <NumberField label="Length" qty="len" value={len} onChange={setLen} />
        <PlainNumber label="BC G1" value={g1} onChange={setG1} />
        <PlainNumber label="BC G7" value={g7} onChange={setG7} />
        <SelectField
          label="Construction"
          value={cons}
          onChange={setCons}
          options={[{ value: '', label: 'unknown' }, ...['cup-and-core', 'bonded', 'partition', 'monolithic-copper', 'monolithic-brass', 'FMJ', 'lead', 'plated'].map((x) => ({ value: x, label: x }))]}
        />
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <button
          className="btn primary"
          disabled={!ok}
          onClick={() =>
            props.onSave({
              id: i?.id ?? `user-bullet-${slug(`${mfr} ${line} ${dia} ${w}`)}`,
              manufacturer: mfr.trim(),
              line: line.trim(),
              name: `${mfr.trim()} ${line.trim()} ${w} gr`,
              diameterIn: dia,
              weightGr: w,
              lengthIn: n(len),
              bcG1: n(g1),
              bcG7: n(g7),
              construction: cons || null,
              status: 'unknown',
              sources: [{ url: 'user entry', type: 'user' }],
            })
          }
        >
          Save
        </button>
        <button className="btn" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

// ---------------- Brass ----------------
function BrassTable() {
  const { db, user, updateUser } = useApp();
  const [q, setQ] = useState('');
  const [brand, setBrand] = useState('');
  const [sel, setSel] = useState<number | null>(null);
  const [editing, setEditing] = useState<{ userIdx: number; c: BrassCase | null } | null>(null);
  const brandName = useMemo(() => new Map(db.brassBrands.map((b) => [b.id, b.name])), [db.brassBrands]);
  const indexed = useMemo(() => db.brassCases.map((c, i) => ({ c, i })), [db.brassCases]);
  const rows = useMemo(() => indexed.filter(({ c }) => (!brand || c.brandId === brand) && has([c.cartridge, c.brandId, brandName.get(c.brandId), c.sku], q)), [indexed, q, brand, brandName]);
  const cols: Column<{ c: BrassCase; i: number }>[] = [
    { key: 'brand', label: 'Brand', render: ({ c }) => <>{brandName.get(c.brandId) ?? c.brandId} {c.user && <span className="chip user">mine</span>}</>, sortValue: ({ c }) => brandName.get(c.brandId) ?? c.brandId },
    { key: 'cart', label: 'Cartridge', render: ({ c }) => c.cartridge, sortValue: ({ c }) => c.cartridge },
    { key: 'cap', label: 'Water cap. gr', num: true, render: ({ c }) => c.waterCapacityGrH2O ?? '—', sortValue: ({ c }) => c.waterCapacityGrH2O ?? null },
    { key: 'cond', label: 'Condition', render: ({ c }) => c.capacityCondition ?? '—' },
    { key: 'wt', label: 'Case wt gr', num: true, render: ({ c }) => c.caseWeightGr ?? '—', sortValue: ({ c }) => c.caseWeightGr ?? null },
    { key: 'primer', label: 'Primer', render: ({ c }) => c.primerSize ?? c.primerPocketType ?? '—' },
    { key: 'basis', label: 'Basis', render: ({ c }) => c.basis ?? '—' },
  ];
  const selected = sel !== null ? db.brassCases[sel] ?? null : null;
  const userIndex = selected?.user ? user.brassCases.findIndex((x) => x.brandId === selected.brandId && x.cartridge === selected.cartridge && x.waterCapacityGrH2O === selected.waterCapacityGrH2O) : -1;
  return (
    <div className="card">
      {db.brassBrands.length > 0 && (
        <details className="collapsible" style={{ marginBottom: 8 }}>
          <summary>{db.brassBrands.length} brass brands</summary>
          <div className="table-wrap" style={{ marginTop: 6 }}>
            <table className="data">
              <thead>
                <tr>
                  <th>Brand</th>
                  <th>Country</th>
                  <th>Parent</th>
                  <th>Sources</th>
                </tr>
              </thead>
              <tbody>
                {db.brassBrands.map((b) => (
                  <tr key={b.id}>
                    <td>{b.name}</td>
                    <td>{b.country ?? '—'}</td>
                    <td>{b.parent ?? '—'}</td>
                    <td>
                      {b.sources.slice(0, 2).map((s, k) => (
                        <a key={k} href={s.url} target="_blank" rel="noopener noreferrer" style={{ marginRight: 6 }}>
                          [{k + 1}]
                        </a>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
      <TableToolbar q={q} setQ={setQ} label="brass" onAdd={() => setEditing({ userIdx: -1, c: null })} onCsv={() => downloadText('orka-brass.csv', toCsv(rows.map((r) => flat(r.c as never))), 'text/csv')}>
        <select aria-label="Brand" value={brand} onChange={(e) => setBrand(e.target.value)} style={{ maxWidth: 180 }}>
          <option value="">All brands</option>
          {[...new Set(db.brassCases.map((c) => c.brandId))].sort().map((b) => (
            <option key={b} value={b}>
              {brandName.get(b) ?? b}
            </option>
          ))}
        </select>
      </TableToolbar>
      {editing && (
        <BrassForm
          initial={editing.c}
          onCancel={() => setEditing(null)}
          onSave={(c) => {
            const k = editing.userIdx;
            updateUser((u) => ({ ...u, brassCases: k >= 0 ? u.brassCases.map((x, j) => (j === k ? c : x)) : [...u.brassCases, c] }));
            setEditing(null);
            setSel(null);
          }}
        />
      )}
      <DataTable rows={rows} columns={cols} rowKey={({ c, i }) => `${i}-${c.brandId}-${c.cartridge}`} onRowClick={({ i }) => setSel(i)} selectedKey={sel !== null && selected ? `${sel}-${selected.brandId}-${selected.cartridge}` : null} testId="db-brass" />
      {selected && (
        <Detail
          obj={selected as never}
          evidenceKey={selected.user || sel === null ? null : `brassCases:${sel}`}
          extra={
            <UserActions
              isUser={!!selected.user && userIndex >= 0}
              onEdit={() => setEditing({ userIdx: userIndex, c: user.brassCases[userIndex] ?? null })}
              onDelete={() => {
                updateUser((u) => ({ ...u, brassCases: u.brassCases.filter((_, k) => k !== userIndex) }));
                setSel(null);
              }}
            />
          }
        />
      )}
    </div>
  );
}

function BrassForm(props: { initial: BrassCase | null; onSave: (c: BrassCase) => void; onCancel: () => void }) {
  const { db } = useApp();
  const i = props.initial;
  const known = i ? db.brassBrands.some((b) => b.id === i.brandId) : true;
  const [brandId, setBrandId] = useState(i ? (known ? i.brandId : '__other') : '');
  const [otherBrand, setOtherBrand] = useState(i && !known ? i.brandId : '');
  const [cartId, setCartId] = useState(i?.cartridgeId ?? '');
  const [cap, setCap] = useState(i?.waterCapacityGrH2O ?? NaN);
  const [cond, setCond] = useState<'new' | 'fired' | 'unknown'>(i?.capacityCondition ?? 'fired');
  const [wt, setWt] = useState(i?.caseWeightGr ?? NaN);
  const [notes, setNotes] = useState(i?.notes ?? '');
  const cart = db.cartridges.find((c) => c.id === cartId) ?? null;
  const resolvedBrand = brandId === '__other' ? otherBrand.trim() : brandId;
  const ok = resolvedBrand && cart && cap > 0;
  return (
    <div className="card" style={{ marginBottom: 10, background: 'var(--surface-2)' }} data-testid="form-brass">
      <h3>{i ? 'Edit my case measurement' : 'Add my case measurement'}</h3>
      <div className="grid-3">
        <SelectField label="Brand *" value={brandId} onChange={setBrandId} options={[{ value: '', label: '— choose —' }, ...db.brassBrands.map((b) => ({ value: b.id, label: b.name })), { value: '__other', label: 'Other…' }]} />
        {brandId === '__other' && <TextField label="Brand name *" value={otherBrand} onChange={setOtherBrand} />}
        <SelectField label="Cartridge *" value={cartId} onChange={setCartId} options={[{ value: '', label: '— choose —' }, ...db.cartridges.map((c) => ({ value: c.id, label: c.name }))]} />
        <NumberField label="Water capacity to mouth *" qty="cap" value={cap} onChange={setCap} />
        <SelectField label="Condition" value={cond} onChange={setCond} options={[{ value: 'fired', label: 'fired' }, { value: 'new', label: 'new' }, { value: 'unknown', label: 'unknown' }]} />
        <PlainNumber label="Case weight" unit="gr" value={wt} onChange={setWt} />
        <TextField label="Notes" value={notes} onChange={setNotes} />
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <button
          className="btn primary"
          disabled={!ok}
          onClick={() =>
            props.onSave({
              brandId: resolvedBrand,
              cartridge: cart!.name,
              cartridgeId: cart!.id,
              waterCapacityGrH2O: cap,
              capacityCondition: cond,
              caseWeightGr: Number.isFinite(wt) && wt > 0 ? wt : null,
              basis: 'my measurement',
              sources: [{ url: 'user entry', type: 'user' }],
              notes,
            })
          }
        >
          Save
        </button>
        <button className="btn" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

// ---------------- Burn-rate charts ----------------
function ChartsView() {
  const { db } = useApp();
  const [idx, setIdx] = useState(0);
  const byId = useMemo(() => new Map(db.powders.map((p) => [p.id, p])), [db.powders]);
  if (!db.burnRateCharts.length) return <div className="card empty">No burn-rate charts in the database yet.</div>;
  const ch = db.burnRateCharts[Math.min(idx, db.burnRateCharts.length - 1)];
  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 8 }}>
        <SelectField label="Chart" value={String(idx)} onChange={(v) => setIdx(Number(v))} options={db.burnRateCharts.map((c, i) => ({ value: String(i), label: `${c.publisher} ${c.edition}` }))} />
        {ch.url && /^https?:/.test(ch.url) && (
          <a href={ch.url} target="_blank" rel="noopener noreferrer" className="small">
            source
          </a>
        )}
      </div>
      <p className="small muted">Relative burn-rate order from the publisher, fastest first. Charts are ordinal guides only — position does not convert to a load.</p>
      <div className="table-wrap" style={{ maxHeight: 520, overflowY: 'auto' }}>
        <table className="data">
          <thead>
            <tr>
              <th className="num">#</th>
              <th>Powder</th>
              <th>Model</th>
            </tr>
          </thead>
          <tbody>
            {ch.orderedPowderIds.map((id, i) => {
              const p = byId.get(id);
              return (
                <tr key={`${id}-${i}`}>
                  <td className="num">{i + 1}</td>
                  <td>{p ? `${p.manufacturer} ${p.name}` : <span className="muted">{id}</span>}</td>
                  <td>{p ? <StatusChip status={modelStatus(p)} /> : '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
