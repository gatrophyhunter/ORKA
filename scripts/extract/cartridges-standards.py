#!/usr/bin/env python3
"""Extract cartridge specifications and maximum pressures from the standards bodies.

Sources (all public, fetched with plain curl, default user agent):
  * ANSI/SAAMI Z299.4 (centerfire rifle) and Z299.3 (centerfire pistol & revolver) PDFs,
    linked from https://saami.org/technical-information/ansi-saami-standards/
    (robots.txt: Crawl-delay 10 -> we sleep >= 10 s between saami.org requests).
  * C.I.P. public TDCC listing https://bobp.cip-bobp.org/en/tdcc_public (Tabs I-IV) and the
    per-cartridge EN TDCC sheets (PDF) linked from it (robots.txt has no active rules;
    we sleep 1.5 s between requests).

Usage:
  python3 -I cartridges-standards.py --download   # fetch any missing source documents
  python3 -I cartridges-standards.py              # parse cached documents and write JSON

Everything is parsed with code from `pdftotext -layout` output / HTML; nothing is typed in.
"""
import json
import os
import random
import re
import subprocess
import sys
import time

SRC = '/tmp/claude-0/-home-user-ORKA/29ce603d-ccc3-55ef-b8fe-c585397ac7c1/scratchpad/sources/cartridges-standards'
OUT = '/home/user/ORKA/research/raw2/cartridges-standards.json'
RETRIEVED = '2026-11-23'

SAAMI_PAGE = 'https://saami.org/technical-information/ansi-saami-standards/'
SAAMI_DOCS = {
    'Z299.4': {
        'url': 'https://saami.org/wp-content/uploads/2026/10/SAAMI-Z299.4-CFR-2025-Centerfire-Rifle-Approved-2-10-2025-2026-10-21.pdf',
        'local': 'Z299.4.pdf',
        'title': 'ANSI/SAAMI Z299.4-2025 Voluntary Industry Performance Standards for Pressure and Velocity of Centerfire Rifle Sporting Ammunition',
        'date': '2025-02-10 (approved; file revision dated 2026-10-21)',
        'kind': 'rifle',
    },
    'Z299.3': {
        'url': 'https://saami.org/wp-content/uploads/2025/05/SAAMI-Z299.3-2022-Centerfire-Pistol-Revolver-Approved-12-13-2022.pdf',
        'local': 'Z299.3.pdf',
        'title': 'ANSI/SAAMI Z299.3-2022 Voluntary Industry Performance Standards for Pressure and Velocity of Centerfire Pistol and Revolver Ammunition',
        'date': '2022-12-13 (approved)',
        'kind': 'handgun',
    },
}
CIP_BASE = 'https://bobp.cip-bobp.org'
CIP_TABS = {1: 'Tab I - Rimless cartridges', 2: 'Tab II - Rimmed cartridges',
            3: 'Tab III - Belted cartridges', 4: 'Tab IV - Pistol and revolver cartridges'}


def cip_tab_url(t):
    return f'{CIP_BASE}/en/tdcc_public?page=1&cartridge_type_id={t}'


def cip_tab_local(t):
    return os.path.join(SRC, 'cip', f'tab{t}.html')


def cip_pdf_local(path):
    # path like /uploads/tdcc/tab-i/308-win-en.pdf -> cip/pdf/tab-i_308-win-en.pdf
    rel = path.split('/uploads/tdcc/', 1)[1]
    return os.path.join(SRC, 'cip', 'pdf', rel.replace('/', '_'))


_last_fetch = {}


def fetch(url, local, delay):
    """Download url to local with plain curl (default UA) unless cached. Returns True if file present."""
    if os.path.exists(local) and os.path.getsize(local) > 0:
        return True
    host = url.split('/')[2]
    wait = _last_fetch.get(host, 0) + delay - time.time()
    if wait > 0:
        time.sleep(wait)
    os.makedirs(os.path.dirname(local), exist_ok=True)
    tmp = local + '.part'
    r = subprocess.run(['curl', '-sS', '-L', '-m', '300', '-o', tmp, '-w', '%{http_code}', url],
                       capture_output=True, text=True)
    _last_fetch[host] = time.time()
    code = r.stdout.strip()
    if r.returncode != 0 or code != '200':
        print(f'FETCH FAILED {url}: rc={r.returncode} http={code} {r.stderr.strip()[:200]}', file=sys.stderr)
        if os.path.exists(tmp):
            os.remove(tmp)
        return False
    os.replace(tmp, local)
    return True


