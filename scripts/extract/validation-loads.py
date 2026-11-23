#!/usr/bin/env python3
"""
Deterministic extractor for ORKA "validation-loads": published, pressure-tested
handload data (cartridge / bullet / case / primer / COL / barrel / powder /
charge / velocity / measured pressure) used to calibrate and validate the
interior-ballistics model.

Sources handled here:
  * Hodgdon Annual Manual 2025 (public PDF in the Hodgdon "Reloading Manuals
    Library").  Every Rifle Data and Pistol Data row (start + max loads) and the
    SubSonic / Reduced Recoil "recommended load" rows are parsed from word
    coordinates (pdftotext -bbox), so the two-column layout is split by
    geometry, never by retyping values.

Run:  python3 -I scripts/extract/validation-loads.py
Downloads are cached in the scratchpad SRC_DIR (not committed).
Output: research/raw2/validation-loads.json
"""
import html
import json
import os
import random
import re
import subprocess
import sys
import time

RETRIEVED = "2026-11-23"
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.environ.get(
    "ORKA_SRC_DIR",
    "/tmp/claude-0/-home-user-ORKA/29ce603d-ccc3-55ef-b8fe-c585397ac7c1/scratchpad/sources/validation-loads",
)
OUT = os.path.join(REPO, "research", "raw2", "validation-loads.json")

HODGDON_DOCS = [
    {
        "key": "AM25",
        "url": "https://hodgdonpowderco.com/wp-content/uploads/2026/04/AM25.pdf",
        "local": "hodgdon/AM25.pdf",
        "title": "Hodgdon 2025 Annual Manual (Hodgdon, IMR, Winchester, Accurate, Ramshot load data)",
        "date": "2025 edition (PDF created 2026-02-26)",
        "landing": "https://hodgdonpowderco.com/reloading-manuals-library/",
    },
]

# --------------------------------------------------------------------------
# download helpers (cache first; obey robots Crawl-delay: 10 on hodgdonpowderco.com)
# --------------------------------------------------------------------------
_last_req = {}


def fetch(url, local, delay=10):
    path = os.path.join(SRC_DIR, local)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    host = url.split("/")[2]
    wait = _last_req.get(host, 0) + delay - time.time()
    if wait > 0:
        time.sleep(wait)
    subprocess.run(["curl", "-sS", "-L", "-m", "600", "-o", path, url], check=True)
    _last_req[host] = time.time()
    return path


def ws(s):
    return re.sub(r"\s+", " ", s).strip()


# --------------------------------------------------------------------------
# powder brand classification (Hodgdon manual prints Accurate/Ramshot/Winchester
# powders without a brand prefix; classification below is by product name).
# --------------------------------------------------------------------------
POWDER_BRAND = {}
for n in ["H4895", "Varget", "Benchmark", "CFE 223", "BL-C(2)", "H335", "H322", "H4198", "H4227", "H110",
          "H4350", "H4831", "H4831SC", "H1000", "H380", "H414", "H450", "H870", "H50BMG", "US 869", "Retumbo",
          "Hybrid 100V", "Superformance", "LEVERevolution", "CFE BLK", "CFE Pistol", "Titegroup", "HP-38",
          "Longshot", "Universal", "HS-6", "Lil'Gun", "Clays", "International", "Titewad", "Extreme",
          "Trail Boss", "H4350SC", "H4166", "Lil’Gun", "Lil' Gun", "Lil’ Gun", "Clays (Hodgdon)", "Purple",
          "CFE 6.5", "H-110"]:
    POWDER_BRAND[n] = "Hodgdon"
for n in ["748", "760", "StaBALL Match", "StaBALL 6.5", "StaBALL HD", "231", "244", "296", "572", "WST", "WSF",
          "AutoComp", "Super Handicap", "Super-Target", "Super Target", "WAP", "WSL", "W571", "Ball 777"]:
    POWDER_BRAND[n] = "Winchester"
for n in ["2015", "2230", "2460", "2495", "2520", "2700", "4064", "4350", "5744", "1680", "3100", "8700",
          "LT-30", "LT-32", "Magpro", "MagPro", "No. 2", "No. 5", "No. 7", "No. 9", "No. 11FS", "4100", "TCM",
          "2200", "2230C", "Solo 1000", "Nitro 100", "Nitro 100 NF", "AA 2200", "4000-MR", "XMR 4350"]:
    POWDER_BRAND[n] = "Accurate"
for n in ["TAC", "Big Game", "Hunter", "Magnum", "X-Terminator", "Enforcer", "True Blue", "Silhouette", "Zip",
          "Competition", "LRT", "Grand", "Wild Boar", "ZIP"]:
    POWDER_BRAND[n] = "Ramshot"
# Alliant / others occasionally appear in manuals; leave unknowns as None.


def powder_brand(name):
    n = name.strip()
    if n.startswith("IMR ") or n in ("Trail Boss",):
        return "IMR" if n.startswith("IMR ") else "Hodgdon"
    if n in ("SR 4756", "SR 7625", "PB", "Hi-Skor 700-X", "Hi-Skor 800-X", "700-X", "800-X", "IMR Red",
             "IMR Blue", "IMR Green", "IMR Unequal", "IMR Target"):
        return "IMR"
    return POWDER_BRAND.get(n)


