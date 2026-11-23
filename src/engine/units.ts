// Unit conversions. Every constant here is an exact definition unless noted.

/** 1 grain = 64.79891 mg (exact, international avoirdupois definition). */
export const KG_PER_GRAIN = 64.79891e-6;
/** 1 inch = 25.4 mm (exact). */
export const M_PER_INCH = 0.0254;
/** 1 ft = 0.3048 m (exact). */
export const M_PER_FOOT = 0.3048;
/** 1 psi = 6894.757293168361 Pa (lbf/in², derived from exact lb and inch definitions and standard gravity). */
export const PA_PER_PSI = 6894.757293168361;
/** 1 bar = 100 000 Pa (exact). */
export const PA_PER_BAR = 1e5;
/** 1 ft·lbf = 1.3558179483314004 J (exact by definition of lbf and ft). */
export const J_PER_FTLBF = 1.3558179483314004;

/**
 * Density of water used to turn "grains of water" (overflow case capacity) into a volume.
 * 0.99820 g/cm³ is the density of pure water at 20 °C (a room-temperature measurement).
 * Using 1.000 instead changes volumes by 0.18 %, well inside case-to-case variation.
 */
export const WATER_DENSITY_G_PER_CM3 = 0.9982;

export const grToKg = (gr: number) => gr * KG_PER_GRAIN;
export const kgToGr = (kg: number) => kg / KG_PER_GRAIN;
export const grToG = (gr: number) => gr * KG_PER_GRAIN * 1000;
export const gToGr = (g: number) => g / (KG_PER_GRAIN * 1000);
export const inToM = (inch: number) => inch * M_PER_INCH;
export const mToIn = (m: number) => m / M_PER_INCH;
export const inToMm = (inch: number) => inch * 25.4;
export const mmToIn = (mm: number) => mm / 25.4;
export const fpsToMs = (fps: number) => fps * M_PER_FOOT;
export const msToFps = (ms: number) => ms / M_PER_FOOT;
export const psiToPa = (psi: number) => psi * PA_PER_PSI;
export const paToPsi = (pa: number) => pa / PA_PER_PSI;
export const barToPa = (bar: number) => bar * PA_PER_BAR;
export const paToBar = (pa: number) => pa / PA_PER_BAR;
export const mpaToPsi = (mpa: number) => paToPsi(mpa * 1e6);
export const psiToMpa = (psi: number) => psiToPa(psi) / 1e6;
export const jToFtlbf = (j: number) => j / J_PER_FTLBF;
export const cToK = (c: number) => c + 273.15;
export const fToC = (f: number) => ((f - 32) * 5) / 9;
export const cToF = (c: number) => (c * 9) / 5 + 32;

/** Grains of water (by mass) -> volume in m³. */
export const grH2OToM3 = (grH2O: number) =>
  (grH2O * KG_PER_GRAIN * 1000) / WATER_DENSITY_G_PER_CM3 * 1e-6;
/** Volume in m³ -> grains of water. */
export const m3ToGrH2O = (m3: number) =>
  ((m3 * 1e6) * WATER_DENSITY_G_PER_CM3) / (KG_PER_GRAIN * 1000);
export const cm3ToGrH2O = (cm3: number) => m3ToGrH2O(cm3 * 1e-6);
export const grH2OToCm3 = (gr: number) => grH2OToM3(gr) * 1e6;

/** Kinetic energy in ft·lbf for a projectile of `gr` grains at `fps` feet per second. */
export const energyFtLbf = (gr: number, fps: number) =>
  jToFtlbf(0.5 * grToKg(gr) * fpsToMs(fps) ** 2);

/**
 * CUP (copper units of pressure) and piezo psi are different measurement systems.
 * There is no fixed conversion factor between them; ORKA never converts one into the other.
 */
export type PressureUnit = 'psi' | 'MPa' | 'bar';

export function formatPressure(pa: number, unit: PressureUnit, digits = 0): string {
  switch (unit) {
    case 'psi':
      return `${paToPsi(pa).toLocaleString('en-US', { maximumFractionDigits: digits })} psi`;
    case 'MPa':
      return `${(pa / 1e6).toFixed(Math.max(digits, 1))} MPa`;
    case 'bar':
      return `${paToBar(pa).toLocaleString('en-US', { maximumFractionDigits: digits })} bar`;
  }
}
