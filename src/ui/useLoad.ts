// Derives the engine setup, pressure limit and component lookups from the shared builder state.

import { useMemo } from 'react';
import { propellantFromParams, toSetup, validateInputs } from '../engine/adapter';
import type { LoadSetup, PropellantModel } from '../engine/types';
import * as U from '../engine/units';
import type { Bullet, Cartridge, Database, ModelStatus, Powder } from '../data/schema';
import { friendlyError } from './format';
import { useApp, type BuilderState, type PressureStandard } from './state';

export interface CapacityOption {
  key: string;
  label: string;
  value: number | null;
  basis: string;
  brandId: string | null;
  sourceUrl: string | null;
}

export function modelStatus(p: Powder | null | undefined): ModelStatus {
  if (!p || !p.model) return 'none';
  return p.model.status;
}

export function powderPropellant(p: Powder | null | undefined): { model: PropellantModel; heatScale: number } | null {
  if (!p || !p.model || p.model.status === 'none') return null;
  return { model: propellantFromParams(p.model.params, p.bulkDensityGcc ?? null), heatScale: p.model.params.heatScale ?? 1 };
}

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '');

export function cartridgeMatches(c: Cartridge, label: string): boolean {
  const n = norm(label);
  return norm(c.name) === n || c.aliases.some((a) => norm(a) === n) || norm(c.id) === n;
}

export function capacityOptions(db: Database, cartridge: Cartridge | null): CapacityOption[] {
  if (!cartridge) return [];
  const brandName = new Map(db.brassBrands.map((b) => [b.id, b.name]));
  const out: CapacityOption[] = [];
  db.brassCases.forEach((c) => {
    const match = c.cartridgeId ? c.cartridgeId === cartridge.id : cartridgeMatches(cartridge, c.cartridge);
    if (!match) return;
    const brand = brandName.get(c.brandId) ?? c.brandId;
    const cond = c.capacityCondition && c.capacityCondition !== 'unknown' ? `, ${c.capacityCondition}` : '';
    const v = typeof c.waterCapacityGrH2O === 'number' ? c.waterCapacityGrH2O : null;
    out.push({
      key: `case:${c.brandId}:${c.sku ?? ''}:${v ?? 'na'}:${c.user ? 'u' : 'b'}`,
      label: `${brand}${c.sku ? ` (${c.sku})` : ''}${cond}${c.user ? ' — my entry' : ''}`,
      value: v,
      basis: `${c.basis ?? 'unspecified basis'}${cond}`,
      brandId: c.brandId,
      sourceUrl: c.sources?.[0]?.url ?? null,
    });
  });
  cartridge.caseCapacityGrH2O.forEach((e, i) => {
    // Skip entries already listed from the brass table (same brand and value).
    const dup = out.some((o) => o.value === e.value && (e.brand ?? '').toLowerCase() !== '' && o.label.toLowerCase().startsWith((e.brand ?? '').toLowerCase()));
    if (dup) return;
    const inferred = /inferred/i.test(e.basis);
    out.push({
      key: `cart:${i}:${e.value}`,
      label: inferred ? `${e.brand ?? 'Case'} — model-inferred, not measured` : `${e.brand ?? 'Brand not stated'} (cartridge record)`,
      value: e.value,
      basis: e.basis,
      brandId: null,
      sourceUrl: e.source,
    });
  });
  // Published / measured values first, model-inferred last.
  return out.sort((a, b) => Number(/inferred/i.test(a.basis)) - Number(/inferred/i.test(b.basis)));
}

export interface Limit {
  mapPa: number | null;
  limitPa: number | null;
  label: string;
  note: string | null;
  /** Set when a custom limit is above the cartridge's published maximum. */
  warning: string | null;
}

/** Standard for a newly chosen cartridge: an explicit C.I.P. choice is kept when the cartridge has a C.I.P. Pmax. */
export function standardForCartridge(current: PressureStandard, c: Cartridge): PressureStandard {
  if (current === 'CIP' && c.cipPmaxBar) return 'CIP';
  return c.saamiMapPsi ? 'SAAMI' : c.cipPmaxBar ? 'CIP' : 'custom';
}

