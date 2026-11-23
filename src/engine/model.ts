// Lumped-parameter interior-ballistics model.
//
// Equations (classical "thermodynamic" / lumped-parameter formulation, see docs/MODEL.md):
//   Free volume:   Vf = V0 − (C/ρp)(1−ψ) − η·C·ψ + S·x
//   Energy (Résal): p·Vf = f·C·ψ + E_ig − (γ−1)·[ ½·(φ1·m + C/3)·v² + Q ]
//   Motion:        (φ1·m + C/3)·dv/dt = S·p          (p = space-mean pressure)
//   Lagrange:      p_base = p / (1 + C/(3φ1·m)),   p_breech = p_base·(1 + C/(2φ1·m))
//   Burn:          dz/dt = β·(p/1 MPa)^n·(1 + κ·(T − Tref)),  ψ = χ·z·(1 + λz + μz²)
//   Heat loss:     dQ/dt = scale·St·ρg·cp·(v/2)·(T − Tw)·Aw   (Reynolds-analogy convective loss)
// State vector y = [z, x, v, Q]. Integrated with adaptive Dormand–Prince 5(4) with event location.

import type { LoadSetup, ModelOptions, SimResult, Trace, BulletGeometry, PropellantModel } from './types';

export const DEFAULT_OPTIONS: ModelOptions = {
  shotStartPressurePa: 25e6,
  ignitionPressurePa: 5e6,
  gaugeDistanceM: 0.025,
  secondaryWorkCoeff: 1.05,
  heatLoss: { enabled: true, scale: 1, wallTempK: 293.15 },
  rtol: 1e-7,
  atol: 1e-9,
  maxSteps: 200000,
  recordTrace: false,
};

/** Stanton number for the Reynolds-analogy heat-loss model (see docs/MODEL.md; calibration absorbs its uncertainty). */
export const STANTON = 0.002;

const MPA = 1e6;

/** Bore cross-section assuming equal land and groove widths: S = π/8·(d_bore² + d_groove²). */
export function boreArea(boreDiameterM: number, grooveDiameterM: number): number {
  return (Math.PI / 8) * (boreDiameterM ** 2 + grooveDiameterM ** 2);
}

/** Volume of the bullet below a plane `depth` above its base (handles a conical boat tail). */
export function bulletVolumeBelow(b: BulletGeometry, depth: number): number {
  if (depth <= 0) return 0;
  const R = b.diameterM / 2;
  const btL = b.boatTailLengthM ?? 0;
  const rb = (b.baseDiameterM ?? b.diameterM) / 2;
  if (btL <= 0 || rb >= R) return Math.PI * R * R * depth;
  const frustum = (h: number) => {
    // radius grows linearly from rb at h=0 to R at h=btL
    const r1 = rb;
    const r2 = rb + ((R - rb) * h) / btL;
    return (Math.PI * h * (r1 * r1 + r1 * r2 + r2 * r2)) / 3;
  };
  if (depth <= btL) return frustum(depth);
  return frustum(btL) + Math.PI * R * R * (depth - btL);
}

export interface DerivedGeometry {
  S: number;
  seatingDepthM: number;
  chamberVolumeM3: number;
  travelM: number;
  chamberWallAreaM2: number;
  messages: string[];
}

export function deriveGeometry(s: LoadSetup): DerivedGeometry {
  const messages: string[] = [];
  const S = boreArea(s.boreDiameterM, s.grooveDiameterM);
  let seatingDepthM = s.bullet.lengthM - (s.coalM - s.caseLengthM);
  if (seatingDepthM < 0) {
    messages.push('Bullet base sits above the case mouth at this COAL (seating depth < 0); treated as 0.');
    seatingDepthM = 0;
  }
  const chamberVolumeM3 = s.caseCapacityM3 - bulletVolumeBelow(s.bullet, seatingDepthM);
  const travelM = s.barrelLengthM - (s.coalM - s.bullet.lengthM);
  // Approximate the powder chamber as a cylinder of the case's internal length.
  const innerLen = Math.max(s.caseLengthM - seatingDepthM, 1e-3);
  const r = Math.sqrt(Math.max(chamberVolumeM3, 1e-9) / (Math.PI * innerLen));
  const chamberWallAreaM2 = 2 * Math.PI * r * innerLen + 2 * Math.PI * r * r;
  return { S, seatingDepthM, chamberVolumeM3, travelM, chamberWallAreaM2, messages };
}

