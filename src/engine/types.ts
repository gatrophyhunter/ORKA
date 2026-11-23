// Core engine types. All engine internals are SI (kg, m, s, Pa, J, K).

/** Thermochemical properties of a propellant (constant-volume, Noble-Abel gas). */
export interface Thermo {
  /** Impetus / "force" f = R·T0 per unit mass, J/kg. */
  forceJkg: number;
  /** Adiabatic isochoric flame temperature T0, K. */
  flameTempK: number;
  /** Ratio of specific heats of the combustion gas. */
  gamma: number;
  /** Noble-Abel covolume, m³/kg. */
  covolumeM3kg: number;
  /** Density of the solid propellant (not bulk density), kg/m³. */
  solidDensityKgM3: number;
}

/**
 * Burn law used by ORKA:
 *   dz/dt = beta · (p / 1 MPa)^n · (1 + tempCoeffPerK·(T_prop − refTempC))
 *   psi(z) = chi · z · (1 + lambda·z + mu·z²),  chi = 1 / (1 + lambda + mu)
 * z is the burnt fraction of the web (0..1), psi the burnt fraction of mass (0..1).
 * lambda < 0 is degressive (cord, flake, ball without deterrent), lambda > 0 progressive.
 */
export interface BurnModel {
  /** Web regression rate coefficient, 1/s at 1 MPa and the reference temperature. */
  beta: number;
  /** Pressure exponent of the burn-rate law. */
  n: number;
  lambda: number;
  mu: number;
  /** Fractional change of beta per kelvin above refTempC (e.g. 0.002 = 0.2 %/K). Also used below refTempC unless tempCoeffColdPerK is set. */
  tempCoeffPerK: number;
  /** Optional separate coefficient for temperatures below refTempC (burn-rate sensitivity is often asymmetric). */
  tempCoeffColdPerK?: number;
  refTempC: number;
}

export interface PropellantModel {
  thermo: Thermo;
  burn: BurnModel;
  /** Bulk (loading) density, kg/m³, used for fill ratio. Optional. */
  bulkDensityKgM3?: number;
}

export interface BulletGeometry {
  massKg: number;
  diameterM: number;
  lengthM: number;
  /** Boat-tail length; 0 or undefined for flat base. */
  boatTailLengthM?: number;
  /** Diameter at the base of the boat tail. */
  baseDiameterM?: number;
}

export interface HeatLossOptions {
  enabled: boolean;
  /** Multiplier on the convective heat-transfer coefficient (calibration knob, 1 = model default). */
  scale: number;
  /** Bore / chamber wall temperature, K. */
  wallTempK: number;
}

export interface ModelOptions {
  /** Base pressure at which the projectile starts to move (engraving / shot-start), Pa. */
  shotStartPressurePa: number;
  /** Pressure contributed by the primer before the powder burns, Pa (energy p·V placed in the free volume at t=0). */
  ignitionPressurePa: number;
  /** Distance of the pressure transducer from the breech face, m (C.I.P.: 25 mm where the case allows). */
  gaugeDistanceM: number;
  /** Secondary-work coefficient phi1 (friction, rotation, engraving) — Lagrange fictitious-mass factor. */
  secondaryWorkCoeff: number;
  heatLoss: HeatLossOptions;
  /** Relative / absolute tolerance for the adaptive integrator. */
  rtol: number;
  atol: number;
  maxSteps: number;
  /** Keep the full time history (for charts). */
  recordTrace: boolean;
}

export interface LoadSetup {
  /** Overflow case capacity to the case mouth, m³. */
  caseCapacityM3: number;
  /** Actual (trimmed) case length, m. */
  caseLengthM: number;
  boreDiameterM: number;
  grooveDiameterM: number;
  /** Barrel length measured from the bolt face to the muzzle, m. */
  barrelLengthM: number;
  bullet: BulletGeometry;
  /** Cartridge overall length (case head to bullet tip), m. */
  coalM: number;
  chargeKg: number;
  propellant: PropellantModel;
  propellantTempC: number;
  options: ModelOptions;
}

export interface Trace {
  t: number[];
  x: number[];
  v: number[];
  pBreech: number[];
  pBase: number[];
  pGauge: number[];
  psi: number[];
}

/** 'diverged' = predicted pressure ran away (free gas volume → 0): far beyond any safe load and outside the model's range. */
export type SimStatus = 'muzzle' | 'stuck' | 'max-steps' | 'invalid' | 'diverged';

export interface SimResult {
  status: SimStatus;
  messages: string[];
  /** Peak breech (chamber) pressure — the quantity comparable to SAAMI/CIP piezo MAP, Pa. */
  peakBreechPa: number;
  peakBasePa: number;
  /** Peak pressure at the gauge station (Lagrange distribution, volume coordinate) — between base and breech pressure. */
  peakGaugePa: number;
  timeOfPeakS: number;
  travelAtPeakM: number;
  muzzleVelocityMs: number;
  muzzleBreechPa: number;
  /** Time from ignition to muzzle exit, s. */
  barrelTimeS: number;
  /** Time from shot start to muzzle exit, s. */
  travelTimeS: number;
  /** Time from the breech pressure first reaching 10 % of its peak to muzzle exit, s (the GRT / QuickLOAD convention). */
  barrelTime10S: number;
  shotStartTimeS: number;
  burntAtMuzzle: number;
  burnoutTravelM: number | null;
  /** Free volume behind the bullet at t=0 (case capacity minus seated bullet), m³. */
  chamberVolumeM3: number;
  /** Charge mass divided by chamber volume, kg/m³. */
  loadDensityKgM3: number;
  /** Bulk-powder volume / chamber volume (1 = case full to the bullet base), null if bulk density unknown. */
  fillRatio: number | null;
  seatingDepthM: number;
  travelM: number;
  /** Projectile kinetic energy / chemical energy available (f·C/(gamma−1)). */
  ballisticEfficiency: number;
  heatLossJ: number;
  trace?: Trace;
}