/** Pressure-limit fields after the cartridge changes (picker and load-book recall). A custom limit typed for another cartridge never carries over. */
export function limitForCartridge(
  b: Pick<BuilderState, 'cartridgeId' | 'standard' | 'customLimitPsi'>,
  nextId: string | null,
  c: Cartridge | null,
): Pick<BuilderState, 'standard' | 'customLimitPsi'> {
  if (nextId === b.cartridgeId) return { standard: b.standard, customLimitPsi: b.customLimitPsi };
  return { standard: c ? standardForCartridge(b.standard, c) : b.standard, customLimitPsi: NaN };
}

/** The cartridge's published maxima that a psi limit exceeds, in words (CUP values are not comparable and are skipped). */
export function exceededMaxima(limitPsi: number, cartridge: Cartridge | null): string[] {
  if (!cartridge || !(Number.isFinite(limitPsi) && limitPsi > 0)) return [];
  const fmt = (v: number) => Math.round(v).toLocaleString('en-US');
  const over: string[] = [];
  if (cartridge.saamiMapPsi && limitPsi > cartridge.saamiMapPsi) {
    over.push(`${cartridge.user ? 'your entered MAP' : 'SAAMI MAP'} (${fmt(cartridge.saamiMapPsi)} psi)`);
  }
  if (cartridge.cipPmaxBar) {
    const psi = U.paToPsi(U.barToPa(cartridge.cipPmaxBar));
    if (limitPsi > psi) over.push(`${cartridge.user ? 'your entered Pmax' : 'C.I.P. Pmax'} (${fmt(cartridge.cipPmaxBar)} bar = ${fmt(psi)} psi)`);
  }
  return over;
}

/** Warning when a custom psi limit is above the cartridge's SAAMI MAP or C.I.P. Pmax. */
export function customLimitWarning(customLimitPsi: number, cartridge: Cartridge | null): string | null {
  const over = exceededMaxima(customLimitPsi, cartridge);
  if (!over.length) return null;
  return `Your custom limit (${Math.round(customLimitPsi).toLocaleString('en-US')} psi) is above this cartridge's ${over.join(' and ')}. Every pressure check now uses your higher limit. Lower it to the published maximum or below.`;
}

export function pressureLimit(b: BuilderState, cartridge: Cartridge | null): Limit {
  let mapPa: number | null = null;
  let label = '';
  const notes: string[] = [];
  // CUP and piezo psi are different measurements: say so whenever the SAAMI MAP exists only in CUP.
  const cupOnly =
    cartridge && !cartridge.saamiMapPsi && cartridge.saamiMapCup
      ? `This cartridge's SAAMI MAP is published in CUP only (${cartridge.saamiMapCup.toLocaleString('en-US')} CUP). CUP and piezo psi are different measurement systems and are not converted.`
      : null;
  if (b.standard === 'SAAMI') {
    if (cartridge?.saamiMapPsi) {
      mapPa = U.psiToPa(cartridge.saamiMapPsi);
      label = cartridge.user
        ? `Your entered MAP ${cartridge.saamiMapPsi.toLocaleString('en-US')} psi (not from the standard)`
        : `SAAMI MAP ${cartridge.saamiMapPsi.toLocaleString('en-US')} psi (piezo)`;
    } else if (cupOnly) {
      notes.push(`${cupOnly} Choose CIP or enter a custom psi limit.`);
    } else {
      notes.push(cartridge ? 'No SAAMI piezo MAP on record for this cartridge. Choose CIP or enter a custom limit.' : 'Select a cartridge or enter a custom limit.');
    }
  } else if (b.standard === 'CIP') {
    if (cartridge?.cipPmaxBar) {
      mapPa = U.barToPa(cartridge.cipPmaxBar);
      label = cartridge.user
        ? `Your entered Pmax ${cartridge.cipPmaxBar.toLocaleString('en-US')} bar (not from the standard)`
        : `C.I.P. Pmax ${cartridge.cipPmaxBar.toLocaleString('en-US')} bar`;
    } else if (cupOnly) {
      notes.push(`No C.I.P. Pmax on record for this cartridge. ${cupOnly} Enter a custom psi limit.`);
    } else {
      notes.push(cartridge ? 'No C.I.P. Pmax on record for this cartridge. Choose SAAMI or enter a custom limit.' : 'Select a cartridge or enter a custom limit.');
    }
  } else {
    if (Number.isFinite(b.customLimitPsi) && b.customLimitPsi > 0) {
      mapPa = U.psiToPa(b.customLimitPsi);
      label = `Custom limit ${b.customLimitPsi.toLocaleString('en-US')} psi`;
      if (cupOnly) notes.push(cupOnly);
    } else notes.push(cupOnly ? `${cupOnly} Enter a custom psi limit.` : 'Enter a custom pressure limit.');
  }
  // The margin actually applied is stated in the label; values outside 0–50 % are clamped and flagged (review finding).
  const raw = b.marginPct;
  const margin = Number.isFinite(raw) ? Math.min(Math.max(raw, 0), 50) : 0;
  if (mapPa !== null) {
    label = `${label} − ${margin} % margin`;
    if (!Number.isFinite(raw)) notes.push('Safety margin is empty: 0 % applied.');
    else if (raw !== margin) notes.push(`Safety margin ${raw} % is outside 0–50 %: ${margin} % applied.`);
  }
  const limitPa = mapPa !== null ? mapPa * (1 - margin / 100) : null;
  const warning = b.standard === 'custom' ? customLimitWarning(b.customLimitPsi, cartridge) : null;
  return { mapPa, limitPa, label, note: notes.length ? notes.join(' ') : null, warning };
}