def cip_rows_raw(t):
    h = open(cip_tab_local(t), encoding='utf-8').read()
    return re.findall(r'<tr id="cartridge-(\d+)"[^>]*>(.*?)</tr>', h, re.S)


def download_all():
    os.makedirs(SRC, exist_ok=True)
    for d in SAAMI_DOCS.values():
        fetch(d['url'], os.path.join(SRC, d['local']), 10.0)
    for t in CIP_TABS:
        fetch(cip_tab_url(t), cip_tab_local(t), 1.5)
    n = 0
    for t in CIP_TABS:
        for rid, r in cip_rows_raw(t):
            tds = re.findall(r'<td[^>]*>(.*?)</td>', r, re.S)
            links = dict((lang, u) for u, lang in re.findall(r'href="(/uploads/tdcc/[^"]+)"[^>]*>(\w\w)</a>', tds[4]))
            u = links.get('EN')
            if not u:
                continue
            ok = fetch(CIP_BASE + u, cip_pdf_local(u), 1.5)
            n += 1
            if n % 25 == 0:
                print(f'... {n} CIP sheets checked', flush=True)
    print('download done', flush=True)




# ----------------------------------------------------------------------------------------------
# generic helpers
# ----------------------------------------------------------------------------------------------

def ws(s):
    """Collapse whitespace (evidence strings are stored whitespace-collapsed)."""
    return re.sub(r'\s+', ' ', s).strip()


def pdftotext_pages(pdf):
    txt = pdf[:-4] + '.txt'
    if not os.path.exists(txt) or os.path.getmtime(txt) < os.path.getmtime(pdf):
        subprocess.run(['pdftotext', '-layout', pdf, txt], check=True, capture_output=True)
    return open(txt, encoding='utf-8', errors='replace').read().split('\f')


def norm_key(name):
    """Normalisation used only for exact-match linking of the same cartridge across tables."""
    s = name.upper().replace('’', '').replace("'", '').replace('”', '').replace('"', '')
    s = s.replace('&', ' AND ')
    return re.sub(r'[^0-9A-Z+]', '', s)


def slug(name):
    s = name.lower().replace('’', '').replace("'", '').replace('”', 'in').replace('"', 'in')
    s = s.replace('+p', ' plus-p').replace('&', ' and ').replace(',', '.')
    s = re.sub(r'(\d)\.(\d)', r'\1-\2', s)
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s


def src(url, typ, page):
    return {'url': url, 'type': typ, 'page': page, 'retrieved': RETRIEVED}


# ----------------------------------------------------------------------------------------------
# SAAMI: velocity & pressure table
# ----------------------------------------------------------------------------------------------
NUMP = r'\d{2,4}(?:\(\d\))?'
RIFLE_P1 = re.compile(r'Crusher Pressures Not Established\s+(' + NUMP + r')\s+(' + NUMP + r')\s+(' + NUMP + r')\s*$')
RIFLE_P2 = re.compile(r'(?<![\d,])(' + NUMP + r')\s+(' + NUMP + r')\s+(' + NUMP + r')\s+Piezo Pressures Not Established\s*$')
TOK6 = r'(N/E|' + NUMP + r')'
SIX = re.compile(r'(?<![\d,/])' + r'\s+'.join([TOK6] * 6) + r'\s*$')
FOOTNOTE_START = re.compile(r'^\s*(\(1\)|1\s*[-–]\s*Based|η=10)')


def _pval(tok):
    if tok is None or tok == 'N/E':
        return None, None
    m = re.match(r'^(\d+)(?:\((\d)\))?$', tok)
    return int(m.group(1)), (m.group(2) and int(m.group(2)))


def parse_pressure_line(line):
    """Return dict(cup=(MAP,MPLM,MPSM) or None, psi=(...) or None, col=start col) or None."""
    m = RIFLE_P1.search(line)
    if m:
        return {'cup': None, 'psi': m.groups(), 'col': m.start()}
    m = RIFLE_P2.search(line)
    if m:
        return {'cup': m.groups(), 'psi': None, 'col': m.start()}
    m = SIX.search(line)
    if m and m.start() >= 55:
        g = m.groups()
        cup = None if g[0] == 'N/E' else g[0:3]
        psi = None if g[3] == 'N/E' else g[3:6]
        return {'cup': cup, 'psi': psi, 'col': m.start()}
    return None


