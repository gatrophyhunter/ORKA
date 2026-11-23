# ORKA physics reference dossier: lumped-parameter interior ballistics for small arms

Compiled 2026-11-23 for ORKA, an open-source handloading and interior-ballistics web app. Version 1.

## 0. Read this first: provenance, access limits, how to use this file

- **Access limit (important).** WebFetch could not open any page from this session. The first two hosts tried (apps.dtic.mil and www.dst.defence.gov.au) failed with "host not in allowed network domains", and the tool said to stop trying other hosts. The session's web-search budget then ran out before all planned queries were run. **Every citation in this file is therefore based on search-result text (snippets and search-engine summaries) seen in this session, not on a full page that was read.** In section 12, each reference is typed `search-snippet`, together with the type the underlying source *would* have (manufacturer, standard, government, peer-reviewed or third-party). A later pass with page access can use that to decide what to re-verify first.
- **Safety status of numbers.** Every number below was "seen in a snippet" and has not been checked against the full document. No number may drive an ORKA pressure limit until a person, or an agent that can fetch pages, opens the cited page and confirms it.
- **Flags used:**
  - **[UNCERTAIN]** marks garbled OCR, ambiguous table columns, or a search summary that pooled several results so the claim cannot be pinned to one URL.
  - **[NOT SOURCED]** marks a standard definition or equation that the planned model uses but that no snippet seen in this session showed. It is kept so the plan stays readable, and it is *not* verified.
  - **[DERIVED]** marks a result worked out in this file by algebra or exact unit arithmetic from stated inputs. Each one shows its derivation and was checked numerically in this session. It is not a literature value.
- **Not in this file:** no value was filled in from memory, and no proprietary GRT or QuickLOAD powder data file was copied (section 9 describes only the parameterization).
- Citation markers [n] point to the reference list in section 12.

---

## 1. Equation of state: Noble-Abel with covolume

**Planned:** p·(V_free) = m_g·R·T, with V_free = V − η·m_g (η = covolume).

**Verified pieces**
- The Noble-Abel EOS is the van der Waals form with the intermolecular-attraction term dropped and only the covolume term kept: P(v − b) = RT, where b is the covolume, which accounts for the finite volume of the gas molecules [1].
- It is widely used for gun propellant gases. A DSTO technical note calls it "a simple and reasonably accurate equation of state for propellant gases at the high densities and temperatures experienced in guns" [2] [UNCERTAIN: attributed to the DTIC ADA454209 hit; the summary did not tie the quote to a URL]. A 2021 paper notes its use in both gun interior ballistics and rocket propulsion [4].
- In closed-vessel analysis the same EOS gives p_max = f·Δ/(1 − α·Δ), where f is impetus, Δ is loading density and α is covolume. The burnt fraction ψ(t) is recovered from measured p(t) under the assumption that f and α are constant [6].
- **Typical covolume:** "about 1 cc per gram for most propellants" (empirical) [5]. Specific values seen:
  - M1: 1.105 [73] and 1.106 [72]. Source [72] labels the unit "grams/cm3", which is evidently a unit-label error for cm³/g.
  - M30: 1.02962 cm³/g, used in an IBHVG2 study [77] [UNCERTAIN attribution].
  - M30A1: 1.041 cm³/g from BLAKE at 0.2 g/cc loading density [77] [UNCERTAIN: column pairing ambiguous].
- Impetus, covolume and ratio of specific heats are the main thermochemical parameters that interior-ballistics codes take from thermochemical codes such as BLAKE. BLAKE was derived from an earlier version of TIGER and is intended for gun propellants at chamber conditions [7].

**Where the plan is weak, and better-documented alternatives**
- A 1993 US Army report (Macpherson & Vladimiroff) states that the Abel-Noble form "is known to be not very accurate". It also needs a separately fitted covolume for each propellant, which adds an adjustable parameter. The report proposes a more accurate EOS that removes the per-propellant covolume [3].
- A first-order virial EOS is a viable alternative, at the cost of solving a nonlinear equation [4].
- **Recommendation for ORKA:** keep Noble-Abel as the default, because every public lumped code and both GRT and QuickLOAD use a covolume (GRT documents a covolume b [13]). Treat η as a per-powder fitted parameter close to 1 cm³/g [5], and record its provenance.

---

## 2. Energy equation (Résal form) and the secondary-work factor

**Planned:** p·[V0 + A·x − (C/ρp)(1−ψ) − η·C·ψ] = f·C·ψ − (γ−1)·[φ·m·v²/2 + E_heat], with φ = K1 + C/(3m).

**Verified pieces**
- Résal's equation is the energy balance of interior ballistics. A 1936 BRL report (R. H. Kent) writes it as three energy terms: energy delivered by the charge, projectile kinetic energy, and remaining work. It uses a *reduced (fictitious) projectile weight* that absorbs the kinetic energy of the powder gas **and the passive-resistance work** [9] [UNCERTAIN: Kent report attributed to the DTIC AD0733736 hit].
- A modified Résal equation (Bergmann, in Cranz) uses γ = 1.2 and a fictitious projectile mass M′ defined from projectile and charge masses [10]. The snippet did not show the formula.
- **One-third of the charge:** AMCP 706-150 (1965) uses an "adjusted projectile weight equal to the projectile weight plus one-third of the charge weight" in its treatment of Lagrange's problem [8]. A patent describing the common lumped-parameter Lagrange model gives the space-mean pressure as (1 + C/3m) × base pressure [14]. Both support the C/(3m) term in φ, because it is the gas kinetic energy under the Lagrange assumption.
- **Size of the work coefficient:** "for classical weapons varies between 1.05 and 1.20, depending upon the weapon" [10]. One large-calibre artillery paper uses 1.02 for large-calibre guns, in the form φ₁ = 1 + (K/3)(ω/m) with K a weapon-specific constant [11]. **No small-arms-specific K1 value was found [coverage gap].**
- **Energy terms to account for:** a small-arms review covers energy losses [56], and BRL Report 1183 lists heat loss to the gun as one of several energy-loss categories [57]. A related Army report on composite charges groups engraving of the rotating band, bore friction and projectile rotation as losses [149] [UNCERTAIN attribution]. GRT's model tracks the following terms [13]:
  - projectile translational and rotational energy;
  - gas flow energy, using a "Sebert factor" (a fraction of the charge added to the bullet mass to form an effective mass) rather than a fixed 1/3;
  - heat losses to tube, bullet and case;
  - gas losses, friction and acoustics;
  - pull-out work and recoil energy.
- A US Army field manual rule of thumb says only about one-third of the energy developed propels the projectile [12].

**Assessment of the planned equation**
- The algebraic form is **[NOT SOURCED verbatim]**. It is consistent with every description above:
  - Noble-Abel free volume;
  - unburnt solid volume (C/ρp)(1−ψ);
  - gas covolume η·C·ψ;
  - energy released f·C·ψ, with f the impetus;
  - losses multiplied by (γ−1).
  
  No snippet showed this exact equation, so it should be checked against AMCP 706-150 ch. 2 [8] or Corner [32], both of which are publicly available.
- **Double-counting risk [engineering note, not sourced].** Kent's reduced mass already includes passive-resistance work [9]. If ORKA also models bore resistance explicitly (section 5) and heat loss explicitly (section 6), then K1 must cover only what is *not* modelled elsewhere, chiefly rotational energy. Otherwise friction is counted twice.
- **Pressure used in the energy equation [engineering note].** Under Lagrange's assumptions the p in the energy equation is the space-mean pressure, and the projectile equation of motion uses the base pressure (section 3). AMCP 706-150 notes that the equation of motion simplifies when bore friction is neglected [8].
- **Missing terms the plan should consider:** a non-zero starting state, meaning primer gas and the ignition or start pressure (a modelling choice discussed in [36]). The plan should also consider gas leakage and recoil (both in GRT's energy list [13]).

---

## 3. Pressure gradient (Lagrange) and what a SAAMI/CIP transducer reads

**Planned:** p_b = p_mean/(1 + C/(3m)); p_br = p_b·(1 + C/(2m)).

**Verified pieces**
- Breech pressure = (1 + C/2m) × base pressure, under the Lagrange assumption of constant gas density between breech and projectile [15]. This is confirmed by a second source [14].
- Mean pressure = (1 + C/3m) × base pressure [14]. This was confirmed in a patent only, but it is consistent with AMCP 706-150's "projectile weight plus one-third of the charge weight" [8].
- **Assumptions:** uniform gas density, infinite sound speed, inviscid gas, circular-cylinder gun, and in the classical derivation the propellant all burnt before motion with no heat loss [14]. AMCP 706-150 says its approximate base-pressure relation from the special Lagrange solution is "restricted to artillery weapons firing at moderate velocities" [8].
- **Alternatives:** the Pidduck–Kent gradient is cited alongside Lagrange for the breech-to-base region [16]. IBHVG2's GRADNT routine computes pressure at the breech, at the projectile base **and at gauge locations** [17]. That is the capability ORKA needs (see below).
- Small arms have a high charge-to-bullet mass ratio, which is exactly where the "moderate velocities" caveat [8] matters. **[DERIVED]** For the M80 load reported as 46 gr powder under a 146 gr bullet [144], C/m = 46/146 = 0.315, so C/(2m) ≈ 0.16 and breech pressure exceeds base pressure by about 16% under Lagrange.

**Where SAAMI, CIP and EPVAT measure**
| Protocol | Sensor | Axial location | Source |
|---|---|---|---|
| SAAMI | Conformal piezo transducer whose face is machined to the chamber-wall curvature; the case is not drilled; it reads through the case wall | Bottleneck case: transducer centre 0.175 in behind the shoulder (0.250 in transducer) or 0.150 in behind it (0.194 in transducer). Straight case: half the transducer diameter plus 0.005 in behind the seated bullet base | [18][19][20] |
| C.I.P. | Piezo transducer through a drilled case | 25 mm from the breech face when the case length permits; otherwise a cartridge-specific location | [18] |
| NATO EPVAT (5.56/7.62 NATO) | Pressure sensor | Mounted *ahead of the case mouth* | [18][22] |
| Legacy drilled-case (PCB guide) | Piston/piezo through a drilled hole | "generally at mid-body"; PCB also lists a case-mouth location | [19] |

**Answer to "which model pressure corresponds to the transducer?"**
- Every protocol puts the sensor in the chamber, between the breech face and the case mouth or just ahead of it. So the reading is neither the model's base pressure nor its breech pressure. It is the gas pressure at the gauge's axial station.
- Under the Lagrange assumption that value lies between p_b and p_br. Early in travel it is close to p_br.
- **Recommendation:**
  - Compute the pressure at the gauge station, as IBHVG2's "gages" do [17], using the published SAAMI or CIP station for the cartridge [18].
  - Report breech pressure as the conservative upper bound.
  - Never compare *base* pressure with SAAMI or CIP MAP; base pressure is the lowest of the three.
  - The closed-form Lagrange pressure distribution along the bore is **[NOT SOURCED]** in this session and must be taken from AMCP 706-150 [8] or Corner [32].
- **The protocols are not interchangeable:**
  - .223 Rem: SAAMI 55,000 psi (conformal), US military SCATP 380 MPa (55,114 psi), CIP 430 MPa (62,366 psi) [21].
  - 5.56×45 NATO: EPVAT service pressure 430 MPa, proof 537.5 MPa [22].
  - "EPVAT pressures cannot be directly compared with SAAMI and C.I.P." [22].
  - The sources conflict on whether EPVAT resembles SAAMI or CIP; one is a Wikipedia talk page, which is not authoritative [22].

---

## 4. Burning law and form functions

### 4.1 Burning-rate law
- Piobert's law (1839): burning proceeds by parallel layers, with the surface regressing normal to itself at every point [24].
- Vieille's (Saint-Robert's) law: r = a·pⁿ. The coefficient a has units of velocity·pressure⁻ⁿ [25]. Vieille described the pressure dependence of smokeless-powder reaction rate in 1893 [24]. The snippets gave only rocket-propellant n values (0.3 and 0.5), so **no gun-propellant n was sourced [coverage gap]**.
- Assumptions of the *geometric* burning law, as used in gun codes [28]:
  - simultaneous ignition of all grains;
  - parallel-layer burning;
  - burning rate a function of pressure only;
  - no cracking.
  
  Closed-vessel results deviate from it, and the deviation is attributed mainly to grain cracking [28].