export interface DerivedLoad {
  cartridge: Cartridge | null;
  powder: Powder | null;
  bullet: Bullet | null;
  status: ModelStatus;
  propellant: PropellantModel | null;
  heatScale: number;
  errors: string[];
  setup: LoadSetup | null;
  limit: Limit;
}

export function deriveLoad(db: Database, b: BuilderState): DerivedLoad {
  const cartridge = b.cartridgeId ? db.cartridges.find((c) => c.id === b.cartridgeId) ?? null : null;
  const powder = b.powderId ? db.powders.find((p) => p.id === b.powderId) ?? null : null;
  const bullet = b.bulletId ? db.bullets.find((x) => x.id === b.bulletId) ?? null : null;
  const status = modelStatus(powder);
  const prop = powderPropellant(powder);
  const errors = validateInputs(b.inputs).map(friendlyError);
  if (!powder) errors.push('Select a powder.');
  else if (!prop) errors.push(`"${powder.name}" has no burn model yet. Calibrate it (Calibrate tab) or enter parameters manually before predicting.`);
  const setup = errors.length === 0 && prop ? toSetup(b.inputs, prop.model, {}, prop.heatScale) : null;
  return {
    cartridge,
    powder,
    bullet,
    status,
    propellant: prop?.model ?? null,
    heatScale: prop?.heatScale ?? 1,
    errors,
    setup,
    limit: pressureLimit(b, cartridge),
  };
}

export function useLoad(): DerivedLoad {
  const { db, builder } = useApp();
  return useMemo(() => deriveLoad(db, builder), [db, builder]);
}

/**
 * Setup for an arbitrary powder using the current builder geometry. The charge is not needed by
 * solvers/search, so a missing charge is replaced by a placeholder that the solver overwrites.
 */
export function geometryErrors(b: BuilderState): string[] {
  const inputs = { ...b.inputs, chargeGr: b.inputs.chargeGr > 0 ? b.inputs.chargeGr : 1 };
  return validateInputs(inputs).map(friendlyError);
}

export function setupForPowder(b: BuilderState, p: PropellantModel, heatScale = 1): LoadSetup | null {
  const inputs = { ...b.inputs, chargeGr: b.inputs.chargeGr > 0 ? b.inputs.chargeGr : 1 };
  if (validateInputs(inputs).length) return null;
  return toSetup(inputs, p, {}, heatScale);
}