# --------------------------------------------------------------------------
# Hodgdon Annual Manual parser
# --------------------------------------------------------------------------
WORD_RE = re.compile(
    r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>', re.S)
PAGE_RE = re.compile(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>', re.S)

NUM_CH = r"\d+(?:\.\d+)?"
PRES = r"\d{1,3}(?:,\d{3})+|\d{3,6}"
UNIT = r"(?i:PSI|CUP)"
ROW6_RE = re.compile(
    r"^(?P<powder>.+?)\s+"
    r"(?P<sg>" + NUM_CH + r")(?P<sc>\s?C?)(?P<sa>\*?)\s+(?P<sv>\d{3,4})\s+(?P<sp>" + PRES + r")\s*(?P<spu>" + UNIT + r")\s+"
    r"(?P<mg>" + NUM_CH + r")(?P<mc>\s?C?)(?P<ma>\*?)\s+(?P<mv>\d{3,4})\s+(?P<mp>" + PRES + r")\s*(?P<mpu>" + UNIT + r")$"
)
ROW3_RE = re.compile(
    r"^(?P<powder>.+?)\s+"
    r"(?P<g>" + NUM_CH + r")(?P<c>\s?C?)(?P<a>\*?)\s+(?P<v>\d{3,4})\s+(?P<p>" + PRES + r")\s*(?P<pu>" + UNIT + r")$"
)
BARREL_RE = re.compile(
    r"^Barrel:\s*(?P<bbl>\d+(?:\.\d+)?)\s*[”\"]?\s*Twist:\s*(?P<tw>[^\s”\"]+)\s*[”\"]?\s*Trim:\s*(?P<trim>\d*\.\d+|\d+)\s*[”\"]?\s*$",
    re.I)
BULLET_RE = re.compile(r"^Bullet:\s*(?P<w>\d+(?:\.\d+)?)\s*GR\.?\s*(?P<rest>.*?)\s+Dia:\s*(?P<dia>\d*\.\d+)\s*[”\"]?\s*$", re.I)
CASE_RE = re.compile(r"^Case:\s*(?P<case>.+?)\s+Primer:\s*(?P<primer>.+?)\s+COL:\s*(?P<col>\d*\.\d+)\s*[”\"]?\s*$", re.I)
POWDER_NAME_RE = re.compile(r"^(?!.*\b(?:PSI|CUP)\b)(?!.*\d+\.\d+\s+\d{3,4})[A-Za-z0-9][A-Za-z0-9 .()'’/+-]{0,30}$")
SKIP_RE = re.compile(
    r"^(Starting Loads|Maximum Loads|Starting Loads Maximum Loads|Powder Grs Vel Pressure.*|Recommended Load.*|"
    r"NEVER EXCEED MAXIMUM LOADS|FINAL|\*Max loads.*|hodgdon(powderco)?\.com\s*\d*|\d+\s+hodgdon(powderco)?\.com|"
    r"R ?ifle D ?ata|P ?istol D ?ata|S ?ub ?S ?onic|R ?educed R ?ecoil)$", re.I)


def norm_key(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def parse_toc(pages_text):
    """Canonical cartridge names from the table of contents ('name .....page')."""
    names = {}
    pat = re.compile(r"([0-9A-Za-z](?:(?!\s{3})[^.\n]|\.(?!\.))*?[^.\s])\s*\.{2,}\s*(\d{1,3})")
    for p in pages_text[:8]:
        for m in pat.finditer(p):
            nm = ws(m.group(1)).rstrip("*").strip()
            names[norm_key(nm)] = nm
    return names


def collapse(k):
    return re.sub(r"(.)\1+", r"\1", k)


TITLE_KEEP = {"ACP", "SPC", "ARC", "GT", "PRC", "FN", "TCM", "AAC", "SOCOM", "SIG", "WSM", "RPM", "H&R", "S&W",
              "H", "T/C", "BMG"}


def canon_cartridge(raw, toc):
    """Map a printed (small-caps, glyph-split) section title to the manual's own TOC spelling."""
    r = raw.rstrip("*").strip()
    note = None
    m = re.match(r"^(.*?)\s+-\s+(Pistol|Rifle)$", r, re.I)
    if m:
        r = m.group(1)
        note = "Printed section title '%s' (%s data); TOC spelling used." % (raw, m.group(2).title())
    k = norm_key(r)
    if k in toc:
        return toc[k], note, True
    ck = collapse(k)
    hits = [v for kk, v in toc.items() if collapse(kk) == ck]
    if len(set(hits)) == 1:
        return hits[0], note or ("Printed section title '%s'; TOC spelling used." % raw), True
    hits = sorted({v for kk, v in toc.items() if collapse(kk).startswith(ck) and len(k) >= 4})
    if len(hits) == 1:
        return hits[0], "Printed section title '%s'; matched to TOC entry '%s'." % (raw, hits[0]), True
    # fallback: tidy small-caps casing, keep as printed otherwise
    toks = []
    for t in r.split():
        if t.upper() in TITLE_KEEP:
            toks.append(t.upper())
        elif re.search(r"[A-Za-z]", t) and not re.match(r"^\d", t):
            toks.append(t[:1].upper() + t[1:].lower())
        else:
            toks.append(t.lower() if re.match(r"^\d", t) else t)
    return " ".join(toks), "Printed section title '%s' not found in TOC; casing normalised." % raw, False


def parse_legend(page_text):
    """Brand abbreviations from the manual's LEGEND page."""
    brands = {}
    bullets = {}
    sect = None
    for line in page_text.splitlines():
        t = line.strip()
        if t in ("BRANDS", "PRIMERS", "DATA", "BULLETS", "LEGEND"):
            sect = t
            continue
        if not t or sect not in ("BRANDS", "BULLETS"):
            continue
        # entries are 'ABBR   Full name' repeated up to 3 times per line, separated by 3+ spaces
        parts = re.split(r"\s{3,}", t)
        i = 0
        while i + 1 < len(parts):
            ab, full = parts[i].strip(), parts[i + 1].strip()
            if sect == "BRANDS":
                brands[ab] = full
            else:
                bullets[ab] = full
            i += 2
    return brands, bullets


def page_words(page_xml):
    words = []
    for m in WORD_RE.finditer(page_xml):
        x0, y0, x1, y1 = (float(m.group(i)) for i in range(1, 5))
        words.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "t": html.unescape(m.group(5))})
    return words


def rows_of(words, tol=2.5):
    """Group words into visual rows by vertical centre (titles mix large and small caps glyph runs)."""
    ws_ = sorted(words, key=lambda w: ((w["y0"] + w["y1"]) / 2, w["x0"]))
    rows = []
    for w in ws_:
        c = (w["y0"] + w["y1"]) / 2
        if rows and abs(c - rows[-1]["y"]) <= tol:
            rows[-1]["w"].append(w)
        else:
            rows.append({"y": c, "w": [w]})
    out = []
    for r in rows:
        r["w"].sort(key=lambda w: w["x0"])
        parts = []
        prev = None
        for w in r["w"]:
            # glyph runs that touch (gap < 0.6 pt) are one printed word, e.g. 'R'+'emington'
            if prev is not None and w["x0"] - prev["x1"] < 0.6:
                parts[-1] += w["t"]
            else:
                parts.append(w["t"])
            prev = w
        out.append({"y": r["y"], "words": r["w"], "text": ws(" ".join(parts))})
    return out


def hodgdon_parse(doc, log):
    pdf = fetch(doc["url"], doc["local"])
    txt_path = pdf[:-4] + ".txt"
    bbox_path = pdf[:-4] + ".bbox.html"
    if not os.path.exists(txt_path):
        subprocess.run(["pdftotext", "-layout", pdf, txt_path], check=True)
    if not os.path.exists(bbox_path):
        subprocess.run(["pdftotext", "-bbox", pdf, bbox_path], check=True)
    pages_text = open(txt_path, encoding="utf-8").read().split("\f")
    toc = parse_toc(pages_text)
    legend_page = next(i for i, p in enumerate(pages_text) if re.search(r"^\s*LEGEND\s*$", p, re.M) and "BRANDS" in p)
    brands, bullet_abbr = parse_legend(pages_text[legend_page])
    intro_page = next(i for i, p in enumerate(pages_text) if "Pressures were gauged by one of two methods" in p)
    # the introduction is set in two columns: rebuild left column then right column from the -layout text
    ip = pages_text[intro_page].split("\n")
    starts = {}
    for l_ in ip:
        mm_ = re.search(r"\S\s{3,}(\S)", l_)
        if mm_:
            starts[mm_.start(1)] = starts.get(mm_.start(1), 0) + 1
    split_at = max(starts, key=starts.get)
    col_text = ws(" ".join(l_[:split_at] for l_ in ip) + " " + " ".join(l_[split_at:] for l_ in ip))
    m = re.search(r"Pressures were gauged by one of two methods.*?pounds per square inch \(PSI\)\.", col_text)
    method_evidence = ws(m.group(0)) if m else None
    m2 = re.search(r"Primarily, the data for this edition.*?measured case heads\.", col_text)
    test_evidence = ws(m2.group(0)) if m2 else None

    xml = open(bbox_path, encoding="utf-8").read()
    pages = PAGE_RE.findall(xml)
    records = []
    unparsed = []
    state = {"cartridge_raw": None, "cartridge": None, "barrel": None, "twist": None, "trim": None,
             "barrel_line": None, "cart_line": None, "bullet": None, "case": None, "section": None}
    pending_name = None
    for pi, (pw, ph, pxml) in enumerate(pages):
        pno = pi + 1
        ptxt = pages_text[pi] if pi < len(pages_text) else ""
        head = ptxt[:400]
        section = None
        for key, lab in (("Rifle Data", "Rifle Data"), ("Pistol Data", "Pistol Data"),
                         ("SubSonic", "SubSonic"), ("Reduced Recoil", "Reduced Recoil")):
            if re.search(r"^\s*" + key + r"\s*$", head, re.M):
                section = lab
        if section is None or not re.search(r"Powder\s+Grs\s+Vel\s+Pressure", head):
            continue
        printed = None
        mm = re.search(r"hodgdon(?:powderco)?\.com\s+(\d{1,3})\s*$|^\s*(\d{1,3})\s+hodgdon(?:powderco)?\.com", ptxt.strip()[-200:], re.M)
        if mm:
            printed = int(mm.group(1) or mm.group(2))
        if section != state["section"]:
            state.update({"section": section})
        words = page_words(pxml)
        width = float(pw)
        hdr = [w for w in words if w["y0"] < 70]
        powders = sorted([w for w in hdr if w["t"] == "Powder"], key=lambda w: w["x0"])
        split = powders[1]["x0"] - 4 if len(powders) >= 2 else width / 2
        if len(powders) < 2:
            unparsed.append({"page": pno, "text": "", "why": "column split fell back to page middle"})
        page_flat = ws(ptxt)
        cols = [[w for w in words if w["x0"] < split], [w for w in words if w["x0"] >= split]]
        for ci, cw in enumerate(cols):
            grs = sorted([w for w in cw if w["t"] == "Grs" and w["y0"] < 70], key=lambda w: w["x0"])
            body = [w for w in cw if w["y0"] >= 58 and w["y0"] < float(ph) - 40]
            for row in rows_of(body):
                t = row["text"]
                if not t or SKIP_RE.match(t):
                    continue
                mb = BARREL_RE.match(t)
                if mb:
                    name_raw = pending_name
                    canon, cnote, ok = canon_cartridge(name_raw, toc) if name_raw else (None, None, False)
                    state.update({"cartridge_raw": name_raw, "cartridge": canon,
                                  "barrel": float(mb.group("bbl")), "twist": mb.group("tw"),
                                  "trim": float(mb.group("trim")), "barrel_line": t, "cart_line": name_raw,
                                  "bullet": None, "case": None, "cart_note": cnote})
                    pending_name = None
                    continue
                mbu = BULLET_RE.match(t)
                if mbu:
                    rest = mbu.group("rest").split()
                    mfr_abbr, model, mfr = None, " ".join(rest), None
                    if rest and rest[0] in brands:
                        mfr_abbr, mfr, model = rest[0], brands[rest[0]], " ".join(rest[1:])
                    state["bullet"] = {"w": float(mbu.group("w")), "dia": float(mbu.group("dia")), "mfr": mfr,
                                       "mfr_abbr": mfr_abbr, "model": model or None, "line": t,
                                       "mfr_in_legend": bool(rest and rest[0] in brands)}
                    state["case"] = None
                    continue
                mc = CASE_RE.match(t)
                if mc:
                    state["case"] = {"case": mc.group("case").strip(), "primer": mc.group("primer").strip(),
                                     "col": float(mc.group("col")), "line": t}
                    continue
                m6 = ROW6_RE.match(t)
                m3 = None if m6 else ROW3_RE.match(t)
                mm_ = m6 or m3
                if mm_ and not POWDER_NAME_RE.match(mm_.group("powder")):
                    unparsed.append({"page": pno, "text": t, "why": "row does not fit the numeric pattern cleanly "
                                     "(e.g. typo in a value); skipped entirely"})
                    continue
                if (m6 or m3) and state["bullet"] and state["case"] and state["cartridge"]:
                    loads = []
                    if m6:
                        loads.append(("start", m6.group("powder"), m6.group("sg"), m6.group("sc"), m6.group("sa"),
                                      m6.group("sv"), m6.group("sp"), m6.group("spu")))
                        loads.append(("max", m6.group("powder"), m6.group("mg"), m6.group("mc"), m6.group("ma"),
                                      m6.group("mv"), m6.group("mp"), m6.group("mpu")))
                    else:
                        if section in ("SubSonic", "Reduced Recoil"):
                            lt = "other"
                        else:
                            # decide start/max column from the charge word's x position vs. the two 'Grs' headers
                            gword = next((w for w in row["words"] if re.fullmatch(NUM_CH + r"C?\*?", w["t"])
                                          and w["t"].startswith(m3.group("g"))), None)
                            lt = "max"
                            if gword and len(grs) >= 2:
                                d0 = abs(gword["x1"] - grs[0]["x1"])
                                d1 = abs(gword["x1"] - grs[1]["x1"])
                                lt = "start" if d0 < d1 else "max"
                        loads.append((lt, m3.group("powder"), m3.group("g"), m3.group("c"), m3.group("a"),
                                      m3.group("v"), m3.group("p"), m3.group("pu")))
                    for lt, powder, g, c, a, v, p, pu in loads:
                        powder = powder.strip()
                        b, k = state["bullet"], state["case"]
                        notes = []
                        if section in ("SubSonic", "Reduced Recoil"):
                            notes.append(section + " section: single 'Recommended Load' (not a start/max ladder).")
                        if a:
                            notes.append("Asterisk after C: compressed with IMR 7828 SSC will not fit with standard "
                                         "IMR 7828; reduce by four percent (manual footnote).")
                        if state["cartridge_raw"] and state["cartridge_raw"].rstrip().endswith("*"):
                            notes.append("Cartridge title carries an asterisk: see the manual's warning page.")
                        if not b["mfr_in_legend"]:
                            notes.append("Bullet description '%s' does not start with a maker abbreviation from the "
                                         "manual legend; bulletMfr left null, description kept in bulletModel."
                                         % b["model"])
                        if state.get("cart_note"):
                            notes.append(state["cart_note"])
                        if printed:
                            notes.append("Printed page %d." % printed)
                        unit = "psi" if pu.upper() == "PSI" else "CUP"
                        rec = {
                            "cartridge": state["cartridge"],
                            "bulletMfr": b["mfr"],
                            "bulletModel": b["model"],
                            "bulletWeightGr": b["w"],
                            "bulletDiameterIn": b["dia"],
                            "bulletLengthIn": None,
                            "caseBrand": k["case"],
                            "caseTrimLengthIn": state["trim"],
                            "primer": k["primer"],
                            "coalIn": k["col"],
                            "barrelLengthIn": state["barrel"],
                            "twist": state["twist"],
                            "powder": powder,
                            "powderMfr": powder_brand(powder),
                            "chargeGr": float(g),
                            "velocityFps": int(v),
                            "pressure": int(p.replace(",", "")),
                            "pressureUnit": unit,
                            "pressureMethod": ("electronic transducer (PSI), per manual introduction" if unit == "psi"
                                               else "copper crusher (CUP), per manual introduction"),
                            "loadType": lt,
                            "compressed": "C" in c,
                            "dataSection": section,
                            "sources": [{"url": doc["url"], "type": "manufacturer", "page": pno,
                                         "retrieved": RETRIEVED}],
                            "evidence": ws(" | ".join(x for x in [state["cart_line"], state["barrel_line"], b["line"],
                                                                   k["line"], t] if x)),
                            "notes": " ".join(notes) or None,
                            "_layout_ok": t in page_flat,
                        }
                        records.append(rec)
                    continue
                if m6 or m3:
                    unparsed.append({"page": pno, "text": t, "why": "data row without bullet/case/cartridge context"})
                    continue
                if re.match(r"^(Case|Bullet|Barrel|Primer)\b", t, re.I):
                    # a context line we could not parse: drop context so later rows are not mis-attributed
                    unparsed.append({"page": pno, "text": t, "why": "unparsed context line; context reset"})
                    state["case"] = None
                    if t.lower().startswith(("bullet", "barrel")):
                        state["bullet"] = None
                    if t.lower().startswith("barrel"):
                        state["cartridge"] = None
                    continue
                # anything else: candidate cartridge title (confirmed only if a Barrel: row follows)
                if pending_name and pending_name != t:
                    unparsed.append({"page": pno, "text": pending_name, "why": "unrecognised row"})
                pending_name = t
    log["hodgdon_" + doc["key"]] = {
        "legendBrands": brands, "legendBulletTypes": bullet_abbr, "pressureMethodEvidence": method_evidence,
        "testConditionsEvidence": test_evidence, "introductionPage": intro_page + 1,
        "unparsedRows": unparsed,
    }
    return records


# --------------------------------------------------------------------------
# Reload Swiss (Nitrochemie Wimmis AG) "Ladedaten / Reloading Data, Issue 2025"
# Official RS data pages only (columns include measured pressure in bar for
# start and max loads).  The "Customer reloading data" section (no pressure,
# customer-measured) is NOT used.
# --------------------------------------------------------------------------
RS_DOC = {
    "key": "RS2025",
    "url": "https://www.reload-swiss.com/Reload%20Swiss/Service/Brosch%C3%BCren%20und%20Produktdatenbl%C3%A4tter/"
           "Reload-Swiss-Ladedaten-Guide-2025-DE-EN-small.pdf",
    "local": "rs/guide2025-small.pdf",
    "title": "Reload Swiss RS Ladedaten / Reloading Data, Issue 2025 (Nitrochemie Wimmis AG)",
    "date": "Issue 2025 (PDF created 2025-01-11)",
    "landing": "https://www.reload-swiss.com/en/loading-data/brochures-and-product-datasheets",
}
RS_DEC = r"\d+,\d+"
RS_Q = "[‘’'\"“”]*"
RS_TAIL_RE = re.compile(
    r"(?P<sg>" + RS_DEC + r"|-)\s+(?P<sgr>" + RS_DEC + r"|-)\s+(?P<sv>\d+|-)\s+(?P<sp>\d+|-)\s+(?P<sf>\d+|-)\s+"
    r"(?P<mg>" + RS_DEC + r")\s+(?P<mgr>" + RS_DEC + r")\s+(?P<mv>\d+)\s+(?P<mp>\d+|-)\s+(?P<mf>\d+|-)\s+"
    r"(?P<e>\d+|-)\s+"
    r"(?P<bbl>n\.a\.|(?P<bblmm>\d+)(?:\s*\((?P<twist>1:\s*[\d.,]+)\s*" + RS_Q + r"\))?)\s+"
    r"(?P<col>" + RS_DEC + r"|n\.a\.|\d+)(?:\s+(?P<notes>\S.*?))?\s*$")
RS_ROW_RE = re.compile(
    r"^(?P<cal>\S.*?)\s{2,}(?P<mass>\d{1,3})\s{2,}(?P<mid>.*?)\s{2,}(?P<powder>RS\s?\d{2})\s{2,}(?P<tail>.*)$")
RS_CANON = {
    "223 Rem.": "223 Remington", "308 Win.": "308 Winchester", "6.5 Creedmoor": "6.5 Creedmoor",
    "30-06 Spring.": "30-06 Springfield", "300 Win. Mag.": "300 Winchester Magnum", "243 Win.": "243 Winchester",
    "6 mm Creedmoor": "6mm Creedmoor", "270 Win.": "270 Winchester", "7 Rem. Mag.": "7mm Remington Magnum",
    "9 mm Luger": "9mm Luger", "45 ACP (Auto)": "45 ACP", "357 Magnum": "357 Magnum",
    "44 Rem. Mag.": "44 Remington Magnum",
}
RS_FLAGS = {"C": "C = Compressed load", "IP": "IP = IPSC load", "HP": "HP = Attention: high pressure",
            "OL": "OL = Over length!"}


def rs_dec(s):
    return None if s in (None, "-", "n.a.") else float(s.replace(",", "."))


def rs_phrases(s, offset=0):
    """Cells of a -layout line: runs of text separated by 2+ spaces, with character centres."""
    return [{"t": m.group(0), "a": m.start() + offset, "b": m.end() + offset,
             "c": (m.start() + m.end()) / 2.0 + offset} for m in re.finditer(r"\S+(?: \S+)*", s)]


def reload_swiss_parse(doc, log, keep_all=False):
    pdf = fetch(doc["url"], doc["local"], delay=2)
    txt_path = pdf[:-4] + ".txt"
    if not os.path.exists(txt_path):
        subprocess.run(["pdftotext", "-layout", pdf, txt_path], check=True, stderr=subprocess.DEVNULL)
    pages = open(txt_path, encoding="utf-8").read().split("\f")
    records, unparsed = [], []
    legend_line = None
    for pi, ptxt in enumerate(pages):
        pno = pi + 1
        # official RS data pages carry 'Filling Ratio' in the header; customer-data pages do not
        if "Filling Ratio" not in ptxt or "Calibre" not in ptxt or "durch Beschussamt" in ptxt:
            continue
        lines = ptxt.split("\n")
        hdr = next((l for l in lines if l.strip().startswith("Calibre")), None)
        units = next((l for l in lines if re.match(r"^\s*gr\s+g\s+gr\s+m/s\s+bar", l)), None)
        section = "Handguns" if "HANDGUNS" in ptxt[:3000] else "Rifles"
        ph = rs_phrases(hdr)
        names = [p["t"] for p in ph]
        if names[:7] != ["Calibre", "Mass", "Type", "Producer", "Producer", "Type", "Type"]:
            unparsed.append({"page": pno, "text": ws(hdr), "why": "unexpected header; page skipped"})
            continue
        centres = [ph[i]["c"] for i in range(2, 6)]  # bullet type, bullet producer, case producer, primer
        colnames = ["bulletModel", "bulletMfr", "caseBrand", "primer"]
        lg = next((ws(l) for l in lines if "C = Compressed load" in l), None)
        if lg:
            legend_line = ws(lg[lg.find("C = Compressed load"):])
        printed = re.findall(r"^\s*(\d{1,3})\s{20,}(\d{1,3})\s*$", ptxt.strip().split("\n")[-1])
        printed = "%s-%s" % printed[0] if printed else None
        # blocks of consecutive non-blank lines
        blocks, cur = [], []
        for idx, l in enumerate(lines):
            if l.strip():
                cur.append((idx, l))
            elif cur:
                blocks.append(cur)
                cur = []
        if cur:
            blocks.append(cur)
        for blk in blocks:
            rows = [(i, l, RS_ROW_RE.match(l)) for i, l in blk]
            data = [(i, l, m) for i, l, m in rows if m and RS_TAIL_RE.match(m.group("tail"))]
            for i, l, m in rows:
                if m and not RS_TAIL_RE.match(m.group("tail")):
                    unparsed.append({"page": pno, "text": ws(l), "why": "numeric columns did not match; skipped"})
            if not data:
                continue
            frags = [(i, l) for i, l in blk if all(i != d[0] for d in data)]
            for di, (i, l, m) in enumerate(data):
                cal = m.group("cal").strip()
                canon = RS_CANON.get(cal)
                if canon is None and not keep_all:
                    continue
                t = RS_TAIL_RE.match(m.group("tail"))
                cells = {k: [] for k in colnames}
                problem = None
                mid_ph = rs_phrases(m.group("mid"), m.start("mid"))
                for p in mid_ph:
                    k = min(range(4), key=lambda j: abs(p["c"] - centres[j]))
                    # a phrase that straddles the midpoint to a neighbouring column centre is ambiguous
                    for j in range(3):
                        mpt = (centres[j] + centres[j + 1]) / 2.0
                        if p["a"] < mpt - 1 < mpt + 1 < p["b"] and len(mid_ph) < 4:
                            problem = "cell text '%s' straddles a column boundary" % p["t"]
                    if cells[colnames[k]] and len(mid_ph) < 4:
                        problem = "two cells assigned to column %s" % colnames[k]
                    cells[colnames[k]].append((i, p["t"]))
                if len(mid_ph) == 4:  # all four present: assign strictly in printed order
                    cells = {colnames[j]: [(i, mid_ph[j]["t"])] for j in range(4)}
                # wrapped cell fragments: lines of the same block, nearest data row
                used_frags = []
                for fi, fl in frags:
                    near = min(range(len(data)), key=lambda q: abs(data[q][0] - fi))
                    if abs(data[near][0] - fi) == abs(data[di][0] - fi) and near != di:
                        problem = "wrapped fragment equidistant from two data rows"
                    if near != di:
                        continue
                    for p in rs_phrases(fl):
                        if p["c"] > (centres[3] + ph[6]["c"]) / 2.0 or p["c"] < ph[1]["c"]:
                            problem = "wrapped fragment '%s' outside the bullet/case/primer columns" % p["t"]
                            continue
                        k = min(range(4), key=lambda j: abs(p["c"] - centres[j]))
                        cells[colnames[k]].append((fi, p["t"]))
                    used_frags.append(fl)
                evidence_lines = [ws(x) for _, x in sorted([(fi, fl) for fi, fl in frags if fl in used_frags] +
                                                         [(i, l)])]
                if problem:
                    unparsed.append({"page": pno, "text": " | ".join(evidence_lines), "why": problem + "; skipped"})
                    continue
                val = {k: (ws(" ".join(x for _, x in sorted(v))) or None) for k, v in cells.items()}
                notes_raw = (t.group("notes") or "").strip()
                flags = [f.strip() for f in notes_raw.split(",")] if notes_raw else []
                compressed = "C" in flags
                bbl_mm = int(t.group("bblmm")) if t.group("bblmm") else None
                col_mm = rs_dec(t.group("col")) if "," in t.group("col") else None
                base_notes = []
                if canon is None:
                    base_notes.append("Cartridge as printed: '%s'." % cal)
                base_notes.append("Velocity is V5 (measured 5 m from the muzzle) printed in m/s; velocityFps = m/s / "
                                  "0.3048, rounded to 1 fps (velocityMps keeps the printed value).")
                base_notes.append("Pressure printed in bar ('Druck / Pressure'); the guide does not state the "
                                  "measurement method.")
                if bbl_mm is not None:
                    base_notes.append("Barrel ('Lauf / Barrel') printed as a bare number (%d), read as mm (the same "
                                      "guide's customer-data tables print barrel lengths as e.g. '600mm'); "
                                      "barrelLengthIn = mm / 25.4." % bbl_mm)
                else:
                    base_notes.append("Barrel length printed as '%s'." % t.group("bbl"))
                if col_mm is not None:
                    base_notes.append("C.O.L. printed in mm (%s); coalIn = mm / 25.4." % t.group("col"))
                for f in flags:
                    if f in RS_FLAGS:
                        base_notes.append("Notes column '%s' (legend: %s)." % (f, RS_FLAGS[f]))
                    else:
                        base_notes.append("Notes column: '%s'." % f)
                for k in ("caseBrand", "primer", "bulletMfr", "bulletModel"):
                    if val[k] in ("n.a.",):
                        base_notes.append("%s printed as 'n.a.'." % k)
                        val[k] = None
                if printed:
                    base_notes.append("Printed page spread %s." % printed)
                for lt, g, gr, v, p, fill in (("start", "sg", "sgr", "sv", "sp", "sf"),
                                             ("max", "mg", "mgr", "mv", "mp", "mf")):
                    if t.group(gr) in (None, "-") or t.group(v) in (None, "-"):
                        continue
                    vm = int(t.group(v))
                    pr = None if t.group(p) == "-" else int(t.group(p))
                    rec = {
                        "cartridge": canon or cal,
                        "bulletMfr": val["bulletMfr"],
                        "bulletModel": val["bulletModel"],
                        "bulletWeightGr": float(m.group("mass")),
                        "bulletDiameterIn": None,
                        "bulletLengthIn": None,
                        "caseBrand": val["caseBrand"],
                        "caseTrimLengthIn": None,
                        "primer": val["primer"],
                        "coalIn": round(col_mm / 25.4, 3) if col_mm is not None else None,
                        "barrelLengthIn": round(bbl_mm / 25.4, 2) if bbl_mm is not None else None,
                        "twist": (t.group("twist").replace(" ", "") + '"') if t.group("twist") else None,
                        "powder": m.group("powder").replace(" ", ""),
                        "powderMfr": "Reload Swiss",
                        "chargeGr": rs_dec(t.group(gr)),
                        "velocityFps": int(round(vm / 0.3048)),
                        "pressure": pr,
                        "pressureUnit": "bar" if pr is not None else None,
                        "pressureMethod": None,
                        "loadType": lt,
                        "compressed": compressed if lt == "max" else (False if not compressed else None),
                        "dataSection": section,
                        "chargeG": rs_dec(t.group(g)),
                        "velocityMps": vm,
                        "velocityMeasuredAt": "5 m from muzzle (V5)",
                        "loadDensityPct": None if t.group(fill) == "-" else int(t.group(fill)),
                        "coalMm": col_mm,
                        "barrelLengthMm": bbl_mm,
                        "cartridgeAsPrinted": cal,
                        "sources": [{"url": doc["url"], "type": "manufacturer", "page": pno, "retrieved": RETRIEVED}],
                        "evidence": " | ".join(evidence_lines),
                        "notes": None,
                        "_raw": [("chargeGr", t.group(gr)), ("velocityMps", t.group(v))]
                                + ([("pressure", t.group(p))] if pr is not None else [])
                                + ([("coalMm", t.group("col"))] if col_mm is not None else [])
                                + ([("barrelLengthMm", t.group("bblmm"))] if bbl_mm is not None else [])
                                + [("bulletWeightGr", m.group("mass"))],
                    }
                    n2 = list(base_notes)
                    if compressed:
                        n2.append("The 'C' flag is printed once per row; compressed is set true for the max load "
                                  "only and left null for the start load (not stated which charge is compressed)."
                                  if lt == "start" else "Compressed ('C') per the row's Notes column.")
                    if rec["loadDensityPct"] is not None:
                        n2.append("Filling ratio (Fuellgrad) %d %% printed for this charge (loadDensityPct)."
                                  % rec["loadDensityPct"])
                    rec["notes"] = " ".join(n2)
                    records.append(rec)
    log["reloadswiss_" + doc["key"]] = {"unparsedRows": unparsed, "legend": legend_line,
                                        "columnsEvidence": "Calibre Mass Type Producer Producer Type Type Charge "
                                                           "Charge Pressure Filling Ratio Charge Charge Pressure "
                                                           "Filling ratio Barrel Patrone C.O.L. Notes / units: gr g "
                                                           "gr m/s bar % g gr m/s bar % J"}
    return records


# --------------------------------------------------------------------------
# Shooters World powder manual (2023).  Tables: Caliber | Case | Projectile |
# Load Length | Starting Charge | Starting Velocity | Max Charge | Max Velocity |
# Max Pressure (PSI).  Cells wrap over several lines, so rows are rebuilt from
# word coordinates (pdftotext -bbox): every data row is a visual line with
# numbers in >= 5 of the 6 numeric columns; wrapped text is attached to the
# vertically nearest data row (only when clearly nearer than any other row).
# --------------------------------------------------------------------------
SW_DOC = {
    "key": "SW2023",
    "url": "https://shootersworldpowder.com/wp-content/uploads/2023/06/"
           "ShootersWorldManualInterior_CHRIS_WITH-COVER__RUSS-REVISED.pdf",
    "local": "sw/manual.pdf",
    "title": "Shooters World reloading manual (Shooters World / Lovex powders)",
    "date": "PDF created 2023-05-25",
    "landing": "https://shootersworldpowder.com/",
}
SW_NUMTOK = re.compile(r"^(N/A|\d[\d,]*(?:\.\d+)?C?|\.\d+|C|Safe|in|Garand|Load)$")
SW_SIDE_LABELS = {"RIFLE", "HANDGUN", "SHOTGUN", "/"}
SW_CAL = [
    (r"^\.?223 rem(ington)?$", "223 Remington"), (r"^\.?308 win(chester)?$", "308 Winchester"),
    (r"^6\.5 creedmoor$", "6.5 Creedmoor"), (r"^6 ?mm creedmoor$", "6mm Creedmoor"),
    (r"^\.?30-06 springfield( garand)?$", "30-06 Springfield"),
    (r"^\.?300 win(chester)? mag(num)?$", "300 Winchester Magnum"), (r"^\.?243 win(chester)?$", "243 Winchester"),
    (r"^\.?270 win(chester)?$", "270 Winchester"), (r"^7 ?mm rem(ington)? mag(num)?$", "7mm Remington Magnum"),
    (r"^9 ?mm luger$", "9mm Luger"), (r"^\.?45 (auto|acp)$", "45 ACP"), (r"^\.?357 mag(num)?$", "357 Magnum"),
    (r"^\.?44 rem(ington)? mag(num)?( carbine)?$", "44 Remington Magnum"),
]
SW_BULLET_MAKERS = ["Sierra", "Hornady", "Nosler", "Speer", "Berger", "Lapua", "Barnes", "Berry's", "Berry",
                    "Winchester", "Sinterfire", "Ervin", "Acme", "Zero", "Xtreme", "X-treme", "Swift",
                    "Precision Delta", "Dead Nuts", "Federal", "Remington"]


def sw_words(pxml):
    out = []
    for m in WORD_RE.finditer(pxml):
        x0, y0, x1, y1 = (float(m.group(i)) for i in range(1, 5))
        out.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "t": html.unescape(m.group(5)),
                    "xc": (x0 + x1) / 2, "yc": (y0 + y1) / 2})
    return out