def clean_table_name(n):
    n = ws(n)
    while True:
        n2 = re.sub(r'\s*\(\d\)\s*$', '', n)
        if n2 == n:
            break
        n = n2
    return n


def saami_vp_table(doc_key, pages):
    """Parse the SAAMI 'Velocity & Pressure Data' table pages. One pressure line per cartridge."""
    out = []
    problems = []
    for pi, page in enumerate(pages):
        if 'VELOCITY & PRESSURE DATA' not in page or 'Cartridge' not in page:
            continue
        lines = page.split('\n')
        # header line with psi/100 / CUP/100 units (kept verbatim for evidence)
        unit_hdr = next((ws(l) for l in lines if 'TRANSDUCER Pressure' in l), None)
        try:
            start = next(i for i, l in enumerate(lines) if re.match(r'^\s*Cartridge\s{3,}', l)) + 1
        except StopIteration:
            continue
        names = []   # [first_line_idx, [text parts], [line idxs]]
        plines = []  # (idx, parsed)
        for i in range(start, len(lines)):
            l = lines[i]
            if FOOTNOTE_START.match(l):
                break
            if not l.strip():
                continue
            p = parse_pressure_line(l)
            if p:
                plines.append((i, p))
            lead = len(l) - len(l.lstrip())
            body = l.lstrip()
            if lead <= 1 and re.match(r'\d', body):
                nm = re.match(r'^(\S.*?)(?:\s{3,}|$)', body).group(1)
                names.append([i, [nm], [i]])
            elif 1 <= lead <= 8 and re.match(r'[A-Za-z(]', body) and names:
                nm = re.match(r'^(\S.*?)(?:\s{3,}|$)', body).group(1)
                names[-1][1].append(nm)
                names[-1][2].append(i)
        if len(names) != len(plines):
            problems.append(f'{doc_key} pdf p{pi+1}: {len(names)} names vs {len(plines)} pressure lines')
            continue
        for k, ((ni, parts, nidx), (pidx, p)) in enumerate(zip(names, plines)):
            prev_n = names[k - 1][0] if k else start - 1
            next_n = names[k + 1][0] if k + 1 < len(names) else len(lines)
            if not (prev_n < pidx < next_n):
                problems.append(f'{doc_key} pdf p{pi+1}: pressure line {pidx} outside block of {parts}')
                continue
            name = clean_table_name(' '.join(parts))
            ev_lines = sorted(set(nidx + [pidx]))
            evidence = (unit_hdr + ' | ' if unit_hdr else '') + ' | '.join(ws(lines[j]) for j in ev_lines)
            rec = {'name': name, 'pdfPage': pi + 1, 'evidence': evidence, 'doc': doc_key}
            if p['psi']:
                v, fn = _pval(p['psi'][0])
                rec['mapPsi100'] = v
                rec['mapPsiFootnote'] = fn
            if p['cup']:
                v, fn = _pval(p['cup'][0])
                rec['mapCup100'] = v
            out.append(rec)
    return out, problems


# ----------------------------------------------------------------------------------------------
# SAAMI: table of contents -> drawing / test-barrel page numbers
# ----------------------------------------------------------------------------------------------

def footer_page(page):
    ls = [l for l in page.split('\n') if l.strip()]
    f = None
    for l in ls[-4:]:
        m = re.match(r'^\s*(\d{1,3})\s*(?:NOTICE.*)?$', l)
        if m:
            f = int(m.group(1))
    return f


def saami_toc(pages):
    """Returns {'drawings': [(name, docpage)], 'barrels': [(name, docpage)]}."""
    res = {'drawings': [], 'barrels': []}
    state = None
    for page in pages[:16]:
        if 'TABLE OF CONTENTS' not in page:
            continue
        for l in page.split('\n'):
            s = l.strip()
            if s.startswith('Cartridge and Chamber Drawings'):
                state = 'drawings'
                continue
            if s.startswith('Standard Velocity and Pressure Test Barrels'):
                state = 'barrels'
                continue
            if re.match(r'^(Miscellaneous|SECTION|Standard V&P Test Barrels - General)', s):
                state = None
                continue
            m = re.match(r'^(.+?)\s*\.{3,}\s*(\d+)$', s)
            if m and state:
                for nm in m.group(1).split(' / '):
                    res[state].append((ws(nm), int(m.group(2))))
    return res


