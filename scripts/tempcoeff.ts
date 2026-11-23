import { simulate, DEFAULT_OPTIONS } from '../src/engine/model';
import { grToKg, inToM, grH2OToM3, msToFps, fToC } from '../src/engine/units';
const mk = (k: number, tF: number) => simulate({
  caseCapacityM3: grH2OToM3(56), caseLengthM: inToM(2.005), boreDiameterM: inToM(0.300), grooveDiameterM: inToM(0.308),
  barrelLengthM: inToM(24), coalM: inToM(2.8), chargeKg: grToKg(44), propellantTempC: fToC(tF),
  bullet: { massKg: grToKg(168), diameterM: inToM(0.308), lengthM: inToM(1.215), boatTailLengthM: inToM(0.15), baseDiameterM: inToM(0.25) },
  propellant: { thermo: { forceJkg: 1.07e6, flameTempK: 2885, gamma: 1.25, covolumeM3kg: 1.0e-3, solidDensityKgM3: 1600 },
    burn: { beta: Number(process.env.B ?? 4.2), n: 1, lambda: 0, mu: 0, tempCoeffPerK: k, refTempC: 21 } },
  options: { ...DEFAULT_OPTIONS } });
for (const k of [0.0007, 0.0008, 0.001]) {
  const lo = mk(k, 40), mid = mk(k, 70), hi = mk(k, 100);
  console.log(k, 'P70', (mid.peakBreechPa/6894.757).toFixed(0), 'V70', msToFps(mid.muzzleVelocityMs).toFixed(0), 'fps/F', ((msToFps(hi.muzzleVelocityMs)-msToFps(lo.muzzleVelocityMs))/60).toFixed(2), 'psi/F', ((hi.peakBreechPa-lo.peakBreechPa)/6894.757/60).toFixed(0));
}