def sw_lines(words, tol=2.0):
    out = []
    for w in sorted(words, key=lambda w: (w["yc"], w["x0"])):
        if out and abs(w["yc"] - out[-1]["yc"]) <= tol:
            out[-1]["w"].append(w)
        else:
            out.append({"yc": w["yc"], "w": [w]})
    for ln in out:
        ln["w"].sort(key=lambda w: w["x0"])
    return out


def sw_join(ws_):
    """Join words of one cell in reading order; re-join words hyphenated at a line break."""
    s = " ".join(w["t"] for w in sorted(ws_, key=lambda w: (round(w["yc"]), w["x0"])))
    return re.sub(r"(\w)- (\w)", r"\1\2", s).strip()


def sw_num(s):
    """'1,146' -> 1146 ; '41,590.0' -> 41590 ; '43.3' -> 43.3"""
    s = s.replace(",", "")
    return float(s)


def shooters_world_parse(doc, log, keep_all=False):
    pdf = fetch(doc["url"], doc["local"], delay=10)
    txt_path = pdf[:-4] + ".txt"
    bbox_path = pdf[:-4] + ".bbox.html"
    if not os.path.exists(txt_path):
        subprocess.run(["pdftotext", "-layout", pdf, txt_path], check=True)
    if not os.path.exists(bbox_path):
        subprocess.run(["pdftotext", "-bbox", pdf, bbox_path], check=True)
    pages_text = open(txt_path, encoding="utf-8").read().split("\f")
    pages = PAGE_RE.findall(open(bbox_path, encoding="utf-8").read())
    # powder names from the tables' own titles, e.g. 'TACTICAL RIFLE D073-08 RELOAD DATA'
    title_re = re.compile(r"^\s*([A-Z][A-Z0-9 ]*?[A-Z0-9]),?\s+([DS]\d{3}-\d{2}|S\d{3})\s+(?:PISTOL\s+)?RELOAD DATA",
                          re.M)
    code_names = {}
    for p in pages_text:
        for m in title_re.finditer(p):
            code_names[m.group(2)] = (m.group(1).strip(), ws(m.group(0)))
    records, unparsed = [], []
    for pi, (pw, ph, pxml) in enumerate(pages):
        pno = pi + 1
        ptxt = pages_text[pi]
        if "Projectile" not in ptxt or "Caliber" not in ptxt or "SHOT SHELL" in ptxt:
            continue
        # powder of this page's table
        powder, code, title_ev = None, None, None
        m = title_re.search(ptxt)
        if m:
            powder, code, title_ev = m.group(1).strip(), m.group(2), ws(m.group(0))
        else:
            mm = re.search(r"([DS]\d{3}-\d{2})\s+RELOAD DATA", ptxt)
            if mm and mm.group(1) in code_names:
                code = mm.group(1)
                powder = code_names[code][0]
                title_ev = ws(mm.group(0)) + " [powder name from the same code's title elsewhere in the manual: '%s']" \
                    % code_names[code][1]
            ms = re.search(r"POWDER SBR - SOCOM 63-01", ptxt)
            if ms:
                powder, code, title_ev = "SBR - SOCOM", "63-01", ms.group(0)
        if powder is None:
            unparsed.append({"page": pno, "text": ws(ptxt[:200]), "why": "no powder title found; page skipped"})
            continue
        powder_name = " ".join(t.capitalize() if t.isalpha() and t not in ("AR", "SBR", "SOCOM", "SW4350") else t
                               for t in powder.split())
        words = sw_words(pxml)
        H = lambda names: sorted([w for w in words if w["t"] in names and w["y0"] < 140], key=lambda w: w["x0"])
        try:
            cal, case, proj, ln = H(("Caliber",))[0], H(("Case",))[0], H(("Projectile", "Projectiles"))[0], \
                H(("Length",))[0]
            ch, vel = H(("Charge",)), H(("Velocity",))
            pr = H(("Pressure", "Pressure,", "Presure"))[0]
            numc = [ln["xc"], ch[0]["xc"], vel[0]["xc"], ch[1]["xc"], vel[1]["xc"], pr["xc"]]
        except (IndexError, KeyError):
            unparsed.append({"page": pno, "text": "", "why": "table header not found; page skipped"})
            continue
        txtc = [cal["xc"], case["xc"], proj["xc"]]
        hdr_bottom = max(w["y1"] for w in words if w["t"] in ("Length", "Charge", "Velocity") and w["y0"] < 140)
        # page numbers: 1-2 digit words alone on their line at the foot of the page
        body = [w for w in words if w["yc"] > hdr_bottom and w["t"] not in SW_SIDE_LABELS
                and not (re.fullmatch(r"\d{1,2}", w["t"]) and w["y0"] > float(ph) - 45
                         and not any(o is not w and abs(o["yc"] - w["yc"]) < 3 for o in words))]
        numreg = lambda w: w["xc"] >= ln["x0"] - 6 and SW_NUMTOK.match(w["t"])
        lines_ = sw_lines(body)
        rows = []
        for l_ in lines_:
            cols = [[] for _ in range(6)]
            for w in l_["w"]:
                if numreg(w):
                    cols[min(range(6), key=lambda j: abs(w["xc"] - numc[j]))].append(w)
            filled = sum(1 for c in cols if c)
            if filled >= 5 or (filled >= 3 and cols[0]):
                # rows with only 3-4 numeric cells are kept as 'broken' so their wrapped text is not
                # attached to a neighbouring row; they never produce records
                rows.append({"yc": l_["yc"], "num": cols, "line": l_, "txt": [[], [], []], "all": list(l_["w"]),
                             "problem": None if filled >= 5 else "only %d of 6 numeric cells on the row" % filled})
        if not rows:
            continue
        for l_ in lines_:
            isrow = any(r["line"] is l_ for r in rows)
            for w in l_["w"]:
                if isrow:
                    r = next(r for r in rows if r["line"] is l_)
                    if numreg(w):
                        continue
                else:
                    ds = sorted((abs(w["yc"] - r["yc"]), i) for i, r in enumerate(rows))
                    if ds[0][0] > 14 or (len(ds) > 1 and ds[1][0] - ds[0][0] < 3.0):
                        if ds[0][0] <= 14:
                            for _, i in ds[:2]:
                                rows[i]["problem"] = "text '%s' is about equally near two rows" % w["t"]
                        continue
                    r = rows[ds[0][1]]
                    r["all"].append(w)
                    if numreg(w):
                        r["num"][min(range(6), key=lambda j: abs(w["xc"] - numc[j]))].append(w)
                        continue
                r["txt"][min(range(3), key=lambda j: abs(w["xc"] - txtc[j]))].append(w)
        for r in rows:
            evl = sw_lines(r["all"])
            evidence = " | ".join(" ".join(w["t"] for w in l_["w"]) for l_ in evl)
            # numbers that landed in the Case column belong to the projectile (left-shifted weight)
            mv_ = [w for w in r["txt"][1] if re.fullmatch(r"\d+", w["t"])]
            for w in mv_:
                r["txt"][1].remove(w)
                r["txt"][2].append(w)
            cal_t = sw_join(r["txt"][0])
            case_t = sw_join(r["txt"][1])
            proj_ws = sorted(r["txt"][2], key=lambda w: (0 if w in mv_ else 1, round(w["yc"]), w["x0"]))
            proj_t = re.sub(r"(\w)- (\w)", r"\1\2", " ".join(w["t"] for w in proj_ws)).strip()
            canon = None
            for pat, nm in SW_CAL:
                if re.match(pat, ws(cal_t).lower()):
                    canon = nm
            if canon is None and not keep_all:
                continue
            num = [" ".join(w["t"] for w in sorted(c, key=lambda w: (round(w["yc"]), w["x0"]))) for c in r["num"]]
            problem = r["problem"]
            mcol = re.fullmatch(r"(\d*\.\d+|\d)", num[0])
            mmc = re.fullmatch(r"(\d+(?:\.\d+)?)\s?(C?)", num[3])
            mmv = re.fullmatch(r"(\d{1,2},\d{3}|\d{3,4})", num[4])
            mmp = re.fullmatch(r"(\d{1,3},\d{3}(?:\.0)?|\d{4,5})|N/A", num[5])
            msc = re.fullmatch(r"(\d+(?:\.\d+)?)\s?(C?)", num[1])
            msv = re.fullmatch(r"(\d{1,2},\d{3}|\d{3,4})", num[2])
            if not (mcol and mmc and mmv and mmp):
                problem = problem or "numeric columns incomplete or not numeric: %s" % num
            mw = re.match(r"^(\d+)\s*(?:gr|grain|grains|gt)?\b\s*(.*)$", proj_t)
            if not mw:
                problem = problem or "projectile '%s' does not start with a weight" % proj_t
            if problem:
                unparsed.append({"page": pno, "text": evidence, "why": problem + "; skipped"})
                continue
            rest = mw.group(2).strip()
            bmfr = next((b for b in SW_BULLET_MAKERS if rest == b or rest.startswith(b + " ")), None)
            notes = ["Projectile printed as '%s'." % proj_t]
            if canon and ws(cal_t) != canon:
                notes.append("Caliber printed as '%s'." % cal_t)
            if "garand" in cal_t.lower() or "Garand" in num[1]:
                notes.append("Garand load (caliber/start cells mention Garand).")
            if "carbine" in cal_t.lower():
                notes.append("Caliber cell says 'carbine': carbine-length barrel, length not stated.")
            bmatch = re.search(r"(\d+)-inch", cal_t + " " + evidence)
            barrel = float(bmatch.group(1)) if bmatch and "Barrel" in evidence else None
            if barrel is None:
                notes.append("The manual does not state the test barrel length or primer for this table.")
            notes.append("Pressure column is 'Max Pressure (PSI)': it belongs to the max load; the start load has no "
                         "published pressure. Measurement method not stated.")
            notes.append("Powder '%s' = Shooters World code %s (table title: '%s')." % (powder_name, code, title_ev))
            base = {
                "cartridge": canon or ws(cal_t),
                "bulletMfr": bmfr,
                "bulletModel": (rest[len(bmfr):].strip() if bmfr else rest) or None,
                "bulletWeightGr": float(mw.group(1)),
                "bulletDiameterIn": None, "bulletLengthIn": None,
                "caseBrand": case_t or None, "caseTrimLengthIn": None, "primer": None,
                "coalIn": float(mcol.group(1)),
                "barrelLengthIn": barrel, "twist": None,
                "powder": powder_name, "powderMfr": "Shooters World", "powderCode": code,
                "cartridgeAsPrinted": cal_t,
                "sources": [{"url": doc["url"], "type": "manufacturer", "page": pno, "retrieved": RETRIEVED}],
                "evidence": evidence,
            }
            loads = []
            if msc and msv:
                loads.append(("start", msc.group(1), msc.group(2), msv.group(1), None))
            elif num[1] or num[2]:
                notes.append("Start-load cells read '%s' / '%s' (no start load recorded)." % (num[1], num[2]))
            loads.append(("max", mmc.group(1), mmc.group(2), mmv.group(1), None if num[5] == "N/A" else mmp.group(1)))
            for lt, g, c, v, p in loads:
                rec = dict(base)
                rec.update({
                    "chargeGr": float(g), "velocityFps": int(sw_num(v)),
                    "pressure": int(sw_num(p)) if p else None, "pressureUnit": "psi" if p else None,
                    "pressureMethod": None, "loadType": lt, "compressed": bool(c),
                    "notes": " ".join(notes + (["Charge printed with 'C' (compressed)."] if c else [])),
                    "_raw": [("chargeGr", g), ("velocityFps", v), ("coalIn", mcol.group(1)),
                             ("bulletWeightGr", mw.group(1))] + ([("pressure", p)] if p else []),
                })
                records.append(rec)
    # identical rows printed more than once on the same page: keep one record, note the repetition
    seen, dedup = {}, []
    for r in records:
        k = (r["cartridge"], r["caseBrand"], r["bulletWeightGr"], r["bulletMfr"], r["bulletModel"], r["coalIn"],
             r["powder"], r["loadType"], r["chargeGr"], r["velocityFps"], r["pressure"], r["sources"][0]["page"])
        if k in seen:
            seen[k][1] += 1
            continue
        seen[k] = [r, 1]
        dedup.append(r)
    for r, n in seen.values():
        if n > 1:
            r["notes"] += " This identical row is printed %d times on this page; recorded once." % n
    records = dedup
    # same component line printed twice with different velocities (e.g. a second block on the page)
    groups = {}
    for r in records:
        k = (r["cartridge"], r["powder"], r["bulletWeightGr"], r["bulletModel"], r["loadType"], r["chargeGr"],
             r["pressure"])
        groups.setdefault(k, []).append(r)
    for k, g in groups.items():
        if len({r["velocityFps"] for r in g}) > 1:
            for r in g:
                r["conflicts"] = [{"field": "velocityFps", "values": [
                    {"value": x["velocityFps"], "source": "%s#page=%d" % (doc["url"], x["sources"][0]["page"]),
                     "caseBrand": x["caseBrand"], "coalIn": x["coalIn"]} for x in g]}]
                r["notes"] += (" Same bullet/powder/charge%s appears %d times in the manual with different "
                               "velocities (%s); barrel/test setup of each block not stated."
                               % ("/pressure" if r["pressure"] else "", len(g),
                                  ", ".join(str(x["velocityFps"]) + " fps p." + str(x["sources"][0]["page"])
                                            for x in g)))
    log["shootersworld_" + doc["key"]] = {"unparsedRows": unparsed,
                                          "powderTitles": {k: v[1] for k, v in code_names.items()}}
    return records