# ----------------------------------------------------------------------------------------------
# SAAMI: dimension tokens on drawings (inch <-> mm pairs verified by the 25.4 ratio)
# ----------------------------------------------------------------------------------------------
DASH = '-–‒─—'
NUM = r'(?:\d*\.\d+|\d+)'
TOLRE = r'(?:\s{0,2}([+\-' + DASH[1:] + r'±])\s{0,2}(\d*\.\d+))?'
TOKRE = re.compile(r'\(\s*(' + NUM + r')' + TOLRE + r'\s*\)|(?<![\d./:°])(' + NUM + r')(?![\d°\'"/])' + TOLRE)


def tokens(line, li):
    line = re.sub(r'\((\d)\)', lambda m: ' ' * len(m.group(0)), line)  # footnote markers -> blanks
    toks = []
    for m in TOKRE.finditer(line):
        if m.group(1) is not None:
            v, sg, tv, paren = m.group(1), m.group(2), m.group(3), True
        else:
            v, sg, tv, paren = m.group(4), m.group(5), m.group(6), False
        try:
            val = float(v)
        except ValueError:
            continue
        sign = None
        if sg:
            sign = '+' if sg == '+' else ('±' if sg == '±' else '-')
        toks.append({'v': val, 'raw': m.group(0).strip(), 'sign': sign, 'tol': float(tv) if tv else None,
                     'paren': paren, 's': m.start(), 'e': m.end(), 'li': li})
    return toks


def pair_err(inch, mm):
    return abs(inch * 25.4 - mm)


def consistent(inch, mm):
    # printed values are rounded (inch to .001/.0001, mm to .01/.001): allow 0.02 mm, or 0.05 % for large values
    return pair_err(inch, mm) <= max(0.02, 0.0005 * mm)


def make_pair(a, b):
    """a, b tokens with exactly one in parentheses. Return pair dict or None."""
    if a['paren'] == b['paren']:
        return None
    if consistent(a['v'], b['v']):
        i, m = a, b
    elif consistent(b['v'], a['v']):
        i, m = b, a
    else:
        return None
    sign = i['sign'] or m['sign']
    return {'in': i['v'], 'mm': m['v'], 'sign': sign, 'tolIn': i['tol'],
            'err': pair_err(i['v'], m['v']),
            'li': min(a['li'], b['li']), 'li2': max(a['li'], b['li']),
            's': min(a['s'], b['s']), 'e': max(a['e'], b['e']),
            'raw': (a['raw'] + ' ' + b['raw']) if a['li'] == b['li'] else (a['raw'] + ' / ' + b['raw']),
            'inTok': i, 'mmTok': m}


def page_pairs(lines):
    """Pair every inch value with its millimetre twin (one of them in parentheses).

    Candidates are horizontal neighbours (only blanks / reference markers between them) and
    vertical neighbours (next 1-2 non-blank lines, overlapping columns).  A candidate is kept
    only if inch*25.4 == mm within rounding; candidates are accepted globally in order of the
    smallest conversion error, so a token is never paired with a worse partner."""
    toks_by_line = [tokens(l, i) for i, l in enumerate(lines)]
    cands = []
    for li, toks in enumerate(toks_by_line):
        for k in range(len(toks) - 1):
            a, b = toks[k], toks[k + 1]
            gap = lines[li][a['e']:b['s']]
            if len(gap) > 8 or re.sub(r'[\s∆*B]', '', gap):
                continue
            p = make_pair(a, b)
            if p:
                cands.append((p['err'], 0, 0, p, (li, k), (li, k + 1)))
    for li, toks in enumerate(toks_by_line):
        nxt = [j for j in range(li + 1, min(li + 4, len(lines))) if lines[j].strip()][:2]
        for k, a in enumerate(toks):
            for j in nxt:
                for kk, b in enumerate(toks_by_line[j]):
                    ca, cb = (a['s'] + a['e']) / 2, (b['s'] + b['e']) / 2
                    if abs(ca - cb) > 5 and not (a['s'] <= b['e'] and b['s'] <= a['e']):
                        continue
                    p = make_pair(a, b)
                    if p:
                        cands.append((p['err'], 1, abs(ca - cb), p, (li, k), (j, kk)))
    cands.sort(key=lambda c: (round(c[0], 4), c[1], c[2]))
    used = set()
    pairs = []
    for err, kind, dist, p, ta, tb in cands:
        if ta in used or tb in used:
            continue
        used.add(ta)
        used.add(tb)
        pairs.append(p)
    return pairs


