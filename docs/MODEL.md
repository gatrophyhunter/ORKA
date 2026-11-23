# ORKA interior-ballistics model

ORKA predicts chamber pressure and muzzle velocity with a **lumped-parameter ("thermodynamic") model**, the same family of model used by QuickLOAD, Gordon's Reloading Tool (GRT), IBHVG2 and NATO STANAG 4367. This document states every equation, every default and where each comes from. Reference numbers `[n]` point to the reference list in `research/raw/physics.md`, and `[P-n]` to `research/raw2/physics-primary.md` where that file exists.

> **Read this first.** A model is not load data. ORKA's numbers depend on calibrated powder data, case capacity, bullet length and seating depth. Each of these can move peak pressure by more than 10 %. Always start from published load data and work up while watching for pressure signs.

## 1. State and equations

The state is integrated in SI units: `z` (burnt fraction of the web), `x` (bullet travel), `v` (bullet velocity) and `Q` (heat lost to the walls).

| Quantity | Equation | Notes |
|---|---|---|
| Free gas volume | `Vf = V0 − (C/ρp)(1−ψ) − η·C·ψ + S·x` | Noble-Abel covolume η; unburnt solid volume `C/ρp·(1−ψ)` [1][5] |
| Energy (Résal) | `p·Vf = f·C·ψ + E_ig − (γ−1)·[½(φ1·m + C/3)v² + Q]` | `p` is the space-mean pressure. The `C/3` term is the gas kinetic energy under Lagrange's assumption [8][14]. |
| Motion | `(φ1·m + C/3)·dv/dt = S·p` | Equivalent to `φ1·m·dv/dt = S·p_base` |
| Lagrange gradient | `p_base = p / (1 + C/(3φ1·m))`, `p_breech = p_base·(1 + C/(2φ1·m))` | [14][15] |
| Gauge pressure | `p_gauge = p_base·[1 + C/(2φ1·m)·(1 − s²)]`, `s = V(breech→gauge)/V(total)` | Lagrange distribution in the volume coordinate. The station defaults to C.I.P.'s 25 mm from the breech face [18]. |
| Burn rate | `dz/dt = β·(p / 1 MPa)^n·(1 + κ·(T − 21 °C))` | Vieille's law in vivacity form [25]. `κ` can differ above and below 21 °C [100][106]. |
| Form function | `ψ = χ·z·(1 + λz + μz²)`, `χ = 1/(1+λ+μ)` | `λ < 0` degressive, `λ > 0` progressive. Fitted per powder as an empirical form function, as QuickLOAD and GRT do [103][114]. |
| Heat loss | `dQ/dt = St·ρg·cp·(v/2)·(T − Tw)·Aw` | Reynolds-analogy (Nordheim-type) convective loss [60][61]; see §4 |
| Shot start | The bullet is held until `p ≥ p_shot-start` | Defaults are in §3 |

Integration uses an adaptive Dormand–Prince 5(4) scheme (relative tolerance 1e-7) with exact event location for shot start and muzzle exit. The peak is refined by a parabola through the surrounding steps. The test suite (`tests/engine.test.ts`) checks the following:
- The bullet-locked case reproduces the closed-form Noble-Abel closed-vessel pressure to 1e-6.
- Work done on the projectile equals its kinetic energy within 0.2 %.
- Tightening the tolerance 1000× changes peak pressure and velocity by less than 0.1 %.
- Pressure rises with charge, seating depth and powder temperature, and falls with case capacity.
- Calibration recovers known parameters from synthetic data.

### Which pressure is compared with SAAMI / C.I.P. limits

SAAMI's conformal transducer and C.I.P.'s drilled-case transducer both sit in the chamber [18][19][20]. They read the gas pressure at that station, which lies between base and breech pressure. ORKA reports three pressures:
- **breech pressure:** the highest of the three. It is the value compared with MAP and Pmax, so the check is conservative.
- **gauge-station pressure:** for .308-class loads it is typically 1–3 % below breech pressure.
- **base pressure:** never used for limits.

Calibration against published data fits the model's breech pressure to the published transducer readings. As a result the reported number and the limit are in the same terms.

**CUP is never converted to psi.** CUP and piezo psi are different measurement systems with no fixed conversion factor. Loads published in CUP contribute only their velocity to calibration.

## 2. Inputs that matter most

The Predict tab lists sensitivities for every load. For a typical .308 Win near maximum:

| Input change | Peak-pressure effect (order of magnitude) |
|---|---|
| +0.1 gr charge | +1 % |
| −1 % case capacity | +1–2 % |
| Bullet seated 0.010 in deeper | +1 % |
| +3 % powder burn rate (lot-to-lot) | +5–8 % |

Measure your own case capacity (fired, water to the mouth) and bullet length whenever you can. Database values are maker-published figures or third-party measurements, and the field shows which.

## 3. Defaults and priors (each overridable)