- **Vivacity form.** "Dynamic vivacity" is the combustion information deduced from closed-vessel pressure history. Units of 1/(MPa·s) are reported [26]. Another source normalizes dp/dt by the maximum pressure and a reference pressure [145] [UNCERTAIN attribution].
- **[DERIVED]** The two planned forms are equivalent. With z = e/e₁ and Vieille's law de/dt = u₁·pⁿ, the chain rule gives dψ/dt = (u₁/e₁)·pⁿ·(dψ/dz). This is the vivacity form with B = u₁/e₁ and Φ(ψ) = dψ/dz expressed as a function of ψ.

### 4.2 Geometric form function ψ = χ·z·(1 + λz + μz²)
- Wikipedia defines the form function as "a burning rate modifying coefficient that includes the shape of the propellant" [23].
- A Résal-based solution for spherical and perforated propellants found that spherical grains are consumed faster than tubular grains up to 0.8 ms and give a higher maximum pressure. At the end of the cycle, 79% (MKE tests) and 87% (Cronemberg tests) of the propellant had burned [147]. **Incomplete burning at muzzle exit is normal and must be modelled.**
- The same cubic form is published as Z = κ·f·(1 + λf + μf²), where κ, λ and μ are grain-shape characteristics and f is the relative burnt web [27]. It also appears as ψ = χz(1 + λz + μz²) in a DRDO paper [29] [snippet garbled].
- The form function for heptatubular and other multitubular powders "is always cubic" [30]. Fortran listings of common form functions, including a 7-perforated cylinder, are in DTIC ADA261969 [31].
- Corner [32] (ch. 2, "propellant shapes and the geometrical form function", the "true form function" and the Charbonnier form) and Hunt [33] (approximations for multitubular grains) are the public primary references. AMCP 706-247 uses a single form coefficient θ [34].
- **No snippet seen in this session showed numeric χ, λ, μ formulas.** The coefficients below are therefore **[DERIVED]** here from the stated geometry, assuming:
  - simultaneous ignition and parallel-layer burning on all exposed surfaces;
  - z = (burnt depth)/(burnt depth at web burnout).
  
  Each identity was checked numerically (2000 random cases, error < 1e-9). Cross-check against Corner before use.

| Grain | Geometry and definitions | χ | λ | μ | Notes |
|---|---|---|---|---|---|
| Sphere (idealized ball) | radius R; z = y/R | 3 | −1 | 1/3 | ψ = 1 − (1−z)³. Strongly degressive. A CFD study reports the sphere as the most degressive and the disc as the least degressive shape [146] [UNCERTAIN attribution]. Real ball powders are deterred (4.3) and are not ideal spheres [NOT SOURCED]. |
| Solid cord or cylinder | radius R, length L ≥ 2R; z = y/R; β = 2R/L | 2 + β | −(1+2β)/(2+β) | β/(2+β) | ψ = 1 − (1−z)²(1−βz). Long cord (β→0): χ=2, λ=−½, μ=0. |
| Flake or disc | thickness w = 2e₁, radius R; z = y/e₁; α = e₁/R | 1 + 2α | −α(2+α)/(1+2α) | α²/(1+2α) | ψ = 1 − (1−z)(1−αz)². Infinite plate (α→0): χ=1, λ=μ=0 (neutral). |
| Single-perforated tube | web w = R_o − r_i = 2e₁, length L; z = y/e₁; β = w/L | 1 + β | −β/(1+β) | 0 | ψ = 1 − (1−z)(1−βz). Cross-section area is ∝ (1−z) exactly. |
| 7-perforated, equal webs, to web burnout | outer radius R, 7 holes of radius r, web w = 2e₁, length L; Q₀ = R² − 7r²; a = 2e₁(R+7r)/Q₀; b = 6e₁²/Q₀; β = 2e₁/L | a + β | (b − aβ)/(a+β) | −bβ/(a+β) | ψ = 1 − (1 − az − bz²)(1 − βz) for 0 ≤ z ≤ 1. Progressive. At z = 1 the remaining mass 1 − ψ(1) is **slivers**, which need a separate sliver form function; that function is not given here [see 31, 32]. |

### 4.3 Deterrent-coated powders (ball powders and many extruded powders)
How the literature models them:
- **Depth-dependent burning rate.** A modified Vieille law whose prefactor and exponent vary with burned distance, combined with depth-dependent thermochemistry, in a lumped-parameter model [37].
- **Deterrent profile shape.** Profiles may be a step (constant deterrent level through the deterred zone) or a linear gradient. Concentration, maximum depth and profile shape all change burn rate against depth burned [40]. For 5.56 mm ball propellant, XKTC and IBHVG2 have been run with "ramp" and "ball" deterrent profiles [41].
- **Layer model.** The burn rate is written as a function of relative burned thickness, with a ratio between deterred-layer and core burn rates. Deterred layers are cited as about 0.1–0.3 mm thick, but that figure is for *large-calibre* propellant [39].
- **Surface concentration matters most early.** At 20 MPa the burn rate depends mainly on deterrent concentration at the surface [43] [UNCERTAIN attribution].
- **Diffusion depth and strength.** For spherical propellant, progressivity relates non-linearly to deterrent diffusion depth and linearly to combined deterring strength [38].
- **Form-function coefficients.** Some codes write the burned mass fraction with form-function coefficients ff1–ff3 against burned distance relative to half the initial web [42].
- **Purpose-built code.** Sandia (Robbins et al., 2021) published "A user-friendly and fast interior ballistic code for performance predictions of deterred propellants" [40]. No abstract was available.
- **How commercial tools do it.**
  - QuickLOAD approximates the burning function φ(z) with two parabolic arcs fitted to measured curves [114].
  - GRT uses a piecewise burn-rate curve with boundaries z1 (progressive to primary-degressive) and z2 (primary-degressive to secondary-degressive) [103][109].
  
  Both are empirical "true form functions" that absorb deterrent effects, rather than modelling the deterrent explicitly.
- **Identifying the experimental form function.** It can be identified by a reverse method from closed-vessel or gun data, as an average over grains that includes grain scatter and prolonged ignition [35]. **Recommendation: ORKA should use an empirical ψ(z) or Φ(ψ) fitted per powder (GRT/QL style), and keep the geometric table above only as a prior.**

---

## 5. Shot start (engraving) and bore resistance

**Values seen (all small-arms figures come from non-peer-reviewed sources; primary sources not identified):**

| Quantity | Value | Context | Source |
|---|---|---|---|
| First engraving-pressure maximum | 24–44 MPa | jacketed rifle bullets, 6.5–9.3 mm | [47] third-party (GitHub issue, measurement source not identified) |
| Second maximum | 41–75 MPa, then a plateau | same | [47] |
| Measured resistance vs travel | peaks 31–42 MPa at engraving, falling to about 4 MPa within 0.05–0.35 m; wide round-to-round scatter | 2 of 3 instrumented guns | [47] |
| Typical shot-start pressure, "normal guns" | 25–40 MPa (Serebryakov) | cited in a 105 mm gun paper, not small arms | [49] |
| QuickLOAD default shot-start | about 25 MPa (3,626 psi) | jacketed lead-core match bullets | forum [50][150][151] [UNCERTAIN attribution] |
| Uncoated lead-core bullet, peak | about 27.5 MPa | forum engraving-force study | [50] |
| Solid copper bullet, peak | about 100 MPa | same | [50] |
| OpenReloading workbench defaults | 29.2 MPa jacketed; 35.3 MPa monolithic; 30.0 MPa lead; powders without a start pressure were fitted at 30 MPa | another open-source project | [48] |

