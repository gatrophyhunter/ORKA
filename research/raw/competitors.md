# Competitor analysis: interior-ballistics / load-prediction tools

Research date: 2026-11-23. Prepared for ORKA (open-source handloading / interior-ballistics web app).

## 0. Method and evidence quality (read first)

- **No page could be opened in this session.** WebFetch failed with DNS errors for `grtools.de` and `forum.accurateshooter.com` (the session network allowlist blocks them), and per the tool's instructions no further hosts were tried. There was no web-fetch subagent available. GitHub repos outside this session's allowlist (e.g. `zen/grt_databases`) were also not readable.
- **Every fact below therefore comes from search-result text** that the search tool returned for the cited URL. Every source in the source list has `type: search-snippet`. A "publisher class" column says what kind of page it is (vendor documentation, retailer, forum, app store), but none of it was read in full.
- The search tool summarises results. Where a summary grouped several URLs and did not make clear which URL carried a given sentence, the claim is marked **[attribution uncertain]** and all candidate URLs are listed.
- The session's web-search budget ran out (shared limit of 200 calls). Items that would have needed more searching are listed in section 9 (Gaps).
- No value was filled from memory. Where a value was not found, it is written as **not found** (equivalent to `null`).
- Forum statements are anecdotes from individual users, not measurements. They are recorded as user reports, not as facts about the software.

---

## 1. Tools in scope

| Tool | Type | Status (as reported) | Platforms | Price / licence |
|---|---|---|---|---|
| Gordon's Reloading Tool (GRT), "classic" | Desktop interior-ballistics simulator | Original author died 2022; community team continues; development of powder models reported stalled by some users [S-T4, S-T5] | Windows 7 SP1/Vista/8.1/10 (32/64-bit); Linux x86/x86_64 with 32-bit GTK libs (cross-compiled, less tested) [S-G11] | Free; Patreon supporters get newer powder models more often [S-G15] |
| GRT NextGen | Rewrite by the GRT Discord group | Forum reports only: a build in Node.js on Electron existed by Dec 2024, "looks and works identical to GRT classic, but without all the wizzards and andvanced reporting, OBT, tables and the like" [S-T15]; another post said it was "on track for release EOY 2024 (Windoz, macOS, Linux)" [S-T16]. No official release announcement found. | Planned Windows/macOS/Linux [S-T16] | not found |
| QuickLOAD (+QuickTARGET) v3.9 | Desktop interior-ballistics predictor (+ exterior) by Hartmut G. Brömel | Still sold with a data update dated 4 Oct 2025 [S-Q2] (but see conflict C6) | Windows only; Win 7 to 11 for v3.6+ [S-Q1]; ARM Windows 11 not supported [S-Q4]; Mac only via Windows emulation [S-Q2] | GBP 139.00 (quickload.co.uk) [S-Q2]; USD 174.95 (NECO) [S-Q4]; data-update download USD 18.95 (NECO) [S-Q2b] |
| ApexLOAD PRO (xxlreloading.com) | Web-based internal-ballistics calculator with parametric powder search | Launched 3 Dec 2025 [S-O2] | Browser ("fully web-based application accessible from any device") [S-O2]; companion mobile app ApexLOAD FIELD (iOS/Android) [S-O6] | USD 34.50 / year, no one-time fee [S-O3]; 5 free calculations before a licence is needed [S-O2] |
| Reload Swiss "Precise Load" | Browser simulator for Reload Swiss powders | Live; "continuously being expanded" [S-O1] | PCs, Macs, tablets, smartphones [S-O1] | not found |
| Strelok Internal Ballistics (formerly "Strelok Reload" / "Strelok QuickLoad") | Mobile interior-ballistics predictor | Live on App Store and Google Play (Play listing updated Sep 14 2026 US / 7 Oct 2026 AU) [S-O7] | iOS, Android [S-O7, S-O8] (see conflict C9) | Free tier incl. prediction engine; Pro (subscription or lifetime) adds chrono calibration, "Load Lab" analytics, cloud sync [S-O8]; Nigerian store: Lifetime NGN 79,900.00, Yearly NGN 69,900.00 [S-O9]; USD price not found |
| LoadOut Ballistics & Reloading | iOS reloading app with a "pressure and velocity predictor" in Pro tier | Live [S-O10] | iOS (Android listing seen only on third-party sites) | Pro tier; price not found [S-O10] |
| BBT "P-Max" | Browser interior-ballistics simulator | Live at time of forum threads; "free at the point of use" per author [S-O11] | Browser [S-O11] | Free at point of use [S-O11] |
| Freebore (iOS) | App claiming "pressure, velocity, and case fill predictions for over 1,000 Hornady and Sierra bullets" [S-O13] | Listing only | iOS | not found |

**Excluded (not interior ballistics / not load prediction):** Hornady 4DOF (exterior only, per task); RCBS .Load — sellers describe it as trajectory + reloading database; a forum user says "RCBS is just exterior ballistics"; listed as "No Longer Available" at OpticsPlanet [S-O14, S-O15]. Hornady and Sierra reloading apps are published-data apps, not predictors (no source checked in depth).

---

## 2. Gordon's Reloading Tool (GRT) — features

All official GRT statements come from the grtools.de DokuWiki (search snippets only). Some pages were shown by the search tool as about 470 days (≈1.3 years) to 1,900 days old.

### 2.1 Model and outputs
- **Burn model:** "three-step representation of the burn-up behavior which accounts for multi base propellant behaviors and partially for additives, such as anti-copper-fouling and temperature stabilizers" [S-G4]. Burn-up is handled by "form functions" fitted to closed-vessel measurements, then calibrated against ballistic data [S-G4]. GRT cites Kneubuehl "Ballistik – Theorie und Praxis" and Rheinmetall "Waffentechnisches Taschenbuch" [S-G4]. The equations themselves were not in the snippets (not found).
- A forum user contrasts "QL is a 2-point curve and GRT is a 3-point curve" [S-T11, attribution uncertain].
- **Outputs (results window):** maximum pressure, muzzle pressure, projectile energy, muzzle velocity, bullet transit time (ignition until projectile leaves barrel), share of powder burnt before exit, and an "effective efficiency" comparing muzzle kinetic energy with the theoretical energy of the charge [S-G12].
- **Primer:** no primer input field; users calibrate via "Initial Pressure (IP)" and/or the OBT tool. IP is documented as covering shot-start pressure, groove press-in pressure, pull-out resistance, primer type, powder variations and other tolerances [S-G19].

### 2.2 Pressure-limit handling
- Caliber data comes largely from CIP [S-G10]; a forum user says caliber data comes from SAAMI or CIP [S-T6].
- The "max allowed pressure" field is set by the selected caliber and the docs advise not to edit it, because it drives the Pmax thresholds and warning zones on the diagram [S-G10].
- Diagram bands: **Pmax and above; Pmax to Pmax-15%; Pmax-15% to Pmax-25%** [S-G10]. GRT defines **PK = Pmax + 15%** (max allowable single statistical pressure) and **PE = Pmax + 25%** (mean impingement pressure) [S-G10].
- Warnings: text is highlighted if the -15% limit or Pmax is exceeded [S-G10]. A user reports the message "Working pressure close to the maximum permissible gas pressure!" and that raising the temperature pushes a load into the warning zone [S-T10].
- Caveat in GRT's own docs: depending on tolerance windows and powders, charges produced by the search tool "can exceed the specified maximum pressures"; the FAQ recommends starting development at -25% Pmax or below [S-G10].

