// Method & limits: what the model does, what it ignores, data policy, safety.

import { DEFAULT_OPTIONS, STANTON } from '../engine/model';
import * as U from '../engine/units';

export function MethodTab() {
  return (
    <div className="card prose" data-testid="method">
      <h2>Method &amp; limits</h2>

      <div className="alert danger" role="note">
        <strong>Safety.</strong> ORKA is a simulation. It cannot see your rifle, your lot of powder or your components. Use published load data from the powder or bullet maker as your primary reference, start at their starting load, work up in small steps while watching for pressure signs, and never exceed published maximums on the strength of a prediction.
      </div>

      <h3 style={{ marginTop: 16 }}>The model</h3>
      <p>ORKA uses a lumped-parameter (“thermodynamic”) interior-ballistics model: the gas behind the bullet is treated as one volume with a Lagrange pressure gradient, integrated in time with an adaptive Dormand–Prince 5(4) solver.</p>
      <div className="eq-block">{`Free volume   Vf = V0 − (C/ρp)(1−ψ) − η·C·ψ + S·x
Energy        p·Vf = f·C·ψ + E_ig − (γ−1)·[ ½(φ1·m + C/3)·v² + Q ]
Motion        (φ1·m + C/3)·dv/dt = S·p
Lagrange      p_base = p/(1 + C/(3φ1·m)),  p_chamber = p_base·(1 + C/(2φ1·m))
Burn          dz/dt = β·(p/1 MPa)^n·(1 + κ·(T − Tref)),  ψ = χ·z·(1 + λz + μz²)
Heat loss     dQ/dt = scale·St·ρg·cp·(v/2)·(T − Tw)·A_wall`}</div>
      <ul className="small">
        <li>
          <span className="eq">V0</span> case capacity (water, to the mouth) minus the volume of the seated bullet (boat tail handled as a cone frustum). Water is converted with ρ = {U.WATER_DENSITY_G_PER_CM3} g/cm³ (20 °C).
        </li>
        <li>
          <span className="eq">S</span> bore area = π/8·(bore² + groove²), i.e. equal land and groove widths assumed.
        </li>
        <li>
          Travel = barrel length − (COAL − bullet length). Freebore jump and engraving profile are not modelled beyond a single shot-start pressure (default {Math.round(U.paToPsi(DEFAULT_OPTIONS.shotStartPressurePa)).toLocaleString('en-US')} psi).
        </li>
        <li>
          Secondary-work coefficient φ1 = {DEFAULT_OPTIONS.secondaryWorkCoeff}; primer modelled as an initial pressure of {Math.round(U.paToPsi(DEFAULT_OPTIONS.ignitionPressurePa)).toLocaleString('en-US')} psi; Stanton number St = {STANTON} in the Reynolds-analogy heat-loss term.
        </li>
        <li>The pressure compared with the limit is the chamber (breech-end) pressure, the closest model quantity to a SAAMI/C.I.P. piezo transducer.</li>
      </ul>

      <h3>What each output means</h3>
      <ul className="small">
        <li><strong>Peak chamber pressure</strong> — maximum breech-end pressure of the model, compared with the working limit (standard MAP × (1 − margin)).</li>
        <li><strong>Burnt at muzzle</strong> — fraction of the powder mass burnt when the bullet exits; low values mean a slow powder for this barrel and more velocity spread.</li>
        <li><strong>Fill ratio</strong> — bulk powder volume / space under the bullet (needs the powder's bulk density). Above 100 % means compressed.</li>
        <li><strong>Ballistic efficiency</strong> — bullet kinetic energy / chemical energy of the charge.</li>
        <li><strong>Sensitivity band</strong> — spread of results when inputs vary by the stated 1σ amounts. It is not a confidence interval on real pressure.</li>
      </ul>

      <h3>What the model ignores</h3>
      <ul className="small">
        <li>Pressure waves, ignition spread and position sensitivity of low fill ratios.</li>
        <li>Barrel-specific friction, throat erosion, chamber and bore dimensions beyond the nominal values you enter.</li>
        <li>Bullet jump, engraving force history and neck tension beyond the shot-start pressure.</li>
        <li>Lot-to-lot powder variation (only through the uncertainty band) and powder ageing.</li>
        <li>Primer brand differences, except through the primer pressure assumption.</li>
      </ul>

      <h3>Where the numbers come from</h3>
      <ul className="small">
        <li>Every shipped record carries its sources. Values nobody could source are left empty, never guessed.</li>
        <li>Powder burn models are labelled: <strong>calibrated</strong> (fitted to published pressure-tested data), <strong>my calibration</strong> (your data or parameters), <strong>estimate</strong> (interpolated from a burn-rate chart — not for load development) or <strong>no model</strong>.</li>
        <li>CUP and piezo psi are different measurement systems; ORKA never converts one into the other.</li>
        <li>How well the model matches published data is shown, with numbers, on the Validation tab.</li>
      </ul>
    </div>
  );
}
