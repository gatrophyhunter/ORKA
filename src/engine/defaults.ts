// Default model inputs and priors. Each value states its basis; see docs/MODEL.md §Defaults and
// research/raw/physics.md (reference numbers [n] below refer to that dossier's reference list).
// These are PRIORS: a powder's own calibration (published pressure data or chronograph data) overrides them.

import type { PowderModelParams } from '../data/schema';
import modelConstants from '../data/model-constants.json';

/**
 * Shot-start (engraving) pressure defaults, psi.
 *  - Jacketed lead-core: 25 MPa — the widely reported QuickLOAD default (forum reports [50][150][151]),
 *    inside the 24–44 MPa first engraving maximum reported for 6.5–9.3 mm jacketed bullets [47].
 *  - Monolithic copper/brass: 35.3 MPa — default of the open-source OpenReloading workbench [48];
 *    a forum engraving-force study reports much higher peaks for solid copper (~100 MPa) [50]. Third-party values.
 *  - Cast / swaged lead / plated: 30.0 MPa — OpenReloading default for lead [48]. Third-party value.
 * All three are calibratable; the uncertainty band varies shot-start by ±20 % (1σ).
 */
const MPA_TO_PSI = 145.03773773020923;

type ShotClass = 'monolithic' | 'lead' | 'jacketed';
/** Shot-start pressure (MPa) per construction class: reference value for jacketed bullets; monolithic and lead values are
 * fitted to published pressure-tested loads by scripts/calibrate-powders.ts (see src/data/model-constants.json for basis). */
export function shotStartMPa(cls: ShotClass): number {
  const v = (modelConstants as any)?.shotStartMPa?.[cls]?.value;
  return typeof v === 'number' && v > 0 ? v : cls === 'monolithic' ? 35.3 : cls === 'lead' ? 30.0 : 25.0;
}
export function shotStartBasis(cls: ShotClass): string {
  return String((modelConstants as any)?.shotStartMPa?.[cls]?.basis ?? '');
}

/** Classify bullet construction text for the shot-start default. Jacketed descriptions are never monolithic. */
export function shotStartClass(construction?: string | null): 'monolithic' | 'lead' | 'jacketed' {
  const c = (construction ?? '').toLowerCase();
  if (!c.trim()) return 'jacketed';
  const jacketed = /jacket|cup-and-core|cup and core|bonded|partition|fmj|tmj|lead[- ]?core|core/.test(c);
  if (!jacketed && /\b(mono|monolithic|monometal|all[- ]copper|solid[- ]copper|solid[- ]brass|lead[- ]free|cuzn|homogeneous|tsx|ttsx|lrx|tac-x|e-tip|cx)\b|monolithic|copper alloy|brass/.test(c)) return 'monolithic';
  if (!jacketed && /\b(lead|cast|swaged|plated|lrn|lswc|lwc|hard cast|coated)\b/.test(c)) return 'lead';
  return 'jacketed';
}
export function defaultShotStartPsi(construction?: string | null, cartridgeType?: 'rifle' | 'handgun'): number {
  void cartridgeType;
  return Math.round(shotStartMPa(shotStartClass(construction)) * MPA_TO_PSI);
}

export const DEFAULT_POWDER_TEMP_F = 70;
/** Default margin kept below the standard's maximum average pressure, percent. */
export const DEFAULT_PRESSURE_MARGIN_PCT = 5;
export const DEFAULT_MAX_FILL = 1.1;
export const DEFAULT_MIN_FILL = 0.8;
export const DEFAULT_MIN_BURNT = 0.85;

/**
 * Generic temperature coefficient of the burn-rate coefficient, 1/K.
 * Chosen so the model reproduces the published rule of thumb of about 1 fps per °F for moderate rifle
 * loads (Sierra [95]; Gun Digest [96]; 1–1.5 fps/°F for .308 Win [98]): 0.0007/K gives 1.0–1.1 fps/°F for a
 * .308 Win 168 gr load at 43–52 kpsi in this model (scripts/tempcoeff.ts). NOT powder-specific: "temperature
 * stable" powders are less sensitive and some ball powders more. Powder-specific values override it.
 */
export const GENERIC_TEMP_COEFF_PER_K = 0.0007;