### 2.3 Parametric powder search (how it works)
- Finds powders **similar to the currently selected (base) powder**, within user-set tolerance windows on individual powder parameters [S-G2].
- One button selects the maximum range; per-factor sliders narrow it; matches appear at the bottom of the list [S-G2].
- Leaving the **minimum loading ratio** blank makes the "Generic Tolerance Synthesis" much slower, especially for long-gun calibers, because many internal-ballistics calculations run per candidate powder [S-G2].
- Companion "relative burning rate table" is described by GRT itself as only a rough cross-manufacturer overview: same-level powders are not 1:1 substitutes and it says nothing about pressure behaviour [S-G3].

### 2.4 Calibration with chronograph data
- Chronograph imports: MagnetoSpeed, Caldwell, ProChrono, LabRadar [S-G1]; LabRadar data also gets a "tracking analysis diagram" [S-G15].
- PressureTrace II (RSI) pressure-curve overlay on the simulation diagram [S-G1, S-G7].
- Users describe entering chronograph readings in a "measurements" tab and recommend about five velocity measurements for the same load [S-T6].
- Users describe tuning Ba and other factors via the OBT tool to match measured velocity [S-T24 and the Ba-tuning search; attribution uncertain].
- Shot group analysis tool [S-G1, S-G15].

### 2.5 Powder-model development process (provenance)
- Powder values come largely from **manufacturer measurement data, supplemented by GRT lab and community measurements**; model values "can differ slightly" from published manufacturer figures [S-G5].
- Each powder in the propellant DB has a **calibration progress bar**; red means the model "urgently requires real-life measurements" [S-G5].
- When a manufacturer will not supply data, GRT "reverse engineer[s] the powder and build[s] a new model from User and GRTLab collected data" [S-G8]. "Many (mostly European) manufacturers are willing to collaborate, but unfortunately several not" [S-G8].
- New powder requires a **2x2x2x5 development run**: 2 calibers × 2 bullet weights × 2 charges (start, max) × 5 shots [S-G6]. Shoot over "a good chronograph like a MagnetoSpeed or LabRadar"; ProChrono "not consistent enough" [S-G6].
- Submissions go through the **GRTLab plugin** as `.grtload` files; velocities only, or velocities and pressures; each file is "reviewed by our team manually" and "This does NOT mean that automatically any user measurement influences a powder model!" [S-G7].
- Development and maintenance are **scheduled**, because "the Patreon coverage, and the voluntary personal time, is somewhat limited" [S-G8, S-G5].
- GRT says QuickLOAD powder values are **incompatible** and copying them "will very likely produce wrong results" [S-G22].
- A third-party video channel (The Reloaders Network) explains GRT powder-model development and asks viewers to submit measurement data [S-T2].
- Powder vendor Reload Swiss publishes its own GRT data file for its 14 powders ("not a download of the GRT software, but an addition to the Reload Swiss datasets") [S-T3].

### 2.6 Temperature
- Powder temperature (Pt) input [S-G13].
- Model uses a **cold coefficient (tcc)** and a **hot coefficient (tch)**: change in Ba between 21 °C and -20 °C (tcc) and between 60 °C and 21 °C (tch), each divided by the temperature span [S-G13].
- An assistant recalculates tcc/tch from the user's own measurements at different temperatures; a reference measurement at 21 °C / 70 °F is required [S-G14].
- If a powder has tcc = tch = 0.0000, **GRT-internal default values** are used [S-G13].

### 2.7 Seating depth / COAL / case capacity / barrel length / bullet base
- OAL is computed from case length, bullet length and seating depth [S-G10]. Deeper seating reduces the remaining combustion volume [S-G25].
- Projectile tail type "flatbase"/"hollowbase" affects combustion volume [S-G1].
- Docs stress measuring the **average interior volume of a fired case** in grains of water to a slightly convex brimful level [S-G10, S-G26]; database case volume and bullet length "must always be checked and measured" [S-G20].
- Case length field is pre-filled with the spec maximum; docs recommend replacing it with the user's own measurement [S-G10].
- Muzzle pressure and energy depend heavily on the barrel length entered [S-G12].
- Forum claims: GRT "does not account for chamber dimensions beyond the neck" (e.g. freebore) [S-T19, attribution uncertain]; in one user's report "GRT just leaves it [COAL jump] at a default of 0" [S-T14].
- Forum claim: "QL uses sized case volume and Gordon's uses fired/unsized - this drops the pressure a bit" [S-T9, attribution uncertain].

### 2.8 OBT / barrel time
- OBT nodes precalculated from barrel length in the cartridge file (German docs: barrel length and measured velocity) [S-G9].
- Compares nodes with predicted **Bullet Lead Time (BLT)**; calibrated BLT is taken at 10% of peak pressure; optional half-nodes; then "automatically calculates the powder charge which adjusts the calculated BLT-Time to the selected OBT node" [S-G9].

### 2.9 Reports, units, languages, other tools
- Printable, customisable results report; unit converter; per-field "ruler" toggle between metric and imperial; **decimal delimiter is always a dot, even in metric mode** [S-G17].
- Bullet weight in grains [S-G17]. Pressure-unit options (bar/psi) **not found**.
- Languages: Afrikaans, Czech, English, French, German, Italian, Polish, Russian, Ukrainian [S-G1]; built-in translation tool [S-G24].
- Other tools: black-powder calculator, effective bore cross-section calculator, cartridge designer [S-G1, S-G27]; plugin API, GRTLab and GRTrace plugins [S-G1].
- Universal Bullet Classification Scheme (UBCS) code per bullet (RFC v1.1b draft); "has no influence on the simulation" [S-G21].

### 2.10 Platforms, distribution, licence
- System requirements: 1080p, 100 MB disk, 1 GB RAM, Windows (7 SP1, Vista, 8.1, 10; 32/64-bit) or Linux x86/x86_64 with 32-bit GTK libraries; "only tested extensively with the recommended system" [S-G11]. GRT "is not developed under Linux… cross-compiled" [S-G23].
- Portable archive "GordonsReloadingTool-<version>"; update = back up, extract over the working folder; data auto-imported [S-G23].
- Free; governed by German law [S-G15, S-G16]. Patreon only partly covers costs; patrons get newer propellant models more frequently [S-G15].
- grtools.de reported "71,210 active users (78,018 total)" at the time the page was indexed [S-G15].
- Docs: online version is the reference; offline PDFs dated 2021-02-27 in one snippet and 2021-09-29 in another (conflict C3) [S-G24].

### 2.11 Database size and provenance
- **Counts of powders, bullets, calibers: not found** in any snippet.
- Projectile DB organised by manufacturer → diameter → product; fields: manufacturer, product name, caliber, diameter (mm), weight (grains), UBCS code, lot, creation/update date [S-G20]. "All measurements in the original database where either submitted by the respective manufacturer or measured by contributing hand loaders"; "no guarantee is given for the correctness of the data" [S-G20].
- Propellant DB: user-extensible; stored as XML; imports GRT-format XML only [S-G1, S-G22].
- Community GitHub repo `zen/grt_databases` collects calibers, projectiles, powder models and loads shared on Discord, with a no-responsibility disclaimer and a note that measurements must be verified [S-T1].
- Brass-brand-specific case capacities: **not found** for GRT.

---

## 3. QuickLOAD — features