- **[DERIVED]** 25 MPa = 3,625.9 psi, which agrees with the forum's 3,626 psi.
- **M855 (ARL-TR-4743).** Engraving forces are "small and localized relative to ballistic pressure". They were studied with rate-controlled push tests and soft recovery [51]. The peak force was not in the snippet.
- **ARL-TR-7479.** Primer output and initial projectile motion for 5.56 and 7.62 mm, with the estimated point of full engraving. The 7.62 mm data scatter more than the 5.56 mm data [52].
- **12.7 mm solid copper.** Quasi-static engraving resistance can predict dynamic engraving resistance [53].
- **Copper friction.** Solid-copper construction increases barrel friction and lowers muzzle velocity [54] [UNCERTAIN attribution].
- **Modelling practice:**
  - GRT takes projectile frictional resistance "primarily specified by the bullet manufacturer", and experienced users may adjust it [13].
  - A modified STANAG 4367 model for small arms adds fitted parameters prm, fR and hw. hw is a heat-transfer coefficient fitted in a two-step procedure; prm and fR were not defined in the snippet but are presumably resistance-related [UNCERTAIN] [35][36].
  - An open project proposes a pressure-proportional bore friction and a start pressure that scales with bearing length (proposal, not validated) [47].
- **Recommendation:**
  - Model shot start as a threshold on base pressure, defaulting to 25–30 MPa for jacketed lead-core bullets, consistent across [47][48][50], and higher for monolithic copper [48][50].
  - Add a travel-dependent resistance pressure that peaks during engraving and then falls to a small plateau [47].
  - Expose both as calibratable parameters.
  - Choosing a shot-start pressure is equivalent to choosing the model's starting state [36].

---

## 6. Heat loss to the barrel

**Bottom line:** no snippet seen in this session contained a complete heat-loss equation with its constants. The models and the documents that contain them are identified below, but **the actual equations and constants are a coverage gap.** They must be read from the public primary sources listed. The IBHVG2 user's guide, Corner and Hunt are all on archive.org as full text.

| Model | What is confirmed | Where the equations are |
|---|---|---|
| **IBHVG2** (Anderson & Fickie, BRL-TR-2829, 1987) | Heat-loss rate is computed with the **Black & Comenetz** treatment from the NDRC hypervelocity report. A flag switches heat loss on (1, default) or off (0). "HEAT" input block: tube-wall shell thickness (default 0.004 in), shell specific heat, shell density, initial wall temperature 293 K, and a free-convective heat-transfer coefficient for air in the tube. The energy balance includes a loss term for work done and heat transferred [17]. An IBHVG2 extension report gives a default convective coefficient of 11.35 W/m²·K and a thin-shell barrel by default [55]. That value is plausibly the same air-side free-convection input, not a bore-gas coefficient [UNCERTAIN, inference]. IBHVG2 losses are subtracted from the propellant's heat of formation before the equilibrium calculation [3]. | IBHVG2 user's guide, full text on archive.org [17] |
| **Hunt / Corner semi-empirical** | Heat loss "estimated by a semi-empirical relationship described by Hunt and Corner". It is the same equation used in the Baer & Frankle model (the OCR spells the name "Frankie") and is reviewed for small arms [56][57]. Hunt's model "does not require as input the distribution of the gas properties in the tube". Nordheim's model and a turbulent boundary-layer model gave similar losses in several cases [14]. | Corner 1950 §10.41 "Semiempirical formulas for heat loss" [32]; Hunt 1951 §6.10 "Heat energy lost to the gun" [33]; Corner p. 425 is cited for barrel heat transfer [59] |
| **Nordheim–Soodak–Nordheim** | "The most popular method for heat transfer correlation." It assumes the gas–wall friction factor depends only on bore roughness, so the heat-transfer coefficient scales with gas density, velocity and specific heat [60]. It uses the Reynolds analogy, so the friction factor is the only quantity to deduce. Nordheim proposed measuring it with fast-response thermocouples and set constants from machine-gun heat input [61]. | Ward & Brosseau [61]; DTIC AD0755111 [60]; AMCP 706-150 heat-transfer chapter [8] |
| **STANAG 4367** | NATO "Thermodynamic Interior Ballistic Model with Global Parameters". The current edition is 2012 (Edition 2 dated 22 May 2000). Paywalled [64]. Its heat-transfer sub-model was found to be the cause of "relatively high deviation" in 155 mm simulations [63]. A small-arms variant fits a heat-transfer coefficient hw [35]. | Standard (purchase) [64]; NWU thesis [63] |
| **"Robbins & Anderson" model** | **Not found.** The nearest matches are Robbins et al. 2021 (Sandia, deterred propellants) [40], Anderson & Fickie's IBHVG2 [17], and Robbins & Kruczynski BRL-TR-3059 (VHBR propellant, not heat loss). The model name in the plan may be a conflation. | none |

**Magnitudes seen**
- Early measurements found about 3% of charge energy goes into heating the bore. Noble & Abel measured 4.2–17% for cannon [58].
- AMCP 706-150 says heat losses are larger "especially in small arms" [8].
- Boundary-layer calculations give 4.6–8.1% of released energy for 40–203 mm guns. A rifle-like proxy gave about 7–16%, but that is a software output, not validation data [69].
- In a tank-gun study, about 66% of the heat was transferred *after* projectile exit (at t = 7.5 ms) [62].
- One fast lumped-parameter model (DST Group) ignores heat loss entirely [65].
- Lumped zone-wise heat transfer with a pipe-flow Nu(Re, Pr) correlation is used for a 35 mm barrel [67]. Cook-off heating was about 90% radiation and 10% convection [68], but that is a different regime.

**Recommendation for ORKA**
- Implement the heat-loss term as a pluggable sub-model with a calibratable coefficient, as in the modified STANAG approach with a fitted hw [35].
- Seed it from the IBHVG2 / Black-Comenetz equations once they have been read from [17].
- Until then, the general convective structure (loss rate = h·A_wetted·(T_gas − T_wall), integrated in time, as in [62]) is **[NOT SOURCED for constants]** and must not ship with invented constants.

---

## 7. Propellant thermochemistry (public sources only)

General ranges and definitions:
- For propellants used in propellant-actuated devices, the ratio of specific heats is about 1.23–1.26, the isochoric flame temperature about 2,000–3,300 K, and the impetus about 3–4 × 10⁵ ft·lbf/lb [71]. **[DERIVED]** That impetus range is about 897–1,196 J/g.
- **Heat of explosion** is defined as the calorific value: the difference, at reference temperature T₀, between the heats of formation of the products and of the propellant [5].
- The Hirschfelder–Sherman method uses the adiabatic isochoric flame temperature, heat of explosion, moles of gas per gram, and impetus [74].
- **Conversion used below [DERIVED, exact]:** 1 ft·lbf/lb = 0.3048 × 9.80665 J/kg = 2.98906692 J/kg = 0.00298906692 J/g. This depends on 1 ft = 0.3048 m, which is **[NOT SOURCED]** here, and on 1 lbf = 0.45359237 kg × 9.80665 m/s², which is sourced [119].

### 7.1 Military propellants
| Propellant | Impetus | Flame temp T_v | γ | Covolume (cm³/g) | Composition | Sources and conflicts |
|---|---|---|---|---|---|---|
| M1 | 923.6 J/g [72]; 919.2 J/g [73] | 2,449 K [72]; 2,447 K [73] | 1.2674 (frozen) [72]; 1.2675 [73] | 1.106 [72]; 1.105 [73] | – | Two sources agree within about 0.5%. Source [72] mislabels the covolume unit as g/cm³. [73] compares BLAKE with Virginia reference data. **conflicts:** small numerical differences as listed. |
| M6 | 317 × 10³ ft·lbf/lb → **947.5 J/g [DERIVED]** | 2,570 K | 1.254 | – | – | [70] OCR of an Army table, column alignment [UNCERTAIN]. One query quoted γ = 1.2588; no source for that number was found. |
| M2 | – | – | – | – | about 20% NG, 77% NC, 3% other | [75]; thermochemical row in [74] is garbled. |
| M26 | – | – | – | – | 67.5% NC, 25.0% NG; NC nitrogen 13.15% | [76] [UNCERTAIN attribution] |
| M30A1 | 1,065.3 J/g | about 3,003 K | 1.241 | 1.041 | – | BLAKE at Δ = 0.2 g/cc [77] [UNCERTAIN attribution and column pairing] |
| M30 | – | – | 1.243 (value used by IBHVG2) | 1.02962 | – | [77] [UNCERTAIN attribution] |
| Unassigned set | 1,085 kJ/kg | 3,132 K | 1.2384 | 1.0383 | – | In [72], but the label (M2, M6, M26 or M30) could not be read. **Do not use.** |
| M10, IMR (military) | – | M10 "near 3,000 K"; IMR possibly 2,835 K | – | – | IMR uses NC as the principal energetic material; low cost, low flame temperature | [74] garbled table, **[UNCERTAIN] do not use**. The same source says erosivity is about ∝ T_v⁸ and that potassium salts suppress secondary flash [74]. |
| WC844 (ball) | – | – | – | – | Generic ball-powder SDS ranges, not WC844-specific: NC 50–100%, NG 0–42%, dibutyl phthalate 0–10%, ethyl centralite 0–10% [45] | Used for 5.56 mm M193, M855 and M196 tracer [46]. Reformulated in 1970 with reduced calcium carbonate after M16 gas-tube fouling [44]. |
| WC846 (ball) | – | – | – | – | – | Used for 7.62 mm M80 ball and M62 tracer [46]. A forum says WC844 and WC846 are chemically identical, with WC846 allowing up to 1.0% CaCO₃ (unverified) [152]. A 1961 Olin lot for .308/.223 had 10% NG and 5.75% DBP deterrent; the same snippet says "10 percent diphenylamine", which is likely a transcription error [44] [UNCERTAIN]. |
| WC860 | – | – | – | – | – | Used for .50 cal M33 ball [46]. |
| WC872 | – | – | – | – | – | No data found. |

- **Generic ball-propellant ranges** attributed to an Olin SDS via Wikipedia: NC 40–70%, NG 10–60%, ethyl centralite 3–7%, DBP 1–5% [44].
- **Third-party database warning:** ammoreference.com lists H335 (ex-WC844) at 908 J/g and BL-C(2) (ex-WC846) at 3,990 J/g. Both entries give bulk densities in "g/cm³" values near 1,000, an evident unit error. **Exclude this source** [94].

### 7.2 Commercial powders: manufacturer-published values
All values are "approx." as published. "Heat of explosion" and "energy content" are quoted exactly as the manufacturer labels them; whether water is counted as liquid or gas is not stated in the snippets [UNCERTAIN basis].

