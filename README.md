# ORKA Load Lab

Open-source **centerfire rifle** handload prediction: interior ballistics with pressure limits, a parametric powder search, calibration against your chronograph, and a component database where every value names its source. Handgun, shotshell, muzzleloader and rimfire data are deliberately left out; the build flag `ORKA_SCOPE=all` restores handgun data.

> **Safety.** ORKA is a simulation tool, not load data. Real pressure depends on your rifle, components and powder lot, none of which a model can see. Use published load data as your primary reference, start low, work up, and never exceed a published maximum because a prediction says it is safe.

## What it does

| Area | What you get |
|---|---|
| **Predict** | Peak chamber pressure compared with the SAAMI MAP or C.I.P. Pmax (stored separately, never converted from CUP), muzzle velocity and energy, % burnt at the muzzle, fill ratio, muzzle pressure, barrel time (from ignition and from 10 % of peak), efficiency, pressure/velocity curves, a temperature sweep, sensitivities and a Monte-Carlo sensitivity band |
| **Safety cross-checks** | The powder maker's published loads for the same cartridge, powder and bullet weight are shown beside the prediction, with a hard warning above the published maximum. Warnings also appear when a prediction extrapolates beyond the cartridges or charges a powder model was calibrated on. |
| **Ladder & solvers** | Charge ladder with rows over the limit or over the published maximum flagged; maximum charge at the pressure limit (or at the fill limit); charge for a target velocity |
| **Parametric powder search** | Every modelled powder is solved to the same pressure limit and fill window. Results are ranked by velocity, with burn completion, fill, muzzle pressure and model status. The search runs in a Web Worker. |
| **Calibrate** | Multi-point least-squares fit of a powder model to your chronograph velocities (and pressures, if you have them). Shows residuals and degrees of freedom; the fit is stored on your device. |
| **Database** | Cartridges, powders, bullets, brass and burn-rate charts. Each record links to its source document and shows the verbatim evidence line. Add your own components; import and export JSON/CSV. |
| **Validation** | Held-out accuracy against published pressure-tested data. Each powder is refitted without one cartridge and then predicts it. Plus model coverage per powder maker. |
| **Method & limits** | The equations, defaults and what the model ignores. See also [docs/MODEL.md](docs/MODEL.md). |

The app runs entirely in the browser: no account, no server, and no network requests after loading. It works offline once loaded. Your entries stay in local storage, and share links carry the load inside the URL fragment.

## Accuracy: read this before using predictions

Measured on published pressure-tested data the model never saw (leave-one-cartridge-out; **only .308 Win and .223 Rem could be tested this way**; see [docs/VALIDATION.md](docs/VALIDATION.md)):

- **Pressure error:** median **±12.7 %**, and 1 in 10 predictions is off by more than **±31 %**.
- **Bias:** on average the model reads **4.4 % low**, which is the unsafe direction.
- **Velocity error:** median 73 fps.

That is not accurate enough to develop loads from, and for other cartridges the error is simply unmeasured. ORKA shows this error on every prediction, sizes its uncertainty band from each powder's own fit, and puts the maker's published loads for your components beside every prediction.

## How it compares with GRT and QuickLOAD

These are verified differences, not claims of better accuracy. On accuracy ORKA is behind: GRT users report about 3 % with well-developed powder models (an unverified forum claim), while ORKA measures about 13 % held-out. ORKA's accuracy is whatever the **Validation** tab measures, and you can check it.

- **Provenance on every number.** Each cartridge, bullet and brass value links to the maker's or standard's document and the exact table line it came from. Each powder model states what it was fitted to and its residuals.
- **Uncertainty is shown.** Sensitivity bands and one-at-a-time sensitivities come with every prediction, and estimated powders carry the measured error of the estimation method.
- **Published-data guard rails.** The maker's maximum for your components is shown, and loads above it are flagged in every view.
- **Honest validation.** Held-out (leave-one-cartridge-out) error is published, not just in-sample fit.
- **Runs anywhere.** Browser or PWA on Windows, macOS, Linux, iOS and Android.

Where GRT and QuickLOAD are still ahead: powder models from closed-vessel measurements (ORKA fits published load data instead), years of community calibration, and features ORKA does not have yet (jump/freebore-dependent engraving, chronograph file import, barrel-harmonics/OBT tools). See `research/raw/competitors.md` for the sourced feature comparison.

## Data

See [docs/DATA.md](docs/DATA.md). In short:
- Values are **parsed from primary documents**: maker catalogs, the SAAMI and C.I.P. standards, and maker load manuals.
- **Verified by an independent re-check** of random samples.
- **Never filled from memory.** Where a document does not state a value, the field is empty and ORKA asks you for a measurement.

## Develop

```bash
npm install
npm run dev          # local dev server
npm test             # engine + UI-logic tests
npm run build        # static build in dist/
npx tsx scripts/build-data.ts          # rebuild src/data/db.json from research/raw2/
npx tsx scripts/calibrate-powders.ts   # refit powder models + validation report
```

Engine code is in `src/engine/` (SI units throughout; `units.ts` holds the exact conversions). The UI is in `src/ui/`. The data pipeline is in `scripts/`.

## License

MIT for the code. Component data belongs to its publishers and is cited per record. Check the publishers' terms before redistributing the database.