/**
 * Thermochemistry prior from a published heat of explosion Q (J/g).
 * With an ideal Noble-Abel gas of constant cv: f = R·Tv and Q ≈ cv·(Tv − T0) = R/(γ−1)·(Tv − T0), so
 *   Tv = T0 + Q·(γ−1)/R,   f = R·Tv.
 * R (specific gas constant of the products) = 0.37 J/(g·K): M1 gives 919–924 J/g / 2447–2449 K = 0.376 [72][73],
 * M6 gives 947.5 J/g / 2570 K = 0.369 [70]. γ = 1.25 sits between M6 (1.254 [70]) and the hotter M30A1 (1.241 [77]).
 * The dossier warns that Q→f is not an identity (Q may count water as liquid; cv varies with T), so the result
 * is a prior that calibration with pressure data refines (the 'force' fit parameter).
 * Sanity check: M6's published f and Tv imply Q ≈ 3,300 J/g with this relation — the right magnitude for M6.
 */
export const GAS_CONSTANT_JgK = 0.37;
export const GAMMA_PRIOR = 1.25;
const T0 = 298.15;

/** Class priors for Q when the maker publishes none: single-base = midpoint of Reload Swiss RS40–RS70 (3,750–3,950 J/g [78]–[82]); double-base = mean of the Vihtavuori N5xx values (3,700–4,000 J/g [85]). */
export const Q_PRIOR_SINGLE_BASE = 3850;
export const Q_PRIOR_DOUBLE_BASE = 3906;

/** Covolume ≈ 1 cm³/g "for most propellants" [5] (M1 1.105 [72][73], M30A1 1.041 [77]). */
export const COVOLUME_PRIOR_CM3G = 1.0;

/**
 * Solid (not bulk) density of nitrocellulose-based propellant. NOT SOURCED in the research dossier yet;
 * 1.6 g/cm³ is the conventional engineering value. It only sets the volume of unburnt grains and is absorbed
 * by calibration; flagged for verification in docs/DATA.md.
 */
export const SOLID_DENSITY_PRIOR_GCC = 1.6;

export function thermoFromHeatOfExplosion(qJg: number): { forceJg: number; flameTempK: number; gamma: number } {
  const tv = T0 + (qJg * (GAMMA_PRIOR - 1)) / GAS_CONSTANT_JgK;
  return { forceJg: GAS_CONSTANT_JgK * tv, flameTempK: tv, gamma: GAMMA_PRIOR };
}

/** Prior model parameters for a powder before calibration (burn rate left to the caller). */
export function priorParams(opts: { heatOfExplosionJg?: number | null; base?: 'single' | 'double' | 'triple' | null; beta: number; lambda?: number }): PowderModelParams {
  const q = opts.heatOfExplosionJg ?? (opts.base === 'double' ? Q_PRIOR_DOUBLE_BASE : Q_PRIOR_SINGLE_BASE);
  const th = thermoFromHeatOfExplosion(q);
  return {
    forceJg: th.forceJg,
    flameTempK: th.flameTempK,
    gamma: th.gamma,
    covolumeCm3g: COVOLUME_PRIOR_CM3G,
    solidDensityGcc: SOLID_DENSITY_PRIOR_GCC,
    beta: opts.beta,
    n: 1,
    lambda: opts.lambda ?? 0,
    mu: 0,
    tempCoeffPerK: GENERIC_TEMP_COEFF_PER_K,
    refTempC: 21,
    heatScale: 1,
  };
}

/** Starting point for a user calibration of a powder that has no model yet. */
export const PRIOR_SINGLE_BASE: PowderModelParams = priorParams({ base: 'single', beta: 5 });
export const PRIOR_DOUBLE_BASE: PowderModelParams = priorParams({ base: 'double', beta: 5 });

export interface ModelValidationSummary {
  heldOutPressureN: number;
  heldOutPressureP50Pct: number;
  heldOutPressureP90Pct: number;
  heldOutPressureBiasPct: number;
  heldOutWithin10Pct: number;
  scope: string;
  heldOutCartridgeIds?: string[];
  heldOutPowders?: number;
}
/** Headline held-out validation of the calibrated models (scripts/validation-summary.ts), or null before calibration. */
export function modelValidation(): ModelValidationSummary | null {
  const v = (modelConstants as any)?.validation;
  return v && typeof v.heldOutPressureP90Pct === 'number' ? (v as ModelValidationSummary) : null;
}