TWIST_RE = re.compile(r'TWIST:\s*(\d*\.?\d+)\s*[\(\[]\s*(\d*\.?\d+)\s*[\)\]]\s*(R\.?\s?H\.?|L\.?\s?H\.?)')


def drawing_dims(page):
    """Extract machine-readable dimensions from one SAAMI cartridge & chamber drawing page."""
    lines = page.split('\n')
    pairs = page_pairs(lines)
    res = {'warnings': []}
    metric = ('METRIC ORIGIN' in page) or ('= INCHES' in page)
    res['metricOrigin'] = metric
    # title line
    iss = next((i for i, l in enumerate(lines) if 'ISSUED:' in l), None)
    res['titleLines'] = [ws(l) for l in lines[:12] if l.strip()]
    start = iss if iss is not None else 0
    # end of cartridge half: first 'BREECH' or a stand-alone 'CHAMBER' label after the title
    end = None
    for i in range(start + 1, len(lines)):
        if 'BREECH' in lines[i] or re.match(r'^\s*CHAMBER\s*$', lines[i]):
            end = i
            break
    if end is None:
        res['warnings'].append('could not locate end of cartridge drawing (no BREECH/CHAMBER label)')
    # ---- twist
    m = TWIST_RE.search(page)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        inch, mm = (a, b) if a < b else (b, a)
        if consistent(inch, mm):
            res['twistIn'] = inch
            res['twistDir'] = 'LH' if m.group(3).upper().startswith('L') else 'RH'
            res['twistEv'] = ws(m.group(0))
        else:
            res['warnings'].append('twist values not consistent: ' + m.group(0))
    # ---- bore / groove diameters (value directly above the label, same columns)
    for key, label in (('boreIn', 'Bore Di'), ('grooveIn', 'Groove Di')):
        hits = [(i, lines[i].find(label)) for i in range(len(lines)) if label in lines[i]]
        vals = []
        for (i, c) in hits:
            cands = [p for p in pairs if p['li2'] < i and i - p['li2'] <= 3 and abs(p['s'] - c) <= 7]
            if cands:
                p = max(cands, key=lambda p: (p['li2'], -abs(p['s'] - c)))
                vals.append((p, i))
        if len(vals) >= 1:
            v = {round(p['in'], 4) for p, _ in vals}
            if len(v) == 1:
                p, i = vals[0]
                res[key] = p['in']
                res[key + 'Mm'] = p['mm']
                res[key + 'Ev'] = ws(lines[p['li']][max(0, p['s'] - 2):p['e'] + 2]) + ' / ' + ws(lines[i][max(0, lines[i].find(label) - 2):lines[i].find(label) + 12])
            else:
                res['warnings'].append(f'{key}: multiple values {sorted(v)}')
        elif hits:
            res['warnings'].append(f'{key}: label found but no value pair above it')
    # ---- bullet diameter(s)
    blabels = [(i, m.start(), m.end()) for i, l in enumerate(lines) for m in re.finditer(r'BULLET(?!\s+PROFILE)', l)]
    bullets = []
    for (i, cs, ce) in blabels:
        cands = []
        for p in pairs:
            if p['sign'] != '-':
                continue
            dl = min(abs(p['li'] - i), abs(p['li2'] - i))
            if dl > 3:
                continue
            # same columns (+-15) or on the same line right before the label
            colok = (p['s'] <= ce + 15 and p['e'] >= cs - 15) or (p['li2'] == i and p['e'] <= cs and cs - p['e'] < 4)
            if not colok or p['in'] > 1.0:
                continue
            cands.append((dl, abs((p['s'] + p['e']) / 2 - (cs + ce) / 2), p))
        if cands:
            cands.sort(key=lambda x: (x[0], x[1]))
            p = cands[0][2]
            # variant word (LEAD / JACKETED) printed next to the value
            seg = ' '.join(lines[j][p['s']:p['e'] + 14] for j in range(p['li'], p['li2'] + 1))
            var = re.search(r'\b(LEAD|JACKETED|PLATED)\b', seg)
            bullets.append({'in': p['in'], 'mm': p['mm'], 'tolIn': p['tolIn'], 'variant': var.group(1) if var else None,
                            'ev': ws(' / '.join(lines[j][max(0, p['s'] - 1):p['e'] + 14] for j in range(p['li'], p['li2'] + 1)))
                            + ' / ' + ws(lines[i][cs:ce + 3])})
    uniq = {}
    for b in bullets:
        uniq.setdefault(round(b['in'], 4), b)
    res['bullets'] = list(uniq.values())
    # ---- lengths in the cartridge half: COAL = largest, case length = nearest line above COAL
    if end is not None:
        half = [p for p in pairs if start < p['li'] < end and p['in'] >= 0.25]
        if half:
            top = max(half, key=lambda p: p['in'])
            coal_line = top['li']
            on_line = [p for p in half if p['li'] == coal_line]
            ltxt = lines[coal_line]
            if 'MAX' in ltxt or top['sign'] == '-':
                res['coalMaxIn'] = top['in']
                res['coalMaxMm'] = top['mm']
                if 'MIN' in ltxt and len(on_line) >= 2:
                    res['coalMinIn'] = min(p['in'] for p in on_line)
                res['coalEv'] = ws(ltxt)
                res['coalLine'] = coal_line
            else:
                res['warnings'].append('largest cartridge length has neither MAX nor minus tolerance: ' + ws(ltxt))
            others = [p for p in half if p['li'] != coal_line and p['li2'] != coal_line]
            above = [p for p in others if p['li'] < coal_line]
            if 'coalMaxIn' in res and above:
                near_li = max(p['li'] for p in above)
                near = [p for p in above if p['li'] == near_li]
                second = max(above, key=lambda p: p['in'])
                if len(near) == 1 and near[0] is second and near[0]['sign'] == '-' and near[0]['in'] < res['coalMaxIn']:
                    res['caseLenIn'] = near[0]['in']
                    res['caseLenMm'] = near[0]['mm']
                    res['caseLenTolIn'] = near[0]['tolIn']
                    res['caseLenEv'] = ws(lines[near_li])
                else:
                    res['warnings'].append('case length not unambiguous (nearest-above-COAL != second-largest or no minus tol): '
                                           + ws(lines[near_li]) + ' vs ' + second['raw'])
    return res




