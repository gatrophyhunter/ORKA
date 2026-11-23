#!/usr/bin/env python3
"""Extract interior-ballistics physics constants/equations from public primary
references (archive.org full-text OCR pages) for ORKA research item
"physics-primary".

Deterministic: reads the archive.org "stream" full-text pages (downloading them
with plain curl if missing), extracts the OCR text from the <pre> block, then
locates every record by an exact anchor string, captures the verbatim lines
(whitespace-collapsed) as evidence, parses the numbers out of that evidence
with regular expressions, and finds the printed page number from the page
markers present in the OCR text.

Only archive.org text pages are used: archive.org download/data nodes
(*.us.archive.org, *.ca.archive.org) and apps.dtic.mil are blocked from this
container, so PDFs/page images could not be read. Wherever the OCR of an
equation is garbled, the record says so ("status") and the "reading" field is
an explicitly-labelled interpretation, never a value from memory.

Run:  python3 -I scripts/extract/physics-primary.py
Outputs: research/raw2/physics-primary.json and research/raw2/physics-primary.md
"""
import html
import json
import math
import os
import random
import re
import subprocess
import sys
import time

REPO = "/home/user/ORKA"
SRC = "/tmp/claude-0/-home-user-ORKA/29ce603d-ccc3-55ef-b8fe-c585397ac7c1/scratchpad/sources/physics-primary"
OUT_JSON = os.path.join(REPO, "research/raw2/physics-primary.json")
OUT_MD = os.path.join(REPO, "research/raw2/physics-primary.md")
RETRIEVED = "2026-11-23"

DOCS = {
    "ibhvg2": {
        "url": "https://archive.org/stream/DTIC_ADB117104/DTIC_ADB117104_djvu.txt",
        "details": "https://archive.org/details/DTIC_ADB117104",
        "html": "ibhvg2_stream.html",
        "title": "Anderson, R. D. & Fickie, K. D., IBHVG2 - A User's Guide, BRL-TR-2829 (DTIC ADB117104), US Army Ballistic Research Laboratory",
        "date": "1987-07",
        "type": "government",
        "pages": "bottom_int",
    },
    "etc_ibhvg2": {
        "url": "https://archive.org/stream/DTIC_ADA276059/DTIC_ADA276059_djvu.txt",
        "details": "https://archive.org/details/DTIC_ADA276059",
        "html": "etc_ibhvg2_stream.html",
        "title": "Earnhart, J., Winsor, N. & Wren, G. P., Electrothermal-Chemical (ETC) Extensions to IBHVG2 With a New User's Tutorial, ARL-TR-348 (DTIC ADA276059), US Army Research Laboratory",
        "date": "1994-01",
        "type": "government",
        "pages": "bottom_int",
    },
    "amcp706150": {
        "url": "https://archive.org/stream/DTIC_AD0462060/DTIC_AD0462060_djvu.txt",
        "details": "https://archive.org/details/DTIC_AD0462060",
        "html": "amcp706150_stream.html",
        "title": "AMCP 706-150, Engineering Design Handbook, Ballistics Series: Interior Ballistics of Guns (DTIC AD0462060), US Army Materiel Command",
        "date": "1965-02",
        "type": "government",
        "pages": "bottom_chap",
    },
    "corner": {
        "url": "https://archive.org/stream/THEORYOFTHEINTERIORBALLISTICSOFGUNS.J.CORNERPHD._201611/THEORY+OF+THE+INTERIOR+BALLISTICS+OF+GUNS.+J.CORNER+PHD._djvu.txt",
        "details": "https://archive.org/details/THEORYOFTHEINTERIORBALLISTICSOFGUNS.J.CORNERPHD._201611",
        "html": "corner_stream.html",
        "title": "Corner, J., Theory of the Interior Ballistics of Guns, John Wiley & Sons, New York",
        "date": "1950",
        "type": "third-party",
        "pages": "header",
    },
    "hunt": {
        "url": "https://archive.org/stream/INTERIORBALLISTICSF.R.HUNT1951MINISTRYOFDEFENSE./INTERIOR%20BALLISTICS%20F.R.HUNT%201951%20MINISTRY%20OF%20DEFENSE._djvu.txt",
        "details": "https://archive.org/details/INTERIORBALLISTICSF.R.HUNT1951MINISTRYOFDEFENSE.",
        "html": "hunt_stream.html",
        "title": "Hunt, F. R. W. (ed.), Internal Ballistics, HMSO (Ministry of Supply / Ministry of Defence, UK)",
        "date": "1951",
        "type": "government",
        "pages": "header",
    },
    "stiefel": {
        "url": "https://archive.org/stream/DTIC_ADA086093/DTIC_ADA086093_djvu.txt",
        "details": "https://archive.org/details/DTIC_ADA086093",
        "html": "smallarms_props_stream.html",
        "title": "Stiefel, L., Thermochemical and Burning Rate Properties of Deterred US Small Arms Propellants, ARSCD-TR-80005 (DTIC ADA086093), US Army ARRADCOM",
        "date": "1980-06",
        "type": "government",
        "pages": "bottom_int",
    },
    "goldstein": {
        "url": "https://archive.org/stream/DTIC_ADA076175/DTIC_ADA076175_djvu.txt",
        "details": "https://archive.org/details/DTIC_ADA076175",
        "html": "goldstein_stream.html",
        "title": "Goldstein, S., Interior Ballistics Modeling Applied to Small Arms Systems, ARSCD-TR-79001 (DTIC ADA076175), US Army ARRADCOM",
        "date": "1979-06",
        "type": "government",
        "pages": "bottom_int",
    },
}

ITEMS = [
    {"item": "a", "status": "resolved-partial",
     "summary": "IBHVG2 heat-loss model structure (Black & Comenetz / Nordheim-Soodak-Nordheim + h0, thin shell, Newton cooling) and all $HEAT defaults (clean via ARL-TR-348 SI list) resolved; gauge (CLEN/NGAG/GLOC/GRAD) and $RES1 resistance inputs resolved; equations C.01-C.22 and D.16-D.27 are only partly legible in the OCR (D.18/D.21 errata illegible)."},
    {"item": "b", "status": "resolved",
     "summary": "Resal/Taylor energy equation with M = [(1+theta)W + C/3]/g, theta = 0.05, heat loss via adjusted gamma (f ~ 0.15, larger in small arms), u = 17.5 and eta = 27.7 in3/lb; heat-transfer eqs 3-1..3-3 (lambda = (13.2 + 4 log10 d_cm)^-2, checked by worked example); Lagrange p(y) quadratic distribution from Hunt eqs 7,06/7,07/7,13 and Corner eq. 13. AMCP's own eqs 5-1..5-7 garbled."},
    {"item": "c", "status": "partial",
     "summary": "Hunt sec. 6.10 and Corner sec. 10.41 Thornhill formulas located and partly transcribed (0.38, 0.6, C^0.8375, d^1.5, roughness 1.25 guns / 1.4+ small arms, eq. 41/42 checked); the d exponent in the denominator and Corner's H/theta exponents are illegible in the OCR."},
    {"item": "d", "status": "resolved",
     "summary": "Hunt 1951 Table 1.01 densities at 20 C: single-base 1.57-1.62 g/cm3 (NCT, NH, FNH/P), double-base cordites 1.54-1.61 g/cm3; AMCP generic 17.5 in3/lb = 1.58 g/cm3. 1940s gun propellants, not modern canister powders."},
    {"item": "e", "status": "partial",
     "summary": "n: small-arms ball-propellant closed-bomb constant-exponent n = 0.8053 (Riefler & Lowery via Stiefel 1980; one OCR variant 0.8033); gun-propellant alpha 0.8-0.9 (AMCP), ~0.9 (Corner), per-propellant Hunt Table 5.01. K1: only artillery-oriented values (AMCP 1+theta = 1.05; Hunt 1.05 w + C/3; Corner rotation m 1.005-1.02); no small-arms K1 found."},
]

BLOCKED = [
    "https://apps.dtic.mil/ (robots.txt and PDFs answered 'The request is blocked' WAF page; not circumvented)",
    "https://dn720003.ca.archive.org/0/items/DTIC_ADB117104/DTIC_ADB117104.pdf (archive.org data node; proxy CONNECT 403)",
    "https://ia600409.us.archive.org/BookReader/BookReaderImages.php?id=DTIC_ADB117104 (archive.org page images; proxy CONNECT 403)",
    "https://diverdi.colostate.edu/ (host not on the allowed list; copies of AMCP 706-150 and BRL-TR-2829)",
]