### 3.1 Identity, version, price, platform
- Developer Hartmut G. Brömel; Windows; German and English; stable release 3.9; bundles exterior-ballistics program QuickTARGET [S-Q1].
- v3.9 sold with "the latest data update (4 October 2025)"; Windows 11 compliant; works on Mac only "with suitable software that will emulate Windows" [S-Q2]. Data updates "will only update the data in the bullet, powder and cartridge files" [S-Q3].
- NECO (US) listing: USD 174.95 [S-Q4]. **Disc only** "due to German ITAR copyright laws"; ARM-based Windows 11 machines "will NOT run the software"; data updates available as download (7-zip decrypt) or CD [S-Q4, S-Q5].
- Historic prices (older listings): USD 152.95 (NECO, c. 2014–2018), USD 149.95, GBP 125 UK reseller [S-Q7, attribution uncertain].

### 3.2 Database size and provenance (conflicting counts)
| Field | Value | Source |
|---|---|---|
| cartridges | more than 1200 | quickload.co.uk [S-Q2] |
| cartridges | over 1500 (retailer) | retailer listing in same search [S-Q6, attribution uncertain] |
| powders | more than 230 | quickload.co.uk [S-Q2] |
| powders | 250 | listing describing v3.9 "current through January 2018" [S-Q6b, attribution uncertain] |
| powders | 270 ("precise data for 270 individual powders") | retailer [S-Q6, attribution uncertain] |
| powders | over 225 | Wikipedia-derived copy [S-Q1b] |
| bullets | more than 2500 | quickload.co.uk [S-Q2]; also Wikipedia-derived copy [S-Q1b] |
| bullets | 2100+ "Bullet data sets included as example" | older listing [S-Q7, attribution uncertain] |

- Provenance: forum users say powder data must come from the powder's actual manufacturer before it can be added [S-Q21]; QuickLOAD powder parameters (heat of explosion, ratio of specific heats, Ba, a0, z1, b, solid density, load density at 100% fill) are user-editable and users reverse-engineer missing powders (e.g. LT-30/LT-32 from A2015) [S-Q20].
- Known data errors acknowledged by the program's own readme (Scribd copy): "Vihtavuori N 150 powder data adjusted - now faster. Old data too slow and measured pressure up to 20% higher than calculated !" (QL 3.1) [S-Q19].
- Case capacity: one cartridge (.300 Win Mag) entry has 5 different case capacities for 5 case manufacturers; but users report the .308 default "doesn't differentiate between 308 brass" (56.0 gr water to overflow) [S-Q25, attribution uncertain]. Default capacities "may be off half a grain (or more)" [S-Q11].
- Bullet data: a user reported an incorrect bullet length for the Hornady 140 gr A-Max .264 in QuickLOAD; another post disputed it [S-Q26].

### 3.3 Prediction outputs, pressure limits, parametric powder search
- Estimates chamber (peak) pressure, muzzle velocity, muzzle pressure [S-Q1]; output tables show charge, velocity, energy, peak pressure, % powder burnt, barrel time, filling/loading ratio, muzzle pressure, with warnings such as figures exceeding max/min recommended loads [S-Q8 and Nosler forum examples].
- **Propellant Table** (the QuickLOAD analogue of a parametric powder search), per a user guide: user sets a nominal maximum pressure and a case-fill target; burn-rate sliders at their extremes search all powders; results sorted by velocity; QL also "suggests popular powders" for the cartridge; powders producing a loading ratio below a user-defined minimum (e.g. 90%) are skipped [S-Q8].
- "Similar powders" workflow: Ba min/max sliders to bracket powders similar to a reference powder, then compare fill ratio and % burnt [S-Q9]; a reply asks whether non-US powders can be filtered out [S-Q9].
- Users trim the powder list by deleting entries from the powder data files in `QuickLOAD\data\powders` with a text editor [S-Q10].
- Pressure-limit provenance: Wikipedia text says CIP/SAAMI standards appear in defaults [S-Q1]; the exact mechanism **not found**.

### 3.4 Calibration with chronograph data
- **No automatic calibration found.** Users iterate Ba by hand until predicted velocity matches the chronograph average [S-Q27, S-Q14]; Chris Long's method adjusts the weighting factor before Ba [S-Q29, attribution uncertain].
- Reported problems: burn rate "changed with pressure", so users avoid extrapolating across charge weights [S-Q14]; matching multiple bullet weights requires Ba changes [S-Q13]; a bullet change plus charge increase needed ~7% burn-rate increase; another user needed +7.8%; a forum guideline of "no more than 5%" Ba change [S-Q31, S-Q29, attribution uncertain].
- "Weighting factor" for case shape: users cite 0.5 bottleneck, ~0.33 overbore, ~0.75 cylindrical [S-Q28]; 0.4 for 6mm Dasher [S-Q11].
- Shot-start pressure must be changed by hand when bullets are jammed into the lands; per Berger article the program's creator agreed [S-Q12].

### 3.5 Temperature, seating depth, barrel length, OBT
- Predicts effect of ambient temperature, seating depth and barrel length [S-Q1]; default load temperature 70 °F [S-Q11].
- Temperature criticism: one user says it is "worthless for predicting temperature sensitivity", assumes a positive slope for all powders, and predicts linear curves while measured response is not linear [S-Q16]; temperature coefficient not constant across calibers [S-Q17].
- OBT: users say QuickLOAD has no dedicated OBT feature; it reports barrel time "from 10% Pmax to the muzzle", which users compare manually with Chris Long's node tables [S-Q18].

### 3.6 Accuracy claims
- **No numeric accuracy claim from the developer found.** Wikipedia: "merely a computer simulation"; double- or triple-check against powder-maker data [S-Q1].
- Reload Swiss offers QuickLOAD calculations on request as "starting points" [S-Q30].

---

## 4. Other current tools (interior ballistics only)