TRANSDUCER_LABEL = re.compile(r'TRANSDUCER(?:\s+LOCATION)?\s+C(?:\s*L)?\s*$|TRANSDUCER(?:\s+LOCATION)?\s+C\s*L?\s{2,}|TRANSDUCER(?:\s+LOCATION)?\s+CL\b')
PISTON_LABEL = re.compile(r'PISTON HOLE\s+C')


def barrel_transducer(page):
    """Transducer location from a SAAMI V&P test-barrel drawing: the minus-toleranced dimension
    (breech face to transducer centre line) printed right below/next to the 'TRANSDUCER (LOCATION) CL'
    label.  Candidates nearer to the 'PISTON HOLE CL' label than to the transducer label are rejected."""
    lines = page.split('\n')
    pairs = page_pairs(lines)
    labs = [(i, m.start()) for i, l in enumerate(lines) for m in [TRANSDUCER_LABEL.search(l)] if m]
    if not labs:
        return None
    i, col = labs[0]
    pist = [j for j, l in enumerate(lines) if PISTON_LABEL.search(l)]
    cands = []
    for p in pairs:
        if p['sign'] != '-' or not (0.3 <= p['in'] <= 3.0):
            continue
        if not (i - 1 <= p['li'] <= i + 7):
            continue
        if abs(p['s'] - col) > 30:
            continue
        d_t = abs(p['li'] - i)
        if pist and min(abs(p['li'] - j) for j in pist) < d_t:
            continue
        # skip intervening dimension lines: only lines between label and value may be blank / 'L' / 'C'
        between = [lines[j] for j in range(min(i, p['li']) + 1, max(i, p['li']))]
        if any(re.sub(r'[\sCL]', '', b) for b in between):
            continue
        cands.append((d_t, p))
    if not cands:
        return {'warning': 'TRANSDUCER label without an unambiguous minus-toleranced inch/mm dimension next to it'}
    cands.sort(key=lambda c: c[0])
    p = cands[0][1]
    if len(cands) > 1 and cands[1][0] == cands[0][0] and abs(cands[1][1]['in'] - p['in']) > 1e-9:
        return {'warning': 'two candidate transducer dimensions at the same distance'}
    ev = ' | '.join(ws(lines[j]) for j in sorted({i, p['li'], p['li2']}))
    return {'in': p['in'], 'mm': p['mm'], 'tolIn': p['tolIn'], 'ev': ev}


