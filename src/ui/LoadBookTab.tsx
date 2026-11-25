// Load book: save the builder state as named loads, recall and delete them.

import { useState } from 'react';
import type { SavedLoad } from '../data/db';
import { PlainNumber, TextField } from './components';
import { fmtInput } from './format';
import { reviveInputs, useApp, type BuilderState } from './state';
import { limitForCartridge } from './useLoad';
import type { Cartridge } from '../data/schema';

/** Builder state after recalling a saved load. The pressure limit follows the same rule as picking the cartridge. */
export function recallLoad(b: BuilderState, l: SavedLoad, cartridges: Cartridge[]): BuilderState {
  const c = l.cartridgeId ? cartridges.find((x) => x.id === l.cartridgeId) ?? null : null;
  return {
    ...b,
    ...limitForCartridge(b, l.cartridgeId, c),
    cartridgeId: l.cartridgeId,
    powderId: l.powderId,
    bulletId: l.bulletId,
    brassBrandId: l.brassBrandId,
    brassKey: 'measured',
    capacityBasis: `saved load “${l.name}”`,
    inputs: reviveInputs(l.inputs as never),
  };
}

export function LoadBookTab() {
  const { user, updateUser, builder, setBuilder, db, prefs, setTab } = useApp();
  const sys = prefs.units;
  const [name, setName] = useState('');
  const [notes, setNotes] = useState('');
  const [vel, setVel] = useState<number>(NaN);
  const [msg, setMsg] = useState<string | null>(null);
  const nameOf = <T extends { id: string; name: string }>(list: T[], id: string | null) => (id ? list.find((x) => x.id === id)?.name ?? id : '—');

  const save = () => {
    const now = new Date();
    const l: SavedLoad = {
      id: `load-${now.getTime().toString(36)}-${Math.floor(Math.random() * 1e6).toString(36)}`,
      name: name.trim() || `Load ${user.loads.length + 1}`,
      createdIso: now.toISOString(),
      cartridgeId: builder.cartridgeId,
      powderId: builder.powderId,
      bulletId: builder.bulletId,
      brassBrandId: builder.brassBrandId,
      inputs: { ...builder.inputs },
      notes: notes.trim() || undefined,
      measuredVelocityFps: Number.isFinite(vel) && vel > 0 ? vel : null,
    };
    updateUser((u) => ({ ...u, loads: [l, ...u.loads] }));
    setName('');
    setNotes('');
    setVel(NaN);
    setMsg(`Saved “${l.name}”.`);
  };

  const recall = (l: SavedLoad) => {
    setBuilder((b) => recallLoad(b, l, db.cartridges));
    setTab('predict');
  };

  return (
    <>
      <div className="card">
        <h2>Load book</h2>
        <p className="small muted">Saves the current load builder (stored in this browser; export from the Database tab to back up).</p>
        <div className="grid-3">
          <TextField label="Name" value={name} onChange={setName} placeholder="e.g. 6.5 CM 140 gr ladder" testId="lb-name" />
          <TextField label="Notes" value={notes} onChange={setNotes} />
          <PlainNumber label="Measured velocity (optional)" unit="fps" value={vel} onChange={setVel} />
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <button className="btn primary" onClick={save} data-testid="lb-save">
            Save current load
          </button>
          {msg && <span className="small" style={{ color: 'var(--ok)' }}>{msg}</span>}
        </div>
      </div>
      <div className="card">
        <h3>Saved loads ({user.loads.length})</h3>
        {user.loads.length === 0 ? (
          <div className="empty">No saved loads yet.</div>
        ) : (
          <div className="table-wrap">
            <table className="data" data-testid="lb-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Cartridge</th>
                  <th>Powder</th>
                  <th className="num">Charge</th>
                  <th className="num">COAL</th>
                  <th className="num">Measured</th>
                  <th>Saved</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {user.loads.map((l) => {
                  const inp = reviveInputs(l.inputs as never);
                  return (
                    <tr key={l.id}>
                      <td title={l.notes}>{l.name}</td>
                      <td>{nameOf(db.cartridges, l.cartridgeId)}</td>
                      <td>{nameOf(db.powders, l.powderId)}</td>
                      <td className="num">{fmtInput('charge', sys, inp.chargeGr)}</td>
                      <td className="num">{fmtInput('len', sys, inp.coalIn)}</td>
                      <td className="num">{l.measuredVelocityFps ? fmtInput('vel', sys, l.measuredVelocityFps) : '—'}</td>
                      <td>{l.createdIso.slice(0, 10)}</td>
                      <td className="nowrap">
                        <button className="btn small" onClick={() => recall(l)}>
                          Load
                        </button>{' '}
                        <button className="btn small danger" onClick={() => updateUser((u) => ({ ...u, loads: u.loads.filter((x) => x.id !== l.id) }))}>
                          Delete
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