### 4.1 ApexLOAD PRO (xxlreloading.com)
- Internal-ballistics calculator modelling chamber pressure, muzzle velocity, powder burn [S-O2].
- **Parametric Powder Search** filtering by fill ratio, pressure limits and velocity targets; **Target Velocity Calculator** (incl. subsonic); trajectory calculator; OBT calculator; "NextGen" tool for choosing bullets/recipes [S-O2].
- Component DB (bullets, calibers, powders) updates "almost daily" [S-O2]; counts **not found**.
- Built because "neither currently maintains or updates bullet, powder, or caliber data" in QuickLOAD and GRT (vendor's claim) [S-O4].
- Declines highly compressed loads: predicting them "requires experimental pressure testing, not purely mathematical modeling" [S-O5].
- Model, calibration method and validation: **not found**. Only vendor and promotional sources; a blog commenter asked whether it was tested with live loads (no answer seen) [S-O2 comments via search].

### 4.2 Reload Swiss Precise Load
- Browser tool for Reload Swiss powders; gas pressure, muzzle velocity, bullet energy; integrated exterior ballistics [S-O1].
- **Only published quantitative validation found among all tools:** "verified with 8,500 measurement data sets… at maximum pressure, the deviation was less than 290 bar in more than two-thirds of cases, and at speed, the deviation was less than 26 m/s in more than two-thirds of cases" (vendor claim) [S-O1].

### 4.3 Strelok Internal Ballistics (mobile)
- Predicts muzzle velocity, peak chamber pressure and case fill across the charge range; plots against SAAMI/CIP maximum with an over-pressure warning zone [S-O7].
- Engine "fit to 34,000+ published loads" across 519 cartridges and 100+ powders, normalised from Hodgdon, Vihtavuori, Alliant and Norma data; runs on-device [S-O7].
- Chrono calibration ("engine tunes itself to your barrel and powder lot") and automatic velocity-node / lowest-spread finder; calibration is in the paid Pro tier [S-O7, S-O8].
- Disclaimer: "not a maximum-charge authority"; predictions are "a development aid, not published load data" [S-O7, S-O8].

### 4.4 LoadOut Ballistics & Reloading (iOS)
- Pro tier includes "the pressure and velocity predictor", Garmin chronograph import, structured load development, encrypted cloud sync; states predictions "are estimates, not load data" and that no LoadOut server sees reloading data [S-O10]. Model not documented (not found).

### 4.5 BBT P-Max (browser)
- Online, free at point of use; at launch only Reload Swiss RS powders and "a couple of Vihtavuori powders"; author says manufacturers are reluctant to release closed-bomb data [S-O11].
- Expects measured case capacity behind the loaded bullet; pressures rise faster than QuickLOAD near full case; author tuned the powder model to velocity, not pressure, and "would rather overstate pressure than understate it" [S-O11]. Users question its pressures vs the Vihtavuori manual [S-O11, S-O12].

---

## 5. Documented accuracy claims (summary)

| Tool | Claim | Source |
|---|---|---|
| GRT | Deviation ≤5% "very good", <10% "good/satisfactory"; for rifle cartridges ≤3% before calibration "excellent"; "Expecting a simulation to be spot on, or at least 99.5% accurate without calibration, in every instance, is to be discouraged." Lists variation sources: loading/tool variation 1.5% or more, chronograph accuracy up to 5%, primer 1–2% | [S-G18] |
| QuickLOAD | No numeric claim found; only "computer simulation" disclaimers | [S-Q1] |
| Reload Swiss Precise Load | 8,500 data sets; >2/3 of cases within 290 bar (Pmax) and 26 m/s (velocity) | [S-O1] |
| Strelok IB | Engine fit to 34,000+ published loads; no error figure | [S-O7] |
| ApexLOAD PRO | not found | — |

User-reported accuracy (anecdotes):
- GRT: "37%" discrepancy for one user's cartridges [S-T8]; ~80 fps slower than measured [S-T23]; "within 3-5%" untuned across 9 bullets/powders [S-T19, attribution uncertain]; "nearly right on" [S-T22]; one load within 15 fps [S-T15 result set, attribution uncertain]; overpredicts pressure vs QuickLOAD for Accurate #5 [S-T8/S-T9, attribution uncertain]; predicted 2400 fps vs user's ~2700 fps estimate, and a suggested load "way over the max value from the powder manufacturer" [S-T14].
- QuickLOAD: suggests charges "as much as 8 grains" above what the user could run; .300 WSM light bullets off by "200 fps +-50 fps"; subsonic 300 BLK off by 200 fps; results "way off" after a component-file update [S-Q15]. N150 pressure up to 20% higher than calculated (readme) [S-Q19].

---

## 6. Recurring user complaints and limitations (with threads)

### GRT
1. **Development stalled / uncertain future** after the author's death (Jan 2022 per a forum quote of the official site; see conflict C1): "GRT powder development is essentially stalled due to Gordon's passing" [S-T5]; download reportedly withdrawn "as it is no longer being developed, and hence may have security flaws" [S-T4]; updates expected to end [S-T14].
2. **Powder coverage gaps:** H4198 and IMR 4198 (and ADI equivalent) missing [S-T12]; an older post said no Winchester, Hodgdon, IMR, Ramshot, Alliant or Western powders [S-T13, attribution uncertain]; users asking for Ramshot Grand data [S-T26]; users fetch powders from Discord into their user DB [S-T12].
3. **Prediction errors** (see section 5) and pressure over-prediction vs QL [S-T8, S-T9].
4. **Calibration = fudging:** "people seem to adjust the burn-rate and pressure inputs to match the prediction" — user asks whether that is sound [S-T21].
5. **Default case capacity sometimes inaccurate** [S-T7].
6. **Linux / Mac:** Linux install "is not a simple matter", Wine workaround [S-T17]; built for an old Mint version, support via Discord [S-T18]; written for 32-bit [S-T4]; no Mac build for classic (not found).
7. **Patreon tiering:** patrons get newer powder models earlier [S-G15]; one user won't sponsor until accuracy improves [S-T8].
8. **Support only via Discord** [S-T18, S-G15].
9. **NextGen regressions:** reported as lacking wizards, advanced reporting, OBT and tables [S-T15].

### QuickLOAD
1. **Windows-only, disc-only, dated distribution:** disc due to "German ITAR"; ARM Win11 unsupported [S-Q4, S-Q5]; Win 11 install problems (desktop icons, 25H2 needs AV off / offline) [S-Q4, S-Q5, S-Q22]; Mac/Linux only via CrossOver with font/tooltip bugs [S-Q23]; "no longer up-to-date in terms of operation and interface" [S-Q24].
2. **Paid data updates and lag for new powders:** RL26 missing in v3.6; "on new powders you are kind of stuck until the update comes out if it comes out at all" [S-Q21].
3. **Generic case capacities and bullet-length errors** [S-Q11, S-Q25, S-Q26].
4. **Manual, single-factor calibration** that does not hold across charge weights or bullet weights [S-Q13, S-Q14, S-Q27].
5. **Temperature model** criticised as linear, positive-slope for all powders [S-Q16, S-Q17].
6. **No OBT feature**; barrel-time reference (10% Pmax) debated [S-Q18].
7. **Large errors for non-traditional loads** (subsonics, light bullets in short magnums) [S-Q15].

### Newer tools
- ApexLOAD PRO, Strelok, LoadOut: no independent validation found; all accuracy statements are vendor marketing [S-O2, S-O7, S-O10].
- P-Max: tiny powder library, pressures disputed [S-O11, S-O12].

---

## 7. Conflicts recorded (do not resolve silently)

| ID | Topic | Value A | Value B |
|---|---|---|---|
| C1 | GRT author death date | Jan 19 2022 (forum post quoting official site) [first GRT discontinuation search, attribution uncertain, S-T4 thread set] | "March" (another poster, same result set) |
| C2 | GRT download needs account? | "no registration needed" (grtools.de) [S-G15] | "you do have to create an account before you can download" (forum) and "register and download" (Reloaders Network summary) [first GRT search, attribution uncertain; S-T2] |
| C3 | GRT offline PDF manual date | 2021-02-27 [S-G24] | 2021-09-29 [S-G24 variant `grtools:docs`] |
| C4 | GRT price | free [S-G15] | "no longer free" (single forum comment) [S-T4 result set, attribution uncertain] |
| C5 | Can QuickLOAD powder data be used in GRT? | "files can be imported, but results won't match exactly" (SnipersHide user) [S-T11] | "incompatible… will very likely produce wrong results" (GRT FAQ) [S-G22] |
| C6 | Is QuickLOAD still sold / maintained? | v3.9 sold with 4 Oct 2025 data update [S-Q2]; NECO lists USD 174.95 [S-Q4] | "currently no longer for sale" and "no longer up-to-date" (XXL review) [S-Q24]; "neither currently maintains or updates… data" (XXL, competitor) [S-O4] |
| C7 | QuickLOAD powder count | >230 [S-Q2] | 250 [S-Q6b]; 270 [S-Q6]; >225 [S-Q1b] |
| C8 | QuickLOAD data-update cadence | "typically every 2 or 3 months" | "annually" (both quickload.co.uk pages) [S-Q3] |
| C9 | Strelok Android availability | Google Play listing live, updated Sep/Oct 2026 [S-O7] | APKPure shows "Coming Soon" [S-O8 result set] |
| C10 | Strelok age rating | 13+ (App Store) | 17+ (Android) [S-O8 result set] |
| C11 | Case-volume convention | GRT: fired case [S-G10]; forum: "QL uses sized case volume" [S-T9] | P-Max expects capacity behind loaded bullet [S-O11] — three tools, three conventions |
| C12 | xxlreloading.com older pricing | USD 19.90/yr + USD 10 setup | EUR 24.90/yr + EUR 10 setup [S-O3 result set] (superseded by ApexLOAD PRO USD 34.50/yr) |

---

## 8. Requirements to beat them

Each requirement is concrete and testable, and tied to a cited gap.

1. **Runs everywhere, installs nowhere.** Browser app (PWA) that works offline after first load on Windows (x64 and ARM), macOS, Linux, iOS, Android. *Gap:* GRT is Windows/Linux-x86 only with 32-bit GTK and hard Linux installs [S-G11, S-T17, S-T18]; QuickLOAD is Windows-only, disc-only, no ARM Win11, Mac only by emulation [S-Q2, S-Q4, S-Q23]. *Test:* e2e suite passes in Chromium, Firefox, WebKit; prediction works with network disabled after first visit.
2. **Free core, no account required.** *Gap:* QuickLOAD GBP 139 / USD 174.95 plus paid data updates [S-Q2, S-Q4]; ApexLOAD USD 34.50/yr after 5 calculations [S-O2, S-O3]; GRT patrons get powder models earlier [S-G15]. *Test:* a full prediction, ladder and parametric search run without login; no feature gate on powder models.
3. **Standards-aware pressure limits with provenance.** Each cartridge stores CIP Pmax and SAAMI MAP as separate fields with source URL and measurement method; never auto-convert between them; show GRT-style bands (Pmax, -15%, -25%) plus PK/PE equivalents [S-G10]. *Gap:* GRT pulls one "max allowed pressure" mostly from CIP and tells users not to edit it [S-G10]; QuickLOAD's limit provenance is undocumented [S-Q1]. *Test:* every cartridge record has `pmax_cip_bar`, `map_saami_psi` (nullable) and `sources`; switching standard changes the warning band; any load over the selected limit is flagged red in table, chart, ladder, search results and exported report.
4. **Pressure-safe parametric powder search across all powders,** constrained by pressure limit, fill-ratio window, barrel length and COAL, ranked by velocity at the limit, showing fill %, % burnt at muzzle, barrel time and a confidence grade; plus a "similar to powder X" mode; filters by brand, country/availability and model confidence. *Gap:* GRT searches only for powders "similar to the base powder" and is slow if minimum loading ratio is blank [S-G2]; its own docs warn results can exceed Pmax [S-G10]; QuickLOAD needs slider tricks and hand-editing of data files to drop unwanted powders, and users ask for region filters [S-Q8, S-Q9, S-Q10]. ApexLOAD already filters by fill, pressure and velocity [S-O2] (parity required). *Test:* for a given cartridge/bullet/barrel, search over the full powder DB completes in under a fixed time budget in a mid-range browser; no returned candidate has predicted Pmax above the chosen limit; brand/country filter reduces the set correctly.
5. **Automatic multi-point calibration from chronograph data.** Fit burn-rate scale (and optionally shot-start pressure) to many shots across several charges and bullet weights by least squares; show per-charge residuals; refuse or flag extrapolation beyond the calibrated charge range. *Gap:* QuickLOAD calibration is manual Ba iteration that drifts with pressure and bullet weight [S-Q13, S-Q14, S-Q27]; GRT users "adjust the burn-rate and pressure inputs to match" [S-T21] and use IP as a catch-all [S-G19]. *Test:* synthetic data generated with known parameters is recovered within tolerance; predictions outside the calibrated charge range carry a visible warning.
6. **Chronograph file import** for LabRadar, MagnetoSpeed, Garmin Xero, Caldwell and ProChrono (CSV). *Gap:* GRT supports four brands [S-G1]; LoadOut advertises Garmin [S-O10]; QuickLOAD import not found. *Test:* sample files from each device parse into shot strings with correct units.
7. **Every prediction carries an uncertainty band.** Propagate input tolerances (case capacity, bullet length, charge, temperature) and powder-model fit error into ± intervals for pressure and velocity. *Gap:* GRT documents 3–10% typical deviation, chronograph error up to 5%, loading variation ≥1.5%, primer 1–2% [S-G18], but shows point values; user-reported misses of 80 fps to 37% [S-T23, S-T8] and 200 fps for QuickLOAD [S-Q15]. *Test:* each output field renders a value ± interval; the interval widens when the powder model is flagged low-confidence or when inputs are database defaults rather than measured.
8. **Powder-model provenance and confidence on every powder.** Show data source (manufacturer closed-vessel, published load data fit, user measurements), N data points, fit residuals (pressure and velocity), last-updated date and model version. *Gap:* GRT only shows a calibration progress bar [S-G5] and relies on reverse-engineering when makers do not cooperate [S-G8]; QuickLOAD shipped N150 data that under-predicted pressure by up to 20% [S-Q19]. *Test:* powder detail page lists `sources` with URLs and residual statistics; models below a minimum data threshold are labelled and excluded from "max charge" suggestions.
9. **Publish a validation report.** Hold-out comparison of predictions vs published manufacturer pressure/velocity data, per powder and overall, with the same style of metric Reload Swiss uses (share of cases within X bar and Y m/s) [S-O1]. *Gap:* QuickLOAD publishes no accuracy figure [S-Q1]; GRT gives only qualitative bands [S-G18]; Strelok says "fit to 34,000+ published loads" without error figures [S-O7]; ApexLOAD validation not found. *Test:* report page shows N, median absolute error and 67th/95th-percentile error for Pmax (bar and psi) and velocity (m/s and fps), regenerated by CI from the DB.
10. **Non-linear, per-powder temperature model** (at least separate cold and hot coefficients like GRT's tcc/tch [S-G13]), fittable from the user's multi-temperature chronograph data, and an explicit "temperature behaviour unknown" state instead of a silent default. *Gap:* QuickLOAD criticised for assuming positive linear slope for all powders [S-Q16, S-Q17]; GRT silently falls back to internal defaults when tcc/tch are 0 [S-G13]. *Test:* fitting a negative or flat slope from data is possible; powders without temperature data show the unknown state in the UI.
11. **Seating depth, jump and freebore as first-class inputs.** COAL and CBTO, bullet ogive/bearing length, jump-to-lands (positive or jam) and freebore length; shot-start pressure modelled as a function of jump; jam warning. *Gap:* GRT reportedly ignores chamber dimensions beyond the neck and leaves jump at 0 [S-T19, S-T14]; QuickLOAD requires manual shot-start changes for jammed bullets [S-Q12]. *Test:* changing jump from off-lands to jammed changes predicted shot-start and peak pressure in the documented direction; jam state is flagged.
12. **Brass-brand case capacities with explicit basis.** Store water capacity per brass manufacturer (and lot where known), marked fired/sized, in grains H2O with source; compute usable volume under the seated bullet; prompt the user to enter a measured value and show the difference. *Gap:* QuickLOAD defaults are generic and "may be off half a grain (or more)" [S-Q11, S-Q25]; GRT default capacity "sometimes inaccurate" [S-T7]; tools disagree on fired vs sized vs behind-bullet conventions (conflict C11) [S-G10, S-T9, S-O11]. *Test:* choosing a brass brand changes capacity; the field shows basis and source; usable volume updates when COAL changes.
13. **Barrel time with a stated reference point,** offering both "from shot start" and "from 10% Pmax" conventions, plus an OBT node helper with selectable node tables. *Gap:* QuickLOAD reports barrel time from 10% Pmax with no OBT feature [S-Q18]; GRT's BLT is at 10% of peak pressure [S-G9]; NextGen reportedly dropped OBT [S-T15]. *Test:* output labels the reference; both conventions agree with each other by the computed pre-10% interval.
14. **Maintained, open, versioned component database** (brass, powders, bullets, cartridges) with dated changelog and per-record `sources`; export/import as JSON/CSV. *Gap:* GRT powder development reported stalled [S-T5]; QuickLOAD new powders wait for paid updates "if it comes out at all" [S-Q21]; community GRT DBs carry no warranty [S-T1]; QuickLOAD bullet-length errors reported [S-Q26]. *Test:* every record has non-empty `sources`; changelog entries have dates; export → import round-trips identically.
15. **Coverage report against current manufacturer catalogues.** For each powder brand (incl. Hodgdon, IMR, Winchester, Accurate, Ramshot, Alliant, Vihtavuori, Norma, Reload Swiss, ADI, Shooters World, Lovex), list which current products have a model and its confidence. *Gap:* GRT users report missing H4198/IMR 4198, Ramshot Grand and (in an older post) whole US brands [S-T12, S-T26, S-T13]; Strelok covers "100+ powders" from four brands [S-O7]. *Test:* the report renders counts per brand and lists missing products by name.
16. **Explicit primer input** with a documented, bounded effect on ignition/shot-start and on the uncertainty band. *Gap:* GRT has no primer field (IP only; primer effect estimated 1–2%) [S-G19, S-G18]. *Test:* primer selection changes the uncertainty interval and is recorded in reports.
17. **Safety cross-check against published data.** When a published manufacturer load exists for the same components, show it beside the prediction and warn if the predicted or chosen charge exceeds the published maximum; flag compressed loads above a set threshold. *Gap:* users found GRT suggestions "way over the max value from the powder manufacturer" [S-T14]; QuickLOAD suggested up to 8 gr more than usable [S-Q15]; ApexLOAD declines highly compressed loads because they need pressure testing [S-O5]. *Test:* a seeded case where the prediction exceeds a published max triggers the warning in every view.
18. **Localisation and units per field,** including decimal-comma input in metric locales, bar/psi/MPa, grains/grams, mm/inches. *Gap:* GRT decimal delimiter is always a dot even in metric mode [S-G17]; QuickLOAD is German/English only [S-Q1]. *Test:* in a de-DE locale, "2,5" parses as 2.5; all unit toggles convert exactly and round-trip.
19. **Reproducible reports.** PDF/print and shareable link containing all inputs, units, model version and DB version hash, uncertainty bands and data sources. *Gap:* GRT has a printable report [S-G17] but NextGen reportedly lacks advanced reporting [S-T15]. *Test:* re-opening a shared report with the same versions reproduces the same numbers.
20. **Community data submission with review, not silent influence.** Users can submit chronograph (and pressure-trace) data; submissions enter a review queue and only change a published powder model after acceptance, with the change logged. *Gap/benchmark:* GRT's GRTLab manual review [S-G7] works but depends on a small volunteer team and Patreon [S-G8]. *Test:* a submitted dataset appears in the queue, does not alter predictions until approved, and the approved change appears in the changelog with its data count.

---

## 9. Gaps in this research (could not source)

- Total counts of powders, bullets and calibers in GRT's database (not in any snippet).
- QuickLOAD's exact equations, its official accuracy statement (manual not readable), and how its default max-pressure values are assigned per cartridge.
- QuickLOAD's current pressure units and unit options; GRT pressure-unit options.
- Whether QuickLOAD 3.9 accepts chronograph files; the "PVM-21 Chronograph" interface mentioned by a retailer could not be checked (search budget exhausted).
- GRT NextGen official release status in 2025–2026.
- ApexLOAD PRO model type, calibration method, database counts and validation.
- Strelok Internal Ballistics USD price; LoadOut Pro price and model.
- Brass-brand capacity coverage in any competitor beyond the QuickLOAD .300 Win Mag example.
- Full texts of every forum thread (only snippets seen).

---

## 10. Source list

All sources: `type: search-snippet` (no page was opened). "Class" is the publisher category of the underlying page. "Fields" lists what the snippet supports.

### GRT official documentation (grtools.de)
| ID | URL | Class | Fields |
|---|---|---|---|
| S-G1 | https://grtools.de/doku.php?id=grtools%3Aen%3Adoku%3Astart | vendor docs | feature list, imports, plugins, languages, XML DB |
| S-G2 | https://grtools.de/doku.php?id=grtools%3Aen%3Adoku%3Appsearch | vendor docs | parametric powder search |
| S-G3 | https://www.grtools.de/doku.php?id=en%3Adoku%3Aburnratechart | vendor docs | burn-rate table caveat |
| S-G4 | https://grtools.de/doku.php?id=en:doku:formalism | vendor docs | three-step model, form functions, closed vessel, references |
| S-G5 | https://grtools.de/doku.php?id=grtools%3Aen%3Adoku%3Adbpropellant | vendor docs | propellant DB, calibration bar, data sources, scheduling |
| S-G6 | https://grtools.de/doku.php?id=en:faq:faq-propelland-modeling | vendor docs | 2x2x2x5 run, chronograph recommendation |
| S-G7 | https://grtools.de/doku.php?id=en%3Aplugin%3Agrtlab%3Aplugin-grtlab | vendor docs | GRTLab submissions, manual review, PressureTrace II |
| S-G8 | https://grtools.de/doku.php?id=en:faq:faq-powderavailable | vendor docs | manufacturer collaboration, reverse engineering, scheduling |
| S-G9 | https://www.grtools.de/doku.php?id=grtools%3Aen%3Adoku%3Aobtconcept (also https://www.grtools.de/doku.php?id=de%3Adoku%3Aobtconcept) | vendor docs | OBT, BLT at 10% peak pressure |
| S-G10 | https://grtools.de/doku.php?id=grtools%3Aen%3Adoku%3Ainputfields-caliber (also https://www.grtools.de/doku.php?id=en%3Adoku%3Ainputfields-caliber) | vendor docs | CIP data, Pmax bands, PK/PE, case volume, OAL |
| S-G11 | https://grtools.de/doku.php?id=grtools%3Aen%3Adoku%3Ainstall | vendor docs | system requirements |
| S-G12 | https://grtools.de/doku.php?id=en:doku:outputfields | vendor docs | outputs, barrel-length dependence |
| S-G13 | https://grtools.de/doku.php?id=en:doku:inputfields-propellant | vendor docs | powder temperature, tcc/tch, defaults |
| S-G14 | https://grtools.de/doku.php?id=en:doku:assist-powdertempcoeff | vendor docs | temperature-coefficient assistant |
| S-G15 | https://grtools.de/ | vendor site | free, no registration, Patreon, user count, shot groups, LabRadar diagram |
| S-G16 | https://grtools.de/doku.php?id=de:doku:license | vendor docs | licence, German law |
| S-G17 | https://grtools.de/doku.php?id=en:doku:toolbar | vendor docs | report, unit converter, metric/imperial, decimal dot |
| S-G18 | https://grtools.de/doku.php?id=en:faq:faq-simaccuracy | vendor docs | accuracy bands, variation sources |
| S-G19 | http://grtools.de/doku.php?id=en:faq:faq-primer | vendor docs | no primer field, IP |
| S-G20 | https://grtools.de/doku.php?id=grtools%3Aen%3Adoku%3Adbprojectile | vendor docs | projectile DB fields, provenance, no guarantee |
| S-G21 | https://grtools.de/doku.php?id=en:doku:ubcs | vendor docs | UBCS |
| S-G22 | https://www.grtools.de/doku.php?id=en:faq:faq-qlpowder | vendor docs | QL data incompatible, GRT XML import |
| S-G23 | https://www.grtools.de/doku.php?id=grtools%3Aen%3Afaq%3Afaq-grt-update | vendor docs | portable archive, update process, cross-compiled Linux |
| S-G24 | https://grtools.de/doku.php?id=docs (also https://www.grtools.de/doku.php?id=grtools:docs) | vendor docs | manual languages, PDF dates |
| S-G25 | https://grtools.de/doku.php?id=en:doku:inputfields-projectile | vendor docs | seating depth, combustion volume |
| S-G26 | https://grtools.de/doku.php?id=en:faq:faq-bulkdensity | vendor docs | water-capacity method |
| S-G27 | https://grtools.de/doku.php?id=en:doku:cartridgedesigner | vendor docs | cartridge designer exists |

### Third-party pages about GRT
| ID | URL | Class | Fields |
|---|---|---|---|
| S-T1 | https://github.com/zen/grt_databases | community repo | community DB, disclaimer |
| S-T2 | https://www.thereloadersnetwork.com/author/gordons-reloading-channel/ | video channel page | powder-model development video, "register and download" |
| S-T3 | https://www.reload-swiss.com/en/simulation-tools/gordons-reloading-tool (also /en/loading-data/… and /en/load-data/…) | powder manufacturer | RS GRT data, 14 powders, "calculates gas pressure and V0" |
| S-T4 | https://www.thestalkingdirectory.co.uk/posts/3533185/ | forum | download withdrawn report, 32-bit, author death date |
| S-T5 | https://forum.accurateshooter.com/threads/gathering-data-for-powder-model-development-gordons-reloading-tool.4072119 | forum | development stalled, submission requirements |
| S-T6 | https://forum.nosler.com/goto/post?id=489493 | forum | measurements tab, ~5 velocities, SAAMI/CIP caliber data |
| S-T7 | https://forum.nosler.com/goto/post?id=489475 | forum | default case capacity sometimes inaccurate |
| S-T8 | https://purple.thefiringline.com/threads/gordons-reloading-tool.607465 | forum | 37% discrepancy, handgun within ~5% of QL, Patreon stance |
| S-T9 | https://www.snipershide.com/shooting/goto/post?id=9997803 (with https://snipershide.com/shooting/goto/post?id=9997652) | forum | fired vs sized case volume; pressure over-prediction (attribution uncertain) |
| S-T10 | https://forum.accurateshooter.com/threads/grt-and-working-pressure-graph.4151866 | forum | warning text, Pmax-15%, temperature |
| S-T11 | https://www.snipershide.com/shooting/goto/post?id=8319464 (with https://www.snipershide.com/shooting/goto/post?id=8185830) | forum | bomb data reluctance, 2-point vs 3-point, QL import claim (attribution uncertain) |
| S-T12 | https://www.canadiangunnutz.com/forum/threads/gordon-reloading-tool-powders-missing-from-database.2087269 | forum | H4198/IMR 4198 missing |
| S-T13 | https://www.canadiangunnutz.com/forum/threads/gordons-reloading-tool.2189161 | forum | "no American powders" (older post; attribution uncertain) |
| S-T14 | https://www.africahunting.com/threads/do-we-trust-gordons-reloading-tool.87291/ | forum | over-max suggestion, COAL jump default 0, 2400 vs 2700 fps |
| S-T15 | https://nzhuntingandshooting.co.nz/f10/gordon-reloading-tool-109244 | forum | NextGen Node.js/Electron, Dec 2024 |
| S-T16 | https://forum.accurateshooter.com/threads/grt-nextgen.4125683 | forum | NextGen planned platforms, EOY 2024 |
| S-T17 | https://www.nzhuntingandshooting.co.nz/f10/grt-linux-help-needed-117870 | forum | Linux install difficulty, Wine |
| S-T18 | https://www.snipershide.com/shooting/threads/linux-mint-vs-grt.7221195 | forum | compiled for old Mint, Discord support |
| S-T19 | https://forum.accurateshooter.com/threads/gordons-vs-quickload.4166498 (with https://forum.accurateshooter.com/threads/gordons-reloading-tool-vs-quickload.4013760) | forum | 3–5% untuned, 50 fps vs QL, no chamber dims beyond neck (attribution uncertain) |
| S-T20 | https://forum.accurateshooter.com/threads/grt-for-6-arc-load-development.4129938 | forum | measured velocity diverged "by quite a lot" |
| S-T21 | https://forum.accurateshooter.com/threads/grt-ql-question-s.4155735 | forum | users adjust inputs to match |
| S-T22 | https://forum.accurateshooter.com/threads/grt-numbers.4134343 | forum | "nearly right on" |
| S-T23 | https://longrangehunting.com/threads/gordon%E2%80%99s-reloading-tool.326351/page-2 | forum | ~80 fps slower than measured |
| S-T24 | https://forum.accurateshooter.com/threads/obt-using-gordons-reloading-tool-grt.4031317 | forum | built-in OBT calculator, barrel-time comparison |
| S-T26 | https://rokslide.com/forums/threads/gordons-reloading-tool-ramshot-grand.450260/ | forum | request for Ramshot Grand data (title only) |

### QuickLOAD
| ID | URL | Class | Fields |
|---|---|---|---|
| S-Q1 | https://en.wikipedia.org/wiki/QuickLOAD | encyclopedia | developer, Windows, languages, v3.9, limits, Win7–11, CIP/SAAMI mention |
| S-Q1b | https://wiki.riteme.site/wiki/QuickLOAD | encyclopedia mirror | >2,500 projectiles, >1,200 cartridges, >225 powders (Wikipedia-derived copy; attribution uncertain among mirrors) |
| S-Q2 | https://quickload.co.uk/products/option-1-quickload-includes-quicktarget-v-3-9-includes-the-latest-data-update-4th-october-2025/ (and https://www.quickload.co.uk/) | vendor | GBP 139, counts, Oct 2025 data, Win11, Mac via emulation |
| S-Q2b | https://www.neconos.com/quickload-ballistic-prediction-software/ | retailer | data update download USD 18.95 |
| S-Q3 | https://quickload.co.uk/faq/ | vendor | update scope, cadence conflict |
| S-Q4 | https://www.neconos.com/item/QuickLOADQuickTARGET-Ballistic-Prediction-Software-V3.9-3 | retailer | USD 174.95, disc only (ITAR), ARM unsupported, 25H2 install advice |
| S-Q5 | https://www.neconos.com/quickload-f-a-q-s/ | retailer FAQ | ITAR, 7-zip download, desktop-icon issue |
| S-Q6 | https://www.neconos.com/category/Software-2 | retailer | 270 powders, 1500+ cartridges (attribution uncertain) |
| S-Q6b | https://www.gunmart.net/ammunition/reloading/quickload-2 | magazine/retailer | 1200 cartridges, 250 powders, 2500 bullets, data through Jan 2018 (attribution uncertain) |
| S-Q7 | https://bulletin.accurateshooter.com/?p=12561 | blog | historic prices, 2100+ bullets, v3.9 through Jan 2018 (attribution uncertain) |
| S-Q8 | https://robrobinette.com/QuickLOAD.htm (and https://robrobinette.com/images/Reloading/QuickLOAD/QuickLOAD_Quick_Start_Guide.pdf) | user guide | propellant table workflow, burn %, capacity |
| S-Q9 | https://www.levergunscommunity.org/viewtopic.php?p=819398 | forum | similar-powder search with Ba sliders, region filter request |
| S-Q10 | https://forum.nosler.com/threads/using-quickload-tips-tricks.20241 (with https://forum.accurateshooter.com/threads/creating-a-new-powder-list-in-ql.3888587) | forum | editing powder files |
| S-Q11 | https://www.6mmbr.com/quickload.html | review/guide | weighting factor, capacity off ≥0.5 gr, 70 °F default |
| S-Q12 | https://bulletin.accurateshooter.com/2009/03/berger-tips-for-loading-vld-bullets/comment-page-1/ | blog | shot-start pressure for jammed bullets |
| S-Q13 | https://forum.accurateshooter.com/threads/quickload-calibration-can-you-get-it-to-match-multiple-bullet-weights.3746714 | forum | multi-bullet-weight calibration |
| S-Q14 | https://forum.accurateshooter.com/threads/calibrating-truing-quickload.4142080 | forum | burn rate changes with pressure |
| S-Q15 | https://longrangehunting.com/threads/quickload-way-off-from-reality-solutions.294389 | forum | 8 gr, 200 fps errors, update regression |
| S-Q16 | https://forum.accurateshooter.com/threads/temperature-sensitivity-of-8-powders-for-223-high-power-service-rifle.4043524 | forum | temperature-model criticism |
| S-Q17 | https://forums.accuratereloading.com/eve/forums/a/tpc/f/2511043/m/30510335 | forum | temp coefficient varies by caliber |
| S-Q18 | https://forum.accurateshooter.com/threads/quickloads-obt-feature.3970135 (with https://snipershide.com/shooting/threads/optimal-barrel-time-and-quickload.226338) | forum | no OBT feature, 10% Pmax barrel time |
| S-Q19 | https://www.scribd.com/document/459530673/readme-txt | user-uploaded vendor readme | N150 data 20% pressure under-prediction |
| S-Q20 | https://forum.accurateshooter.com/threads/quickload-reverse-engineering-powder-parameters-for-accurate-lt-30-and-lt-32.4052451 | forum | powder parameter set, reverse engineering |
| S-Q21 | https://www.longrangehunting.com/threads/rl26-quickload-help.167290 | forum | missing new powders, manufacturer data dependency |
| S-Q22 | https://forum.accurateshooter.com/threads/quickload-on-windows-11.4160940 | forum | Win11 install issues |
| S-Q23 | https://www.codeweavers.com/compatibility/crossover/forum/quickload-39 | compatibility forum | Mac/Linux via CrossOver, font/tooltip bugs |
| S-Q24 | https://www.xxlreloading.com/post/quickload-ballistics-simulation-program-review | competitor blog | "no longer up-to-date… no longer for sale" |
| S-Q25 | https://forum.nosler.com/threads/ql-question-case-capacities.33464 (with https://forum.accurateshooter.com/threads/quickload-300wm.3877054) | forum | per-manufacturer capacities, generic .308 default (attribution uncertain) |
| S-Q26 | https://bulletin.accurateshooter.com/?p=60816 | blog comments | bullet-length error claim and rebuttal |
| S-Q27 | https://www.ballisticstudies.com/Resources/Discussion+Forums/x_forum/17/thread/22927.html | forum | Ba tuning to chronograph |
| S-Q28 | https://forums.accuratereloading.com/eve/forums/a/tpc/f/2511043/m/1561073721 | forum | weighting-factor values |
| S-Q29 | https://www.tapatalk.com/groups/practicalriflerfr/quickload-help-wanted-t583.html (with https://www.snipershide.com/shooting/threads/fudging-quickload-to-match-real-life.19243) | forum | Chris Long weighting-factor-before-Ba method; Ba adjustment size reports (attribution uncertain) |
| S-Q30 | https://www.reload-swiss.com/en/about-us/tips-tricks/calculated-load-data | powder manufacturer | QL calculations as starting points |
| S-Q31 | https://forum.nosler.com/threads/quickload-questions-thread.30761/page-2 | forum | ~7% burn-rate increase after bullet change (attribution uncertain) |

### Other tools
| ID | URL | Class | Fields |
|---|---|---|---|
| S-O1 | https://www.reload-swiss.com/en/simulation-tools/precise-load | powder manufacturer | Precise Load features, platforms, 8,500-set validation |
| S-O2 | https://www.xxlreloading.com/post/update-regarding-apexload-pro | vendor | ApexLOAD launch date, tools, parametric search, 5 free calcs, DB updates |
| S-O3 | https://www.xxlreloading.com/pricing-access-options | vendor | USD 34.50/yr, companion apps |
| S-O4 | https://www.xxlreloading.com/post/introducing-quickload-pro | vendor | rationale (QL/GRT data unmaintained, vendor claim) |
| S-O5 | https://www.xxlreloading.com/post/why-we-do-not-offer-load-data-for-highly-compressed-loads | vendor | compressed loads need pressure testing |
| S-O6 | https://www.xxlreloading.com/post/apexload-field-your-ballistics-bench-soon-in-your-pocket | vendor | ApexLOAD FIELD mobile logging |
| S-O7 | https://play.google.com/store/apps/details?id=com.strelok.reload | app store | Strelok IB features, 34,000+ loads, 519 cartridges, 100+ powders, SAAMI/CIP chart |
| S-O8 | https://apps.apple.com/gh/app/strelok-quickload/id6781934024 | app store | iOS listing, tiers, disclaimers |
| S-O9 | https://apps.apple.com/ng/app/strelok-quickload/id6781934024 | app store | NGN prices |
| S-O10 | https://apps.apple.com/app/id6767068691 | app store | LoadOut Pro predictor, Garmin import, privacy |
| S-O11 | https://ukvarminting.com/topic/49695-new-bbt-p-max-internal-ballistics-program/ | forum | P-Max description, powder set, pressure behaviour |
| S-O12 | https://www.thestalkingdirectory.co.uk/goto/post?id=3090294 | forum | P-Max pressure doubts |
| S-O13 | https://apps.apple.com/us/app/freebore/id6818360828 | app store | Freebore claims |
| S-O14 | https://www.opticsplanet.com/rcbs-dot-load-99915.html | retailer | RCBS .Load discontinued (excluded tool) |
| S-O15 | https://www.longrangehunting.com/threads/rcbs-rcbs-load-reloading-software.354933/ | forum | "RCBS is just exterior ballistics" (excluded tool) |

Distinct cited source entries in this list: 101 (S-G: 27, S-T: 25, S-Q: 34, S-O: 15). Some entries group 2–3 closely related URLs from the same site/thread; they are counted once.