# --------------------------------------------------------------------------
# download + text extraction
# --------------------------------------------------------------------------
def ensure_doc(key):
    d = DOCS[key]
    path = os.path.join(SRC, d["html"])
    if not os.path.exists(path) or os.path.getsize(path) < 1000:
        os.makedirs(SRC, exist_ok=True)
        time.sleep(1.5)  # >= 1 s between requests; archive.org robots.txt has no Crawl-delay
        subprocess.run(["curl", "-sS", "-m", "180", "-o", path, d["url"]], check=True)
    raw = open(path, encoding="utf-8", errors="replace").read()
    m = re.search(r"<pre[^>]*>(.*?)</pre>", raw, re.S)
    if not m:
        raise SystemExit("no <pre> block in %s" % path)
    text = html.unescape(m.group(1))
    txt_path = os.path.join(SRC, key + "_ocr.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)
    d["localPath"] = path
    d["textPath"] = txt_path
    return text.split("\n")


def ws(s):
    return re.sub(r"\s+", " ", s).strip()


# --------------------------------------------------------------------------
# page markers
# --------------------------------------------------------------------------
def page_markers(lines, mode):
    out = []
    for i, ln in enumerate(lines):
        s = ws(ln)
        if mode == "bottom_int":
            if re.fullmatch(r"\d{1,3}", s):
                out.append((i, s))
        elif mode == "bottom_chap":
            if re.fullmatch(r"\d-\d{1,2}", s):
                out.append((i, s))
        elif mode == "header":
            m = (re.fullmatch(r"(\d{1,3})", s)
                 or re.fullmatch(r"(\d{1,3}) [A-Z][A-Za-z ,'’\-]{6,}", s)
                 or re.fullmatch(r"[A-Z][A-Za-z ,'’\-]{6,} (\d{1,3})", s))
            if m:
                out.append((i, m.group(1)))
    return out


def _nonempty(lines, i, step):
    j = i + step
    while 0 <= j < len(lines):
        if ws(lines[j]):
            return ws(lines[j])
        j += step
    return ""


def hunt_header(lines, i):
    """Hunt 1951 running heads: even pages 'NN INTERNAL BALLISTICS' (sometimes the
    number and title on separate lines); odd pages '<CHAPTER TITLE IN CAPS> NN'."""
    s = ws(lines[i])
    m = re.fullmatch(r"(\d{1,3}) INTERNAL BALLISTICS", s)
    if m:
        return int(m.group(1))
    m = re.fullmatch(r"[A-Z][A-Z ,'’\-]{5,} (\d{1,3})", s)
    if m:
        return int(m.group(1))
    if re.fullmatch(r"\d{1,3}", s):
        nxt, prv = _nonempty(lines, i, 1), _nonempty(lines, i, -1)
        if nxt == "INTERNAL BALLISTICS" or re.fullmatch(r"[A-Z][A-Z ,'’\-]{5,}", prv) and prv != "INTERNAL BALLISTICS":
            return int(s)
    return None


def hunt_page(lines, idx):
    back = None
    for i in range(idx, -1, -1):
        p = hunt_header(lines, i)
        if p is not None:
            back = (p, i)
            break
    fwd = None
    for i in range(idx + 1, len(lines)):
        p = hunt_header(lines, i)
        if p is not None:
            fwd = (p, i)
            break
    # accept the preceding running head when the next one is 1 or 2 pages on
    # (a head can be missing from the OCR); otherwise trust the next head - 1.
    if back and fwd and 1 <= fwd[0] - back[0] <= 2:
        return str(back[0]), back[1]
    if fwd:
        return str(fwd[0] - 1), fwd[1]
    return (str(back[0]), back[1]) if back else (None, None)


def find_page(lines, markers, mode, idx):
    """bottom_*: printed page number is the first marker AFTER the evidence;
    header: it is the last marker BEFORE the evidence. Returns (page, marker_line)."""
    if mode.startswith("bottom"):
        for i, p in markers:
            if i >= idx:
                return p, i
        return None, None
    best = (None, None)
    for i, p in markers:
        if i <= idx:
            best = (p, i)
        else:
            break
    return best


# --------------------------------------------------------------------------
# numeric parsing helpers
# --------------------------------------------------------------------------
def num(tok):
    """Plain float; None if the token is not a clean number."""
    t = tok.strip()
    if re.fullmatch(r"-?\d+(\.\d+)?([eE]-?\d+)?", t):
        return float(t)
    return None


def hunt_dec(tok):
    """Hunt prints a raised decimal point which the OCR renders as '-', '·',
    '*' or a space: '1-58', '1 -59', '0*5'. Tokens whose separator was lost
    entirely (e.g. '105', '017') are NOT interpreted: value None."""
    t = tok.strip()
    m = re.fullmatch(r"(\d+)\s*[-·*]\s*(\d+)", t)
    if m:
        return float(m.group(1) + "." + m.group(2))
    return None


# --------------------------------------------------------------------------
# record specifications
#   anchor: exact substring of a whitespace-collapsed OCR line
#   n: number of non-empty lines captured (anchor line included)
#   values: list of (name, regex on evidence, unit, parser) ; group(1) is the token
# --------------------------------------------------------------------------
F = num
RAW = None  # keep token as raw string only

SPECS = [
    # ---------------- (a) IBHVG2 -------------------------------------------
    dict(id="a01", item="a", doc="ibhvg2", topic="IBHVG2 heat-loss routine is the Black & Comenetz treatment",
         anchor="calculate heat-loss rate from treatment of Black and Comenetz", n=2,
         values=[], status="legible",
         reading="Subroutine HIRATE: 'calculate heat-loss rate from treatment of Black and Comenetz in Chap. 5, vol. 1 of NDRC hypervelocity report (See Reference [7])'."),
    dict(id="a02", item="a", doc="ibhvg2", topic="IBHVG2 references [7] Black & Comenetz and [8] Nordheim-Soodak-Nordheim",
         anchor="[7] H.L. Black and G. Com", n=6,
         values=[], status="legible",
         reading="[7] H.L. Black and G. Comenetz, 'Heating of Guns During Firing', Hypervelocity Guns and the Control of Gun Erosion, Summary Technical Report of Division 1, NDRC, J.S. Burlew (ed.), 1946. [8] L.W. Nordheim, H. Soodak, G. Nordheim, 'Thermal Effects of Propellant Gases in Erosion Vents and in Guns', Armor and Ordnance Report A-262 (OSRD No. 3447), 1944. Neither primary report was found on an allowed host in this pass."),
    dict(id="a03", item="a", doc="ibhvg2", topic="IBHVG2 $HEAT input deck: variables and defaults (English units, OCR)",
         anchor="For heat-loss-related variables, namely", n=16,
         values=[("TSHL_default_in", r"tube shell thickness for heat sink \[in \) \(default \S+ (0\.004)", "in", F),
                 ("CSHL_default_raw", r"shell specific heat lin—lbf/lbm—K\) covering a broad range of\s*\n?\s*steels \[default - (\S+)\]", "in-lbf/lbm-K", RAW),
                 ("RSHL_default_raw", r"shell material density .*?\[default \S+ (0\.\d+)\)", "lbm/in3", RAW),
                 ("TWAL_default_K", r"initial wall tempera.*?\[default \S+ (\d+\.\d)\)", "K", F),
                 ("HO_default_raw", r"free convective heat transfer coefficient for air in the tube\s*\n?\s*/in\*~sec~/C\) \[default \S+ (0\.\d+)\)", "lbf/in-sec-K (unit OCR-garbled)", RAW)],
         status="ocr_ambiguous",
         reading="$HEAT deck: TSHL tube-shell thickness for heat sink [in] default 0.004; CSHL shell specific heat [in-lbf/lbm-K] 'covering a broad range of steels' (OCR '1S48.0'); RSHL shell material density [lbm/in3] (OCR '0.244'); TWAL initial wall temperature [K] default 293.0; HO free-convective heat-transfer coefficient for air in the tube (OCR '0.0048'); HL = 0 ignore heat losses in energy balance, 1 (default) include. The CSHL/RSHL/HO OCR tokens are resolved against ARL-TR-348 (record a04) in 'conflicts'.",
         page_note="Deck description follows the page-10 marker; printed page markers 11-13 are absent from the OCR, so the page is the first page after p. 10 (inferred).",
         page_override="11"),
    dict(id="a04", item="a", doc="etc_ibhvg2", topic="IBHVG2 $HEAT input defaults in SI (ARL-TR-348 input reference)",
         anchor="For heat-loss-related variables, namely", n=15,
         values=[("TSHL_default_m", r"tube shell thickness for heat sink \[m\] \[default = ([\d.]+)\]", "m", F),
                 ("CSHL_default_J_per_kgK", r"\[default s ([\d.]+)\]", "J/kg-K", F),
                 ("RSHL_default_kg_per_m3", r"shell material density \(kg/m3\) \(default = ([\d.]+)\)", "kg/m3", F),
                 ("TWAL_default_K", r"initial wall temperature \[K\] \(default = ([\d.]+)\]", "K", F),
                 ("HO_default_W_per_m2K", r"\[W/m2-K\] \(default = ([\d.]+)\]", "W/m2-K", F)],
         status="legible",
         reading="TSHL = 0.0001016 m, CSHL = 460.316318 J/kg-K, RSHL = 7861.0916 kg/m3, TWAL = 293.0 K, HO = 11.34821852 W/m2-K, HL = 1 (include heat loss) by default."),
    dict(id="a05", item="a", doc="etc_ibhvg2", topic="ARL-TR-348 prose: HO default 11.35 W/m2-K, thin-shell heat sink, TWAL 293 K",
         anchor="3-8 SHEAT Deck. Heat loss from the combustion gases", n=6,
         values=[("HO_default_prose", r"HO \(default is (1 1\.35) W/m2- K\)", "W/m2-K", RAW)],
         status="legible",
         reading="'Heat is transferred from the combustion gases to the barrel through a convective heat transfer coefficient, HO (default is 11.35 W/m2-K)'; heat sink modelled as a thin shell; shell initially at TWAL = 293 K. (OCR '1 1.35' has a stray space.)"),
    dict(id="a06", item="a", doc="ibhvg2", topic="IBHVG2 heat-loss model: thin shell, Newton's law of cooling (eqs D.16-D.17)",
         anchor="The last energy loss considered is that due to heat transfer to the gun barrel", n=13,
         values=[], status="reconstructed",
         reading="Verbatim prose: a metal shell of thickness delta, initially at T0, surrounds the system; it is assumed to come to thermal equilibrium instantaneously radially and axially as projectile motion exposes more shell; heat-transfer rate proportional to (mean gas temperature T_mean - average shell temperature T_w) by Newton's law of cooling. READING of the OCR-garbled D.16/D.17 (verify on page image): Q = integral of Qdot dt, Qdot = A_w * h * (T_mean - T_w).",
         page_note="Equations D.16-D.27 span printed pp. 48-50; the OCR lacks the p. 48 and p. 49 markers (errata places D.18 and D.21 on p. 49).",
         page_override="48-49"),
    dict(id="a07", item="a", doc="ibhvg2", topic="IBHVG2 wetted area and heat-transfer coefficient (eqs D.18-D.20): Nordheim-Soodak-Nordheim plus natural-convection term h0",
         anchor="where the wall area of the shell exposed to the system is that of the chamber plus that which", n=15,
         values=[("friction_factor_const_Z", r"A- (13\.2) \+41ofio", "-", F),
                 ("friction_factor_log_term_raw", r"13\.2 (\+41ofio)", "-", RAW),
                 ("friction_factor_argument_raw", r"\n(\[i\* Dfc\]J)\n", "-", RAW)],
         status="reconstructed",
         reading="Wall area = chamber wall area + bore area uncovered by projectile travel (D.18; errata sheet gives a corrected D.18 that is illegible in the OCR). h = lambda*c_p*rho_m*v_m + h0 (D.19, READING of OCR 'A - A Cpfif +h.'), i.e. Nordheim, Soodak & Nordheim [8] 'with the addition of a natural convective term, h0, to allow heat transfer in the absence of projectile motion'. Friction factor (D.20) READING: lambda = [13.2 + 4*log10(<bore diameter term>)]^-2, 'based on studies with rifled and unrifled tubes'; the argument and exponent are illegible in the OCR ('[i* Dfc]J'). AMCP 706-150 eq. 3-3 (record b10) gives the same constants with d in cm.",
         page_override="49", page_note="Errata sheet: D.18 is on p. 49."),
    dict(id="a08", item="a", doc="ibhvg2", topic="IBHVG2 mean gas velocity, density and c_p for the heat-transfer coefficient (D.21-D.24)",
         anchor="based on studies with rilled and unrilled tubes. The mean gas velocity is", n=9,
         values=[], status="reconstructed",
         reading="Mean gas velocity (D.21) is taken 'from the linear gas velocity distribution in the Lagrange model (C.06)' (errata: D.21 corrected, illegible in OCR). Mean gas density (D.22) = 'total weight of propellant burned divided by the volume of the system'. c_p (D.23-D.24) = 'charge-weight-burned weighted average' over the propellants.",
         page_override="49", page_note="Errata sheet: D.21 is on p. 49."),
    dict(id="a09", item="a", doc="ibhvg2", topic="IBHVG2 shell heat balance and shell temperature (D.25-D.27); friction pre-heating fraction",
         anchor="At any instant, the heat already transfered to the shell is", n=11,
         values=[], status="reconstructed",
         reading="Heat in shell = Q + f*E_fr (D.25/D.26) where 'f is that fraction of work done against bore friction which pre-heats the shell' (input HTFR, record a11). READING of OCR-garbled D.27: T_w = (Q + f*E_fr)/(c_w*rho_w*A_w*delta) + T0, i.e. shell temperature from its heat capacity, density, thickness and exposed area (the prose says 'Knowledge of the heat capacity, density, and thickness of the shell permit calculation of the temperature of the shell').",
         page_override="49-50", page_note="D.27 precedes the p. 50 marker; D.25 follows D.24 on p. 49 (inferred)."),
    dict(id="a10", item="a", doc="ibhvg2", topic="IBHVG2 errata for the heat-loss equations",
         anchor="49 Equation (D. 18) should be:", n=3, page_override='errata sheet (unnumbered front matter)', page_note='Errata sheet bound before the report documentation page; it lists corrections for printed p. 49.',
         values=[], status="illegible",
         reading="The errata sheet replaces equations D.18 and D.21 (p. 49); the replacement equations are illegible in the OCR. Any transcription of D.18/D.21 must use the errata version from a page image."),
    dict(id="a11", item="a", doc="ibhvg2", topic="IBHVG2 bore-resistance input deck $RES1",
         anchor="This precedes resistance pressure inputs. The variables are:", n=13,
         values=[("NPTS_max", r"number of travel/pressure pairs \[min \S+ 0, max - (\d+)\]", "-", F),
                 ("TRAV_array_size", r"projectile travel array of size (\d+) \[in \)", "-", F),
                 ("PRES_array_size", r"resistance pressure array of size (\d+) \[psi \]", "-", F),
                 ("HTFR_default", r"\[default \* (0\.0)\]", "-", F)],
         status="legible",
         reading="$RES1: NPTS = number of travel/pressure pairs (0..20); TRAV = projectile travel array [in]; PRES = resistance pressure array [psi]; AIR = 0 suppress / 1 include air resistance (default 1); HTFR = fraction of work done against barrel resistance used to pre-heat the tube wall, 0 < HTFR < 1, default 0.0."),
    dict(id="a12", item="a", doc="ibhvg2", topic="IBHVG2 bore resistance in the model: tabular P_r(x) and work integral (D.13)",
         anchor="Currently, IBHVG2 requires tabular input of barrel frictional resistance pressure", n=6,
         values=[], status="legible",
         reading="Barrel frictional resistance pressure is tabular input vs projectile displacement; 'These resistance profiles have been experimentally determined from measurements of force required to push projectiles through gun tubes or ... via instrumented projectiles'. Work against resistance E_r = A * integral P_r(x) dx (D.13, READING; the OCR of the integral is garbled), displacement measured relative to the barrel.",
         page_override="47", page_note="Text precedes the p. 47 marker."),
    dict(id="a13", item="a", doc="ibhvg2", topic="IBHVG2 resistance interpolation and shot start",
         anchor="Resistance pressure due to engraving", n=3,
         values=[], status="legible",
         reading="'Resistance pressure due to engraving of the rotating band is interpolated from tabular resistance pressures as a function of the tube-referenced projectile displacement'. Subroutine SHOTGO 'set[s] a shot-start flag based on initial chamber pressures' (record a14). No separate shot-start-pressure input variable appears in the deck descriptions read; the first $RES1 point (TRAV=0) is the resistance at zero travel (inference from the deck definition, not an explicit statement)."),
    dict(id="a14", item="a", doc="ibhvg2", topic="IBHVG2 SHOTGO subroutine (shot start)",
         anchor="set a shot-start flag based on initial chamber pressures", n=2, page_override='37-38', page_note='Between the p. 36 and p. 38 markers; the p. 37 marker is absent from the OCR.',
         values=[], status="legible",
         reading="SHOTGO: 'set a shot-start flag based on initial chamber pressures and prepares for first search for maximum pressure'."),
    dict(id="a15", item="a", doc="ibhvg2", topic="IBHVG2 sample $RES1 resistance profile (155-mm test case, illustrative only)",
         anchor="NOMINAL PROJECTILE AND RESISTANCE PROFILE", n=7,
         values=[("PRWT_lb", r"PRWT-(\d+)", "lb", F),
                 ("TRAV_in_raw", r"TRAV-(0, 0\.3, 3\. 600)", "in", RAW),
                 ("PRES_psi_raw", r"PRES- (100, 4000, 1800, 800)", "psi", RAW)],
         status="legible",
         reading="Example deck (large-calibre plastic lab sabot, 52 lb): resistance 100 psi at 0 in, 4000 psi at 0.3 in, 1800 psi at 3 in, 800 psi at 600 in. Format illustration only; NOT a small-arms value."),
    dict(id="a16", item="a", doc="ibhvg2", topic="IBHVG2 gauge-location inputs (pressure at gauges)",
         anchor="effective chamber k", n=12,
         values=[("NGAG_max", r"number of gage locations \[default \S+ 0 x - (\d+)\]", "-", F)],
         status="ocr_ambiguous",
         reading="CLEN = effective chamber length [in] for scaling in-chamber pressure gauge locations (default = chamber volume / bore area); NGAG = number of gauge locations (default 0, max 30); GLOC = gauge location array [in], measured (+) downtube from the breech or (-) into the chamber from the initial position of the projectile base. ARL-TR-348 repeats this with GLOC in metres (max 30)."),
    dict(id="a17", item="a", doc="ibhvg2", topic="IBHVG2 gradient option",
         anchor="1 for Lagrange gradient", n=2, page_override='11', page_note='In the $INFO deck that follows $HEAT after the p. 10 marker; markers 11-13 absent from the OCR (inferred p. 11).',
         values=[], status="legible",
         reading="$INFO GRAD = 1 Lagrange gradient (default), 2 Pidduck-Kent gradient."),
    dict(id="a18", item="a", doc="ibhvg2", topic="IBHVG2 Lagrange gradient assumptions (section III.C)",
         anchor="We will consider two ways of calculating the pressure gradient", n=7,
         values=[], status="legible",
         reading="Lagrange approximation 'with the added assumption that the introduction of recoil does not appreciably disturb the gradient'; central assumptions: 'the entire charge may at any time be treated as gaseous - that is, all burned - and that the density of the gas is uniformly distributed along the gun tube at any given time'. Equations C.01-C.16 are illegible in the OCR."),
    dict(id="a19", item="a", doc="ibhvg2", topic="IBHVG2 Lagrange result and Pidduck-Kent option (C.16-C.22)",
         anchor="Thus, according to the Lagrange model, knowledge of the charge-to-pro jectile weight ratio", n=4,
         values=[], status="legible",
         reading="'according to the Lagrange model, knowledge of the charge-to-projectile weight ratio, the mean pressure, and the resistance pressures is sufficient to calculate the entire pressure gradient down the tube and, in particular, the desired base and breech pressures.' Pidduck-Kent option uses C/m, gamma and space-mean pressure; Pidduck-Kent constant fitted (Grollman & Baer, BRL Report 1519) as a fifth-order polynomial in charge-to-mass ratio scaled with gamma, max error 0.21% over gamma in [1.2, 1.3]."),
    dict(id="a20", item="a", doc="ibhvg2", topic="IBHVG2 Pidduck-Kent fit accuracy",
         anchor="surprisingly with ten parameters, the regression error is quite smalt", n=3,
         values=[("max_error_pct", r"maximum error was (0\.21)%", "%", F)],
         status="legible",
         reading="Fit max error 0.21% over gamma in [1.2, 1.3] (theta range OCR-garbled)."),
    dict(id="a21", item="a", doc="ibhvg2", topic="IBHVG2 energy-loss terms included in L(t)",
         anchor="The term L(i) in (A.09) comprises the total work done", n=9,
         values=[], status="legible",
         reading="L(t) includes: projectile translational KE, translational KE of propellant and gases, projectile rotational KE, recoiling-barrel KE, work against barrel friction, work against air resistance in the tube, heat lost to the gun tube. Neglected: barrel deformation energy, work against propellant-bed friction / gas friction on the wall."),
    dict(id="a22", item="a", doc="ibhvg2", topic="IBHVG2 projectile moment of inertia assumption",
         anchor="where the moment of inertia of the projectile is taken to be that of a solid cylinder of bore", n=3,
         values=[], status="legible",
         reading="Rotational KE uses I_p of a solid cylinder of bore diameter and uniform density for all projectiles; twist r in calibers per turn."),

    # ---------------- (b) AMCP 706-150 --------------------------------------
    dict(id="b01", item="b", doc="amcp706150", topic="AMCP 706-150 general energy equation (eq. 1-10) and gas equation of state (1-8)",
         anchor="P(U, - c-n) = cnRT (1-8)", n=16,
         values=[], status="reconstructed",
         reading="Eq. 1-8: P(U_c - c*eta) = c*n*R*T. Eq. 1-10 READING of OCR 'cF / P(.u. - crj) / + K / 7 - 1 7 - 1': c*F/(gamma-1) = P*(U_c - c*eta)/(gamma-1) + K, 'where K is the energy expended by the gas in the doing of work and in heat conducted to the gun'. U_c = actual gas volume, c = mass burned, eta = covolume, F = force (impetus)."),
    dict(id="b02", item="b", doc="amcp706150", topic="AMCP 706-150 energy equation statement (eq. 2-1) and internal energy (2-3)",
         anchor="The energy equation may be stated simply as", n=14, page_override='2-3', page_note="Between the 2-2 and 2-3 page markers (a spurious '7-1' OCR token was ignored).",
         values=[], status="reconstructed",
         reading="Eq. 2-1: T = K + I, T = energy released by the charge burned, K = work done by the gas plus energy lost by heating the barrel, I = internal energy of the gas. Eq. 2-3 READING: I = P(U_g - c*eta)/(gamma-1). Taylor system units: inch, pound (weight), second."),
    dict(id="b03", item="b", doc="amcp706150", topic="AMCP 706-150 gas + unburnt propellant kinetic energy (Lagrange)",
         anchor="an approximation cf Lagrange in which the density", n=8,
         values=[], status="reconstructed",
         reading="Lagrange approximation, density independent of position, 'may be used for ordinary velocities'; gas velocity linear from 0 at breech to V at the base; mean-square velocity V^2/3; hence kinetic energy of unburnt propellant and gas = C*V^2/(6g) (OCR 'CV 2/%'; READING consistent with mean-square V^2/3 and the C/3 term of eq. 2-11)."),
    dict(id="b04", item="b", doc="amcp706150", topic="AMCP 706-150 rotation and friction factors; effective mass (eqs 2-8 to 2-11) = secondary-work factor",
         anchor="For most guns, n is between 18 and 32 calibers", n=38,
         values=[("twist_calibers_low", r"n is between (\d+) and \d+ calibers", "calibers", F),
                 ("twist_calibers_high", r"n is between \d+ and (\d+) calibers", "calibers", F),
                 ("k_over_d_sq_solid_cylinder", r"\(k/d\)2 is (0\.125)", "-", F),
                 ("k_over_d_sq_HE_shell", r"it is about (0\.14)", "-", F),
                 ("rotation_factor_approx", r"\(2w k/nd\)2 is approximately (0\.01)", "-", F),
                 ("theta1_friction", r"The value of 9 , is usually cf the order\s*\n?\s*cf (0\.04)", "-", F),
                 ("theta_total", r"9 will be taken equal to (0\.05)", "-", F)],
         status="reconstructed",
         reading="Rotational KE factor (2*pi*k/(n*d))^2 ~ 0.01 (n 18-32 calibers, say 25; (k/d)^2 = 0.125 solid cylinder, ~0.14 HE shell). Friction/engraving work = theta1*W*V^2/(2g), theta1 ~ 0.04 ('equivalent to assuming that the resistance is proportional to the pressure'). Eq. 2-10: theta = (2*pi*k/(n*d))^2 + theta1, taken = 0.05. Eq. 2-11 (READING of OCR): M = [(1 + theta)*W + C/3]/g ('effective mass'). Recoil term dropped as negligible (ratio (W + C/2)/R ~ 0.02 for standard weapons). These are artillery-oriented values, not small-arms measurements."),
    dict(id="b05", item="b", doc="amcp706150", topic="AMCP 706-150 heat loss via adjusted gamma (eqs 2-12 to 2-14); f larger in small arms",
         anchor="It is customary to take account of the heat loss", n=28,
         values=[("f_heat_loss_typical", r"In practice / is about (0\.15)", "-", F),
                 ("taylor_adjusted_gamma", r"adjusted value cf y equal to\s*\n?\s*(1\.30)", "-", F)],
         status="reconstructed",
         reading="Eq. 2-13 READING: Q = f*M*V^2/2 (heat loss proportional to projectile-system KE). Eq. 2-14 READING: (gamma_bar - 1)/(gamma - 1) = 1 + f. 'In practice f is about 0.15 but may be considerably larger than this especially in small arms.' Taylor assumed adjusted gamma = 1.30. For detail see References 2 and 6 and Corner p. 141."),
    dict(id="b06", item="b", doc="amcp706150", topic="AMCP 706-150 free volume, propellant specific volume and covolume (eqs 2-16 to 2-18a)",
         anchor="The complete expression for the free volume is", n=34,
         values=[("u_specific_volume_in3_per_lb", r"The specific voluiiie of the propellant \(u\) is about\s*\n?\s*(17\.5) in3/lb", "in3/lb", F),
                 ("eta_covolume_in3_per_lb", r"is approximately (27\.7) in3/lb", "in3/lb", F),
                 ("eta_over_u", r"about (1\.5) times", "-", F)],
         status="reconstructed",
         reading="Eq. 2-16 READING: U = A*X + U_ch - C*u + c*(u - eta). Initial (2-17): U_0 = U_ch - C*u + c_0*(u - eta), c_0 = charge burned before shot start. u ~ 17.5 in3/lb (specific volume of solid propellant), eta ~ 27.7 in3/lb (covolume), ~1.5x; the handbook then assumes eta = u for simplicity, 'but its validity becomes questionable for high ratios of charge to chamber volume'."),
    dict(id="b07", item="b", doc="amcp706150", topic="AMCP 706-150 Taylor energy equation (eq. 2-19)",
         anchor="in Equation 2-1 the energy equation becomes", n=3,
         values=[], status="reconstructed",
         reading="READING of OCR 'Fc M V2 P / - 1 = - + 7TTT (AX + u« ~ Cu ) (2-19>': F*c/(gamma-1) = M*V^2/2 + P*(A*X + U_ch - C*u)/(gamma-1), with eta = u assumed and gamma the heat-loss-adjusted value. Built from eqs 2-1, 2-2, 2-12 and 2-18a as the handbook states."),
    dict(id="b08", item="b", doc="amcp706150", topic="AMCP 706-150 breech : mean : base pressure relation (eq. 2-20) and its restriction",
         anchor="the result in terms of the measured pressure. Pc", n=14,
         values=[], status="reconstructed",
         reading="Eq. 2-20 READING (OCR garbled): P_c : P : P_s = [1 + C/(2(1+theta)W)] : [1 + C/(3(1+theta)W)] : 1. Consistent with eq. 2-21 as OCR'd: P_s/P = (1+theta)W/((1+theta)W + C/3) = (1+theta)W/(M*g). VERBATIM restriction: 'This relation is an approximation based on a special solution of the Lagrange problem ... Its use is restricted to artillery weapons firing at moderate velocities. When applied to treatments of high velocity weapons or to small arms, it yields poor results.'"),
    dict(id="b09", item="b", doc="amcp706150", topic="AMCP 706-150 burning-rate law and exponent used in the Taylor system (eq. 2-27)",
         anchor="a is the burning rate pressure exponent, which is", n=2,
         values=[("alpha_assumed", r"here assumed to be (0\.8)\.", "-", F)],
         status="legible",
         reading="dc/dt = rho*S*B*P^alpha (eq. 2-27), alpha 'here assumed to be 0.8'; B 'should be determined for each type of propellant under actual conditions of use ... by adjusting its value for best fit of the theory to actual firing records'; closed-chamber B 'usually yield poor results when used in gun calculations'."),
    dict(id="b10", item="b", doc="amcp706150", topic="AMCP 706-150 heat-transfer coefficient (Nordheim, Soodak & Nordheim): eqs 3-1 to 3-3",
         anchor="heat transfer equation", n=14,
         values=[], status="reconstructed",
         reading="Eq. 3-1: H' = h*(theta_g - theta_s) (H' time rate of heat flow per area, theta_g gas temperature beyond the boundary layer, theta_s surface temperature)."),
    dict(id="b11", item="b", doc="amcp706150", topic="AMCP 706-150 h = 0.5*lambda*Cp*rho*v and lambda for caliber .50",
         anchor="was adopted by the investigators, namely", n=30,
         values=[("h_coefficient", r"h = (0\.5) \\Cppv \(3-2\)", "-", F),
                 ("lambda_cal50_MG_raw", r"equal approximately to (5 X 10-3)", "-", RAW)],
         status="reconstructed",
         reading="Eq. 3-2: h = 0.5*lambda*C_p*rho*v (C_p gas specific heat at constant pressure, rho and v gas density and velocity; Reynolds analogy). lambda = friction factor, 'must be determined by comparison with experiment'. From calorimetric measurements just beyond the forcing cone of a caliber .50 machine gun (Machler), lambda ~ 5 x 10^-3; unburnt propellant assumed uniformly distributed in the gas."),
    dict(id="b12", item="b", doc="amcp706150", topic="AMCP 706-150 friction factor vs caliber (eq. 3-3) and 105-mm example",
         anchor="ou licat transfer in pipes was modified aiid stated", n=11,
         values=[("Z_constant", r"Z has the value\s*\n?\s*(13\.2)", "-", F)],
         status="reconstructed",
         reading="Eq. 3-3 READING of OCR 'X = (Z + 4 log,,, tf)'2': lambda = (Z + 4*log10 d)^-2, d = caliber in centimetres, Z = 13.2 (empirical). 'This formula asserts that lambda depends only on d. Later experiment has shown that this is not so ... The validity of Equation 3-3 is doubtful, but it will be used here.' Worked example (record b13): d = 10.5 cm gives lambda = 1/300."),
    dict(id="b13", item="b", doc="amcp706150", topic="AMCP 706-150 worked example: lambda = 1/300 for d = 10.5 cm; h values",
         anchor="By Equation 3-3, with", n=26,
         values=[("Z", r"Z = (13\.2)", "-", F),
                 ("d_cm", r"id = (10\.5) cm", "cm", F),
                 ("lambda_result_raw", r"X = (1/300)", "-", RAW),
                 ("Cp_raw", r"C„ equal to (199) cal Tb-°K", "cal/lb-K (OCR 'cal Tb-°K')", RAW),
                 ("h_chamber", r"h = (0\.187) eal/in", "cal/in2-s-K", F),
                 ("h_muzzle", r"h = (1\.493) eal/in2", "cal/in2-s-K", F)],
         status="legible",
         reading="105-mm howitzer example: Z = 13.2, d = 10.5 cm -> lambda = 1/300; C_p = 199 cal/lb-K; h = 0.187 cal/in2-s-K at the front of the chamber, 1.493 at the muzzle. Large-calibre example; used here only to check eq. 3-3."),
    dict(id="b14", item="b", doc="amcp706150", topic="AMCP 706-150 Lagrange/Pidduck-Kent relations: validity statement (sec. 5-1.1)",
         anchor="The Pidduck-Kent solutions for the pressure and", n=10,
         values=[], status="legible",
         reading="'When all the terms in the expansions beyond those in the first power of e are dropped, Equations 5-1, 5-2 and 5-3 result. These equations are, therefore, only valid, even as approximations, for small values of e - that is, for relatively low velocity guns.' (e = C/M). Equations 5-1..5-7 themselves are OCR-garbled."),

    # ---------------- Lagrange p(y): Hunt & Corner ---------------------------
    dict(id="b15", item="b", doc="hunt", topic="Hunt 1951: equation of motion with W = 1.05 w (eq. 7,01)",
         anchor="where W = T05 w and p, is the pressure on the base of the shot", n=1, page_override='74', page_note='Chapter VII opens on p. 74 (page number printed at the foot of p. 74 in the OCR).',
         values=[("W_over_w_raw", r"where W = (T05) w", "-", RAW)],
         status="reconstructed",
         reading="'the loss of energy due to recoil and mechanical friction can be represented by an increase in the mass of the projectile of about 5 per cent': A*p_s = W dv/dt (7,01) with W = 1.05 w (OCR 'T05' = 1.05, cf. eq. 6,19 OCR '1-05')."),
    dict(id="b16", item="b", doc="hunt", topic="Hunt 1951: quadratic (Lagrange) pressure distribution and space-mean pressure (eqs 7,05-7,07)",
         anchor="and obtain, by integrating,", n=9,
         values=[], status="reconstructed",
         reading="sigma = fraction of the breech-to-base volume behind the section (0 at breech, 1 at shot base). Eq. 7,05: (p - p_s)/p_s = (1 - sigma^2) * C/(2W) * d(zv)/dv. Eq. 7,06: p - p_s = (1 - sigma^2)(p_b - p_s). Eq. 7,07: p_m = integral_0^1 p d(sigma) = (1/3)(2 p_b + p_s). 'The quadratic distribution of pressure given by 7,06 is the best simple approximation known for the form of the pressure gradient due to the inertia of the gases'."),
    dict(id="b17", item="b", doc="hunt", topic="Hunt 1951: gas-friction pressure drop (eq. 7,10)",
         anchor="Then, approximately,", n=10,
         values=[], status="ocr_ambiguous",
         reading="p_b - p_s = k*C*v^2/d^3 (7,10), k non-dimensional; the numerical k is OCR-garbled ('M0 x 10- 3'; k1*mu^(2/(n+3)) quoted as 9.53e-3 c.g.s. / 6.53e-3 ft-lb-sec). Not transcribed as a number."),
    dict(id="b18", item="b", doc="hunt", topic="Hunt 1951: combined distribution, modified masses and pressure ratios (eqs 7,13-7,17)",
         anchor="Then 7,06 becomes", n=10,
         values=[], status="reconstructed",
         reading="7,13: p = p_s[1 + (1/2)(1 - sigma^2) F(t) C/W]; space mean p_m = p_s[1 + (1/3) F(t) C/W] = (1/3)(2 p_b + p_s); 7,14: A*p_m = w1 dv/dt; 7,15: w1 = 1.05 w + (1/3) C F(t) (OCR 'T05' = 1.05). F(t) is defined in 7,12 (inertia term d(zv)/dv before all-burnt, 1 + 2kWv^2/(d^3 p_s) at and after all-burnt).",
         ),
    dict(id="b18b", item="b", doc="hunt", topic="Hunt 1951: KE term in Resal's equation and pressure ratios with w1 = w2 = 1.05 w + C/3 (eqs 7,16-7,17)",
         anchor="7.07. The kinetic energy term in Resal's equation", n=32,
         values=[("w2_factor", r"w 2 = (1-05) w -f- z", "-", hunt_dec)],
         status="reconstructed",
         page_override="79-80", page_note="Section 7.07 starts on p. 79; eq. 7,17 and the pressure ratios follow the p. 80 head.",
         reading="Gas KE = (1/2)(1/3) C z v^2 (Lagrange, solid portion neglected); KE term in Resal's equation (1/2) w2 v^2 with 7,16: w2 = 1.05 w + (1/3) C z. 'Lagrange's approximation will not give so good a value for the kinetic energy of the gases as it does for their momentum ... w2 may exceed the above value by a small amount.' 7,17 (mean value unity for F(t) and z): w1 = w2 = 1.05 w + (1/3) C ('the result foreshadowed in Section 6.14'). Pressure relations READING of OCR 'Pb P™ p / 1 + i C/W~ 1 + i C/W “ 1 + } (1 — a 2 ) C/W ~ p ‘': p_b/(1 + C/2W) = p_m/(1 + C/3W) = p/(1 + (1/2)(1 - sigma^2) C/W) = p_s (the '1/2' vs '1/3' fractions are OCR 'i'/'}' and are read from eqs 7,05-7,07 and 7,13), with W = 1.05 w."),
    dict(id="b19", item="b", doc="hunt", topic="Hunt 1951: validity of Lagrange ratios in C/W",
         anchor="Throughout this chapter, it has always been assumed that the ratio C/W is not greater", n=6,
         values=[], status="legible",
         reading="'a constant value of the ratio p_b/p_s is deduced which is not significantly different from (1 + C/2W) for values of C/W up to unity, even when second and third order terms in C/W are taken into account.'"),
    dict(id="b20", item="b", doc="corner", topic="Corner 1950: Lagrange pressure distribution with bore resistance (eq. 13) and ratios (eq. 16, 17)",
         anchor="Let the pressure at the shot be ps, at the breech be pa", n=28, page_override="344-345", page_note="Eq. 13 on p. 344; eqs 16-17 after the p. 345 header.",
         values=[], status="reconstructed",
         reading="x = distance from breech, y = shot-base position, p_r = bore resistance as equivalent pressure. Eq. 13 READING of OCR 'p = Ps + Sir V - iV (ps \" w)': p(x) = p_s + (C/2W)(1 - x^2/y^2)(p_s - p_r). With no bore resistance, eq. 16: (mean pressure)/p_s = 1 + C/(3W), compared with eq. 17: total KE/shot KE = 1 + C/(3W); 'The similarity of equations 16 and 17 holds only to this order of approximation.' Gas KE = (1/6) C V^2 (eq. 9)."),
    dict(id="b21", item="b", doc="corner", topic="Corner 1950: Lagrange approximation validity",
         anchor="More exact analytical solutions usually give for velocity and density", n=6, page_override='343', page_note="Precedes the p. 344 header; the preceding marker is a spurious '0'.",
         values=[], status="legible",
         reading="'the Lagrange corrections derived from equations 9 and 10 are correct to the order of C/W, if the common assumptions of these theories are correct.'"),
    dict(id="b22", item="b", doc="corner", topic="Corner 1950: Resal energy equation with heat-loss factor (sec. 5.1, eqs 1-6)",
         anchor="The kinetic energy of the shot at any time is", n=40, page_override='175-176', page_note='Section 5.1 starts on p. 175; eqs 5-6 continue on p. 176.',
         values=[], status="reconstructed",
         reading="KE of shot + gas = (1/2)(W + C/3)V^2 (eq. 1), corrected for rotation, resistance and recoil to (1/2)(W1 + C/3)V^2 (eq. 2). Heat loss up to any time = fraction x of this KE; total energy loss (1/2)(1 + x)(W1 + C/3)V^2. Effective gamma: gamma_bar - 1 = (1 + x)(gamma - 1) (eq. 3). Eq. 4 READING: phi(1 - T') = ((gamma_bar - 1)/2)(W1/C + 1/3) V^2/(R T0). 'Either equation 4 or equation 6 may be regarded as the basic energy equation for orthodox guns ... equation 6 is usually called the Resal equation.' 'Heat losses to the walls of the bore have been taken into account by a suitable choice of gamma. A resistance to shot motion, proportional to the instantaneous pressure, requires an adjustment to W1.'"),
    dict(id="b23", item="b", doc="corner", topic="Corner 1950: effective gamma and size of heat-loss ratio x (eq. 33)",
         anchor="X is biggest for small calibers and high muzzle velocities", n=7,
         values=[("x_rarely_exceeds", r"rarely\s+exceeds (0\.3)", "-", F),
                 ("gamma_practical_low", r"practical range being\s*\n?\s*(1\.22) to", "-", F),
                 ("gamma_practical_high", r"1\.22 to (1\.28)", "-", F),
                 ("gamma_bar_low", r"may vary from (1\.22) to", "-", F),
                 ("gamma_bar_high", r"may vary from 1\.22 to (1\.36)", "-", F),
                 ("gamma_bar_large_hot", r"convenient figure is (1\.25)", "-", F),
                 ("gamma_bar_medium", r"can be taken as (1\.3)\.", "-", F)],
         status="legible",
         reading="gamma_bar - 1 = (gamma - 1)(1 + x) (eq. 33, Kent & Vinti: heat loss proportional to shot KE). x 'is biggest for small calibers and high muzzle velocities and rarely exceeds 0.3'; thermochemical gamma 1.22-1.28; gamma_bar 1.22-1.36; 1.25 for large calibres and hot propellants; 1.3 for most medium-calibre firings; exact value can be calculated from sec. 10.41."),
    dict(id="b24", item="b", doc="corner", topic="Corner 1950: effect of heat loss example (sec. 5.27)",
         anchor="where x is the ratio of the heat loss at any time to the kinetic energy", n=8,
         values=[("x_3p7in_AA", r"X = (0\.21), which is perhaps slightly overestimated", "-", F)],
         status="legible",
         reading="x = heat loss / KE of shot and gas; 3.7-in AA gun example uses x = 0.21; omitting heat loss changes MV by 57 ft/s in 2700 ft/s at constant charge and pressure."),

    # ---------------- (c) Hunt 6.10 / Corner 10.41 ---------------------------
    dict(id="c01", item="c", doc="hunt", topic="Hunt 1951 sec. 6.10: Thornhill semi-empirical heat loss E_h (eq. 6,15)",
         anchor="6.10. Heat energy lost to the gun", n=23,
         values=[("coef", r"(0-38) d 1 5", "-", hunt_dec),
                 ("d_exponent_raw", r"0-38 d (1 5) \(x 3", "-", RAW),
                 ("denominator_raw", r"(1 \+ 0-6 175/0 8375)", "-", RAW)],
         status="ocr_ambiguous",
         reading="Thornhill formula, heat lost to the gun proportional to the square of shot velocity. READING of OCR: E_h = [0.38 d^1.5 (x3 + x0)(T0 - T1) / (1 + 0.6 d^a / C^0.8375)] * v^2/v3^2 ft-lb, (numerator exponent 1.5 read from OCR 'd 1 5'; Corner's p. 426 heat/KE ratio shows 'd3/2', consistent) where the exponent a of d in the denominator is NOT legible (OCR '175'; eq. 6,22 shows \"rf 2 ' 1 ”\"). T0 = adiabatic flame temperature, T1 = initial gun temperature (both deg C), C = charge [lb], d = calibre [in], x3 = shot travel to muzzle [in], x0 = K0/A [in], v3 = muzzle velocity [ft/s]. Refinement: for travels > ~20 calibres E_h ~ (x + x0), for < ~20 calibres E_h ~ x. DO NOT implement until the exponents are read from a page image."),
    dict(id="c02", item="c", doc="hunt", topic="Hunt 1951 sec. 6.14: modified Resal equation; w1 = 1.05 w + C/3; heat factor k (eqs 6,19-6,24)",
         anchor="1 -05 x \\ tw 2 + | Cv 2 + E*", n=28,
         values=[("w1_factor", r"v\\ — (1-05) w -f \^C", "-", hunt_dec),
                 ("k_coef", r"(0-76) d”", "-", hunt_dec),
                 ("recoil_pct", r"energy loss of (one) per cent", "-", RAW),
                 ("friction_pct", r"and (four) per cent", "-", RAW)],
         status="reconstructed",
         reading="Secondary energies replace A*int p_s dx by 1.05 x (1/2) w v^2 + (1/2)(1/3) C v^2 + E_h; w1 = 1.05 w + (1/3) C (6,19); footnote: 1.05 'includes an energy loss of one per cent to allow for recoil (Section 6.09) and four per cent to allow for friction (Section 6.12)'. Heat loss written E_h = (1/2) w1 v^2 k/g (6,21) with k = 0.76 d^... (x3 + x0)(T0 - T1) g / [w1 (1 + 0.6 d^.../C^0.8375) v3^2] (6,22; exponents OCR-garbled), and gamma' - 1 = (gamma - 1)(1 + k) (6,23)."),
    dict(id="c03", item="c", doc="hunt", topic="Hunt 1951 sec. 6.12: engraving/shot-start and friction work",
         anchor="rough empirical value of the pressure developed in the chamber before the shot begins", n=9,
         values=[("sugot_shot_start_kg_cm2", r"Sugot as (400) kg\./cm\. 2", "kg/cm2", F),
                 ("sugot_shot_start_tsi", r"or (2-5) tons/sq\. in\.", "tons/sq in", hunt_dec),
                 ("friction_fraction", r"E[j/] = (0-04) x", "-", hunt_dec)],
         status="legible",
         reading="Sugot's rough empirical shot-start pressure 400 kg/cm2 or 2.5 tons/sq in ('the actual value must vary for different equipments'); friction work 'unlikely to exceed about 4 or 5 per cent of the kinetic energy of the shot'; taken as E_f = 0.04 x (1/2) w v^2/g (6,17), which 'implies a resistive pressure proportional to the gas pressure and thus gives a resistance too small at the beginning and end of shot travel'. Artillery context (driving band)."),
    dict(id="c04", item="c", doc="corner", topic="Corner 1950 sec. 10.41: Thornhill semi-empirical heat-loss formulas",
         anchor="Thornhill has fitted formulas, whose form has a rough theoretical", n=48, page_override="425-426", page_note="Section 10.41 begins on p. 425 (header 'Semiempirical Formulas for Heat Loss 425'); eq. 42 onward is on p. 426.",
         values=[("H_coef_raw", r"H = (1\.27 X lO_20)", "cal/sq cm", RAW),
                 ("theta_denominator_raw", r"(1\.7 \+ 0\.38dH)", "-", RAW),
                 ("roughness_guns", r"usually about\s*\n?\s*(1\.25) in guns", "-", F),
                 ("roughness_small_arms", r"rising to (1\.4) or more in small arms", "-", F),
                 ("eq41_coef", r"(10\.13)", "cal", F),
                 ("eq41_cm2_per_in2", r"X (6\.451) cal", "cm2/in2", F),
                 ("eq42_coef_raw", r"(5\.03 X I0~3)", "cal", RAW),
                 ("whole_firing_chamber_peak", r"from zero to (1\.2) H", "-", F)],
         status="ocr_ambiguous",
         reading="d [in] calibre, C [lb] charge, T0 [K] uncooled explosion temperature, U [cu in] total internal volume, A [sq in] bore area, theta [K] max temperature rise at the commencement of rifling above 300 K. theta = (T0 - 300)/(1.7 + 0.38 d^? ...) and H = 1.27 x 10^-? d^? ... Omega [cal/sq cm per round at the start of rifling] are OCR-garbled (exponents illegible). LEGIBLE: Omega = roughness factor > 1, 'usually about 1.25 in guns, rising to 1.4 or more in small arms'. Total heat loss to shot ejection (eq. 41, READING, triangular distribution zero at breech -> H at start of rifling -> zero at muzzle): (U/(2A)) * pi * d * H * 6.451 cal = 10.13 U H d / A cal. Shot + charge KE (eq. 42, READING): 5.03 x 10^-3 (W + C/3) V^2 cal (W lb, V ft/s). Heat-loss/KE factor x at the muzzle = ratio of (41) to (42) (garbled). Whole-firing estimate: linear from zero to 1.2 H in the chamber, falling linearly in the bore."),
    dict(id="c05", item="c", doc="goldstein", topic="Goldstein 1979 (small arms): Hunt/Corner semi-empirical heat loss used in small-arms IB models",
         anchor="Energy losses resulting from heat loss are estimated by a semi", n=3,
         values=[], status="legible",
         reading="In Trafton's small-arms model: 'Energy losses resulting from heat loss are estimated by a semi-empirical relationship described by Hunt (ref. 42) and Corner (ref. 43). This is the same equation that is used in the Baer and Frankle model.'",
         page_override="13-15", page_note="Between the printed p. 12 and p. 16 markers; markers 13-15 absent from the OCR."),
    dict(id="c06", item="c", doc="goldstein", topic="Goldstein 1979 (small arms): Pidduck-Kent gradient in small arms; base/breech ratio varies with travel",
         anchor="Trafton used the Pidduck-Kent function", n=7,
         values=[], status="legible",
         reading="'This approximation appears to work satisfactorily for small arms systems ... However, recent tests (ref. 41) have shown that the ratio of projectile base pressure to breech pressure (which the Pidduck-Kent describes as a constant) does indeed vary as the projectile travels down the barrel.' Inputs listed: bullet pull, primer thermochemistry, empirical ignition delay, engraving and frictional resistance.",
         page_override="13-15", page_note="Between the printed p. 12 and p. 16 markers; markers 13-15 absent from the OCR."),

    # ---------------- (d) solid density -------------------------------------
    dict(id="d02", item="d", doc="amcp706150", topic="AMCP 706-150: specific volume of solid propellant ~17.5 in3/lb",
         anchor="The specific voluiiie of the propellant (u) is about", n=2,
         values=[("u_in3_per_lb", r"about\s*\n?\s*(17\.5) in3/lb", "in3/lb", F)],
         status="legible",
         reading="u ~ 17.5 in3/lb for 'the propellant' (generic; no composition given). [DERIVED] density = 1/u (see 'derived')."),
    dict(id="d03", item="d", doc="amcp706150", topic="AMCP 706-150 Table 1-1 density row (column alignment lost in OCR)",
         anchor="Density, lbs/in3", n=12, page_override='1-13/1-14', page_note='Table 1-1 is a fold-out at the back of the handbook, labelled 1-13/1-14.',
         values=[], status="ocr_ambiguous",
         reading="Table 1-1 'Calculated thermochemical values for standard propellants' has 18 columns (M1, M2, M5, M6, M14, M15, M17, T20, M10, T18, T25, M26, M7, M8, M9, IMR, M12, M18) but the OCR density row holds only 11 values (blank cells dropped), so values cannot be assigned to propellants. Range only; see 'derived'."),
    dict(id="d04", item="d", doc="corner", topic="Corner 1950: propellant densities in worked examples",
         anchor="1.0 cc/g, density 1.64 g/cc", n=1,
         values=[("density_flashless_g_cc", r"density (1\.64) g/cc", "g/cm3", F)],
         status="legible",
         reading="3.7-in AA gun example: 'a flashless propellant with covolume 1.0 cc/g, density 1.64 g/cc' (composition not stated; base type not stated)."),
    dict(id="d05", item="d", doc="corner", topic="Corner 1950: 'hot' cord propellant density 1.57 g/cc",
         anchor="(ton/sq in.) X (cc/g), density 1.57 g/cc", n=2,
         values=[("density_hot_cord_g_cc", r"density (1\.57) g/cc", "g/cm3", F)],
         status="legible",
         reading="Naval gun cord charges: 'a relatively \"hot\" type, with RT0 = 70.9 (ton/sq in.) x (cc/g), density 1.57 g/cc, and thermochemical gamma = 1.24' (base type not stated)."),
    dict(id="d06", item="d", doc="corner", topic="Corner 1950 conversion 1 lb/cu in = 27.681 g/cc",
         anchor="1 ft = 30.480 cm; 1 lb/cu in. = 27.681 g/cc", n=1, page_override='431-432', page_note="Appendix B follows the 'Appendix A 431' header; no later page marker before it in the OCR.",
         values=[("lb_per_in3_to_g_cc", r"1 lb/cu in\. = (27\.681) g/cc", "g/cm3 per lb/in3", F)],
         status="legible",
         reading="Conversion printed by Corner: 1 lb/cu in = 27.681 g/cc (exact value from the definitions of lb and in is 27.6799; see derived)."),

    # ---------------- (e) K1 and n -------------------------------------------
    dict(id="e01", item="e", doc="amcp706150", topic="AMCP 706-150: burning-rate pressure index range",
         anchor="The burning rate pressure index, a, varies for", n=5,
         values=[("alpha_low", r"lies between (0\.8) and", "-", F),
                 ("alpha_high", r"between 0\.8 and (0\.9)", "-", F)],
         status="legible",
         reading="'The burning rate pressure index, alpha, varies for different propellants, but the latest experiments indicate that it lies between 0.8 and 0.9. A figure as low as 2/3 [OCR 'i'] has been used by some authors, and frequently it is assumed to be equal to unity.' Gun propellants generally, not small-arms specific."),
    dict(id="e02", item="e", doc="corner", topic="Corner 1950: pressure index alpha near 0.9; highest production value 1.02",
         anchor="The constants depend on the composition; Fx is usually quoted as of", n=3,
         values=[("alpha_typical", r"is commonly near (0\.9)", "-", F)],
         status="legible",
         reading="'The \"pressure index\" alpha is commonly near 0.9, and is almost always less than unity.' Footnote 14: 'Among production propellants, the highest alpha recorded has been 1.02.' (British service propellants; not small-arms specific.)"),
    dict(id="e03", item="e", doc="corner", topic="Corner 1950 footnote: highest production alpha",
         anchor="Among production propellants, the highest a recorded has been", n=1,
         values=[("alpha_highest_production", r"has been (1\.02)", "-", F)],
         status="legible", reading="Highest alpha recorded among production propellants: 1.02."),
    dict(id="e04", item="e", doc="corner", topic="Corner 1950: rotational effective-mass factor m",
         anchor="ally of the order of 30, making m", n=6,
         values=[("m_n30", r"making m \S* ?(1\.005)", "-", F),
                 ("m_n15_proof_shot", r"m is about (1\.02) for proof shot", "-", F)],
         status="legible",
         reading="W1 = m*W (eq. 11); 'In guns the twist n is usually of the order of 30, making m ~ 1.005. This is hardly worth bothering about.' 'For n = 15, for example, m is about 1.02 for proof shot.' Bore friction may be included 'by simply increasing the effective mass' (resistance proportional to gas pressure)."),
    dict(id="e05", item="e", doc="stiefel", topic="Stiefel 1980 (US small-arms propellants): Riefler & Lowery constant-exponent burning-rate model, n = 0.8053",
         anchor="Two models are offered by Riefler and Lowery", n=21,
         values=[("n_constant_exponent", r"A least-squares method was used to fit the flame\s*\n?.*?\n?.*?constant exponent, n ■\s*\n?\s*(0\.8053)", "-", F),
                 ("n_OCR_variant_raw", r"A constant exponent\s*\n?\s*\(n - (0\.8033)\) was assumed", "-", RAW),
                 ("bv_fit_slope_raw", r"b = -0\.0006 \+ (0\.064 x 10~6)T", "in/s/psi^n per K", RAW)],
         status="ocr_ambiguous",
         reading="r = b*P^n (De Saint Robert). Riefler & Lowery (Olin, BRL CR-172, 1974, 'Linear Burn Rates of Ball Propellants Based on Closed Bomb Firings'), 16 propellants, flame temperatures 1802-3131 K, closed-bomb data; constant-exponent model n = 0.8053 with r in in/s and P in psi (the OCR shows 0.8053 four times and '0.8033' once: OCR conflict, see conflicts). Stiefel's linear fit: b = -0.0006 + 0.064e-6*T_v (in/s, psi, n = 0.8053) (OCR-uncertain). The DBP/NG composition coefficients are OCR-garbled ('%NC' vs prose 'nitroglycerin'; 0.015970 vs 0.015907) and are not transcribed."),
    dict(id="e06", item="e", doc="stiefel", topic="Stiefel 1980: burning-rate law statement",
         anchor="by means of an equation of the following form: r = bP", n=2,
         values=[], status="legible",
         reading="'r = bP^n, known as the De Saint Robert equation' (exponent superscript lost in OCR)."),
    dict(id="e07", item="e", doc="goldstein", topic="Goldstein 1979: small-arms burning-rate coefficient and exponent from closed bombs (no values given)",
         anchor="rate data on deterred small arms propellants was probably achieved", n=8,
         values=[], status="legible",
         reading="Riefler and Lowery obtained 'the burning rate coefficient and exponent for the burning rate equation of the form R = AP^n ... in terms of the percentage of deterrent (DBP) and the percentage of nitroglycerin (NG) and polynomials involving web size.' No numeric exponent in Goldstein.",
         page_override="6", page_note="Precedes the printed p. 6 marker."),
]


# --------------------------------------------------------------------------
def locate(lines, anchor, start=0):
    for i in range(start, len(lines)):
        if anchor in ws(lines[i]):
            return i
    return None


def capture(lines, i, n):
    out, j = [], i
    while j < len(lines) and len(out) < n:
        s = ws(lines[j])
        if s:
            out.append(s)
        j += 1
    return out


def build_record(spec, texts, markers):
    key = spec["doc"]
    lines = texts[key]
    i = locate(lines, spec["anchor"])
    if i is None:
        raise SystemExit("ANCHOR NOT FOUND: %s %r" % (spec["id"], spec["anchor"]))
    ev_lines = capture(lines, i, spec["n"])
    evidence = "\n".join(ev_lines)
    if key == "hunt":
        page, mline = hunt_page(lines, i)
        page_basis = "Hunt running head (even 'NN INTERNAL BALLISTICS' / odd 'TITLE NN') at OCR line %s" % (mline + 1 if mline is not None else None)
    else:
        page, mline = find_page(lines, markers[key], DOCS[key]["pages"], i)
        page_basis = "printed page marker in OCR text at line %s" % (mline + 1 if mline is not None else None)
    if spec.get("page_override"):
        page_basis = "override: " + spec.get("page_note", "")
        page = spec["page_override"]
    vals = {}
    for name, rx, unit, parser in spec["values"]:
        m = re.search(rx, evidence, re.S)
        if not m:
            raise SystemExit("VALUE NOT FOUND: %s %s /%s/\nEVIDENCE:\n%s" % (spec["id"], name, rx, evidence))
        tok = m.group(1)
        v = parser(tok) if parser else None
        vals[name] = {"raw": tok, "value": v, "unit": unit}
    return {
        "id": spec["id"],
        "item": spec["item"],
        "topic": spec["topic"],
        "status": spec["status"],
        "values": vals,
        "reading": spec["reading"],
        "sources": [{"url": DOCS[key]["url"], "type": DOCS[key]["type"], "page": page, "retrieved": RETRIEVED}],
        "page_basis": page_basis,
        "ocr_line": i + 1,
        "evidence": evidence,
        "conflicts": [],
        "derived": [],
    }


# --------------------------------------------------------------------------
# tables parsed with code
# --------------------------------------------------------------------------
HUNT_T101_NAMES = ["MD", "W", "WM", "SC", "HSC", "A", "AN", "ASN", "N", "NQ", "NFQ", "NCT", "NH", "FNH/P"]


def hunt_table_101(lines, markers):
    """Hunt Table 1.01: composition tokens, then density (gm/c.c.), gas volume
    (c.c./gm), calorific value (cals/gm). Each row = name followed by tokens until
    the next name; the last three numeric tokens are density, gas volume, cal. value."""
    start = locate(lines, "TABLE 1.01")
    # the first 'TABLE 1.01' occurrence that is followed by the table title
    while start is not None and "Composition and Physical Properties of Propellants" not in " ".join(capture(lines, start, 3)):
        start = locate(lines, "TABLE 1.01", start + 1)
    end = locate(lines, "TABLE 2.01", start)
    page, mline = hunt_page(lines, start)
    seg = [(k, ws(lines[k])) for k in range(start, end) if ws(lines[k])]
    # find row starts
    def is_name(s, nm):
        base = s.replace("§", "").replace("5", "") if nm == "NH" else s
        if nm == "NH":
            return re.fullmatch(r"NH[5§]?", s) is not None
        if nm == "FNH/P":
            return s.startswith("FNH/P")
        return s == nm
    idxs, pos = [], 0
    for nm in HUNT_T101_NAMES:
        for k in range(pos, len(seg)):
            if is_name(seg[k][1], nm):
                idxs.append((nm, k))
                pos = k + 1
                break
        else:
            raise SystemExit("Hunt T1.01 row not found: " + nm)
    rows = []
    for r, (nm, k) in enumerate(idxs):
        stop = idxs[r + 1][1] if r + 1 < len(idxs) else len(seg)
        toks = [t for _, t in seg[k + 1:stop]]
        # cut at footnotes / page furniture
        cut = len(toks)
        for q, t in enumerate(toks):
            if t.startswith(("•", "f With", "$ With", "5 Dupont", "TABLES")) or t.startswith("With"):
                cut = q
                break
        toks = toks[:cut]
        # density token = last token matching d-dd before the two trailing integers
        dens_i = None
        for q in range(len(toks) - 1, -1, -1):
            if re.fullmatch(r"1\s*-\s*\d\d", toks[q]):
                dens_i = q
                break
        if dens_i is None or dens_i + 2 >= len(toks) + 0 and dens_i + 2 > len(toks) - 1 + 1:
            raise SystemExit("density token not found for " + nm)
        density = hunt_dec(toks[dens_i])
        gasvol = num(toks[dens_i + 1]) if dens_i + 1 < len(toks) else None
        calval = num(toks[dens_i + 2]) if dens_i + 2 < len(toks) else None
        comp = toks[:dens_i]
        first = comp[0] if comp else ""
        nc_first = "(" in first  # nitrocellulose token carries '(N content)'
        picrite = any(re.fullmatch(r"55\s*[$\$]?", t.replace("$", "")) for t in comp)
        if nc_first:
            base = "single-base (nitrocellulose; no nitroglycerine column value)"
        elif picrite:
            base = "triple-base (nitroglycerine + nitrocellulose + picrite 55%)"
        else:
            base = "double-base (nitroglycerine + nitrocellulose)"
        ev = "\n".join([nm if nm != "NH" else seg[k][1]] + toks[:dens_i + 3])
        rows.append({
            "id": "d01-" + nm.replace("/", "_"),
            "item": "d",
            "topic": "Hunt 1951 Table 1.01 density at 20 C: %s" % nm,
            "status": "legible",
            "propellant": nm,
            "base_type_from_composition": base,
            "values": {
                "density_g_cm3_at_20C": {"raw": toks[dens_i], "value": density, "unit": "g/cm3"},
                "gas_volume_cc_per_g": {"raw": toks[dens_i + 1], "value": gasvol, "unit": "c.c./gm"},
                "calorific_value_cal_per_g_water_liquid": {"raw": toks[dens_i + 2], "value": calval, "unit": "cals/gm"},
                "composition_tokens_raw": {"raw": " | ".join(comp), "value": None, "unit": "% (column alignment of minor ingredients not reliable in OCR)"},
            },
            "reading": "Hunt Table 1.01 'Composition and Physical Properties of Propellants'; columns: Nitroglycerine, Nitro-cellulose (N content), Carbamite, Mineral Jelly, Diphenylamine, Picrite, Dinitrotoluene, Dibutylphthalate, Density at 20 C gm/c.c., Gas volume c.c./gm, Calorific value (water liquid) cals/gm. 'The thermal data in this table are always subject to revision.' Base type inferred by the script from whether the first composition value is the nitrocellulose entry (carries '(N%)') and whether the 55% picrite entry is present.",
            "sources": [{"url": DOCS["hunt"]["url"], "type": "government", "page": page, "retrieved": RETRIEVED}],
            "page_basis": "Hunt running head nearest the table title, OCR line %d" % (mline + 1),
            "ocr_line": seg[k][0] + 1,
            "evidence": ev,
            "conflicts": [],
            "derived": [],
        })
    return rows


HUNT_T501_NAMES = ["MD", "W", "WM", "SC", "HSC", "A", "AN", "ASN", "N", "NQ", "NFQ", "NCT", "NH (Dupont)", "FNH/P (Dupont)"]


def hunt_table_501(lines, markers):
    start = locate(lines, "TABLE 5.01")
    end = locate(lines, "There are no reliable figures available", start)
    page, mline = hunt_page(lines, start)
    seg = [(k, ws(lines[k])) for k in range(start, end + 1) if ws(lines[k])]
    hdr_end = [q for q, (_, s) in enumerate(seg) if s == "per cent."][-1]
    idxs, pos = [], hdr_end + 1
    for nm in HUNT_T501_NAMES:
        for q in range(pos, len(seg)):
            if seg[q][1] == nm:
                idxs.append((nm, q))
                pos = q + 1
                break
        else:
            raise SystemExit("Hunt T5.01 row not found: " + nm)
    rows = []
    for r, (nm, q) in enumerate(idxs):
        stop = idxs[r + 1][1] if r + 1 < len(idxs) else len(seg) - 1
        toks = [s for _, s in seg[q + 1:stop]]
        a_raw = toks[0] if toks else None
        a_val = hunt_dec(a_raw) if a_raw else None
        note = None
        if a_val is None:
            note = "alpha token %r: decimal separator lost or token garbled in OCR; not interpreted" % a_raw
        rows.append({
            "id": "e08-" + nm.split(" ")[0].replace("/", "_"),
            "item": "e",
            "topic": "Hunt 1951 Table 5.01 pressure index alpha: %s" % nm,
            "status": "legible" if a_val is not None else "ocr_ambiguous",
            "propellant": nm,
            "values": {
                "alpha_pressure_index": {"raw": a_raw, "value": a_val, "unit": "-"},
                "row_tokens_raw": {"raw": " | ".join(toks), "value": None,
                                   "unit": "alpha | beta (non-linear coeff.) | beta1 (linear-law coeff.) | d(beta1)/beta1 % per 10 F | dF/F % per 10 F"},
            },
            "note": note,
            "reading": "Hunt Table 5.01 'Rate-of-burning Indices and Coefficients with Initial Temperature Effects'. 'The figures give the rate of reduction of the least grain dimension in inches per second when the pressure is in tons/sq. in. They are always subject to revision.' British/US gun propellants of the 1940s; NOT small-arms propellants.",
            "sources": [{"url": DOCS["hunt"]["url"], "type": "government", "page": page, "retrieved": RETRIEVED}],
            "page_basis": "Hunt running head nearest the table title, OCR line %d" % (mline + 1),
            "ocr_line": seg[q][0] + 1,
            "evidence": "\n".join([nm] + toks),
            "conflicts": [],
            "derived": [],
        })
    return rows


def amcp_density_row(lines):
    i = locate(lines, "Density, lbs/in3")
    vals = []
    j = i + 1
    while j < len(lines):
        s = ws(lines[j])
        if s.startswith("Covolume"):
            break
        if s:
            vals.append(s)
        j += 1
    return vals


# --------------------------------------------------------------------------
# derived checks (exact unit arithmetic only)
# --------------------------------------------------------------------------
LB_KG = 0.45359237
IN_M = 0.0254
IN3_CM3 = 16.387064
INLBF_J = 0.0254 * 0.45359237 * 9.80665  # 1 in*lbf in J (exact from definitions)
CAL_TH = 4.184


HUNT_SC_XCHECK = None


def add_derived(recs):
    by = {r["id"]: r for r in recs}
    g_cc_per_lb_in3 = LB_KG * 1000.0 / IN3_CM3

    # a03/a04: reconcile IBHVG2 English OCR defaults with ARL-TR-348 SI defaults
    a3, a4 = by["a03"], by["a04"]
    si = {k: v["value"] for k, v in a4["values"].items()}
    tshl_in = si["TSHL_default_m"] / IN_M
    cshl_eng = si["CSHL_default_J_per_kgK"] * LB_KG / INLBF_J
    rshl_eng = si["RSHL_default_kg_per_m3"] * (IN_M ** 3) / LB_KG
    ho_eng = si["HO_default_W_per_m2K"] * (IN_M ** 2) / INLBF_J  # W/m2K -> in*lbf/(s*in2*K) = lbf/(in*s*K)
    d = [
        {"what": "TSHL 0.0001016 m in inches", "value": round(tshl_in, 6), "unit": "in",
         "calc": "0.0001016 / 0.0254", "matches_ibhvg2_ocr": a3["values"]["TSHL_default_in"]["raw"]},
        {"what": "CSHL 460.316318 J/kg-K in in-lbf/lbm-K", "value": round(cshl_eng, 2), "unit": "in-lbf/lbm-K",
         "calc": "460.316318 * 0.45359237 / (0.0254*0.45359237*9.80665)", "ibhvg2_ocr_token": a3["values"]["CSHL_default_raw"]["raw"]},
        {"what": "RSHL 7861.0916 kg/m3 in lbm/in3", "value": round(rshl_eng, 5), "unit": "lbm/in3",
         "calc": "7861.0916 * 0.0254^3 / 0.45359237", "ibhvg2_ocr_token": a3["values"]["RSHL_default_raw"]["raw"]},
        {"what": "HO 11.34821852 W/m2-K in lbf/(in-s-K)", "value": round(ho_eng, 6), "unit": "lbf/(in-s-K)",
         "calc": "11.34821852 * 0.0254^2 / (0.0254*0.45359237*9.80665)", "ibhvg2_ocr_token": a3["values"]["HO_default_raw"]["raw"]},
    ]
    a4["derived"] = d
    a3["derived"] = d
    a3["conflicts"] = [
        {"field": "CSHL_default", "values": [
            {"value": a3["values"]["CSHL_default_raw"]["raw"] + " (OCR token, in-lbf/lbm-K)", "source": DOCS["ibhvg2"]["url"] + " p. 11"},
            {"value": "%s J/kg-K = %.2f in-lbf/lbm-K [DERIVED]" % (si["CSHL_default_J_per_kgK"], cshl_eng), "source": DOCS["etc_ibhvg2"]["url"] + " p. 31"}],
         "resolution": "OCR '1S48.0' is consistent with 1848.0 (converted ARL-TR-348 value 1848.00); page image not seen."},
        {"field": "RSHL_default", "values": [
            {"value": a3["values"]["RSHL_default_raw"]["raw"] + " (OCR token, lbm/in3)", "source": DOCS["ibhvg2"]["url"] + " p. 11"},
            {"value": "%s kg/m3 = %.5f lbm/in3 [DERIVED]" % (si["RSHL_default_kg_per_m3"], rshl_eng), "source": DOCS["etc_ibhvg2"]["url"] + " p. 31"}],
         "resolution": "OCR '0.244' disagrees with the converted ARL-TR-348 value 0.28400; probably an OCR misread of 0.284 (unverified)."},
        {"field": "HO_default", "values": [
            {"value": a3["values"]["HO_default_raw"]["raw"] + " (OCR token, lbf/in-sec-K)", "source": DOCS["ibhvg2"]["url"] + " p. 11"},
            {"value": "%s W/m2-K = %.6f lbf/(in-s-K) [DERIVED]" % (si["HO_default_W_per_m2K"], ho_eng), "source": DOCS["etc_ibhvg2"]["url"] + " p. 31"}],
         "resolution": "OCR '0.0048' disagrees with the converted ARL-TR-348 value 0.0648; probably an OCR misread of 0.0648 (unverified). Use the ARL-TR-348 SI value."},
    ]

    # b12/b13: check lambda = (13.2 + 4 log10 d_cm)^-2 against the printed 1/300
    lam = (13.2 + 4.0 * math.log10(10.5)) ** -2
    by["b13"]["derived"].append({"what": "lambda = (13.2 + 4*log10(10.5))^-2", "value": round(lam, 6),
                                 "as_fraction": "1/%.1f" % (1.0 / lam), "printed": "1/300",
                                 "conclusion": "reading of eq. 3-3 reproduces the handbook's worked example"})
    by["b12"]["derived"] = by["b13"]["derived"]

    # c04: check eq. 41 arithmetic and eq. 42 coefficient
    by["c04"]["derived"] += [
        {"what": "pi * 6.451 / 2 (eq. 41 reading: (U/2A) * pi*d*H * 6.451)", "value": round(math.pi * 6.451 / 2, 3), "printed": "10.13"},
        {"what": "(1/2) lb*(ft/s)^2 in thermochemical cal", "value": round(0.5 * LB_KG * 0.3048 ** 2 / CAL_TH, 6),
         "printed": "5.03 x 10^-3 (eq. 42)"},
    ]

    # d02: density from u = 17.5 in3/lb
    u = by["d02"]["values"]["u_in3_per_lb"]["value"]
    by["d02"]["derived"].append({"what": "density = 1/u", "value": round(g_cc_per_lb_in3 / u, 4), "unit": "g/cm3",
                                 "calc": "(453.59237 g / 16.387064 cm3) / 17.5"})
    # d03: AMCP density row range
    row = by["d03"]["values"]["density_row_raw"]["raw"].split(" | ")
    clean = [float(t) for t in row if re.fullmatch(r"0\.\d{4}", t)]
    by["d03"]["derived"].append({"what": "range of clean density-row tokens (lb/in3 -> g/cm3)",
                                 "lb_in3_min": min(clean), "lb_in3_max": max(clean),
                                 "g_cm3_min": round(min(clean) * g_cc_per_lb_in3, 3),
                                 "g_cm3_max": round(max(clean) * g_cc_per_lb_in3, 3),
                                 "n_clean_tokens": len(clean), "n_columns_in_table": 18})
    sc = by.get("d01-SC")
    if sc is not None and HUNT_SC_XCHECK:
        sc["derived"].append({"what": "cross-check: Hunt text quotes the Table 1.01 calorific value for Cordite SC",
                              "text_evidence": HUNT_SC_XCHECK[0], "text_page": HUNT_SC_XCHECK[1],
                              "table_value": sc["values"]["calorific_value_cal_per_g_water_liquid"]["value"]})
    by["d06"]["derived"].append({"what": "exact lb/in3 -> g/cm3", "value": round(g_cc_per_lb_in3, 4),
                                 "calc": "453.59237 / 16.387064"})


# --------------------------------------------------------------------------
def main():
    texts, markers = {}, {}
    for key in DOCS:
        texts[key] = ensure_doc(key)
        markers[key] = page_markers(texts[key], DOCS[key]["pages"])

    recs = [build_record(s, texts, markers) for s in SPECS]

    # AMCP density row: attach parsed raw tokens to d03
    for r in recs:
        if r["id"] == "d03":
            toks = amcp_density_row(texts["amcp706150"])
            r["values"]["density_row_raw"] = {"raw": " | ".join(toks), "value": None, "unit": "lbs/in3 (unassignable)"}

    global HUNT_SC_XCHECK
    k = locate(texts["hunt"], "well with the experimental value, 970 cals./gm. in Table 1.01")
    if k is not None:
        pg = hunt_page(texts["hunt"], k)[0]
        nxt = hunt_page(texts["hunt"], k + 60)[0]  # the p. 18 head follows ~40 lines later
        if pg is not None and nxt is not None and int(nxt) - int(pg) == 2:
            pg = "%s-%d (running head of p. %d absent in OCR)" % (pg, int(pg) + 1, int(pg) + 1)
        HUNT_SC_XCHECK = (ws(texts["hunt"][k]), pg)
    t101 = hunt_table_101(texts["hunt"], markers)
    t501 = hunt_table_501(texts["hunt"], markers)
    recs += t101 + t501
    add_derived(recs)

    # stiefel n conflict
    for r in recs:
        if r["id"] == "e05":
            r["conflicts"].append({"field": "n_constant_exponent", "values": [
                {"value": r["values"]["n_constant_exponent"]["raw"], "source": DOCS["stiefel"]["url"] + " p. 31 (appears 4 times)"},
                {"value": r["values"]["n_OCR_variant_raw"]["raw"], "source": DOCS["stiefel"]["url"] + " p. 31 (appears once, 'A constant exponent (n - 0.8033) was assumed')"}],
                "resolution": "majority OCR reading 0.8053; page image not seen."})
        if r["id"].startswith("e08-") and r["propellant"] in ("WM", "SC", "AN", "ASN"):
            r["conflicts"].append({"field": "alpha_pressure_index", "values": [
                {"value": r["values"]["alpha_pressure_index"]["raw"] + " (OCR, decimal lost)", "source": DOCS["hunt"]["url"] + " p. 226"},
                {"value": "Corner: highest alpha recorded among production propellants 1.02", "source": DOCS["corner"]["url"] + " p. 41 fn. 14 (see e03)"}],
                "resolution": "unresolved: Hunt Table 5.01 lists ASN at a legible 1.05 and WM/SC/AN tokens '105'/'104'/'106' (decimal lost), all above Corner's 1.02; the two books may describe different lots, eras or measurement methods."})

    # ---------------- self-check -----------------------------------------
    problems = []
    for r in recs:
        for k, v in r["values"].items():
            if v["raw"] is not None:
                pieces = v["raw"].split(" | ")
                hay = r["evidence"] if k != "density_row_raw" else "\n".join(amcp_density_row(texts["amcp706150"]))
                for piece in pieces:
                    if piece not in hay:
                        problems.append((r["id"], k, piece))
            if v["value"] is not None:
                # numeric value must be recoverable from the raw token in the evidence
                rawnorm = re.sub(r"[\s·*\-]", ".", v["raw"]).replace("..", ".")
                if abs(float(re.sub(r"[^0-9.]", "", rawnorm) or "nan") - v["value"]) > 1e-9:
                    problems.append((r["id"], k, "value/raw mismatch %r %r" % (v["raw"], v["value"])))
    for r in recs:
        if r["id"] == "d03":
            continue
    print("records:", len(recs))
    print("by item:", {it: sum(1 for r in recs if r["item"] == it) for it in "abcde"})
    print("by status:", {st: sum(1 for r in recs if r["status"] == st) for st in sorted(set(r["status"] for r in recs))})
    print("self-check problems:", problems)
    random.seed(7)
    for r in random.sample(recs, 5):
        print("----", r["id"], r["topic"], "| page", r["sources"][0]["page"])
        print("values:", {k: (v["raw"], v["value"]) for k, v in r["values"].items()})
        print("evidence:", r["evidence"][:600].replace("\n", " ⏎ "))
    if problems:
        raise SystemExit("self-check failed")

    meta = {
        "documents": [{"url": d["url"], "details": d["details"], "localPath": d.get("localPath"),
                       "textPath": d.get("textPath"), "title": d["title"], "date": d["date"]} for d in DOCS.values()],
        "items": ITEMS,
        "blockedHosts": BLOCKED,
        "notes": ("All documents read as archive.org OCR full text (stream pages); page images/PDFs were not reachable. "
                  "'page' is the printed page number of the document, located from page markers in the OCR text "
                  "(or an override with page_basis when markers are missing). 'status': legible = numbers read from clean OCR; "
                  "reconstructed = equation structure read from garbled OCR and checked for internal consistency; "
                  "ocr_ambiguous = some tokens unreadable or conflicting; illegible = cannot be transcribed. "
                  "'reading' fields are transcriptions/interpretations of the evidence, never values from memory. "
                  "'derived' entries are exact unit arithmetic done by this script. Nothing here is a load-data pressure limit."),
        "script": "scripts/extract/physics-primary.py",
        "retrieved": RETRIEVED,
    }
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "records": recs}, f, indent=2, ensure_ascii=False)
    print("wrote", OUT_JSON)
    write_md(recs, meta)
    print("wrote", OUT_MD)


