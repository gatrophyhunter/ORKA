// Default model inputs that depend on component type. Values are revisited against docs/MODEL.md sources.

import { DEFAULT_OPTIONS } from './model';
import { paToPsi } from './units';

/** Default shot-start (engraving) pressure in psi for a bullet construction. */
export function defaultShotStartPsi(construction?: string | null, cartridgeType?: 'rifle' | 'handgun'): number {
  const base = paToPsi(DEFAULT_OPTIONS.shotStartPressurePa);
  void construction;
  void cartridgeType;
  return Math.round(base);
}

export const DEFAULT_POWDER_TEMP_F = 70;
/** Default margin kept below the standard's maximum average pressure, percent. */
export const DEFAULT_PRESSURE_MARGIN_PCT = 5;
export const DEFAULT_MAX_FILL = 1.1;
export const DEFAULT_MIN_FILL = 0.8;
export const DEFAULT_MIN_BURNT = 0.85;