# --------------------------------------------------------------------------
# Vihtavuori Reloading Guide 2026 (ENG).  Two printed pages per PDF page: each
# half is converted separately (pdftotext -layout with a crop box).  Loads are
# CIP pressure-tested but the guide publishes no pressure values; each section
# states test barrel length/twist, primer type and case brand/trim length.
# --------------------------------------------------------------------------
VV_DOC = {
    "key": "VV2026",
    "url": "https://vihtavuori.com/wp-content/uploads/2026/04/Vihtavuori_Reloading_Guide_2026_ENG_web.pdf",
    "local": "vv/VV_Reloading_Guide_2026_ENG_web.pdf",
    "title": "Vihtavuori Reloading Guide 2026 (English, web edition)",
    "date": "2026 (PDF created 2026-03-24)",
    "landing": "https://vihtavuori.com/resources/news-media/downloads/",
}
VV_CANON = {
    ".223 Remington": "223 Remington", ".308 Winchester": "308 Winchester", "6,5 Creedmoor": "6.5 Creedmoor",
    ".30-06 Springfield": "30-06 Springfield", ".300 Winchester Magnum": "300 Winchester Magnum",
    ".243 Winchester": "243 Winchester", "6 mm Creedmoor": "6mm Creedmoor", ".270 Winchester": "270 Winchester",
    "7 mm Remington Magnum": "7mm Remington Magnum", "9 mm Luger / 9x19 mm": "9mm Luger",
    ".45 Auto / .45 ACP": "45 ACP", ".357 Magnum": "357 Magnum", ".44 Remington Magnum": "44 Remington Magnum",
}
VV_FRAC = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅛": 0.125, "⅜": 0.375, "⅝": 0.625,
           "⅞": 0.875, "⅓": 1 / 3.0, "⅔": 2 / 3.0}