| Powder | Heat of explosion / energy content (J/g) | Bulk density | Other | Source |
|---|---|---|---|---|
| Reload Swiss RS40 | 3,950 | 940 g/L | Derived from a military-qualified 5.56 mm propellant. The datasheet calls it extruded single-base NC. | [79] |
| Reload Swiss RS50 | 3,750 | 950 g/L | extruded, single-base NC | [80] |
| Reload Swiss RS52 | 3,900 | 950 g/L | – | [81] |
| Reload Swiss RS62 | 3,750 | 960 g/L | grain 0.85 mm dia × 1.9 mm length; lot tolerance v₅ ±12 m/s, p_max ±250 bar | [78] |
| Reload Swiss RS70 | 3,900 | 990 g/L | grain 1.0 mm dia | [82] |
| Reload Swiss RS60 | not on official page | 970 kg/m³ (retailer) | **conflict:** a forum claims about 4,000 J/g and double-base. The manufacturer calls the RS40–RS70 line single-base. | [84] forum; [82]/[83] manufacturer |
| Vihtavuori N530 | 3,950 | – | N500 line is "enhanced with nitroglycerin" | [85] |
| Vihtavuori N540 | 4,000 | – | – | [85] |
| Vihtavuori N550 | 3,900 | – | – | [85] |
| Vihtavuori N555 | 3,700 | – | – | [85] |
| Vihtavuori N560 | 4,000 | – | – | [85] |
| Vihtavuori N565 | 4,000 | 960 g/L | – | [85][86] |
| Vihtavuori N568 | 3,850 | – | – | [85] |
| Vihtavuori N570 | 4,000 | – | – | [85] |
| Vihtavuori N100 series (single-base) | values of about 3,500–3,950 seen but **not mappable to individual powders** | – | – | [88]. The 2022 guide row "4100, 4100, 3050, 4100, …" is also unmapped [89]. |
| Vihtavuori N140 | – | 902 kg/m³ (third party) | – | [91] |

- **Vihtavuori N500 series notes.**
  - The 2026 Reloading Guide lists seven N500 values (4000, 3900, 3700, 4000, 4000, 3850, 4000) where the web page lists eight [87]. Possibly N530 is absent from the 2026 guide [UNCERTAIN; check discontinuation].
  - The N500 SDS (2026) gives cellulose nitrate at 80 to <99%. The NG percentage was not visible in the snippet [90].
- **Nitrochemie EI** (lead-free small-calibre military propellant): no heat-of-explosion value found [92].
- **Not found / not searched (coverage gaps):**
  - Norma: no published thermochemistry found. Its pages give load data only [93].
  - ADI, Shooters World, Hodgdon, Alliant: not searched because the search budget ran out.
  - IMR single-base military composition: not confirmed.
  - WC844, WC846, WC860 and WC872 thermochemistry: not found.
- **Using manufacturer heat of explosion in the model [DERIVED caveat, not sourced].** For an ideal gas with constant c_v, R = (γ−1)·c_v, so f ≈ (γ−1)·Q at constant volume. GRT's documented progressivity factor couples the two parameters (Bp ∝ Ba·φ(z1)·Qex·√(2(k−1)) [104]). That shows GRT ties k to Qex, but it does **not** confirm the f ≈ (γ−1)·Q relation. Real f differs: Q may count H₂O as liquid, and c_v varies with T. Treat Q→f mapping as a calibrated relation, not an identity.

---

## 8. Temperature sensitivity

| Measure | Value | Source |
|---|---|---|
| Rule of thumb (velocity) | about 1 fps per °F for moderate loads | Sierra [95]; Gun Digest, relative to 68 °F [96] |
| .308 Win | 1 to 1.5 fps per °F | [98] |
| "Popular powders" | up to 1.5–2.0 fps per °F. Handloader data showed about 1.9 fps/°F for one load | [97] |
| Summer-to-winter loss | 41 fps for one load vs 93 fps for another (IMR 4064) | [99] |
| Burn-rate temperature sensitivity, spherical single-base gun propellant (closed vessel) | 0.305 %/°C toward high temperature; 0.121 %/°C toward low temperature (asymmetric). The paper's wording says burn rate *decreases* with conditioning temperature, which is the opposite of the usual expectation; read the full paper [UNCERTAIN]. | Boulkadid 2017 [100] |
| Single-base vs double-base | Single-base compositions are less temperature dependent than double-base. Peak pressure falls about 7% between 21 °C and −32 °C. The OCR reads "210C and -320C" [UNCERTAIN]. | DTIC AD0265123 [102] |

- **Definitions.** The temperature sensitivity σ_r [%/°C] is a property of the propellant. The temperature coefficient is a property of the weapon [148] [UNCERTAIN attribution]. Local temperature-sensitivity coefficients of a deterred spherical propellant are measured per STANAG 4115 [101].
- **GRT parameterization:**
  - tcc = (Ba(+21 °C) − Ba(−20 °C))/41 (cold side) and tch = (Ba(+60 °C) − Ba(+21 °C))/39 (hot side), with reference 21 °C.
  - If both are 0.0000, internal defaults (values not published in the snippet) are used [106][103].
  - GRT's assistant suggests measuring at about −10 °C, 21 °C and +50 °C [106].
- **[DERIVED]** 1 fps/°F = 1.8 fps/°C. At 3,000 fps that is about 0.06 %/°C of velocity (illustrative only).
- **Recommendation:** use an asymmetric, piecewise-linear temperature coefficient on the burn-rate coefficient, as in GRT [106] and consistent with [100], with powder-specific values where a manufacturer publishes them.

---

## 9. How GRT and QuickLOAD parameterize powders (public descriptions only)

### 9.1 GRT (Gordon's Reloading Tool), from the grtools.de wiki
| Field | Meaning (as documented) | Source |
|---|---|---|
| Qex | Total explosive energy of the powder from calorimetric measurement. Sets the maximum attainable pressure. | [103][13] |
| Ba | Combustion coefficient: how fast the powder ignites and starts burning. It is the *start* of a burn-rate curve "composed of two or more sections". | [103] |
| a0 | Indicates whether the powder burns progressively or degressively | [103] |
| z1 | Boundary where progressive combustion turns into primary-degressive combustion | [103][109] |
| z2 | Boundary where primary-degressive combustion turns into secondary-degressive combustion. Often left at a default; a forum says QuickLOAD's "factor b" maps to z2 after conversion. | [103][112][111] |
| k | Isentropic exponent | [103] |
| covolume b; η label | The formalism page describes covolume (b), loading density Δ (powder mass / chamber volume) and material density. The "eta" field name is not confirmed in snippets. | [13] |
| pc | Density of the powder material | [103] |
| pcd | Bulk density, including voids. The FAQ calibrates it by adjusting pcd until the fill ratio reads 100%. | [103][107] |
| Pt | Powder temperature | [103] |
| tcc, tch | Cold and hot temperature coefficients (section 8) | [106] |
| Bp (derived) | GRT-specific progressivity factor: Bp = sqrt(2·(k−1)·(Ba·φ(z1)·Qex)²)/10000 (as rendered in the snippet; verify the exact bracket placement) | [104] |

- **Model provenance.** The model is a custom build based on:
  - Rheinmetall's *Waffentechnisches Taschenbuch*;
  - Kneubuehl, *Ballistik – Theorie und Praxis*;
  - Kutterer, *Ballistik*.
  
  It is influenced by IBHVG2 [13].
- **Where powder data comes from.**
  - Powder data come from validated manufacturer data sets [109]. Model values "can be slightly different from the figures published by the manufacturer" because of differing analysis filters [13].
  - Closed-vessel data are "one of the most important initial data" [13].
  - Powders without manufacturer data are reverse-engineered from user and GRTLab measurements [110].
  - The German wiki strongly advises against editing manufacturer values from Qex to Pcd without background knowledge [103].
- **Accuracy claim.**
  - The FAQ says rifle performance is typically predicted within about 3%, and that a deviation of 3% or less is "excellent".
  - Error sources: reloading and tool variation about 1.5% or more, chronograph up to 5%, worst case additive.
  - The FAQ therefore recommends starting load development at about −25% of maximum pressure or lower [105].
  - Calibration (OBT tool) adjusts the initial pressure or Ba and k to match measured velocity [105][108].
- **Status (forum, unverified).** GRT is "frozen" after the developer's death, and powder models are ageing [111]. Users commonly tune Ba to chronograph data [111].

### 9.2 QuickLOAD
- Developer Hartmut G. Brömel. The default database has more than 225 powders. Accurate predictions need a measured case volume (water-weighing). Wikipedia calls the tool "merely a computer simulation" and advises double- or triple-checking against powder makers' data [113].
- **Burning function.** φ(z) is approximated by two parabolic arcs, and users can fit it to measured curves [114] (third-party upload of the manual).
- **Fields seen in public forum printouts** [115][116]:
  - Burning Rate Factor Ba, in 1/s;
  - Pro-/Degressivity Factor a0, either sign;
  - Burning Function Limit z1;
  - Factor b;
  - Weighting Factor;
  - heat of explosion;
  - "Ratio of Specific Heats" (isentropic exponent);
  - covolume.
- **[UNCERTAIN, inference]** Ba is reported in 1/s, which implies that QuickLOAD's burning law normalizes pressure by a reference pressure.
- Users tune Ba to chronograph data and use ±10% Ba to show lot-to-lot sensitivity [115].
- **No vendor accuracy percentage was found [coverage gap].**

### 9.3 Implication for ORKA
Both tools use the same structure:
- a Noble-Abel / Résal lumped model;
- an empirical, piecewise vivacity-type burn function (Ba plus shape parameters a0, z1, z2 or b);
- per-powder thermochemistry (Qex, k, covolume, densities);
- temperature coefficients;
- a shot-start or friction model.

ORKA can reproduce this structure from public physics. It must **build its own powder fits from public pressure and velocity data** and must not copy either tool's data files.

---

## 10. Exact unit conversions