export function formFunction(burn: PropellantModel['burn']) {
  const { lambda, mu } = burn;
  const chi = 1 / (1 + lambda + mu);
  return {
    chi,
    psi: (z: number) => {
      const zc = z <= 0 ? 0 : z >= 1 ? 1 : z;
      return chi * zc * (1 + lambda * zc + mu * zc * zc);
    },
  };
}

// Dormand–Prince 5(4) tableau
const A = [
  [],
  [1 / 5],
  [3 / 40, 9 / 40],
  [44 / 45, -56 / 15, 32 / 9],
  [19372 / 6561, -25360 / 2187, 64448 / 6561, -212 / 729],
  [9017 / 3168, -355 / 33, 46732 / 5247, 49 / 176, -5103 / 18656],
  [35 / 384, 0, 500 / 1113, 125 / 192, -2187 / 6784, 11 / 84],
];
const B5 = [35 / 384, 0, 500 / 1113, 125 / 192, -2187 / 6784, 11 / 84, 0];
const E = [71 / 57600, 0, -71 / 16695, 71 / 1920, -17253 / 339200, 22 / 525, -1 / 40];

type Vec = [number, number, number, number];

export function simulate(setup: LoadSetup): SimResult {
  const o = setup.options;
  const g = deriveGeometry(setup);
  const messages = [...g.messages];
  const C = setup.chargeKg;
  const m = setup.bullet.massKg;
  const th = setup.propellant.thermo;
  const burn = setup.propellant.burn;
  const f = th.forceJkg;
  const gam = th.gamma;
  const theta = gam - 1;
  const eta = th.covolumeM3kg;
  const rhoP = th.solidDensityKgM3;
  const R = f / th.flameTempK;
  const cp = (gam * R) / theta;
  const phi1 = o.secondaryWorkCoeff;
  const phiM = phi1 * m + C / 3;
  const baseFactor = 1 / (1 + C / (3 * phi1 * m));
  const breechFactor = baseFactor * (1 + C / (2 * phi1 * m));
  const V0 = g.chamberVolumeM3;
  const S = g.S;
  const L = g.travelM;
  const ff = formFunction(burn);
  const dT = setup.propellantTempC - burn.refTempC;
  const kT = dT < 0 && burn.tempCoeffColdPerK !== undefined ? burn.tempCoeffColdPerK : burn.tempCoeffPerK;
  const tempFactor = Math.max(0.05, 1 + kT * dT);
  const betaEff = burn.beta * tempFactor;
  const n = burn.n;
  const heat = o.heatLoss;
  const Tw = heat.wallTempK;
  const stHeat = heat.enabled ? STANTON * heat.scale : 0;
  const perimeter = Math.PI * setup.boreDiameterM;

  const solidVol = C / rhoP;
  const bulk = setup.propellant.bulkDensityKgM3;
  const fillRatio = bulk && bulk > 0 && V0 > 0 ? C / bulk / V0 : null;

  const empty = (status: SimResult['status']): SimResult => ({
    status,
    messages,
    peakBreechPa: NaN,
    peakBasePa: NaN,
    peakGaugePa: NaN,
    timeOfPeakS: NaN,
    travelAtPeakM: NaN,
    muzzleVelocityMs: NaN,
    muzzleBreechPa: NaN,
    barrelTimeS: NaN,
    travelTimeS: NaN,
    barrelTime10S: NaN,
    shotStartTimeS: NaN,
    burntAtMuzzle: NaN,
    burnoutTravelM: null,
    chamberVolumeM3: V0,
    loadDensityKgM3: C / V0,
    fillRatio,
    seatingDepthM: g.seatingDepthM,
    travelM: L,
    ballisticEfficiency: NaN,
    heatLossJ: NaN,
  });

  if (!(C > 0) || !(m > 0) || !(V0 > 0) || !(L > 0)) {
    messages.push('Invalid geometry or masses (charge, bullet mass, chamber volume and travel must be positive).');
    return empty('invalid');
  }
  if (V0 - solidVol <= 0) {
    messages.push('Charge does not physically fit: the solid propellant volume alone exceeds the chamber volume.');
    return empty('invalid');
  }

  const Vf0 = V0 - solidVol;
  // Gauge station as a fraction of the powder-chamber volume (chamber approximated as a cylinder of the
  // case's internal length), then expressed in the Lagrange volume coordinate s = V(gauge)/V(total gas).
  const innerLen = Math.max(setup.caseLengthM - g.seatingDepthM, 1e-3);
  const gaugeVol = Math.min(1, Math.max(0, o.gaugeDistanceM / innerLen)) * V0;
  const Eig = o.ignitionPressurePa * Vf0;
  const p0 = o.shotStartPressurePa;
  const chemEnergy = (f * C) / theta;

  let moving = false;

  // Returns mean pressure for a state.
  const pressure = (y: Vec): number => {
    const psi = ff.psi(y[0]);
    const Vf = V0 - solidVol * (1 - psi) - eta * C * psi + S * y[1];
    const numer = f * C * psi + Eig - theta * (0.5 * phiM * y[2] * y[2] + y[3]);
    return numer / Vf;
  };

  const deriv = (y: Vec, out: Vec) => {
    const z = y[0];
    const psi = ff.psi(z);
    const Vf = V0 - solidVol * (1 - psi) - eta * C * psi + S * y[1];
    const energy = f * C * psi + Eig;
    const numer = energy - theta * (0.5 * phiM * y[2] * y[2] + y[3]);
    const p = numer / Vf;
    const pPos = p > 0 ? p : 0;
    out[0] = z < 1 ? betaEff * Math.pow(pPos / MPA, n) : 0;
    if (moving) {
      out[1] = y[2];
      out[2] = (S * p) / phiM;
    } else {
      out[1] = 0;
      out[2] = 0;
    }
    if (stHeat > 0 && y[2] > 0 && psi > 0) {
      const gasMass = C * psi;
      const T = th.flameTempK * (pPos * Vf) / energy;
      const rhoG = gasMass / (Vf + eta * gasMass);
      const area = g.chamberWallAreaM2 + perimeter * y[1];
      out[3] = stHeat * rhoG * cp * (0.5 * y[2]) * Math.max(T - Tw, 0) * area;
    } else {
      out[3] = 0;
    }
  };

  const k: Vec[] = Array.from({ length: 7 }, () => [0, 0, 0, 0] as Vec);
  const tmp: Vec = [0, 0, 0, 0];
  const yNew: Vec = [0, 0, 0, 0];
  const errV: Vec = [0, 0, 0, 0];
  const atolV: Vec = [o.atol, o.atol, o.atol * 1e3, o.atol * 1e3];

  // One DP step of size h from y (k[0] must hold f(y)). Writes yNew and returns error norm.
  const step = (y: Vec, h: number): number => {
    for (let s = 1; s < 7; s++) {
      for (let i = 0; i < 4; i++) {
        let acc = y[i];
        const row = A[s];
        for (let j = 0; j < s; j++) acc += h * row[j] * k[j][i];
        tmp[i] = acc;
      }
      deriv(tmp, k[s]);
    }
    let errSum = 0;
    for (let i = 0; i < 4; i++) {
      let acc = y[i];
      let e = 0;
      for (let j = 0; j < 7; j++) {
        acc += h * B5[j] * k[j][i];
        e += h * E[j] * k[j][i];
      }
      yNew[i] = acc;
      errV[i] = e;
      const sc = atolV[i] + o.rtol * Math.max(Math.abs(y[i]), Math.abs(acc));
      errSum += (e / sc) ** 2;
    }
    return Math.sqrt(errSum / 4);
  };

  const trace: Trace | undefined = o.recordTrace
    ? { t: [], x: [], v: [], pBreech: [], pBase: [], pGauge: [], psi: [] }
    : undefined;

  const breechOf = (p: number) => (moving ? p * breechFactor : p);
  const baseOf = (p: number) => (moving ? p * baseFactor : p);
  const gaugeOf = (p: number, yy: Vec) => {
    if (!moving) return p;
    const totalVol = V0 + S * yy[1];
    const s = Math.min(1, gaugeVol / totalVol);
    return p * baseFactor * (1 + (C / (2 * phi1 * m)) * (1 - s * s));
  };

  let t = 0;
  let y: Vec = [0, 0, 0, 0];
  let h = 1e-8;
  const hMax = 2e-6;
  let shotStartTime = NaN;
  let burnoutX: number | null = null;
  // Peak tracking (three most recent samples around the max for parabolic refinement)
  let peak = -Infinity;
  let peakT = 0;
  let peakX = 0;
  let peakBase = -Infinity;
  let peakGauge = -Infinity;
  let prev1: [number, number] | null = null;
  let peakNeighbors: [[number, number], [number, number], [number, number] | null] | null = null;

  const histT: number[] = [];
  const histP: number[] = [];
  const record = (tt: number, yy: Vec) => {
    const p = pressure(yy);
    const pb = breechOf(p);
    histT.push(tt);
    histP.push(pb);
    if (trace) {
      trace.t.push(tt);
      trace.x.push(yy[1]);
      trace.v.push(yy[2]);
      trace.pBreech.push(pb);
      trace.pBase.push(baseOf(p));
      trace.pGauge.push(gaugeOf(p, yy));
      trace.psi.push(ff.psi(yy[0]));
    }
    if (pb > peak) {
      peak = pb;
      peakT = tt;
      peakX = yy[1];
      peakNeighbors = [prev1 ?? [tt, pb], [tt, pb], null];
    } else if (peakNeighbors && peakNeighbors[2] === null && peakNeighbors[1][0] === peakT) {
      peakNeighbors[2] = [tt, pb];
    }
    const bp = baseOf(p);
    if (bp > peakBase) peakBase = bp;
    const gp = gaugeOf(p, yy);
    if (gp > peakGauge) peakGauge = gp;
    prev1 = [tt, pb];
  };

  record(t, y);
  deriv(y, k[0]);

  let steps = 0;
  const tLimit = 0.05; // 50 ms — far beyond any real barrel time
  while (steps++ < o.maxSteps) {
    if (h > hMax) h = hMax;
    const err = step(y, h);
    if (!(err <= 1) || !Number.isFinite(err)) {
      const fac = Number.isFinite(err) ? Math.max(0.2, 0.9 * Math.pow(err, -0.2)) : 0.1;
      h *= fac;
      if (h < 1e-15) {
        messages.push('Integrator step size underflow.');
        return empty('invalid');
      }
      continue;
    }

    // Event: shot start
    if (!moving && pressure(yNew) >= p0) {
      let lo = 0;
      let hi = h;
      const y0: Vec = [y[0], y[1], y[2], y[3]];
      const k0: Vec = [k[0][0], k[0][1], k[0][2], k[0][3]];
      for (let it = 0; it < 40; it++) {
        const mid = 0.5 * (lo + hi);
        k[0][0] = k0[0]; k[0][1] = k0[1]; k[0][2] = k0[2]; k[0][3] = k0[3];
        step(y0, mid);
        if (pressure(yNew) >= p0) hi = mid;
        else lo = mid;
        if (hi - lo < 1e-13) break;
      }
      k[0][0] = k0[0]; k[0][1] = k0[1]; k[0][2] = k0[2]; k[0][3] = k0[3];
      step(y0, hi);
      t += hi;
      y = [yNew[0], yNew[1], yNew[2], yNew[3]];
      record(t, y);
      moving = true;
      shotStartTime = t;
      deriv(y, k[0]);
      h = Math.min(h, 1e-8);
      continue;
    }

    // Event: muzzle exit
    if (moving && yNew[1] >= L) {
      let lo = 0;
      let hi = h;
      const y0: Vec = [y[0], y[1], y[2], y[3]];
      const k0: Vec = [k[0][0], k[0][1], k[0][2], k[0][3]];
      for (let it = 0; it < 50; it++) {
        const mid = 0.5 * (lo + hi);
        k[0][0] = k0[0]; k[0][1] = k0[1]; k[0][2] = k0[2]; k[0][3] = k0[3];
        step(y0, mid);
        if (yNew[1] >= L) hi = mid;
        else lo = mid;
        if (hi - lo < 1e-14) break;
      }
      k[0][0] = k0[0]; k[0][1] = k0[1]; k[0][2] = k0[2]; k[0][3] = k0[3];
      step(y0, hi);
      t += hi;
      y = [yNew[0], yNew[1], yNew[2], yNew[3]];
      if (burnoutX === null && y[0] >= 1) burnoutX = y[1];
      record(t, y);
      break;
    }

    // Accept step
    const prevZ = y[0];
    const prevX = y[1];
    t += h;
    y = [yNew[0], yNew[1], yNew[2], yNew[3]];
    if (burnoutX === null && prevZ < 1 && y[0] >= 1) {
      const frac = (1 - prevZ) / (y[0] - prevZ);
      burnoutX = prevX + frac * (y[1] - prevX);
    }
    record(t, y);
    deriv(y, k[0]); // (DP is FSAL, but recomputing keeps event handling simple)

    if (!moving && y[0] >= 1) {
      messages.push('All powder burned before the bullet started to move (pressure never reached shot-start). Bullet stuck in bore / squib.');
      return { ...empty('stuck'), peakBreechPa: peak, peakBasePa: peakBase, peakGaugePa: peakGauge, burntAtMuzzle: 1 };
    }
    if (t > tLimit) {
      messages.push('Bullet did not exit within 50 ms; treated as stuck.');
      return { ...empty('stuck'), peakBreechPa: peak, peakBasePa: peakBase, peakGaugePa: peakGauge };
    }
    const fac = Math.min(5, Math.max(0.2, 0.9 * Math.pow(Math.max(err, 1e-10), -0.2)));
    h *= fac;
  }

  if (steps >= o.maxSteps) {
    messages.push('Integrator hit the step limit.');
    return empty('max-steps');
  }

  // Parabolic refinement of the peak breech pressure using its neighbours.
  let peakRefined = peak;
  let peakTRefined = peakT;
  const pn = peakNeighbors as [[number, number], [number, number], [number, number] | null] | null;
  if (pn && pn[2]) {
    const [[t1, p1], [t2, p2], [t3, p3]] = [pn[0], pn[1], pn[2]];
    const d = (t1 - t2) * (t1 - t3) * (t2 - t3);
    if (Math.abs(d) > 0 && t1 !== t2) {
      const a = (t3 * (p2 - p1) + t2 * (p1 - p3) + t1 * (p3 - p2)) / d;
      const b = (t3 * t3 * (p1 - p2) + t2 * t2 * (p3 - p1) + t1 * t1 * (p2 - p3)) / d;
      if (a < 0) {
        const tv = -b / (2 * a);
        if (tv > t1 && tv < t3) {
          const c = p1 - a * t1 * t1 - b * t1;
          const pv = a * tv * tv + b * tv + c;
          if (pv >= peak && pv < peak * 1.01) {
            peakRefined = pv;
            peakTRefined = tv;
          }
        }
      }
    }
  }

  // Barrel time from 10 % of peak breech pressure (linear interpolation on the recorded history).
  let t10 = NaN;
  const p10 = 0.1 * peakRefined;
  for (let i = 1; i < histP.length; i++) {
    if (histP[i] >= p10) {
      const a = histP[i - 1];
      const fr = histP[i] > a ? (p10 - a) / (histP[i] - a) : 0;
      t10 = histT[i - 1] + Math.min(1, Math.max(0, fr)) * (histT[i] - histT[i - 1]);
      break;
    }
  }
  const pM = pressure(y);
  const vM = y[2];
  const ke = 0.5 * m * vM * vM;
  return {
    status: 'muzzle',
    messages,
    peakBreechPa: peakRefined,
    peakBasePa: peakBase,
    peakGaugePa: peakGauge,
    timeOfPeakS: peakTRefined,
    travelAtPeakM: peakX,
    muzzleVelocityMs: vM,
    muzzleBreechPa: pM * breechFactor,
    barrelTimeS: t,
    travelTimeS: t - shotStartTime,
    barrelTime10S: t - t10,
    shotStartTimeS: shotStartTime,
    burntAtMuzzle: ff.psi(y[0]),
    burnoutTravelM: burnoutX,
    chamberVolumeM3: V0,
    loadDensityKgM3: C / V0,
    fillRatio,
    seatingDepthM: g.seatingDepthM,
    travelM: L,
    ballisticEfficiency: ke / chemEnergy,
    heatLossJ: y[3],
    trace,
  };
}
