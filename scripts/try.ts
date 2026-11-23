import { simulate, DEFAULT_OPTIONS } from '../src/engine/model';
import { grToKg, inToM, grH2OToM3, msToFps, paToPsi } from '../src/engine/units';
const beta = Number(process.argv[2] ?? 10);
const charge = Number(process.argv[3] ?? 44);
const setup = {
  caseCapacityM3: grH2OToM3(56), caseLengthM: inToM(2.005), boreDiameterM: inToM(0.300), grooveDiameterM: inToM(0.308),
  barrelLengthM: inToM(24), coalM: inToM(2.8), chargeKg: grToKg(charge), propellantTempC: 21,
  bullet: { massKg: grToKg(168), diameterM: inToM(0.308), lengthM: inToM(1.215), boatTailLengthM: inToM(0.15), baseDiameterM: inToM(0.25) },
  propellant: { thermo: { forceJkg: 1.0e6, flameTempK: 2900, gamma: 1.24, covolumeM3kg: 1.0e-3, solidDensityKgM3: 1600 },
    burn: { beta, n: 1, lambda: 0, mu: 0, tempCoeffPerK: 0, refTempC: 21 } },
  options: { ...DEFAULT_OPTIONS },
};
const r = simulate(setup);
const t0 = performance.now(); for (let i=0;i<200;i++) simulate(setup); const dt=(performance.now()-t0)/200;
console.log(r.status, r.messages.join(';'), 'Pmax psi', paToPsi(r.peakBreechPa).toFixed(0), 'V fps', msToFps(r.muzzleVelocityMs).toFixed(0),
 'burnt', r.burntAtMuzzle.toFixed(3), 'Pmuz', paToPsi(r.muzzleBreechPa).toFixed(0), 'bt ms', (r.barrelTimeS*1e3).toFixed(3),
 'eff', r.ballisticEfficiency.toFixed(3), 'heatJ', r.heatLossJ.toFixed(0), 'V0grH2O', (r.chamberVolumeM3*1e6*0.9982/0.06479891).toFixed(2), 'travel', (r.travelM/0.0254).toFixed(3), 'ms/sim', dt.toFixed(3));