| Conversion | Value | Status |
|---|---|---|
| 1 grain | **64.79891 mg exactly** (international definition 1958/1959) | [117][118] |
| 1 g | 15.4323584 gr; **[DERIVED]** exact 100000000/6479891 = 15.432358352941… | [118] |
| 1 lbf | 0.45359237 kg × 9.80665 m/s² = **4.4482216152605 N exactly** | [119][120] |
| 1 psi | 6.894757 kPa [121][122]. **[DERIVED]** with 1 in = 0.0254 m (that definition is [NOT SOURCED] here): 6,894.757293168… Pa | sourced value plus derivation |
| 1 MPa | **[DERIVED]** 145.0377377 psi | from above |
| 1 psi | **[DERIVED]** 0.06894757 bar, taking 1 bar = 100,000 Pa ([NOT SOURCED] here) | – |
| 1 bar | **[DERIVED]** 14.50377377 psi | – |
| Water density 15 °C | 999.1026 kg/m³ [123]; NBS Circular 19: 0.99913 g/mL [125] | – |
| Water density 20 °C | 0.99820 g/cm³ [124]; 998.2071 kg/m³ [123]; 0.99823 g/mL [125]. **conflict** in the 5th decimal (0.003%) | – |
| Water density 25 °C | 997.0479 kg/m³ [123]; 0.99708 g/mL [125] | – |
| Grains of water → cm³ | **[DERIVED]** V(cm³) = m(gr) × 0.06479891 / ρ_w(T). At 20 °C (ρ = 0.9982071): 0.0649153 cm³/gr, i.e. 15.40469 gr/cm³. At 25 °C: 15.38680 gr/cm³. With ρ ≡ 1: 15.43236 gr/cm³. | Using ρ = 1 understates volume by about 0.18% at 20 °C and about 0.30% at 25 °C. **ORKA should store the water temperature with every measured case capacity.** |
| ft·lbf/lb → J/g | **[DERIVED]** 0.00298906692 (1 ft = 0.3048 m, [NOT SOURCED] here) | – |

**CUP vs psi: not interconvertible by a fixed factor.**
- Copper crusher (CUP) and piezo-transducer (psi) readings are different measurements. The numbers "are not equivalent" [126], and "there is no standard conversion ratio or correlation" [127].
- SAAMI publishes both CUP and psi values for many cartridges rather than converting [127].
- **Crusher readings run lower.** The crusher's peak pressure is always lower than the Kistler piezo reading, by up to 20% [131].
- **Time integration.** The crusher deformation integrates pressure over time [129] (weak source).
- **Empirical regression (Bramwell), with conflicting coefficients:**
  - psi = −17,902 + 1.516 × CUP, correlating within 3,000 psi for about two-thirds of rifle cartridges and failing for "statistically peculiar" ones [128];
  - psi ≈ 1.52 × CUP − 18,000, valid only for SAAMI crusher pressures of 28,000–54,000 CUP [130][126] [UNCERTAIN attribution].
  
  Neither applies to handgun, shotgun or black-powder loads [129]. Handloader's verdict: "yes and no, mostly no" [128].
- **ORKA rule:** never convert CUP to psi to produce a pressure limit. Store CUP-based data in CUP, and compare a model's psi only with transducer-psi data.
- **Strain-gauge measurements** are the least accurate method and are used for *relative* comparisons [142].

---

## 11. Public validation data (what exists, what was seen)

| Dataset / reference | Values seen | Type | Source |
|---|---|---|---|
| 7.62×51 mm NATO Ball, EPVAT barrel, case-mouth port | Peak about **363 MPa**, reached about **0.240 ms** after the pressure rise begins. The sensor was an HPI GP6 transducer with a B217 charge amplifier. Theoretical and PRODAS curves are compared with experiment. | **conflict:** one summary calls the curve "theoretical", another calls it a measurement [UNCERTAIN] | MDPI Sensors 2023 [136] |
| 7.62 mm M80 (IBal2000 simulation file "NATO reference") | chamber 3.27761 cm³; propellant 2.6762 g (**[DERIVED]** 41.30 gr); predicted MV 869 m/s; max breech 352.69 MPa | **model output, not data** | [133] |
| 7.62 mm M80 published load | about 46 gr WC846 behind a 146 gr bullet. **conflict** with the 41.3 gr in the IBal2000 file. | [UNCERTAIN attribution] | [144] |
| 7.62 mm M80 velocity | 838 ± 9.1 m/s at 23.7 m (MKE datasheet) | manufacturer | [134] |
| 7.62 mm M80 pressure spec | 50,000 psi max average (copper crusher, MIL-C-46931F); 365 MPa (52,940 psi) EPVAT. Another post: 379 MPa max / 345 MPa mean (work-hardening) vs 400/365 MPa (piezo). | forum quotes of spec | [135] |
| 7.62 mm M80 delayed ignition | WC846 vs WC846FS: time to 25% of peak pressure; a step in the p-t curve | government report | [132] |
| 7.62 mm machine gun | theoretical vs experimental barrel p-t curves; sampling 25 µs; vivacity from closed vessel | peer-reviewed figure | [139] |
| 7.62 mm blank (Goldstein 1979) | p-t records in a test barrel and a vented chamber | government review | [56] |
| 5.56×45 / .223 limits | EPVAT 430 MPa service, 537.5 MPa proof; SAAMI 55,000 psi; SCATP 380 MPa; CIP 430 MPa | standards via Wikipedia | [21][22] |
| 5.56 mm NGEN3 + primer model | ARL-TR-4903 (data not in snippet) | government | [140] |
| 5.56/7.62 primer output and initial motion | ARL-TR-7479 | government | [52] |
| Intermediate cartridges (5.56×45 and others) | about 0.5 ms interval between pressure jumps at transducers | peer-reviewed | [138] |
| EPVAT-style piezo uncertainty | two-sensor peak means 343.70 MPa and 116.61 MPa (cartridge not identified in snippet) | peer-reviewed | [137] |
| STANAG 4367 vs test | MV 310.92 m/s (STANAG code) vs 330 m/s (test) vs 332.72 m/s (CFD), small gun chamber | peer-reviewed | [66] |
| .308 Win example | peak 44,100 psi | patent example, not validation | [143] |

- **Coverage gap.** No openly published, digitized p(t) trace with full load data was retrieved for 5.56, 7.62 or .308. The best candidates to open next are:
  - [136] (has the 7.62×51 curve);
  - the intermediate-cartridge paper [138];
  - ARL-TR-4903 [140] and ARL-TR-7479 [52];
  - Goldstein [56];
  - the Leciejewski figure [139].
- **Accuracy benchmarks reported for lumped or CFD codes (not small arms):**
  - an anti-aircraft cannon model estimated peak pressure and MV within 6.0% without extra fitting coefficients [141];
  - a 3-D model was within 1% on peak pressure and 1.5% on peak velocity [146] [UNCERTAIN attribution].

---

## 12. Reference list

Every entry has type **search-snippet**. The bracketed "underlying" type shows what the page would count as once opened. Several entries list more than one URL for the same document.