VV_POWDER = r"(?:N\d{3}|\d{1,2}N\d{2}|N32C)"
VV_CH = r"\d+,\d{2}[ACF]?"
VV_CHGR = r"\d+\.\d[ACF]?"
VV_LOAD_RE = re.compile(
    r"(?P<powder>" + VV_POWDER + r")\s+(?P<sg>" + VV_CH + r")\s+(?P<sgr>" + VV_CHGR + r")\s+(?P<sv>\d{3,4})\s+"
    r"(?P<svf>\d{3,4})\s+(?P<mg>" + VV_CH + r")\s*(?P<mgr>" + VV_CHGR + r")\s+(?P<mv>\d{3,4})\s+(?P<mvf>\d{3,4})\s*$")
VV_BULLET_RE = re.compile(
    r"^\s*(?P<bg>\d+,\d{1,2})\s+(?P<bgr>\d+(?:\.\d)?)\s+(?P<text>\S.*?)\s+(?P<colmm>\d{2,3},\d)\s+(?P<colin>\d\.\d{3})\s+"
    r"(?=" + VV_POWDER + r"\s)")
VV_BARREL_RE = re.compile(r"Test barrel:\s+(?P<mm>\d+) mm \((?P<inch>[\d¼-¾⅓-⅞]+)”\), "
                          r"1 in (?P<tw>[\d¼-¾⅓-⅞.]+)” twist")