def page_title(page):
    """Cartridge title on a SAAMI drawing / barrel page (line before 'ISSUED:' or text on the ISSUED line)."""
    lines = [l for l in page.split('\n')]
    for k, l in enumerate(lines):
        if 'ISSUED:' in l:
            m = re.search(r'ISSUED:\s*\S+\s+(.*?)\s+REVISED', l)
            t = ws(m.group(1)) if m else ''
            if not t or 'TEST BARREL' in t.upper():
                prev = [x for x in lines[:k] if x.strip()]
                t = ws(prev[-1]) if prev else t
            return t
    return ''


def saami_names(pages):
    """Full and abbreviated names list (Section I)."""
    res = []
    on = False
    for pi, page in enumerate(pages):
        if 'FULL AND ABBREVIATED NAMES' in page:
            on = True
        elif on and ('VELOCITY DATA INTERPRETATION' in page or 'VELOCITY & PRESSURE DATA' in page
                     or 'FACTORS AFFECTING' in page):
            break
        if not on or 'TABLE OF CONTENTS' in page:
            continue
        for l in page.split('\n'):
            m = re.match(r'^\s*(\S.*?)\s*\.{3,}\s*(\S.*?)\s*$', l)
            if m:
                res.append((ws(m.group(1)), ws(m.group(2)), pi + 1, ws(l)))
    return res


# ----------------------------------------------------------------------------------------------
# C.I.P.
# ----------------------------------------------------------------------------------------------

def cip_table_rows():
    """Rows of the public TDCC listing (Tabs I-IV)."""
    import html as _html
    rows = []
    for t, tabname in CIP_TABS.items():
        h = open(cip_tab_local(t), encoding='utf-8').read()
        for rid, r in re.findall(r'<tr id="cartridge-(\d+)"[^>]*>(.*?)</tr>', h, re.S):
            tds = re.findall(r'<td([^>]*)>(.*?)</td>', r, re.S)
            cells = []
            for attrs, v in tds:
                title = re.search(r'title="([^"]*)"', attrs)
                txt = ws(_html.unescape(re.sub(r'<[^>]+>', ' ', v)).replace('\xa0', ' '))
                cells.append((title.group(1) if title else None, txt, v))
            links = dict((lang, u) for u, lang in re.findall(r'href="(/uploads/tdcc/[^"]+)"[^>]*>(\w\w)</a>', cells[4][2]))
            num = {}
            for title, txt, _ in cells[6:]:
                if not title:
                    continue
                key = {'location of the pressure take (mm)': 'M',
                       'maximum average pressure (bar)': 'Pmax'}.get(title)
                if title.startswith('1,15 Pmax'):
                    key = 'PK'
                elif title.startswith('1,25 Pmax'):
                    key = 'PE'
                elif title.startswith('minimal proof energy'):
                    key = 'EE'
                if key:
                    num[key] = txt
            rows.append({'rowId': rid, 'tab': t, 'tabName': tabname, 'name': cells[0][1], 'date': cells[1][1],
                         'rev': cells[2][1], 'country': cells[3][1], 'enPdf': links.get('EN'),
                         'cells': num,
                         'evidence': 'C.I.P. TDCC list ' + tabname + ': ' + ' | '.join(
                             [cells[0][1], 'Date ' + cells[1][1], 'Rev ' + (cells[2][1] or '-'), cells[3][1]]
                             + [f'{k}={v}' for k, v in num.items()])})
    return rows


def cip_num(s):
    if s is None:
        return None
    s = s.strip().replace(',', '.')
    if not re.match(r'^\d+(\.\d+)?$', s):
        return None
    return float(s)


CIP_VAL = r'(\d+(?:[.,]\d+)?)'
CIP_FN = r'(?:\s*\d\))*'


def cip_label_re(lab):
    return re.compile(r'(?<![A-Za-z0-9+])' + lab + CIP_FN + r'\s*\*?' + CIP_FN + r'\s*=\s*' + CIP_VAL + r'(?![\d°\'"])')


CIP_LABELS = {k: cip_label_re(v) for k, v in {
    'L3': 'L3', 'L6': 'L6', 'G1': 'G1', 'F': 'F', 'Z': 'Z', 'u': 'u'}.items()}