1. Altair Radioss, "EOS Noble-Abel" [underlying: third-party/vendor doc]. https://help.altair.com/hwsolvers/rad/topics/solvers/rad/eos_noble_abel_starter_r.htm
2. DTIC ADA454209 (DSTO technical note on Noble-Abel EOS for gun gases) [government] [UNCERTAIN attribution]. https://apps.dtic.mil/sti/pdfs/ADA454209.pdf
3. Macpherson, A. K. & Vladimiroff, T. (1993), "Interior Ballistic Calculations Using an Accurate Equation of State for the Propellant Gases", DTIC ADA263014 [government]. https://apps.dtic.mil/sti/tr/pdf/ADA263014.pdf ; https://ntrl.ntis.gov/NTRL/dashboard/searchResults/titleDetail/ADA263014.xhtml
4. "Noble-Abel / First-order virial equations of state for gas mixtures resulting of multiple condensed reactive materials combustion", arXiv:2111.10120 [peer-reviewed preprint]. https://arxiv.org/pdf/2111.10120
5. AMCP 706-175, Engineering Design Handbook, Solid Propellants Part One [government]. https://www.bulletpicker.com/pdf/AMCP-706-175.pdf
6. Closed-vessel analysis paper (Military University of Technology, Warsaw; Noja/Gabriel), Problems of Mechatronics 13(4) [peer-reviewed]. https://yadda.icm.edu.pl/baztech/element/bwmeta1.element.baztech-62f04430-c2b1-44e3-b600-9ab623f5aac8/c/4_Nr-13_4_s.9-22_Noja-Gabriel_ver3.pdf
7. DTIC ADA590866 (ARL report on BLAKE-derived impetus, covolume and γ for IB codes) [government]. https://apps.dtic.mil/sti/pdfs/ADA590866.pdf
8. AMCP 706-150, Engineering Design Handbook, Ballistic Series: Interior Ballistics of Guns (Feb 1965; Jones, Hitchcock, Villegas) [government]. https://apps.dtic.mil/sti/pdfs/AD0462060.pdf ; copy: https://diverdi.colostate.edu/C477/experiments/interior%20ballistics%20of%20a%20cannon/references/interior%20ballistics%20of%20guns%201965.pdf ; https://archive.org/details/DTIC_AD0462060 ; https://everyspec.com/ARMY/ARMY-General/AMCP_706-150_FEB1965_50902/
9. Kent, R. H. (1936), BRL report on the equations of interior ballistics (Résal) [government] [UNCERTAIN attribution]. https://apps.dtic.mil/sti/pdfs/AD0733736.pdf ; https://archive.org/details/DTIC_AD0733736
10. Bhaskara Rao & Sharma (1982), "Art in Internal Ballistics", Defence Science Journal 32(2):157–174 [peer-reviewed]. https://publications.drdo.gov.in/ojs/index.php/dsj/article/download/6277/3355
11. "Simulation and Calculation of Interior Ballistic of A Large Caliber Artillery" (ResearchGate) [peer-reviewed/conference]. https://www.researchgate.net/publication/338434322_Simulation_and_Calculation_of_Interior_Ballistic_of_A_Large_Caliber_Artillery
12. US Army FM 6-40, ch. 3 [government]. https://man.fas.org/dod-101/sys/land/docs/fm6-40-ch3.htm
13. GRT wiki, "Interior ballistic model, Powder modeling & Sources" [third-party/software vendor]. https://grtools.de/doku.php?id=en:doku:formalism (German: https://grtools.de/doku.php?id=de:doku:formalism)
14. US Patent 8,789,795, "Propulsion system and method using a combustion chamber discharging a concentrated mass" [government/patent]. https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/8789795
15. DTIC ADA241552 (US Army report applying the Lagrange assumption) [government]. https://apps.dtic.mil/sti/tr/pdf/ADA241552.pdf
16. Guermonprez et al. (2025), Defence Technology, S2214914725000601 [peer-reviewed]. https://www.fie.undef.edu.ar/ceptm/wp-content/uploads/2025/03/1-s2.0-S2214914725000601-main.pdf
17. Anderson, R. D. & Fickie, K. D. (1987), "IBHVG2 (Interior Ballistics of High Velocity Guns, Version 2) – A User's Guide", BRL-TR-2829, DTIC ADB117104 [government]. https://archive.org/stream/DTIC_ADB117104/DTIC_ADB117104_djvu.txt ; https://apps.dtic.mil/sti/tr/pdf/ADB117104.pdf ; https://diverdi.colostate.edu/C477/experiments/interior%20ballistics%20of%20a%20cannon/references/ball_res_lab_1987_2829.pdf
18. Wikipedia, "Small arms ammunition pressure testing" [third-party]. https://en.wikipedia.org/wiki/Small_arms_ammunition_pressure_testing
19. PCB Piezotronics, Ballistic Pressure Sensors Reference Guide; Conformal ballistic sensors [manufacturer]. https://pcb.com/Resources/ProductLiterature/BallisticPressureSensorsReferenceGuide ; https://www.pcb.com/SensorsforTestMeasurement/PressureTransducers/Ballistic/Conformal
20. SAAMI glossary, "conformal gauge" [standard]. https://saami.org/glossary/conformal-gauge/
21. Wikipedia, ".223 Remington" [third-party]. https://en.wikipedia.org/wiki/.223_Remington
22. Wikipedia, "5.56×45mm NATO" and "NATO EPVAT testing" [third-party]. https://en.wikipedia.org/wiki/5.56%C3%9745mm_NATO ; https://en.wikipedia.org/wiki/NATO_EPVAT_testing
23. Wikipedia, "Internal ballistics" [third-party]. https://en.wikipedia.org/wiki/Internal_ballistics
24. Wikipedia, "Piobert's law" [third-party]. https://en.wikipedia.org/wiki/Piobert%27s_law
25. proptools documentation, "Solid-Propellant Rocket Motors" (Vieille's law) [third-party]. https://proptools.readthedocs.io/en/latest/solid_tutorial.html
26. Wiley book excerpt, "Solid propellants and their combustion characteristics" (ISBN 9781118127568) [peer-reviewed/book]. https://catalogimages.wiley.com/images/db/pdf/9781118127568.excerpt.pdf
27. Advances in Military Technology 16(1) 2021, pp. 49–58 [peer-reviewed]. https://www.aimt.cz/index.php/aimt/article/download/1300/28/4634
28. "On Influence of Mechanical Properties of Gun Propellants on Their Ballistic Characteristics Determined in Closed Vessel Tests", Materials 13 (2020) 3243 [peer-reviewed]. https://pmc.ncbi.nlm.nih.gov/articles/PMC7411880/
29. "Low Acceleration Overload Catapult Technique…", Defence Science Journal [peer-reviewed]. https://publicationsdrdo.in/index.php/dsj/article/download/9815/5694/29637
30. "On the internal ballistics of a supergun using multitubular powders", Defence Science Journal [peer-reviewed]. https://publications.drdo.gov.in/ojs/index.php/dsj/article/download/6447/3505/16800
31. DTIC ADA261969 (form functions, including 7-perforated grain, with Fortran listings) [government]. https://apps.dtic.mil/sti/pdfs/ADA261969.pdf
32. Corner, J. (1950), *Theory of the Interior Ballistics of Guns*, Wiley [book; full text]. https://archive.org/stream/THEORYOFTHEINTERIORBALLISTICSOFGUNS.J.CORNERPHD._201611/THEORY+OF+THE+INTERIOR+BALLISTICS+OF+GUNS.+J.CORNER+PHD._djvu.txt
33. Hunt, F. R. W. (ed.) (1951), *Internal Ballistics*, HMSO / Ministry of Defence [government/book; full text]. https://archive.org/stream/INTERIORBALLISTICSF.R.HUNT1951MINISTRYOFDEFENSE./INTERIOR%20BALLISTICS%20F.R.HUNT%201951%20MINISTRY%20OF%20DEFENSE._djvu.txt
34. AMCP 706-247, Design for Projection [government]. https://archive.org/stream/AMCP706247DesignForProjection/AMCP%20706-247,%20Design%20for%20Projection_djvu.txt
35. Trębiński et al., "Identification of experimental form function using lumped parameter model" (poster, 32nd International Symposium on Ballistics) [peer-reviewed/conference]. https://www.ballistics.org/docs/posterISB32.pdf
36. "Estimation of Ignition Pressure in Ammunition", Energies 15 (2022) 5916 [peer-reviewed]. https://www.mdpi.com/1996-1073/15/16/5916 ; https://psecommunity.org/wp-content/plugins/wpor/includes/file/2303/LAPSE-2023.25161-1v1.pdf
37. Wurster et al. (2022), "Improved Burn Rate Measurement of Deterred Gun Propellants with Multivariate Size Distribution", Propellants Explos. Pyrotech. [peer-reviewed]. https://onlinelibrary.wiley.com/doi/full/10.1002/prep.202200043
38. "The Influence of Propellant Deterrent Concentration Profile on Combustion Performance", J. Phys.: Conf. Ser. 2478 (2023) 032020 [peer-reviewed]. https://iopscience.iop.org/article/10.1088/1742-6596/2478/3/032020
39. "Study on the analysis method on ballistic performance of deterred propellant with large web size in large caliber artillery", Defence Technology (2018) [peer-reviewed]. https://www.sciencedirect.com/science/article/pii/S2214914718302575
40. Robbins, Dale, Payne, Cothell, Ritchie (2021), "A User-Friendly and Fast Interior Ballistic Code for Performance Predictions of Deterred Propellants", Sandia [government]. https://www.sandia.gov/research/publications/details/a-user-friendly-and-fast-interior-ballistic-code-for-performance-prediction-2021-06-01/ ; https://www.osti.gov/servlets/purl/1872523
41. DTIC AD1008230 (deterred propellants, XKTC/IBHVG2, 5.56 mm ramp and ball deterrent profiles) [government]. https://apps.dtic.mil/sti/pdfs/AD1008230.pdf
42. "Treatment of Deterred Propellants in Interior Ballistic Calculations" (ResearchGate) [peer-reviewed/conference]. https://www.researchgate.net/publication/267231319_Treatment_of_Deterred_Propellants_in_Interior_Ballistic_Calculations
43. Jeunieau et al., "Characterization of Deterred Propellants by Closed Vessel Tests", CEJEM [peer-reviewed] [UNCERTAIN attribution]. https://wydawnictwa.ipo.lukasiewicz.gov.pl/wp-content/uploads/2021/06/Jeunieau.pdf
44. Wikipedia, "Ball propellant" [third-party]. https://en.wikipedia.org/wiki/Ball_propellant
45. Hodgdon H110 SDS (Ball Powder), NCFS-hosted [manufacturer]. https://ncfs.ucf.edu/powders/documents/powder%2000000371/Hodgdon_H110.pdf
46. General Dynamics OTS, Ball Powder® Propellants page and brochure [manufacturer]. https://www.gdots.com/propellants/ball-powder-propellants/ ; https://www.gdots.com/wp-content/uploads/2024/01/400002982-BALL-POWDER-Propellants-4.pdf
47. OpenReloading/Ballistics GitHub issue #360, "Interior model: test pressure-proportional bore friction and a start pressure that scales with bearing length" [third-party]. https://github.com/OpenReloading/Ballistics/issues/360
48. OpenReloading/Ballistics GitHub issue #944, "rifle start pressure by construction differs from the 30 MPa…" [third-party]. https://github.com/OpenReloading/Ballistics/issues/944
49. "Prediction of Shot Start Pressure for Rifled Gun System" (ResearchGate) [peer-reviewed]. https://www.researchgate.net/publication/323884718_Prediction_of_Shot_Start_Pressure_for_Rifled_Gun_System
50. AccurateShooter forum, "Bullet engraving Force study" [third-party]. https://forum.accurateshooter.com/threads/bullet-engraving-force-study.3958139/
51. South et al. (2009), "A Study of the Engraving of the M855 5.56-mm Projectile", ARL-TR-4743 [government]. https://apps.dtic.mil/sti/pdfs/ADA499555.pdf
52. Ritter & Beyer (2015), "Primer Output and Initial Projectile Motion for 5.56- and 7.62-mm Ammunition", ARL-TR-7479 [government]. https://apps.dtic.mil/sti/pdfs/ADA622138.pdf
53. He et al., 12.7 mm solid copper bullet engraving, Proc. Int. Symp. Ballistics (DPI) [peer-reviewed]. https://dpi-proceedings.com/index.php/ballistics25/article/view/37141
54. Courtney et al., arXiv:1604.01000 (solid copper and barrel friction) [peer-reviewed preprint] [UNCERTAIN attribution]. https://web3.arxiv.org/abs/1604.01000
55. "Electrothermal-Chemical (ETC) Extensions to IBHVG2", DTIC ADA276059 [government]. https://apps.dtic.mil/sti/tr/pdf/ADA276059.pdf
56. Goldstein, S. (1979), "Interior Ballistics Modeling Applied to Small Arms Systems", ARRADCOM, DTIC ADA076175 [government]. https://archive.org/stream/DTIC_ADA076175/DTIC_ADA076175_djvu.txt ; https://apps.dtic.mil/sti/tr/pdf/ADA076175.pdf
57. BRL Report No. 1183 (Dec 1962) [government]. https://apps.dtic.mil/sti/tr/pdf/AD0299980.pdf ; https://diverdi.colostate.edu/C477/experiments/interior%20ballistics%20of%20a%20cannon/references/ball_res_lab_1962_1183.pdf
58. Lane, J. R. (1938), BRL Report 104 (bore heating) [government]. https://apps.dtic.mil/sti/tr/pdf/AD0700971.pdf
59. Singh, "On heat transfer to gun barrel in some important guns", Defence Science Journal [peer-reviewed]. https://publications.drdo.gov.in/ojs/index.php/dsj/article/view/3704
60. DTIC AD0755111 (gun-tube heat transfer; Nordheim–Soodak–Nordheim) [government]. https://apps.dtic.mil/sti/pdfs/AD0755111.pdf
61. Ward & Brosseau, "Heat Transfer in Guns – Determination of Friction Factor from Heat Input Measurements" [government]. https://www.semanticscholar.org/paper/Heat-Transfer-in-Guns-Determination-of-Friction-Ward-Brosseau/ca4497ece82bb08e994bd80193219b628871548f
62. BRL-MR-3932, "Heating of a Tank Gun Barrel", DTIC ADA241136 [government]. https://apps.dtic.mil/sti/tr/pdf/ADA241136.pdf
63. Alzannan, K. Y. A., "Selection of suitable sub-models for improved confidence in lumped parameter internal ballistic codes", MSc thesis, North-West University [peer-reviewed thesis]. https://repository.nwu.ac.za/items/a78b42fa-c6ad-490b-8d1c-d71e605cece0 ; https://repository.nwu.ac.za/handle/10394/34389
64. STANAG 4367 (2012), "Thermodynamic Interior Ballistic Model with Global Parameters", catalogue listings [standard]. https://standards.globalspec.com/std/1686991/stanag-4367 ; https://www.intertekinform.com/en-gb/standards/stanag-4367-2012-736133_saig_nato_nato_1787993/ ; https://shop.standards.ie/en-ie/standards/stanag-4367-2012-736133_saig_nato_nato_1787993
65. DST Group TN-1655, "Development of a Fast Lumped Parameter Interior Ballistic…" [government]. https://www.dst.defence.gov.au/sites/default/files/publications/documents/DST-Group-TN-1655.pdf
66. Bougamra et al. (2014), "Multiphase CFD Simulation of Solid Propellant Combustion in a Small Gun Chamber", Int. J. Chem. Eng. [peer-reviewed]. https://onlinelibrary.wiley.com/doi/10.1155/2014/971808
67. Zieliński et al. (2022), Energies 15(5) 1868 (35 mm barrel heat transfer) [peer-reviewed]. https://www.mdpi.com/1996-1073/15/5/1868
68. Yagla & Anderson (2021), "Barrel Heating for Hot Gun Cook-Off: Thermal Analysis", NDIA [government/conference]. https://ndia.dtic.mil/wp-content/uploads/2021/imem/Yagla.pdf
69. OpenReloading/Ballistics GitHub issue #368, "Check the heat-loss and leak models against published gun and mortar results" [third-party]. https://github.com/OpenReloading/Ballistics/issues/368
70. Scribd upload of an Army thermochemical table (propellant-actuated devices) [government, third-party upload]. https://www.scribd.com/document/49461210/The
71. TB 9-1377-200 (TPub) [government]. https://chemical-biological.tpub.com/TB-9-1377-200/TB-9-1377-2000053.htm
72. alternatewars.com, "Military Propellants" [third-party compilation]. https://www.alternatewars.com/BBOW/Ballistics/Int/Propellants.htm
73. ARL report (GovInfo GOVPUB-D101-PURL-gpo1849), M1 thermodynamic data (BLAKE vs Virginia reference) [government]. https://www.govinfo.gov/content/pkg/GOVPUB-D101-PURL-gpo1849/pdf/GOVPUB-D101-PURL-gpo1849.pdf
74. EPA-hosted propellant chapter (military explosives/propellants manual excerpt) [government]. https://19january2021snapshot.epa.gov/sites/static/files/2015-05/documents/9530609-4.pdf
75. NASA NTRS 19710013221, heat of reaction of M-2 double-base propellant [government]. https://ntrs.nasa.gov/citations/19710013221
76. DTIC report on gun-propellant mechanical properties (M1, M8, M26, JA2, M30A2) [government] [UNCERTAIN attribution: one of] https://apps.dtic.mil/sti/pdfs/ADA425264.pdf ; https://apps.dtic.mil/sti/pdfs/ADA243045.pdf
77. DTIC reports with M30/M30A1 BLAKE values and IBHVG2 γ [government] [UNCERTAIN attribution: one of] https://apps.dtic.mil/sti/tr/pdf/ADA126130.pdf ; https://apps.dtic.mil/sti/tr/pdf/ADA187174.pdf ; https://apps.dtic.mil/sti/tr/pdf/ADA263014.pdf
78. Reload Swiss RS62 product page and datasheet [manufacturer]. https://www.reload-swiss.com/en/product/rifle/rs62-rifle-powder ; https://www.reload-swiss.com/Reload%20Swiss/Produkte/RS62/RS62-EN.pdf
79. Reload Swiss RS40 product page and datasheet [manufacturer]. https://www.reload-swiss.com/en/product/long-gun/rs40-rifle-powder ; https://www.reload-swiss.com/Reload%20Swiss/Produkte/RS40/RS40-EN.pdf
80. Reload Swiss RS50 product page and datasheet [manufacturer]. https://www.reload-swiss.com/en/product/rifle/rs50-rifle-powder ; https://www.reload-swiss.com/Reload%20Swiss/Produkte/RS50/RS50-EN.pdf
81. Reload Swiss RS52 product page [manufacturer]. https://www.reload-swiss.com/en/product/rifle/rs52-rifle-powder
82. Reload Swiss RS70 product page [manufacturer]. https://www.reload-swiss.com/en/reload_swiss/produkte/rs40_rifle_powder/rs70_rifle_powder/index.php
83. Reload Swiss brochure 2016 [manufacturer]. https://www.reload-swiss.com/Reload%20Swiss/Service/Brosch%C3%BCren%20und%20Produktdatenbl%C3%A4tter/RS_Brosch_e_2016.pdf
84. The Stalking Directory forum, "Swiss powder load data" (RS60 claims) [third-party]. https://www.thestalkingdirectory.co.uk/threads/swiss-powder-load-data.163832/
85. Vihtavuori, N500 High Energy Rifle Powders [manufacturer]. https://www.vihtavuori.com/powders/n500-powders/
86. Vihtavuori, "N565 – the new Vihtavuori High Energy powder" [manufacturer]. https://vihtavuori.com/n565-the-new-vihtavuori-high-energy-powder/
87. Vihtavuori Reloading Guide 2026 [manufacturer]. https://vihtavuori.com/wp-content/uploads/2026/04/Vihtavuori_Reloading_Guide_2026_ENG_web.pdf
88. Vihtavuori, N100 Smokeless Powders [manufacturer]. https://www.vihtavuori.com/powders/n100-powders/
89. Vihtavuori Reloading Guide 2022 [manufacturer]. https://www.vihtavuori.com/wp-content/uploads/2022/03/Vihtavuori_Reloading_Guide_2022_ENG.pdf
90. Vihtavuori SDS, N-Powder High Energy N500 series (2026) [manufacturer]. https://vihtavuori.com/wp-content/uploads/2026/08/N-Powder-High-Energy-N500-series-IP-19-01-2026-en.pdf
91. XXL Reloading, Vihtavuori N140 [third-party]. https://xxlreloading.com/powders/vihtavuori-n140
92. Vogelsanger (Nitrochemie), NDIA IMEM 2013, small-calibre propellants including EI® [manufacturer/conference]. https://ndia.dtic.mil/wp-content/uploads/2013/IMEM/W15931_Vogelsanger.pdf
93. Norma, reloading data and 203-B product page [manufacturer]. https://norma-ammunition.com/en-gb/reloading-data ; https://www.norma-ammunition.com/products/components/gunpowder/norma-203-b---20902035
94. Ammunition Reference Database, propellants (values judged unreliable; excluded) [third-party]. https://www.ammoreference.com/propellents.php?orderBy=Base
95. Sierra Bullets, "5.6 Muzzle Velocity Dependence on Cartridge Temperature" [manufacturer]. https://www.sierrabullets.com/?p=17413
96. Gun Digest, "Reloading: Temperature Sensitive Powder?" [third-party]. https://gundigest.com/gear-ammo/reloading/reloading-temperature-sensitive-powder
97. PrecisionRifleBlog (2025), "Powder temperature sensitivity" [third-party]. https://precisionrifleblog.com/2025/03/08/powder-temperature-sensitivity/
98. Guns & Ammo, "Rifle shooting and temperature effect" [third-party]. https://www.gunsandammo.com/editorial/rifle-shooting-and-temperature-effect/247890
99. American Rifleman, "Loading Bench: Hit The Mark, Weather Or Not" [third-party]. https://www.americanrifleman.org/content/loading-bench-hit-the-mark-weather-or-not/
100. Boulkadid et al. (2017), CEJEM, spherical single-base propellant temperature sensitivity [peer-reviewed]. https://yadda.icm.edu.pl/baztech/element/bwmeta1.element.baztech-b5741abc-ec02-486f-b599-482bace08206/c/Boulkadid_4_2017.pdf
101. Royal Military Academy (BE), "Local temperature sensitivity coefficients of a deterred spherical…" [peer-reviewed]. https://researchportal.rma.ac.be/en/publications/local-temperature-sensitivity-coefficients-of-a-deterred-spherica-2/
102. DTIC AD0265123 (closed-bomb temperature dependence, single vs double base) [government]. https://apps.dtic.mil/sti/tr/pdf/AD0265123.pdf
103. GRT wiki, propellant input fields (EN and DE) [third-party/software vendor]. https://grtools.de/doku.php?id=en:doku:inputfields-propellant ; https://grtools.de/doku.php?id=de:doku:inputfields-propellant
104. GRT wiki, "Table for relative burning rate" [third-party/software vendor]. https://grtools.de/doku.php?id=en:doku:burnratechart
105. GRT FAQ, "How accurate is the simulation?" [third-party/software vendor]. https://grtools.de/doku.php?id=en:faq:faq-simaccuracy
106. GRT wiki, powder temperature coefficient assistant [third-party/software vendor]. https://grtools.de/doku.php?id=en:doku:assist-powdertempcoeff
107. GRT FAQ, bulk density (Pcd) [third-party/software vendor]. https://grtools.de/doku.php?id=en:faq:faq-bulkdensity
108. GRT wiki, Optimal Barrel Time (OBT) [third-party/software vendor]. https://www.grtools.de/doku.php?id=grtools%3Aen%3Adoku%3Aobtconcept
109. GRT user manual 2021-09-29 (Scribd upload) [third-party upload of vendor doc]. https://www.scribd.com/document/866321500/grt-manual-2021-09-29-en
110. GRT FAQ, powder availability / reverse engineering [third-party/software vendor]. https://grtools.de/doku.php?id=grtools%3Aen%3Afaq%3Afaq-powderavailable
111. AccurateShooter forum, "Gathering Data for Powder Model Development – Gordon's Reloading Tool" [third-party]. https://forum.accurateshooter.com/threads/gathering-data-for-powder-model-development-gordons-reloading-tool.4072119/
112. Shooters Forum, "Reverse engineering powder for Gordons Reloading Tool" [third-party]. https://www.shootersforum.com/threads/reverse-engineering-powder-for-gordons-reloading-tool.245682/
113. Wikipedia, "QuickLOAD" [third-party]. https://en.wikipedia.org/wiki/QuickLOAD
114. QuickLOAD manual excerpt (third-party upload, kupdf) [third-party upload of vendor doc]. https://kupdf.net/download/div-class2qs3tf-truncatedtext-modulewrapperfg1km9p-classtruncatedtext-modulelineclamped85ulhh-style-max-lines5quickload-pdf-p-div_67550bb6b6d692cf5c8b456c_pdf
115. AccurateShooter forum, "QuickLOAD reverse engineering powder parameters for Accurate LT-30 and LT-32" [third-party]. https://forum.accurateshooter.com/threads/quickload-reverse-engineering-powder-parameters-for-accurate-lt-30-and-lt-32.4052451/
116. AccurateShooter forum, "QuickLoad Burn Rate Factor for H4895" [third-party]. https://forum.accurateshooter.com/threads/quickload-burn-rate-factor-for-h4895.3786825/
117. Wikipedia, "Grain (unit)" (cites NIST HB 44 and NIST General Tables) [third-party]. https://en.wikipedia.org/wiki/Grain_(unit)
118. QUDT, unit GRAIN [third-party/standards vocabulary]. https://qudt.org/vocab/unit/GRAIN.html
119. Wikipedia, "Pound (force)" [third-party]. https://en.wikipedia.org/wiki/Pound_(force)
120. NIST glossary, pound-force [government]. https://nist.gov/glossary-term/29611
121. Wikipedia, "Pound per square inch" [third-party]. https://en.wikipedia.org/wiki/Pound_per_square_inch
122. CRAN NISTunits, NISTpoundForcePerSqrInchTOpascal (cites NIST SP 811 App. B.8) [third-party citing government]. https://search.r-project.org/CRAN/refmans/NISTunits/html/NISTpoundForcePerSqrInchTOpascal.html
123. LibreTexts, "Properties of Water" (density table) [third-party/educational]. https://chem.libretexts.org/Bookshelves/Ancillary_Materials/Reference/Reference_Tables/Solvents/S2%3A_Properties_of_Water
124. Columbia University, water density table [third-party/educational]. https://www.columbia.edu/itc/chemistry/c2507/water_density.html
125. NBS Circular 19 (density of ethanol–water mixtures, 0% column) [government]. https://nvlpubs.nist.gov/nistpubs/Legacy/circ/nbscircular19.pdf
126. Wikipedia, "Copper units of pressure" [third-party]. https://en.wikipedia.org/wiki/Copper_units_of_pressure
127. AccurateShooter Bulletin, "CUP vs. PSI — What's The Difference in Pressure Measurements" [third-party]. https://bulletin.accurateshooter.com/?p=55409 ; https://bulletin.accurateshooter.com/?p=58576
128. Handloader Magazine, "From the Bench" (Bramwell CUP–psi regression) [third-party]. https://www.handloadermagazine.com/from-the-bench-1
129. Calculator Academy, CUP to PSI calculator [third-party, weak]. https://calculator.academy/cup-to-psi-calculator/
130. yarchive, "Copper units of pressure" [third-party]. https://yarchive.net/gun/ammo/copper_units_of_pressure.html
131. "Experimental techniques for ballistic pressure measurements…", J. Phys.: Conf. Ser. 459 (2013) 012048 [peer-reviewed]. https://iopscience.iop.org/article/10.1088/1742-6596/459/1/012048/pdf
132. "7.62-MM Primer/Propellant Interface Study", DTIC ADA341390 [government]. https://apps.dtic.mil/sti/tr/pdf/ADA341390.pdf
133. IBal2000 output file "7.62 MM M80 BALL – NATO REFERENCE" (engineering.com upload) [third-party]. https://files.engineering.com/files/f85e4f86-87e7-4447-88ad-ab841a0afc93/Interior_Ballistics.pdf
134. MKE, 7.62×51 Ball M80 datasheet [manufacturer]. https://www.mkeusa.com/en-US/catalogue/ammunition/762-mmx51-ball-m80/44/48
135. International Ammunition Association forum, "7,62 NATO pressure?" [third-party]. https://forum.cartridgecollectors.org/t/7-62-nato-pressure/14409
136. "Modeling of Ammunition Dynamic Pressure Measurement Chain in Ballistic Tests", Sensors 23 (2023) 8081 [peer-reviewed]. https://www.mdpi.com/1424-8220/23/19/8081 ; https://pmc.ncbi.nlm.nih.gov/articles/PMC10575385/
137. "Assessment of uncertainties in pressure and velocity measurements in ballistics using piezoelectric transducers and light screens", IJMQE (2026) [peer-reviewed]. https://www.metrology-journal.org/articles/ijmqe/full_html/2026/01/ijmqe250019/ijmqe250019.html
138. "Preliminary Comparative Investigations on Ballistic Properties of Intermediate Cartridges" (ResearchGate) [peer-reviewed]. https://www.researchgate.net/publication/348007657_Preliminary_Comparative_Investigations_on_Ballistic_Properties_of_Intermediate_Cartridges
139. Leciejewski et al., pressure-time curves in a 7.62 mm machine-gun barrel (ResearchGate figure) [peer-reviewed]. https://www.researchgate.net/figure/Pressure-time-curves-in-the-barrel-of-a-762-mm-machine-gun-the-theoretical-curves-are_fig10_225757848
140. Schmidt & Nusca (2009), "Progress Toward a Multidimensional Representation of the 5.56-mm Interior Ballistics", ARL-TR-4903 [government]. https://apps.dtic.mil/sti/pdfs/ADA508142.pdf
141. "Investigations of Middle-Caliber Anti-Aircraft Cannon Interior Ballistics including Heat Transfer Problem…", Processes 10 (2022) 607 [peer-reviewed]. https://mdpi.com/2227-9717/10/3/607/htm
142. Wikipedia, "Chamber pressure" [third-party]. https://en.wikipedia.org/wiki/Chamber_pressure
143. US Patent 6,386,028, "Pressure monitor" [patent]. https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/6386028
144. M80 load description (46 gr WC846, 146 gr bullet) [third-party] [UNCERTAIN attribution: one of] https://www.falfiles.com/threads/m80-ball-7-62-nato-specs.57139/ ; https://www.scribd.com/document/697213265/7-62mm-NATO-Ammunition-History
145. NWU repository document defining vivacity (dp/dt normalized by p_max) [peer-reviewed thesis] [UNCERTAIN attribution]. https://repository.nwu.ac.za/bitstreams/b1db9bb0-aea5-4e08-b6e2-ea50cd85802c/download
146. Grain-shape degressivity CFD study and 3-D IB model accuracy [peer-reviewed] [UNCERTAIN attribution: one of] https://www.sciencedirect.com/science/article/abs/pii/S0016236115000411 ; https://www.mdpi.com/2227-7390/9/21/2714
147. "Internal and transitional ballistic solution for spherical and perforated propellants and verification with experimental results" (Résal-based; 79% and 87% burnt at end of cycle) [peer-reviewed]. https://dergipark.org.tr/tr/download/article-file/400698
148. CEJEM paper distinguishing temperature sensitivity (propellant) from temperature coefficient (weapon) [peer-reviewed] [UNCERTAIN attribution]. https://yadda.icm.edu.pl/baztech/element/bwmeta1.element.baztech-5e3e77b5-b77a-46fa-aa4b-a6f23de57925/c/433-448_cejem_16_3.pdf
149. DTIC ADA028851 (Army report on composite charges; energy-loss categories) [government] [UNCERTAIN attribution]. https://apps.dtic.mil/sti/pdfs/ADA028851.pdf
150. hammerbullets forum, James A. Boatright thread (QuickLOAD shot-start default) [third-party] [UNCERTAIN attribution]. https://hammerbullets.boards.net/thread/1037/james-boatright
151. yarchive, "Bullet engraving force (Steven R Faber)" [third-party] [UNCERTAIN attribution]. https://www.yarchive.net/gun/engraving_force.html
152. Forum threads on surplus ball powders (WC844/WC846/WC860/WC872 relationships) [third-party] [UNCERTAIN attribution: one of] https://www.shootersforum.com/threads/powders.91641/ ; https://forum.nosler.com/threads/reloading-with-surplus-and-other-non-canister-powders.11580/

---

## 13. Open items for the next pass (needs page access)
1. Read the IBHVG2 user's guide [17] (archive.org full text) and transcribe the Black & Comenetz heat-loss equations, the resistance table input, and the gauge-pressure gradient formula.
2. Read Corner [32] §2 (form functions, χ, λ, μ, sliver functions), §10.41 (heat loss) and the Lagrange distribution. Then confirm or correct the [DERIVED] table in 4.2.
3. Read AMCP 706-150 [8] ch. 2 to confirm the Résal form and the φ definition.
4. Open the MDPI Sensors 2023 paper [136] and digitize its 7.62×51 p(t) curve, and establish whether it is measured or theoretical.
5. Search ADI, Shooters World, Hodgdon/IMR, Alliant and Norma technical sheets for heat of explosion and bulk density. The search budget ran out before these.
6. Identify the primary source behind the 24–44 MPa engraving-pressure figures in [47].
7. Find gun-propellant pressure exponents n for small-arms powders.