VV_CASES_RE = re.compile(r"Cases:\s+(?P<case>.+?), trim-to length (?P<mm>[\d,]+) mm \((?P<inch>\d?\.\d+)”\)")


def vv_frac(s):
    v = 0.0
    num = re.match(r"\d+", s)
    if num:
        v = float(num.group(0))
    for ch in s:
        if ch in VV_FRAC:
            v += VV_FRAC[ch]
    return v


def vihtavuori_parse(doc, log, keep_all=False):
    pdf = fetch(doc["url"], doc["local"], delay=2)
    info = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True).stdout
    npages = int(re.search(r"Pages:\s+(\d+)", info).group(1))
    halves_dir = os.path.join(os.path.dirname(pdf), "halves")
    os.makedirs(halves_dir, exist_ok=True)
    texts = []
    for p in range(1, npages + 1):
        sz = subprocess.run(["pdfinfo", "-f", str(p), "-l", str(p), pdf], capture_output=True, text=True).stdout
        m = re.search(r"Page\s+%d size:\s+([\d.]+) x ([\d.]+)" % p, sz)
        w, h = float(m.group(1)), float(m.group(2))
        sides = [("L", 0, w / 2), ("R", w / 2, w / 2)] if w > h else [("S", 0, w)]
        for side, x, ww in sides:
            path = os.path.join(halves_dir, "p%02d%s.txt" % (p, side))
            if not os.path.exists(path):
                subprocess.run(["pdftotext", "-layout", "-f", str(p), "-l", str(p), "-x", str(int(x)), "-y", "0",
                                "-W", str(int(ww) + 1), "-H", str(int(h) + 1), pdf, path],
                               check=True, stderr=subprocess.DEVNULL)
            texts.append((p, side, open(path, encoding="utf-8").read()))
    records, unparsed = [], []
    st = {"cart": None, "barrel": None, "barrel_line": None, "primer": None, "primer_line": None, "case": None,
          "case_line": None, "bullet": None, "pending_barrel": None, "pending_barrel_line": None}
    hdr_pos = None
    for p, side, txt in texts:
        lines = txt.split("\n")
        foot = re.search(r"^\s*(\d{1,3})\s+LIGHT GREY|LOADS LESS THAN MINIMUM CHARGES SHOWN ARE NOT RECOMMENDED\s+(\d{1,3})\s*$",
                         txt, re.M)
        printed = (foot.group(1) or foot.group(2)) if foot else None
        name_cont = None
        if re.search(r"RELOADING DATA FOR\s+SHOTGUN", txt):
            st.update({"cart": None, "bullet": None, "barrel": None})
            continue  # shotshell data
        if "COWBOY ACTION SHOOTING" in txt:
            st.update({"cart": None, "bullet": None, "barrel": None, "cowboy": True})
        for li, line in enumerate(lines):
            s = line.strip()
            if not s:
                continue
            mb = VV_BARREL_RE.search(line)
            if mb:
                st["pending_barrel"] = mb
                st["pending_barrel_line"] = ws(line)
                continue
            if "Primers:" in line:
                name = line[:line.index("Primers:")].strip()
                st["primer"] = line[line.index("Primers:") + 8:].strip()
                st["primer_line"] = ws(line)
                if name.endswith("/"):
                    name_cont = name
                    name = None
                st.update({"cart": name, "bullet": None, "case": None, "case_line": None,
                           "barrel": st["pending_barrel"], "barrel_line": st["pending_barrel_line"]})
                st["pending_barrel"] = None
                if st["barrel"] is None:
                    unparsed.append({"page": p, "text": ws(line), "why": "section without a preceding Test barrel "
                                     "line; its rows are skipped"})
                continue
            mc = VV_CASES_RE.search(line)
            if mc:
                if name_cont is not None:
                    pre = line[:line.index("Cases:")].strip()
                    st["cart"] = ws(name_cont + " " + pre)
                    st["primer_line"] = st["primer_line"] + " " + ws(pre)
                    name_cont = None
                st["case"] = mc
                st["case_line"] = ws(line)
                continue
            mcont = re.match(r"^\s*(\S.*?)\s+cont\.\s*$", line)
            if mcont:
                if ws(mcont.group(1)) != st["cart"]:
                    unparsed.append({"page": p, "text": ws(line), "why": "continuation page does not match the "
                                     "current section '%s'; state reset" % st["cart"]})
                    st.update({"cart": None, "bullet": None})
                continue
            if re.match(r"^\s*Weight\s+Mfg\s+Type/Name", line):
                hdr_pos = (line.index("Mfg") + 1.5, line.index("Type/Name") + 4.5)
                continue
            ml = VV_LOAD_RE.search(line)
            if not ml:
                if re.search(r"\s" + VV_POWDER + r"\s+\d", line):
                    unparsed.append({"page": p, "text": ws(line), "why": "powder row does not match the strict "
                                     "column pattern; skipped"})
                continue
            canon = VV_CANON.get(st["cart"]) if st["cart"] else None
            prefix = line[:ml.start()]
            mbl = VV_BULLET_RE.match(line)
            if mbl:
                parts = rs_phrases(mbl.group("text"), mbl.start("text"))
                mfg, typ = [], []
                for ph_ in parts:
                    if hdr_pos and abs(ph_["c"] - hdr_pos[0]) > abs(ph_["c"] - hdr_pos[1]):
                        typ.append(ph_["t"])
                    else:
                        mfg.append(ph_["t"])
                st["bullet"] = {"bg": mbl.group("bg"), "bgr": mbl.group("bgr"), "mfg": mfg, "typ": typ,
                                "colmm": mbl.group("colmm"), "colin": mbl.group("colin"), "line": ws(line),
                                "frag_lines": [], "marker": bool(re.search(r"\d\)", line[:ml.start()]))}
            elif prefix.strip():
                # wrapped bullet maker / type text on a continuation row.  Numbers in the prefix mean a bullet
                # line that did not match the strict pattern: never treat it as wrapped text.
                if re.search(r"\d+,\d|\d\.\d{3}|^\s*\d", prefix):
                    unparsed.append({"page": p, "text": ws(line), "why": "bullet line does not match the strict "
                                     "pattern; this bullet's rows are skipped"})
                    st["bullet"] = None
                    continue
                if st["bullet"] is None:
                    unparsed.append({"page": p, "text": ws(line), "why": "text before powder but no bullet"})
                    continue
                for ph_ in rs_phrases(prefix):
                    if hdr_pos and abs(ph_["c"] - hdr_pos[0]) > abs(ph_["c"] - hdr_pos[1]):
                        st["bullet"]["typ"].append(ph_["t"])
                    else:
                        st["bullet"]["mfg"].append(ph_["t"])
                    if re.search(r"\d\)", ph_["t"]):
                        st["bullet"]["marker"] = True
                st["bullet"]["frag_lines"].append(ws(line))
            b = st["bullet"]
            if canon is None and not keep_all:
                continue
            if b is None or st["barrel"] is None or st["cart"] is None:
                unparsed.append({"page": p, "text": ws(line), "why": "row without bullet/section context; skipped"})
                continue
            if b["marker"] or re.search(r"\d\)", line[ml.start():]):
                unparsed.append({"page": p, "text": ws(line), "why": "footnote marker on this bullet/row (footnotes "
                                 "may change barrel, twist or case); skipped"})
                continue
            # internal unit consistency (g vs gr, m/s vs fps, mm vs in)
            problems = []
            for gk, grk in (("sg", "sgr"), ("mg", "mgr")):
                g = float(ml.group(gk).rstrip("ACF").replace(",", "."))
                gr = float(ml.group(grk).rstrip("ACF"))
                if abs(g * 15.4324 - gr) > 0.2:
                    problems.append("%s g vs %s gr" % (ml.group(gk), ml.group(grk)))
            for vk, fk in (("sv", "svf"), ("mv", "mvf")):
                if abs(int(ml.group(vk)) / 0.3048 - int(ml.group(fk))) > 4:
                    problems.append("%s m/s vs %s fps" % (ml.group(vk), ml.group(fk)))
            if abs(float(b["colmm"].replace(",", ".")) - float(b["colin"]) * 25.4) > 0.15:
                problems.append("COL %s mm vs %s in" % (b["colmm"], b["colin"]))
            # bullet mass in g is printed to 0.1 g (about 1.5 gr), so allow up to 1.6 gr
            if abs(float(b["bg"].replace(",", ".")) * 15.4324 - float(b["bgr"])) > 1.6:
                problems.append("bullet %s g vs %s gr" % (b["bg"], b["bgr"]))
            if problems:
                unparsed.append({"page": p, "text": ws(line), "why": "unit cross-check failed (%s); skipped"
                                 % "; ".join(problems)})
                continue
            bar = st["barrel"]
            case = st["case"]
            ev_lines = [x for x in [st["barrel_line"], st["primer_line"], st["case_line"], b["line"]]
                        + b["frag_lines"] + [ws(line)] if x]
            evidence = " | ".join(dict.fromkeys(ev_lines))
            mfg_t = ws(" ".join(b["mfg"])) or None
            typ_t = ws(" ".join(b["typ"])) or None
            notes = ["Vihtavuori guide: 'All the loads in this guide are pressure tested according to the C.I.P. "
                     "method'; no pressure values are published. velocityFps / chargeGr / coalIn are the printed "
                     "[fps] / [grs] / [in.] columns."]
            notes.append("Test barrel printed as '%s mm (%s”)'; barrelLengthIn uses the printed inch value."
                         % (bar.group("mm"), bar.group("inch")))
            notes.append("Primer printed only as type: '%s'." % st["primer"])
            if printed:
                notes.append("Printed page %s (%s half of PDF page %d)." % (printed, "left" if side == "L" else "right",
                                                                            p))
            if hdr_pos is None or (mfg_t and typ_t is None):
                notes.append("Bullet maker/type split by column position; check bulletMfr/bulletModel.")
            if st.get("cowboy"):
                notes.append("Cowboy Action Shooting section: 'The maximum load is determined by the velocity limit "
                             "about 300 m/s, or by the maximum pressure limit according to the CIP October 1, 1992 "
                             "rules. The bold text in the tables indicate the maximum load according to CIP pressure "
                             "level.' (bold type is not recoverable from the text layer).")
            for lt, gk, grk, vk, fk in (("start", "sg", "sgr", "sv", "svf"), ("max", "mg", "mgr", "mv", "mvf")):
                flag = ml.group(grk)[-1] if ml.group(grk)[-1] in "ACF" else ""
                n2 = list(notes)
                if flag == "F":
                    n2.append("Charge flagged 'F' (legend: F = Case full).")
                if flag == "A":
                    n2.append("Charge flagged 'A' (legend: A = Accuracy load).")
                if flag == "C":
                    n2.append("Charge flagged 'C' (legend: C = Compressed load).")
                rec = {
                    "cartridge": canon or st["cart"],
                    "bulletMfr": mfg_t, "bulletModel": typ_t,
                    "bulletWeightGr": float(b["bgr"]), "bulletDiameterIn": None, "bulletLengthIn": None,
                    "caseBrand": case.group("case") if case else None,
                    "caseTrimLengthIn": float(case.group("inch")) if case else None,
                    "primer": st["primer"],
                    "coalIn": float(b["colin"]),
                    "barrelLengthIn": vv_frac(bar.group("inch")),
                    "twist": "1:%g\"" % vv_frac(bar.group("tw")),
                    "powder": ml.group("powder"), "powderMfr": "Vihtavuori",
                    "chargeGr": float(ml.group(grk).rstrip("ACF")),
                    "velocityFps": int(ml.group(fk)),
                    "pressure": None, "pressureUnit": None,
                    "pressureMethod": "C.I.P. (stated for the guide as a whole; values not published)",
                    "loadType": lt, "compressed": flag == "C",
                    "dataSection": "Cowboy Action Shooting loads" if st.get("cowboy") else "Reloading data",
                    "chargeG": float(ml.group(gk).rstrip("ACF").replace(",", ".")),
                    "velocityMps": int(ml.group(vk)),
                    "coalMm": float(b["colmm"].replace(",", ".")),
                    "barrelLengthMm": int(bar.group("mm")),
                    "cartridgeAsPrinted": st["cart"],
                    "sources": [{"url": doc["url"], "type": "manufacturer", "page": p, "retrieved": RETRIEVED}],
                    "evidence": evidence,
                    "notes": " ".join(n2),
                    "_raw": [("chargeGr", ml.group(grk).rstrip("ACF")), ("velocityFps", ml.group(fk)),
                             ("coalIn", b["colin"]), ("bulletWeightGr", b["bgr"]),
                             ("barrelLengthMm", bar.group("mm"))],
                }
                records.append(rec)
    log["vihtavuori_" + doc["key"]] = {"unparsedRows": unparsed}
    return records