| Parameter | Default | Basis |
|---|---|---|
| Shot-start, jacketed lead-core | 25 MPa (3,626 psi) | Widely reported QuickLOAD default [50][150][151]. Inside the reported 24–44 MPa first engraving peak for 6.5–9.3 mm jacketed bullets [47]. |
| Shot-start, monolithic copper/brass | fitted (see `src/data/model-constants.json`) | Fitted to published loads relative to the jacketed reference; falls back to the OpenReloading default 35.3 MPa [48] when not fitted. |
| Shot-start, cast / plated lead | fitted (see `src/data/model-constants.json`) | As above; fallback 30 MPa [48]. |
| Primer (ignition) pressure | 5 MPa as initial energy `p·V` | Modelling choice for the starting state [36]; absorbed by calibration |
| Secondary-work factor φ1 | 1.05 | Classical weapons 1.05–1.20 [10]. No small-arms value is published. Calibration absorbs the difference. |
| Specific gas constant R | 0.37 J/(g·K) | M1: 919–924 J/g at 2447–2449 K [72][73]. M6: 947.5 J/g at 2570 K [70]. |
| γ | 1.25 | Between M6 (1.254) [70] and the hotter M30A1 (1.241) [77] |
| Impetus f, flame temperature | `Tv = 298 K + Q(γ−1)/R`, `f = R·Tv` | Uses the maker's published heat of explosion `Q` where available. Otherwise single-base 3,850 J/g (Reload Swiss RS line, 3,750–3,950 [78]–[82]) or double-base 3,906 J/g (Vihtavuori N5xx, 3,700–4,000 [85]). This is a prior. Calibration with pressure data refits `f`. |
| Covolume η | 1.0 cm³/g | "About 1 cc/g for most propellants" [5]. M1 1.105 [72], M30A1 1.041 [77]. |
| Solid density ρp | 1.6 g/cm³ | Conventional value. **Not yet sourced** (see docs/DATA.md open items). It only sets the volume of the unburnt grains. |
| Burn-rate exponent n | fitted per powder (prior 0.8) | No sourced small-arms value. Published load data constrain it (§4). 1 is the default for user calibrations with too little data. |
| Temperature coefficient κ | 0.0007 /K (generic) | Chosen so the model reproduces the published ~1 fps/°F rule of thumb [95][96][98] (script `scripts/tempcoeff.ts`). Not powder-specific. |
| Heat-loss Stanton number | 0.002 × scale | Model assumption with no sourced constant [§6 of the dossier]. Its structure follows the Reynolds analogy [60][61]. With this value, heat loss for a .308 load is about 12–16 % of chemical energy. That is within the 7–16 % rifle-like range reported in [69]. The per-powder `heatScale` absorbs the uncertainty. |

## 4. Calibration against published data

`scripts/calibrate-powders.ts` fits every powder that has published, pressure-tested loads. The main source is the Hodgdon 2025 Annual Manual, which covers Hodgdon, IMR, Winchester, Accurate and Ramshot. Reload Swiss's guide (pressures in bar), the Vihtavuori guide (velocities) and the Shooters World manual are also used.

- **Fitted parameters:** burn rate β, pressure exponent n, progressivity λ, and, where the data constrain them, energy (force) and heat-loss scale. Weak priors keep weakly identified parameters physical: force ±10 % of the class prior, heat ±40 %, n ≈ 0.8 ± 25 %, λ ≈ 0 ± 0.6.
  - *Why n is fitted:* with n fixed at 1, held-out pressure errors showed a strong bullet-weight trend. Light bullets were under-predicted by 20–40 % and heavy bullets over-predicted by 30–45 %. Fitting n removed the trend, and the fitted values cluster around 0.75–0.85.
- **Stages:**
  1. Fit powders on loads whose test-case capacity is published for that brand, using jacketed bullets only.
  2. With those powders fixed, fit the shot-start pressure of monolithic and cast/lead bullets relative to the 25 MPa jacketed reference, then infer an "effective capacity" for each (cartridge, case brand) with no published capacity.
  3. Refit every powder on all loads.
- **Validation:** leave-one-cartridge-out on cartridges whose capacity is published, training only on loads with published capacities, so no inferred quantity leaks into the test. Results, with breakdowns, are on the Validation tab.
- **Bullet lengths:** when the bullet maker publishes no length (Hornady and Sierra product pages publish none), calibration uses a log-linear estimate from bullets whose lengths are published. There are separate fits for pointed and blunt bullets, and each is used only if its leave-one-out error is at most 6.5 %. Estimated lengths are never shipped as data.

## 5. Powder models and their status

Every powder shows one of four statuses:
- **calibrated:** fitted to the maker's published, pressure-tested loads. The validation report shows how well the fit predicts *held-out cartridges*.
- **user-calibrated:** fitted to your chronograph data (Calibrate tab). This is best for your rifle, but only inside the charge range you measured.
- **estimated:** burn rate interpolated from the two nearest calibrated neighbours on a maker's relative burn-rate chart. Charts are ordinal, so the uncertainty band uses the interpolation error measured by re-estimating calibrated powders. **Not for load development.**
- **none:** no model. ORKA will not predict with it until you calibrate it or enter parameters.

## 6. What the model ignores

- Gas leakage, bullet jump and freebore effects on engraving, and a travel-dependent resistance profile. Shot start is a threshold.
- Barrel harmonics.
- Primer brand, and the propellant's position in the case.
- Non-ideal (virial) equations of state [3][4], and the sliver phase of multi-perforated grains.
- Erosion, fouling, chamber and bore tolerances, and throat wear.

Each of these is a reason real pressure can differ from the prediction. That is why predictions come with a sensitivity band and why published data comes first.
