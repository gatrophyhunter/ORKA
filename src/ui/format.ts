// Display-unit helpers. Builder inputs are stored in reloader (imperial) units; engine results are SI.

import * as U from '../engine/units';

export type UnitSystem = 'imperial' | 'metric';

/** Quantities that appear as builder inputs (stored imperial). */
export type InputQty = 'len' | 'barrel' | 'bulletMass' | 'charge' | 'cap' | 'vel' | 'press' | 'temp' | 'plain';

interface QtyDef {
  units: [string, string];
  decimals: [number, number];
  toMetric: (imp: number) => number;
  toImperial: (met: number) => number;
}

const id = (v: number) => v;

export const QTY: Record<InputQty, QtyDef> = {
  len: { units: ['in', 'mm'], decimals: [3, 2], toMetric: U.inToMm, toImperial: U.mmToIn },
  barrel: { units: ['in', 'mm'], decimals: [2, 1], toMetric: U.inToMm, toImperial: U.mmToIn },
  bulletMass: { units: ['gr', 'g'], decimals: [1, 3], toMetric: U.grToG, toImperial: U.gToGr },
  charge: { units: ['gr', 'g'], decimals: [2, 3], toMetric: U.grToG, toImperial: U.gToGr },
  cap: { units: ['gr H₂O', 'cm³'], decimals: [2, 3], toMetric: U.grH2OToCm3, toImperial: U.cm3ToGrH2O },
  vel: { units: ['fps', 'm/s'], decimals: [0, 1], toMetric: U.fpsToMs, toImperial: U.msToFps },
  press: { units: ['psi', 'MPa'], decimals: [0, 2], toMetric: U.psiToMpa, toImperial: U.mpaToPsi },
  temp: { units: ['°F', '°C'], decimals: [0, 1], toMetric: U.fToC, toImperial: U.cToF },
  plain: { units: ['', ''], decimals: [3, 3], toMetric: id, toImperial: id },
};

export const unitOf = (q: InputQty, sys: UnitSystem) => QTY[q].units[sys === 'imperial' ? 0 : 1];
export const decimalsOf = (q: InputQty, sys: UnitSystem) => QTY[q].decimals[sys === 'imperial' ? 0 : 1];
export const toDisplay = (q: InputQty, sys: UnitSystem, imp: number) => (sys === 'imperial' ? imp : QTY[q].toMetric(imp));
export const fromDisplay = (q: InputQty, sys: UnitSystem, disp: number) => (sys === 'imperial' ? disp : QTY[q].toImperial(disp));

export function fmtNum(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** Format an imperial-stored input quantity in the chosen system, with unit. */
export function fmtInput(q: InputQty, sys: UnitSystem, imp: number | null | undefined, digits?: number): string {
  if (imp === null || imp === undefined || !Number.isFinite(imp)) return '—';
  const d = digits ?? decimalsOf(q, sys);
  return `${fmtNum(toDisplay(q, sys, imp), d)} ${unitOf(q, sys)}`.trim();
}

// ---- SI result formatting ----
export const pUnit = (sys: UnitSystem) => (sys === 'imperial' ? 'psi' : 'MPa');
export const pVal = (pa: number, sys: UnitSystem) => (sys === 'imperial' ? U.paToPsi(pa) : pa / 1e6);
export const fmtP = (pa: number | null | undefined, sys: UnitSystem, withUnit = true) =>
  pa === null || pa === undefined || !Number.isFinite(pa) ? '—' : `${fmtNum(pVal(pa, sys), sys === 'imperial' ? 0 : 1)}${withUnit ? ' ' + pUnit(sys) : ''}`;

export const vUnit = (sys: UnitSystem) => (sys === 'imperial' ? 'fps' : 'm/s');
export const vVal = (ms: number, sys: UnitSystem) => (sys === 'imperial' ? U.msToFps(ms) : ms);
export const fmtV = (ms: number | null | undefined, sys: UnitSystem, withUnit = true) =>
  ms === null || ms === undefined || !Number.isFinite(ms) ? '—' : `${fmtNum(vVal(ms, sys), 0)}${withUnit ? ' ' + vUnit(sys) : ''}`;

export const lenUnit = (sys: UnitSystem) => (sys === 'imperial' ? 'in' : 'mm');
export const lenVal = (m: number, sys: UnitSystem) => (sys === 'imperial' ? U.mToIn(m) : m * 1000);
export const fmtLen = (m: number | null | undefined, sys: UnitSystem, digits?: number) =>
  m === null || m === undefined || !Number.isFinite(m) ? '—' : `${fmtNum(lenVal(m, sys), digits ?? (sys === 'imperial' ? 3 : 1))} ${lenUnit(sys)}`;

export const massUnit = (sys: UnitSystem) => (sys === 'imperial' ? 'gr' : 'g');
export const fmtChargeKg = (kg: number | null | undefined, sys: UnitSystem, digits?: number) =>
  kg === null || kg === undefined || !Number.isFinite(kg)
    ? '—'
    : sys === 'imperial'
      ? `${fmtNum(U.kgToGr(kg), digits ?? 2)} gr`
      : `${fmtNum(kg * 1000, digits ?? 3)} g`;

export const fmtE = (j: number | null | undefined, sys: UnitSystem) =>
  j === null || j === undefined || !Number.isFinite(j) ? '—' : sys === 'imperial' ? `${fmtNum(U.jToFtlbf(j), 0)} ft·lbf` : `${fmtNum(j, 0)} J`;

export const fmtTempC = (c: number, sys: UnitSystem) => (sys === 'imperial' ? `${fmtNum(U.cToF(c), 0)} °F` : `${fmtNum(c, 0)} °C`);
export const fmtPct = (frac: number | null | undefined, digits = 0) =>
  frac === null || frac === undefined || !Number.isFinite(frac) ? '—' : `${fmtNum(frac * 100, digits)} %`;
export const fmtMs = (s: number | null | undefined) => (s === null || s === undefined || !Number.isFinite(s) ? '—' : `${fmtNum(s * 1000, 3)} ms`);

/** Human labels for LoadInputs keys (used to rewrite validateInputs messages). */
export const INPUT_LABELS: Record<string, string> = {
  boreDiameterIn: 'Bore diameter',
  grooveDiameterIn: 'Groove diameter',
  caseLengthIn: 'Case length',
  caseCapacityGrH2O: 'Case capacity',
  barrelLengthIn: 'Barrel length',
  bulletWeightGr: 'Bullet weight',
  bulletDiameterIn: 'Bullet diameter',
  bulletLengthIn: 'Bullet length',
  boatTailLengthIn: 'Boat-tail length',
  bulletBaseDiameterIn: 'Boat-tail base diameter',
  coalIn: 'COAL',
  chargeGr: 'Charge',
  powderTempF: 'Powder temperature',
  shotStartPsi: 'Shot-start pressure',
};

export function friendlyError(msg: string): string {
  const m = msg.match(/^(\w+) must be a positive number$/);
  if (m && INPUT_LABELS[m[1]]) return `${INPUT_LABELS[m[1]]} is required (positive number).`;
  return msg;
}

export function slug(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60);
}

export function downloadText(filename: string, text: string, mime = 'application/json') {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function toCsv(rows: Record<string, unknown>[]): string {
  if (!rows.length) return '';
  const keys = [...new Set(rows.flatMap((r) => Object.keys(r)))];
  const esc = (v: unknown) => {
    if (v === null || v === undefined) return '';
    const s = typeof v === 'object' ? JSON.stringify(v) : String(v);
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [keys.join(','), ...rows.map((r) => keys.map((k) => esc(r[k])).join(','))].join('\n');
}