# --------------------------------------------------------------------------
def generic_raw_check(records):
    """Each parsed numeric value must appear verbatim in the evidence and convert back to the stored value."""
    bad = 0
    for r in records:
        for f, raw in r.get("_raw", []):
            if not re.search(r"(?<![\d.,])" + re.escape(raw) + r"(?![\d])", r["evidence"]):
                bad += 1
                print("RAW CHECK FAIL (not in evidence)", f, raw, "|", r["evidence"])
                continue
            v = float(raw.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", raw)
                      else raw.replace(",", "."))
            if r.get(f) is None or abs(float(r[f]) - v) > 1e-9:
                bad += 1
                print("RAW CHECK FAIL (value)", f, raw, r.get(f))
    return bad


def self_check(records):
    print("records:", len(records))
    bad = 0
    for r in records:
        if "_raw" in r:
            continue  # sources other than the Hodgdon manual are checked by generic_raw_check()
        ev = r["evidence"]
        want = [("%g" % r["chargeGr"]) if r["chargeGr"] != int(r["chargeGr"]) else ("%.1f" % r["chargeGr"]),
                str(r["velocityFps"]), "{:,}".format(r["pressure"])]
        last = ev.split(" | ")[-1]
        for wv in want:
            if wv not in last and wv.replace(",", "") not in last:
                bad += 1
                print("CHECK FAIL", wv, "not in", last)
                break
        for f in ("coalIn", "bulletDiameterIn", "barrelLengthIn", "caseTrimLengthIn", "bulletWeightGr"):
            v = r[f]
            if v is None:
                continue
            forms = {("%.3f" % v), ("%.4f" % v), ("%g" % v), ("%.1f" % v)}
            forms |= {x.lstrip("0") for x in forms}
            if not any(re.search(r"(?<![\d.])" + re.escape(x) + r"(?!\d)", ev) for x in forms):
                bad += 1
                print("CHECK FAIL", f, v, ev)
    bad += generic_raw_check(records)
    print("evidence check failures:", bad)
    nl = [r for r in records if not r.pop("_layout_ok", True)]
    print("rows not found verbatim in the page's -layout text:", len(nl))
    for r in nl[:10]:
        print("   LAYOUT?", r["sources"][0]["page"], r["evidence"].split(" | ")[-1])
    # start/max consistency per printed row
    pairs = {}
    for r in records:
        pairs.setdefault((r["sources"][0]["url"], r["sources"][0]["page"], r["evidence"]), {})[r["loadType"]] = r
    anomalies = 0
    for k, d in pairs.items():
        if "start" in d and "max" in d:
            s_, m_ = d["start"], d["max"]
            if not (s_["chargeGr"] <= m_["chargeGr"] and s_["velocityFps"] <= m_["velocityFps"]
                    and (s_["pressureUnit"] != m_["pressureUnit"] or s_["pressure"] is None
                         or m_["pressure"] is None or s_["pressure"] <= m_["pressure"])):
                anomalies += 1
                print("   ORDER ANOMALY (kept, as printed):", k[2].split(" | ")[-1], "page", k[1])
    print("start>max anomalies:", anomalies)
    for r in records:
        if r["pressure"] is None:
            continue
        if (r["pressureUnit"] == "psi" and not 5000 <= r["pressure"] <= 70000) or \
                (r["pressureUnit"] == "CUP" and not 5000 <= r["pressure"] <= 56000) or \
                (r["pressureUnit"] == "bar" and not 300 <= r["pressure"] <= 5000):
            print("   PRESSURE RANGE?", r["cartridge"], r["pressure"], r["pressureUnit"], r["evidence"].split(" | ")[-1])
    # cross-source plausibility: COAL far from the median of all records of the same cartridge
    by_c = {}
    for r in records:
        if r["coalIn"]:
            by_c.setdefault(r["cartridge"], []).append(r["coalIn"])
    outl = 0
    for r in records:
        v = sorted(by_c.get(r["cartridge"], []))
        if r["coalIn"] and v:
            med = v[len(v) // 2]
            if abs(r["coalIn"] - med) / med > 0.10:
                outl += 1
                print("   COAL OUTLIER?", r["cartridge"], r["coalIn"], "median", med, r["powder"],
                      r["sources"][0]["url"][-30:], r["sources"][0]["page"], r["evidence"][-90:])
    print("COAL outliers (>10% from cartridge median):", outl)
    random.seed(7)
    for r in random.sample(records, min(5, len(records))):
        print(json.dumps({k: r[k] for k in ("cartridge", "bulletMfr", "bulletModel", "bulletWeightGr", "caseBrand",
                                            "primer", "coalIn", "barrelLengthIn", "powder", "powderMfr", "chargeGr",
                                            "velocityFps", "pressure", "pressureUnit", "loadType", "compressed")}))
        print("   EVIDENCE:", r["evidence"], "| page", r["sources"][0]["page"])
    return bad


PRIORITY = ["223 Remington", "308 Winchester", "6.5 Creedmoor", "30-06 Springfield", "300 Winchester Magnum",
            "243 Winchester", "6mm Creedmoor", "270 Winchester", "7mm Remington Magnum", "9mm Luger", "45 ACP",
            "357 Magnum", "44 Remington Magnum"]


NOTES = (
    "Published load data for calibrating/validating ORKA. One record per printed load (start and max are separate "
    "records sharing the same evidence). Only the 13 priority cartridges are kept (run with --all for every "
    "cartridge in the documents). Pressure: Hodgdon 2025 Annual Manual gives start+max pressure per load in psi "
    "(transducer) or CUP (copper crusher) - CUP is never converted; Reload Swiss 2025 gives start+max pressure in "
    "bar (method not stated; velocity is V5 at 5 m); Shooters World gives only the max-load pressure in psi "
    "(method and test barrel not stated); Vihtavuori 2026 guide gives no pressure values (CIP-tested, max loads at "
    "CIP/SAAMI limit) but states test barrel, twist, case and primer type per cartridge. Values are copied from "
    "the printed columns (gr / fps / in / psi / CUP / bar). Derived values are flagged in notes: Reload Swiss "
    "velocityFps = printed m/s / 0.3048 and coalIn / barrelLengthIn = printed mm / 25.4 (raw values kept in "
    "velocityMps / coalMm / barrelLengthMm). Rows were skipped (never guessed) when a value had a typo (e.g. "
    "'46.500 PSI'), when a footnote marker could change barrel/case/twist, when unit pairs printed in the same row "
    "disagreed (g vs gr, m/s vs fps, mm vs in), when wrapped cells could not be attributed unambiguously, or when "
    "a continuation page's header did not match the running section; every skipped row is listed in "
    "meta.parseLog.*.unparsedRows. Rows whose COAL is shorter than the case trim length printed for that "
    "cartridge are physically impossible as printed and are moved to meta.excludedRecords. Identical rows printed "
    "twice on one Shooters World page are recorded once; the same component line printed with different "
    "velocities is kept and cross-referenced in 'conflicts'.")
DOCS_NOT_USED = [
    {"url": "https://www.reload-swiss.com/Reload%20Swiss/Service/Brosch%C3%BCren%20und%20Produktdatenbl%C3%A4tter/"
            "Reload-Swiss-Ladedaten-Guide-2025-DE-EN-small.pdf",
     "part": "Customer reloading data (PDF pages 59-128)",
     "why": "customer-submitted loads, no pressure, non-standard barrels; only Reload Swiss's own data is used"},
    {"url": "https://shootersworldpowder.com/wp-content/uploads/2023/06/"
            "ShootersWorldManualInterior_CHRIS_WITH-COVER__RUSS-REVISED.pdf",
     "part": "PDF page 46 (SW-BMG .50 BMG) and page 49 (Clean Shot hard-cast competition table)",
     "why": ".50 BMG is not a priority cartridge; page 49 uses a different column order (4 priority rows) and was "
            "not parsed"},
    {"url": "https://shootersworldpowder.com/wp-content/uploads/2025/05/Vectan-Reloading-catalogue_vUS_compressed.pdf",
     "why": "shotshell data only"},
    {"url": "https://hodgdonpowderco.com/reloading-manuals-library/",
     "why": "older Hodgdon Annual Manuals (AM17-AM24) not parsed: same publisher as AM25, would mostly duplicate it"},
    {"url": "https://hodgdonpowderco.com/wp-content/uploads/2023/04/Accurate_DP68-1.pdf",
     "why": "Accurate 'Data Powder' surplus lots (DP68/73/74/79/85/86/2200/2230-C/2230-S) are discontinued one-off "
            "surplus powders; Accurate No. 11FS and TCM data PDFs duplicate powders already in the 2025 Annual "
            "Manual. Downloaded, not used."},
    {"url": "https://www.alliantpowder.com/reloaders/RecipeList.aspx?gtypeid=2",
     "why": "Alliant web recipes: one page per bullet (~270 pages for the priority cartridges), max load only, the "
            "pressure column is hidden and shows 0, and recipe pages redirect to a disclaimer page; not crawled"},
    {"url": "https://vihtavuori.com/reloading-data/reloading-data-tool/",
     "why": "data served only through a JavaScript app/private API; the printed 2026 guide PDF was used instead"},
    {"url": "https://www.reload-swiss.com/en/loading-data/rs-loading-data",
     "why": "data served only through a JavaScript app/private API; the 2025 guide PDF was used instead"},
    {"url": "https://www.nosler.com/load-data",
     "why": "load data served through a JavaScript SDK/private API (omniguide); not used"},
    {"url": "https://www.norma-ammunition.com/sitemap.xml",
     "why": "no reloading data published on the site"},
    {"url": "https://www.adi-powders.com.au/",
     "why": "host unreachable from this environment (proxy 502)"},
    {"url": "https://westernpowders.com/",
     "why": "connection reset (site appears retired; Accurate/Ramshot data now in the Hodgdon Annual Manual)"},
]


def main():
    log = {}
    records = []
    docs_meta = []
    keep_all = "--all" in sys.argv
    for d in HODGDON_DOCS:
        recs = hodgdon_parse(d, log)
        if not keep_all:
            recs = [r for r in recs if r["cartridge"] in PRIORITY]
        records += recs
        docs_meta.append({"url": d["url"], "localPath": os.path.join(SRC_DIR, d["local"]), "title": d["title"],
                          "date": d["date"], "landingPage": d["landing"], "records": len(recs)})
    for d, fn in ((RS_DOC, reload_swiss_parse), (SW_DOC, shooters_world_parse), (VV_DOC, vihtavuori_parse)):
        recs = fn(d, log, keep_all)
        records += recs
        docs_meta.append({"url": d["url"], "localPath": os.path.join(SRC_DIR, d["local"]), "title": d["title"],
                          "date": d["date"], "landingPage": d["landing"], "records": len(recs)})
    # physically impossible rows: COAL shorter than the shortest case trim length any source prints for
    # that cartridge (e.g. a mislabelled row).  Removed from 'loads' and listed in meta.excludedRecords.
    trims = {}
    for r in records:
        if r.get("caseTrimLengthIn"):
            trims.setdefault(r["cartridge"], []).append(r["caseTrimLengthIn"])
    excluded, kept = [], []
    for r in records:
        t = min(trims.get(r["cartridge"], [0]) or [0])
        if r["coalIn"] is not None and t and r["coalIn"] < t:
            excluded.append({"reason": "coalIn %.3f is shorter than the shortest case trim length printed for %s "
                                       "(%.3f in) in these sources: row is physically impossible as printed"
                                       % (r["coalIn"], r["cartridge"], t),
                             "record": {k: v for k, v in r.items() if not k.startswith("_")}})
        else:
            kept.append(r)
    records = kept
    print("excluded (COAL < case trim length):", len(excluded))
    for e in excluded:
        print("   EXCLUDED", e["record"]["cartridge"], e["record"]["coalIn"], e["record"]["evidence"][-100:])
    unknown_powders = sorted({r["powder"] for r in records if r["powderMfr"] is None})
    for r in records:
        r.setdefault("conflicts", [])
    for dm in docs_meta:
        dm["records"] = sum(1 for r in records if r["sources"][0]["url"] == dm["url"])
    coverage = {}
    for r in records:
        c = coverage.setdefault(r["cartridge"], {"records": 0, "withPressure": 0, "powders": set(),
                                                 "powdersWithPressure": set()})
        c["records"] += 1
        c["powders"].add("%s %s" % (r["powderMfr"], r["powder"]))
        if r["pressure"] is not None:
            c["withPressure"] += 1
            c["powdersWithPressure"].add("%s %s" % (r["powderMfr"], r["powder"]))
    coverage = {k: {"records": v["records"], "recordsWithPressure": v["withPressure"],
                    "distinctPowders": len(v["powders"]), "distinctPowdersWithPressure": len(v["powdersWithPressure"])}
                for k, v in sorted(coverage.items())}
    out = {
        "meta": {
            "documents": docs_meta,
            "generated": RETRIEVED,
            "script": "scripts/extract/validation-loads.py",
            "notes": NOTES,
            "documentsNotUsed": DOCS_NOT_USED,
            "coverage": coverage,
            "parseLog": log,
            "unknownPowderBrands": unknown_powders,
            "excludedRecords": excluded,
        },
        "loads": records,
    }
    bad = self_check(records)
    for r in records:
        r.pop("_layout_ok", None)
        r.pop("_raw", None)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("unknown powder brands:", unknown_powders)
    for k, v in log.items():
        print(k, "unparsed rows:", len(v["unparsedRows"]))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
