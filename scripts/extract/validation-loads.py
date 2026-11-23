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
ROW6_RE = re.compile(
    r"^(?P<powder>.+?)\s+"
    r"(?P<sg>" + NUM_CH + r")(?P<sc>C?)(?P<sa>\*?)\s+(?P<sv>\d{3,4})\s+(?P<sp>\d{1,3}(?:,\d{3})+|\d{3,6})\s+(?P<spu>PSI|CUP)\s+"
    r"(?P<mg>" + NUM_CH + r")(?P<mc>C?)(?P<ma>\*?)\s+(?P<mv>\d{3,4})\s+(?P<mp>\d{1,3}(?:,\d{3})+|\d{3,6})\s+(?P<mpu>PSI|CUP)$"
)
ROW3_RE = re.compile(
    r"^(?P<powder>.+?)\s+"
    r"(?P<g>" + NUM_CH + r")(?P<c>C?)(?P<a>\*?)\s+(?P<v>\d{3,4})\s+(?P<p>\d{1,3}(?:,\d{3})+|\d{3,6})\s+(?P<pu>PSI|CUP)$"
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
    for p in pages_text[:8]:
        for m in re.finditer(r"([0-9A-Za-z][^.\n]*?[^.\s])\s*\.{3,}\s*(\d{2,3})", p):
            nm = ws(m.group(1))
            # TOC lines are 3 columns: keep only the trailing part after a page number of a previous entry
            nm = re.sub(r"^\d{1,3}\s+(?=[0-9])", "", nm) if re.match(r"^\d{1,3}\s+\d", nm) and False else nm
            names[norm_key(nm.rstrip("*"))] = nm.rstrip("*").strip()
    return names


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
    m = re.search(r"Pressures were gauged by one of two methods.*?pounds per square inch \(PSI\)\.",
                  " ".join(re.split(r"\s{3,}", pages_text[intro_page])), re.S)
    method_evidence = ws(m.group(0)) if m else None

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
                    key = norm_key((name_raw or "").rstrip("*"))
                    canon = toc.get(key)
                    if canon is None and name_raw:
                        # try without trailing qualifier text
                        canon = None
                    state.update({"cartridge_raw": name_raw, "cartridge": canon or name_raw,
                                  "barrel": float(mb.group("bbl")), "twist": mb.group("tw"),
                                  "trim": float(mb.group("trim")), "barrel_line": t, "cart_line": name_raw,
                                  "bullet": None, "case": None, "cart_canon_ok": canon is not None})
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
                        if not state.get("cart_canon_ok"):
                            notes.append("Cartridge name not matched to table of contents; kept as printed.")
                        if printed:
                            notes.append("Printed page %d." % printed)
                        unit = "psi" if pu == "PSI" else "CUP"
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
                            "pressureMethod": ("piezo/force transducer (PSI), per manual introduction" if unit == "psi"
                                               else "copper crusher (CUP), per manual introduction"),
                            "loadType": lt,
                            "compressed": bool(c),
                            "dataSection": section,
                            "sources": [{"url": doc["url"], "type": "manufacturer", "page": pno,
                                         "retrieved": RETRIEVED}],
                            "evidence": ws(" | ".join(x for x in [state["cart_line"], state["barrel_line"], b["line"],
                                                                   k["line"], t] if x)),
                            "notes": " ".join(notes) or None,
                        }
                        records.append(rec)
                    continue
                if m6 or m3:
                    unparsed.append({"page": pno, "text": t, "why": "data row without bullet/case/cartridge context"})
                    continue
                # anything else: candidate cartridge title (confirmed only if a Barrel: row follows)
                if pending_name and pending_name != t:
                    unparsed.append({"page": pno, "text": pending_name, "why": "unrecognised row"})
                pending_name = t
        if pending_name and not re.match(r"^[0-9]", pending_name) and False:
            pending_name = None
    log["hodgdon_" + doc["key"]] = {
        "legendBrands": brands, "legendBulletTypes": bullet_abbr, "pressureMethodEvidence": method_evidence,
        "unparsedRows": unparsed,
    }
    return records


# --------------------------------------------------------------------------
def self_check(records):
    print("records:", len(records))
    bad = 0
    for r in records:
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
    print("evidence check failures:", bad)
    random.seed(7)
    for r in random.sample(records, min(5, len(records))):
        print(json.dumps({k: r[k] for k in ("cartridge", "bulletMfr", "bulletModel", "bulletWeightGr", "caseBrand",
                                            "primer", "coalIn", "barrelLengthIn", "powder", "powderMfr", "chargeGr",
                                            "velocityFps", "pressure", "pressureUnit", "loadType", "compressed")}))
        print("   EVIDENCE:", r["evidence"], "| page", r["sources"][0]["page"])
    return bad


def main():
    log = {}
    records = []
    docs_meta = []
    for d in HODGDON_DOCS:
        recs = hodgdon_parse(d, log)
        records += recs
        docs_meta.append({"url": d["url"], "localPath": os.path.join(SRC_DIR, d["local"]), "title": d["title"],
                          "date": d["date"], "landingPage": d["landing"], "records": len(recs)})
    unknown_powders = sorted({r["powder"] for r in records if r["powderMfr"] is None})
    out = {
        "meta": {
            "documents": docs_meta,
            "generated": RETRIEVED,
            "script": "scripts/extract/validation-loads.py",
            "notes": "",
            "parseLog": log,
            "unknownPowderBrands": unknown_powders,
        },
        "loads": records,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    bad = self_check(records)
    print("unknown powder brands:", unknown_powders)
    for k, v in log.items():
        print(k, "unparsed rows:", len(v["unparsedRows"]))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