CIP_LABEL_ANY = {k: re.compile(r'(?<![A-Za-z0-9+])' + v + CIP_FN + r'\s*\*?' + CIP_FN + r'\s*=') for k, v in {
    'L3': 'L3', 'L6': 'L6', 'G1': 'G1', 'F': 'F', 'Z': 'Z', 'u': 'u'}.items()}


def cip_sheet(pdf):
    """Parse one C.I.P. TDCC data sheet (pdftotext -layout).  Left column = CARTRIDGE MAXI,
    right column = CHAMBER MINI / Barrel.  Returns dict of values (mm / bar) with evidence lines."""
    pages = pdftotext_pages(pdf)
    text = '\n'.join(pages)
    lines = text.split('\n')
    res = {'warnings': [], 'ev': {}}
    if not re.search(r'\d', text) or 'Pmax' not in text:
        res['warnings'].append('no machine-readable text / no Pmax label in sheet')
        return res
    res['mmUnits'] = bool(re.search(r'Dimensions in\s*<<\s*mm\s*>>', text))
    # header name (line(s) above 'Country of Origin')
    hdr = ''
    for k, l in enumerate(lines[:12]):
        if 'Country of Origin' in l:
            seg = [ws(re.sub(r'C\.I\.P\.|TAB\.?:?\s+\S+|Date:?\s+\S*|Revision:?\s*\S*', ' ', x)) for x in lines[max(0, k - 3):k]]
            hdr = ' '.join(x for x in seg if x)
            break
    res['header'] = hdr
    # column split: x position of the chamber-side labels
    rights = []
    for l in lines:
        found = [m.start() for m in re.finditer(r'(?<![A-Za-z0-9])L[123]\b', l)]
        if len(found) >= 2:
            rights.append(found[-1])
        for m in re.finditer(r'\b(Barrel|Grooves|Commencement of Rifling|CHAMBER MINI)\b', l):
            rights.append(m.start())
    if not rights:
        res['warnings'].append('could not determine the chamber column position')
        return res
    split = min(rights) - 3
    res['split'] = split
    # Barrel section start (F / Z of the barrel follow it in the right column)
    barrel_li = next((i for i, l in enumerate(lines) if re.search(r'\bBarrel\b', l)), None)

    def grab(key, side, after=None):
        hits = []
        for i, l in enumerate(lines):
            if after is not None and i <= after:
                continue
            for m in CIP_LABEL_ANY[key].finditer(l):
                if (m.start() < split) != (side == 'L'):
                    continue
                mv = CIP_LABELS[key].match(l, m.start())
                if mv and ((mv.start(1) < split) == (side == 'L') or side == 'R'):
                    hits.append((i, cip_num(mv.group(1)), mv.group(1), l))
                else:
                    hits.append((i, None, None, l))
        return hits

    for key, side, after in (('L3', 'L', None), ('L6', 'L', None), ('G1', 'L', None),
                             ('F', 'R', barrel_li), ('Z', 'R', barrel_li), ('u', 'R', barrel_li)):
        if side == 'R' and after is None:
            res['warnings'].append(f'{key}: no Barrel section found')
            continue
        hits = grab(key, side, after)
        vals = [h for h in hits if h[1] is not None]
        if not hits:
            res['warnings'].append(f'{key}: label not found')
        elif not vals:
            res['warnings'].append(f'{key}: label present but no value on the same line ({ws(hits[0][3])})')
        else:
            if len({v[1] for v in vals}) > 1 and key in ('L3', 'L6', 'G1'):
                res['warnings'].append(f'{key}: several different values {[v[2] for v in vals]}')
                continue
            if key in ('F', 'Z', 'u'):
                vals = vals[:1]
            res[key] = vals[0][1]
            res['ev'][key] = ws(vals[0][3])
    m = re.search(r'Pmax\s*=\s*(\d+)\s*bar', text)
    if m:
        res['Pmax'] = int(m.group(1))
        res['ev']['Pmax'] = ws(next(l for l in lines if m.group(0) in l))
    m = re.search(r'Method\s+(Transducer|Crusher|[A-Za-z]+)', text)
    if m:
        res['method'] = m.group(1)
        res['ev']['method'] = ws(m.group(0))
    m = re.search(r'(?<![A-Za-z])M\s*=\s*(\d+[.,]\d+)', text)
    if m:
        res['M'] = cip_num(m.group(1))
        res['ev']['M'] = ws(m.group(0))
    return res