# --------------------------------------------------------------------------
def write_md(recs, meta):
    by = {r["id"]: r for r in recs}
    L = []
    A = L.append

    def src(r):
        s = r["sources"][0]
        return "%s, p. %s" % (s["url"], s["page"])

    def ev(r, maxlen=900):
        e = r["evidence"].replace("\n", " ⏎ ")
        if len(e) > maxlen:
            e = e[:maxlen] + " …"
        return "> " + e

    def block(rid, heading=None):
        r = by[rid]
        A("#### %s %s" % (rid, heading or r["topic"]))
        A("")
        A("- Source: %s (%s)" % (src(r), r["page_basis"]))
        A("- Status: **%s**" % r["status"])
        if r["values"]:
            vs = "; ".join("%s = %s%s" % (k, v["value"] if v["value"] is not None else "`%s` (raw OCR)" % v["raw"],
                                         (" " + v["unit"]) if v["unit"] not in ("-",) else "")
                           for k, v in r["values"].items() if k not in ("composition_tokens_raw", "row_tokens_raw"))
            A("- Parsed values: " + vs)
        A("- Reading: " + r["reading"])
        for dv in r["derived"]:
            A("- [DERIVED] " + json.dumps(dv, ensure_ascii=False))
        for c in r["conflicts"]:
            A("- Conflict (%s): %s" % (c["field"], " vs ".join("%s [%s]" % (x["value"], x["source"]) for x in c["values"]))
              + ((" Resolution: " + c["resolution"]) if c.get("resolution") else ""))
        A("- Evidence (verbatim OCR, whitespace-collapsed, ⏎ = line break):")
        A("")
        A(ev(r))
        A("")

    A("# Physics primary sources: transcriptions for ORKA (raw2, physics-primary)")
    A("")
    A("Generated by `scripts/extract/physics-primary.py` on %s. Machine-readable copy: `research/raw2/physics-primary.json`." % RETRIEVED)
    A("")
    A("## Read this first")
    A("")
    A("- **Access.** apps.dtic.mil answered every request with a WAF block page; archive.org PDFs and page images live on data nodes that the proxy refuses. Every transcription below therefore comes from the **archive.org OCR full text** of each document. Prose and most numbers are clean. Many **equations are garbled** in the OCR.")
    A("- **Status flags.** Each record carries one of four flags:")
    A("  - `legible`: the numbers were read from clean OCR.")
    A("  - `reconstructed`: the equation structure was read from garbled OCR, and a consistency check is given (another equation in the same document, or a worked example).")
    A("  - `ocr_ambiguous`: some tokens are unreadable or conflict.")
    A("  - `illegible`: the text could not be transcribed.")
    A("  The `Reading` lines are labelled interpretations of the quoted evidence. They are never values from memory.")
    A("- **Before shipping.** Anything marked `reconstructed` or `ocr_ambiguous` must be checked against a page image before it drives ORKA output. None of these numbers is a pressure limit.")
    A("- **Page numbers.** Page numbers are the documents' printed page numbers. Some come from an override because the OCR dropped the page marker; the record says so.")
    A("")
    A("## Item status")
    A("")
    for it in ITEMS:
        A("- **(%s) %s.** %s" % (it["item"], it["status"], it["summary"]))
    A("")
    A("## Documents")
    A("")
    for d in meta["documents"]:
        A("- %s (%s). Full text: %s ; item page: %s" % (d["title"], d["date"], d["url"], d["details"]))
    A("")
    A("Blocked (not circumvented):")
    A("")
    for b in meta["blockedHosts"]:
        A("- " + b)
    A("")

    A("## (a) IBHVG2 user's guide (BRL-TR-2829, 1987)")
    A("")
    A("### (a1) Heat-loss model and default constants")
    A("")
    A("Summary:")
    A("")
    A("- **Model.** The heat-loss rate comes from the Black & Comenetz treatment (NDRC 1946) [a01, a02]:")
    A("  - convection from the gas, at its space-mean temperature, into a thin steel shell, by Newton's law of cooling [a06];")
    A("  - a Nordheim-Soodak-Nordheim heat-transfer coefficient (friction factor × c_p × mean gas density × mean gas velocity) plus a natural-convection term h0 [a07, a08];")
    A("  - shell temperature from its heat capacity, density, thickness and exposed area, plus a fraction HTFR of the bore-friction work [a09].")
    A("- **Errata.** The errata sheet corrects D.18 and D.21. Both corrections are illegible in the OCR [a10].")
    A("- **Default constants.** These are transcribed cleanly from ARL-TR-348 (the 1994 IBHVG2 input reference in SI) [a04]:")
    A("  - TSHL = 0.0001016 m (= 0.004 in);")
    A("  - CSHL = 460.316318 J/kg·K;")
    A("  - RSHL = 7861.0916 kg/m³;")
    A("  - TWAL = 293.0 K;")
    A("  - HO = 11.34821852 W/m²·K;")
    A("  - HL = 1 (heat loss on).")
    A("- **OCR disagreements.** The 1987 guide's English-unit OCR tokens for CSHL, RSHL and HO disagree with these values or are unreadable. Exact unit conversion shows they are consistent with 1848.0 in·lbf/lbm·K, 0.284 lbm/in³ and 0.0648 lbf/(in·s·K) [a03 conflicts].")
    A("- **Friction factor.** In IBHVG2 (D.20) the constants 13.2 and 4·log10 are legible, but the argument is not. AMCP 706-150 eq. 3-3 gives λ = (13.2 + 4·log10 d)^-2 with d in cm, and its worked example checks [b12, b13].")
    A("")
    for rid in ["a01", "a02", "a03", "a04", "a05", "a06", "a07", "a08", "a09", "a10"]:
        block(rid)
    A("### (a2) Gauge pressure and gradient")
    A("")
    for rid in ["a16", "a17", "a18", "a19", "a20"]:
        block(rid)
    A("### (a3) Shot start and bore resistance")
    A("")
    for rid in ["a11", "a12", "a13", "a14", "a15", "a21", "a22"]:
        block(rid)

    A("## (b) AMCP 706-150 (1965): Résal energy equation, Lagrange distribution, heat transfer; plus the Lagrange p(y) in Hunt and Corner")
    A("")
    A("Summary:")
    A("")
    A("- **Energy equation.** Fc/(γ−1) = MV²/2 + P(AX + U_ch − Cu)/(γ−1), with:")
    A("  - M = [(1+θ)W + C/3]/g;")
    A("  - θ = (2πk/nd)² + θ1 ≈ 0.01 + 0.04 = 0.05 (artillery);")
    A("  - heat loss through an adjusted γ, (γ̄−1)/(γ−1) = 1 + f, where f is about 0.15 'but may be considerably larger ... especially in small arms' [b02–b07].")
    A("- **Pressure ratios.** The handbook's breech : mean : base ratio (eq. 2-20) 'yields poor results' for small arms [b08].")
    A("- **Pressure distribution p(y).** Hunt (eqs 7,06/7,07/7,13) and Corner (eq. 13) give the quadratic Lagrange distribution between breech and base:")
    A("  - p = p_s[1 + ½(1 − σ²)·C/W], where σ is the volume fraction behind the section;")
    A("  - p_m = ⅓(2p_b + p_s);")
    A("  - p_b/p_s = 1 + C/2W;")
    A("  - p_m/p_s = 1 + C/3W;")
    A("  - with bore resistance (Corner): p(x) = p_s + (C/2W)(1 − x²/y²)(p_s − p_r) [b16, b18, b18b, b20].")
    A("- **Heat-transfer chapter.** h = 0.5·λ·C_p·ρ·v, and λ = (13.2 + 4 log10 d_cm)^-2. A caliber .50 MG gives λ ≈ 5×10⁻³ [b10–b13].")
    A("")
    for rid in ["b01", "b02", "b03", "b04", "b05", "b06", "b07", "b08", "b09", "b10", "b11", "b12", "b13", "b14",
                "b15", "b16", "b17", "b18", "b18b", "b19", "b20", "b21", "b22", "b23", "b24"]:
        block(rid)

    A("## (c) Semi-empirical heat loss: Corner 1950 §10.41 and Hunt 1951 §6.10")
    A("")
    A("Summary:")
    A("")
    A("- **What both books give.** Both quote C. K. Thornhill's fitted formula. Its structure and several constants are legible: 0.38, 0.6, the exponent 0.8375 on C, and the factor 0.76 = 2 × 0.38.")
    A("- **What cannot be read.** The numerator d exponent reads as 1.5 (Hunt OCR 'd 1 5'; Corner's heat/KE ratio shows 'd3/2'). The denominator d exponent, and the 10^-? exponent and d/C exponents in Corner's θ and H, are illegible in the OCR.")
    A("- **Do not implement yet.** Do not implement Thornhill's formula until a page image is read.")
    A("- **Legible and useful.** Corner's bore-roughness factor is 'usually about 1.25 in guns, rising to 1.4 or more in small arms'. His total-heat geometry (eq. 41) and KE factor (eq. 42) check arithmetically. Hunt's 1.05 secondary-work factor is 1% recoil plus 4% friction.")
    A("")
    for rid in ["c01", "c02", "c03", "c04", "c05", "c06"]:
        block(rid)

    A("## (d) Solid density of single-base and double-base nitrocellulose propellants")
    A("")
    A("Hunt 1951 Table 1.01 (p. 216), 'Density at 20° C. gm/c.c.', parsed by the script:")
    A("")
    A("| Propellant | Base type (inferred from composition) | Density g/cm³ | Gas volume c.c./g | Calorific value cal/g | Raw density token |")
    A("|---|---|---|---|---|---|")
    for r in recs:
        if r["id"].startswith("d01-"):
            v = r["values"]
            A("| %s | %s | %s | %s | %s | `%s` |" % (r["propellant"], r["base_type_from_composition"], v["density_g_cm3_at_20C"]["value"],
                                                   v["gas_volume_cc_per_g"]["value"], v["calorific_value_cal_per_g_water_liquid"]["value"],
                                                   v["density_g_cm3_at_20C"]["raw"]))
    sb = [r["values"]["density_g_cm3_at_20C"]["value"] for r in recs if r["id"].startswith("d01-") and r["base_type_from_composition"].startswith("single")]
    db = [r["values"]["density_g_cm3_at_20C"]["value"] for r in recs if r["id"].startswith("d01-") and r["base_type_from_composition"].startswith("double")]
    A("")
    A("Ranges:")
    A("")
    A("- Single-base: %.2f–%.2f g/cm³ (n=%d; NCT is a 99.5%% nitrocellulose propellant; NH and FNH/P are Dupont manufacture)." % (min(sb), max(sb), len(sb)))
    A("- Double-base (British cordites): %.2f–%.2f g/cm³ (n=%d)." % (min(db), max(db), len(db)))
    A("")
    A("These are 1940s British and Dupont gun propellants, not modern canister powders.")
    A("")
    A("Supporting values:")
    A("")
    A("- AMCP 706-150 gives a generic specific volume of 17.5 in³/lb, which is about 1.58 g/cm³ [d02].")
    A("- AMCP Table 1-1's density row could not be assigned to propellants because the OCR dropped its blank cells [d03].")
    A("- Corner's examples give 1.57 and 1.64 g/cm³, with the base type unstated [d04, d05].")
    A("")
    for rid in ["d02", "d03", "d04", "d05", "d06"]:
        block(rid)
    A("Per-propellant evidence for the table:")
    A("")
    for r in recs:
        if r["id"].startswith("d01-"):
            A("- **%s** (%s, p. %s): %s" % (r["propellant"], r["sources"][0]["url"], r["sources"][0]["page"], ev(r, 400)[2:]))
    A("")

    A("## (e) Secondary-work factor K1 and pressure exponent n")
    A("")
    A("Summary:")
    A("")
    A("- **No source gives a measured small-arms K1.** The published factors are all artillery-oriented:")
    A("  - AMCP 706-150: 1 + θ = 1.05, with θ1 ≈ 0.04 friction and ≈ 0.01 rotation, plus C/3 for the gas [b04];")
    A("  - Hunt: 1.05 w + C/3, made up of 1% recoil and 4% friction [b15, c02];")
    A("  - Corner: rotational m ≈ 1.005 at 30 cal/turn and 1.02 at 15 cal/turn [e04].")
    A("- **Small-arms context.** Corner says x is largest for small calibres [b23], and AMCP says the heat-loss f is larger in small arms [b05]. Both statements bear on how the losses should be split.")
    A("- **Pressure exponent n.**")
    A("  - The one small-arms value found is from Stiefel 1980 (US small-arms propellants), quoting Riefler & Lowery's closed-bomb constant-exponent model for ball propellants: **n = 0.8053**, with r in in/s and P in psi [e05]. The OCR shows 0.8033 once.")
    A("  - General gun-propellant statements: AMCP gives 0.8–0.9, and assumes 0.8 in the Taylor system [e01, b09]. Corner gives 'commonly near 0.9', with 1.02 the highest production value [e02, e03].")
    A("  - Hunt Table 5.01 gives per-propellant α for British and Dupont gun propellants [e08-*].")
    A("")
    for rid in ["e01", "e02", "e03", "e04", "e05", "e06", "e07"]:
        block(rid)
    A("Hunt 1951 Table 5.01 (p. 226) pressure index α (parsed by the script; tokens with a lost decimal separator are not interpreted):")
    A("")
    A("| Propellant | α | raw α token | raw row tokens |")
    A("|---|---|---|---|")
    for r in recs:
        if r["id"].startswith("e08-"):
            v = r["values"]
            A("| %s | %s | `%s` | `%s` |" % (r["propellant"], v["alpha_pressure_index"]["value"], v["alpha_pressure_index"]["raw"], v["row_tokens_raw"]["raw"].replace(" | ", " ; ")))
    A("")
    A("## Still open")
    A("")
    A("- **Page images needed.** Read page images of the following:")
    A("  - IBHVG2 pp. 43–50 (equations C.01–C.22 and D.13–D.27, with the errata to D.18 and D.21);")
    A("  - Hunt p. 71 (eq. 6,15 exponents);")
    A("  - Corner pp. 425–426 (Thornhill θ, H and x exponents).")
    A("- **Black & Comenetz original.** The NDRC 1946 Div. 1 summary report, chapter 5, was not found on an allowed host.")
    A("- **K1.** No small-arms-specific secondary-work factor was found.")
    A("- **Small-arms solid density.** No small-arms canister-powder solid density was found. AMCP 706-175 or the propellant specifications would be the next place to look.")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
