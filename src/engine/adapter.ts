// Converts user-facing load inputs (reloader units) into an engine LoadSetup (SI).

import { DEFAULT_OPTIONS } from './model';
import type { LoadSetup, ModelOptions, PropellantModel } from './types';
import type { PowderModelParams } from '../data/schema';
import * as U from './units';

export interface LoadInputs {
  boreDiameterIn: number;
  grooveDiameterIn: number;
  caseLengthIn: number;
  caseCapacityGrH2O: number;
  barrelLengthIn: number;
  bulletWeightGr: number;
  bulletDiameterIn: number;
  bulletLengthIn: number;
  boatTailLengthIn: number;
  bulletBaseDiameterIn: number;
  coalIn: number;
  chargeGr: number;
  powderTempF: number;
  shotStartPsi: number;
}

export function propellantFromParams(p: PowderModelParams, bulkDensityGcc?: number | null): PropellantModel {
  return {
    thermo: {
      forceJkg: p.forceJg * 1000,
      flameTempK: p.flameTempK,
      gamma: p.gamma,
      covolumeM3kg: p.covolumeCm3g * 1e-3,
      solidDensityKgM3: p.solidDensityGcc * 1000,
    },
    burn: { beta: p.beta, n: p.n, lambda: p.lambda, mu: p.mu, tempCoeffPerK: p.tempCoeffPerK, refTempC: p.refTempC },
    bulkDensityKgM3: bulkDensityGcc ? bulkDensityGcc * 1000 : undefined,
  };
}

export function paramsFromPropellant(m: PropellantModel, heatScale = 1): PowderModelParams {
  return {
    forceJg: m.thermo.forceJkg / 1000,
    flameTempK: m.thermo.flameTempK,
    gamma: m.thermo.gamma,
    covolumeCm3g: m.thermo.covolumeM3kg * 1000,
    solidDensityGcc: m.thermo.solidDensityKgM3 / 1000,
    beta: m.burn.beta,
    n: m.burn.n,
    lambda: m.burn.lambda,
    mu: m.burn.mu,
    tempCoeffPerK: m.burn.tempCoeffPerK,
    refTempC: m.burn.refTempC,
    heatScale,
  };
}

export function toSetup(inp: LoadInputs, propellant: PropellantModel, opts: Partial<ModelOptions> = {}, heatScale = 1): LoadSetup {
  const options: ModelOptions = {
    ...DEFAULT_OPTIONS,
    ...opts,
    shotStartPressurePa: U.psiToPa(inp.shotStartPsi),
    heatLoss: { ...DEFAULT_OPTIONS.heatLoss, ...(opts.heatLoss ?? {}), scale: heatScale },
  };
  return {
    caseCapacityM3: U.grH2OToM3(inp.caseCapacityGrH2O),
    caseLengthM: U.inToM(inp.caseLengthIn),
    boreDiameterM: U.inToM(inp.boreDiameterIn),
    grooveDiameterM: U.inToM(inp.grooveDiameterIn),
    barrelLengthM: U.inToM(inp.barrelLengthIn),
    bullet: {
      massKg: U.grToKg(inp.bulletWeightGr),
      diameterM: U.inToM(inp.bulletDiameterIn),
      lengthM: U.inToM(inp.bulletLengthIn),
      boatTailLengthM: U.inToM(inp.boatTailLengthIn || 0),
      baseDiameterM: U.inToM(inp.bulletBaseDiameterIn || inp.bulletDiameterIn),
    },
    coalM: U.inToM(inp.coalIn),
    chargeKg: U.grToKg(inp.chargeGr),
    propellant,
    propellantTempC: U.fToC(inp.powderTempF),
    options,
  };
}

/** Returns human-readable problems with the inputs (empty array = OK). */
export function validateInputs(inp: LoadInputs): string[] {
  const errs: string[] = [];
  const pos: (keyof LoadInputs)[] = ['boreDiameterIn', 'grooveDiameterIn', 'caseLengthIn', 'caseCapacityGrH2O', 'barrelLengthIn', 'bulletWeightGr', 'bulletDiameterIn', 'bulletLengthIn', 'coalIn', 'chargeGr', 'shotStartPsi'];
  for (const k of pos) if (!(Number(inp[k]) > 0)) errs.push(`${k} must be a positive number`);
  if (inp.grooveDiameterIn < inp.boreDiameterIn) errs.push('Groove diameter must be ≥ bore diameter');
  if (inp.coalIn <= inp.caseLengthIn) errs.push('COAL must be longer than the case');
  if (inp.barrelLengthIn <= inp.coalIn - inp.bulletLengthIn) errs.push('Barrel is shorter than the loaded cartridge');
  if (inp.boatTailLengthIn < 0 || inp.boatTailLengthIn >= inp.bulletLengthIn) errs.push('Boat-tail length must be ≥ 0 and shorter than the bullet');
  return errs;
}
