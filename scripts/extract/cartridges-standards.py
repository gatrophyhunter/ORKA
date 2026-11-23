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
    'Z299.3': {
        'url': 'https://saami.org/wp-content/uploads/2025/05/SAAMI-Z299.3-2022-Centerfire-Pistol-Revolver-Approved-12-13-2022.pdf',
        'local': 'Z299.3.pdf',
        'title': 'ANSI/SAAMI Z299.3-2022 Voluntary Industry Performance Standards for Pressure and Velocity of Centerfire Pistol and Revolver Ammunition',
        'date': '2022-12-13 (approved)',
        'kind': 'handgun',
    },
    'Z299.4': {
        'url': 'https://saami.org/wp-content/uploads/2026/10/SAAMI-Z299.4-CFR-2025-Centerfire-Rifle-Approved-2-10-2025-2026-10-21.pdf',
        'local': 'Z299.4.pdf',
        'title': 'ANSI/SAAMI Z299.4-2025 Voluntary Industry Performance Standards for Pressure and Velocity of Centerfire Rifle Sporting Ammunition',
        'date': '2025-02-10 (approved; file revision dated 2026-10-21)',
        'kind': 'rifle',
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
                rec['psiTriple100'] = [_pval(x)[0] for x in p['psi']]
            if p['cup']:
                v, fn = _pval(p['cup'][0])
                rec['mapCup100'] = v
                rec['cupTriple100'] = [_pval(x)[0] for x in p['cup']]
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
            after = lines[top['li2']][top['e']:]
            labelled_max = bool(re.match(r'^\s*MAX\b', after)) or (top['sign'] == '-' and 'MIN' not in ltxt)
            if 'MAX' in ltxt and not labelled_max:
                res['warnings'].append('largest paired cartridge length is not the value labelled MAX (MAX value probably has an inconsistent inch/mm pair): '
                                       + ws(ltxt))
            elif labelled_max:
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




TRANSDUCER_LABEL = re.compile(r'\bTRANSDUCER(?:\s+LOCATION)?(?=\s+(?:C\s*L|CL|C|L)\b|\s*$)')
PISTON_LABEL = re.compile(r'PISTON HOLE\s+C')


def barrel_transducer(page):
    """Transducer location from a SAAMI V&P test-barrel drawing: the minus-toleranced dimension
    (breech face to transducer centre line) printed right below (or just above) the
    'TRANSDUCER (LOCATION) CL' label, in the same column region.  Candidates nearer to the
    'PISTON HOLE CL' label than to the transducer label are rejected; ties are reported, not guessed."""
    lines = page.split('\n')
    pairs = page_pairs(lines)
    labs = []
    for i, l in enumerate(lines):
        if re.search(r'DIAMETER|INSTALLATION|TRANSDUCERS|HOLE|OF TRANSDUCER', l):
            continue
        m = TRANSDUCER_LABEL.search(l)
        if m:
            labs.append((i, m.start()))
    if not labs:
        return None
    if len(labs) > 1:
        return {'warning': 'more than one TRANSDUCER label on the barrel drawing'}
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
        # the value must not lie beyond a PISTON HOLE label (that label owns the dimensions on its side)
        if any((i < j <= p['li']) or (p['li'] <= j < i) for j in pist):
            continue
        cands.append(((0 if p['li'] >= i else 1), d_t, p))
    if not cands:
        return {'warning': 'TRANSDUCER label without a minus-toleranced inch/mm dimension next to it'}
    cands.sort(key=lambda c: (c[0], c[1]))
    p = cands[0][2]
    if len(cands) > 1 and cands[1][:2] == cands[0][:2] and abs(cands[1][2]['in'] - p['in']) > 1e-9:
        return {'warning': 'two candidate transducer dimensions at the same distance'}
    ev = ' | '.join(ws(lines[j]) for j in sorted({i, p['li'], p['li2']}))
    return {'in': p['in'], 'mm': p['mm'], 'tolIn': p['tolIn'], 'ev': ev}


def header_block(page):
    """Title block of a SAAMI drawing page: everything down to the first 'ISSUED:' line (+1 line)."""
    lines = page.split('\n')
    k = next((i for i, l in enumerate(lines) if 'ISSUED:' in l), 8)
    return ' '.join(ws(l) for l in lines[:k + 2])


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
    pm = [l.find('Pmax') for l in lines if re.search(r'Pmax\s*=', l)]
    if not pm or pm[0] >= split:
        res['warnings'].append('column split check failed (Pmax label not left of the chamber column): dimensions not read')
        return res
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


# ----------------------------------------------------------------------------------------------
# SAAMI aggregation
# ----------------------------------------------------------------------------------------------

def validate_drawing(d, name):
    """Plausibility gates on values read from a drawing.  Anything failing is dropped (null) and
    reported; nothing is corrected or estimated."""
    out = {'warnings': list(d['warnings'])}
    bore, groove = d.get('boreIn'), d.get('grooveIn')
    if bore is not None and groove is not None and not (0.002 <= groove - bore <= 0.025):
        out['warnings'].append(f'bore {bore} / groove {groove} implausible (groove-bore not in 0.002..0.025 in): both dropped')
        bore = groove = None
    out['boreIn'], out['grooveIn'] = bore, groove
    if bore is not None:
        out['boreMm'], out['boreEv'] = d['boreInMm'], d['boreInEv']
    if groove is not None:
        out['grooveMm'], out['grooveEv'] = d['grooveInMm'], d['grooveInEv']
    # bullets
    bl = d.get('bullets') or []
    ok = []
    for b in bl:
        if groove is not None and not (-0.003 - 1e-9 <= b['in'] - groove <= 0.008 + 1e-9):
            out['warnings'].append(f"bullet value {b['in']} inconsistent with groove {groove}: dropped")
            continue
        ok.append(b)
    out['bullets'] = ok
    if len(ok) == 1:
        out['bulletIn'], out['bulletMm'], out['bulletEv'] = ok[0]['in'], ok[0]['mm'], ok[0]['ev']
    elif len(ok) > 1:
        jac = [b for b in ok if b['variant'] == 'JACKETED']
        if len(jac) == 1 and all(b['variant'] for b in ok):
            out['bulletIn'], out['bulletMm'], out['bulletEv'] = jac[0]['in'], jac[0]['mm'], jac[0]['ev']
            out['warnings'].append('several bullet diameters by bullet type; bulletDiameterIn = JACKETED value, see saami.bulletDiameterVariantsIn')
        else:
            out['warnings'].append('several unlabeled bullet diameters on drawing; bulletDiameterIn left null, see saami.bulletDiameterVariantsIn')
    # lengths
    case, coal = d.get('caseLenIn'), d.get('coalMaxIn')
    if case is not None and coal is not None:
        if not (0.04 <= coal - case <= 1.9):
            out['warnings'].append(f'COAL {coal} vs case length {case} implausible: both dropped')
            case = coal = None
    elif coal is not None and case is None:
        out['warnings'].append(f'COAL candidate {coal} found but case length not identified: COAL not accepted (cannot be cross-checked on the drawing)')
        coal = None
    out['caseIn'] = case
    if case is not None:
        out['caseMm'], out['caseEv'], out['caseTolIn'] = d['caseLenMm'], d['caseLenEv'], d.get('caseLenTolIn')
    out['coalIn'] = coal
    if coal is not None:
        out['coalMm'], out['coalEv'] = d['coalMaxMm'], d['coalEv']
        out['coalMinIn'] = d.get('coalMinIn')
    tw = d.get('twistIn')
    if tw is not None and not (4.0 <= tw <= 60.0):
        out['warnings'].append(f'twist {tw} implausible: dropped')
        tw = None
    out['twistIn'] = tw
    if tw is not None:
        out['twistDir'], out['twistEv'] = d['twistDir'], d['twistEv']
    return out


def saami_collect():
    """Returns list of per-(doc, cartridge) dicts with everything read from SAAMI."""
    entries = []
    problems = []
    for key, doc in SAAMI_DOCS.items():
        pdf = os.path.join(SRC, doc['local'])
        pages = pdftotext_pages(pdf)
        vp, probs = saami_vp_table(key, pages)
        problems += probs
        toc = saami_toc(pages)
        names = saami_names(pages)
        f2p = {}
        for i, p in enumerate(pages):
            f = footer_page(p)
            if f is not None and i > 8:
                f2p.setdefault(f, []).append(i)
        tocd = {norm_key(n): (n, dp) for n, dp in toc['drawings']}
        tocb = {norm_key(n): (n, dp) for n, dp in toc['barrels']}
        namemap = {norm_key(f): (f, a, pg, ev) for f, a, pg, ev in names}
        # page footnotes for MAP markers
        for r in vp:
            e = {'doc': key, 'docInfo': doc, 'vp': r, 'name': r['name'], 'warnings': []}
            nk = norm_key(r['name'])
            nm = namemap.get(nk)
            if nm:
                e['fullName'], e['abbrev'], e['namesPage'], e['namesEv'] = nm
            else:
                e['warnings'].append('not found in the full/abbreviated names list')
            # footnote text for a MAP psi marker
            if r.get('mapPsiFootnote'):
                pg = pages[r['pdfPage'] - 1].split('\n')
                fn = r['mapPsiFootnote']
                txt = None
                for l in pg:
                    m = re.search(r'(?:^|\s)\(?' + str(fn) + r'\)?\s*[-–]\s*(.+?)(?:\s{3,}\(?\d\)?\s*[-–]|$)', l)
                    if m and ('Based' in m.group(1) or 'WARNING' in m.group(1)):
                        txt = ws(m.group(1))
                        break
                e['mapFootnoteText'] = txt
            # drawing
            dn = tocd.get(nk)
            if dn and dn[1] in f2p:
                pi = f2p[dn[1]][0]
                title = page_title(pages[pi])
                tk = norm_key(header_block(pages[pi]))
                okt = nk in tk or (nm and norm_key(nm[1]) in tk) or norm_key(dn[0]) in tk
                if not okt:
                    e['warnings'].append(f'drawing page title "{title}" does not contain the cartridge name: drawing not used')
                else:
                    raw = drawing_dims(pages[pi])
                    e['drawing'] = validate_drawing(raw, r['name'])
                    e['drawing']['raw'] = raw
                    e['drawingPage'] = pi + 1
                    e['drawingDocPage'] = dn[1]
                    e['drawingTitle'] = title
                    e['metricOrigin'] = raw['metricOrigin']
            else:
                e['warnings'].append('no cartridge & chamber drawing found in the table of contents')
            bn = tocb.get(nk)
            if bn and bn[1] in f2p:
                pi = f2p[bn[1]][0]
                title = page_title(pages[pi])
                tl = barrel_transducer(pages[pi])
                e['barrelPage'] = pi + 1
                e['barrelTitle'] = title
                if tl and 'warning' not in tl:
                    e['transducer'] = tl
                elif tl:
                    e['warnings'].append('V&P barrel p.%d: %s' % (pi + 1, tl['warning']))
                else:
                    e['warnings'].append('V&P barrel p.%d: no transducer label' % (pi + 1))
            entries.append(e)
    return entries, problems


# ----------------------------------------------------------------------------------------------
# Name linking (SAAMI <-> C.I.P.)
# ----------------------------------------------------------------------------------------------
WORDMAP = {'WINCHESTER': 'WIN', 'REMINGTON': 'REM', 'MAGNUM': 'MAG', 'SPRINGFIELD': 'SPRING', 'SPRG': 'SPRING',
           'WEATHERBY': 'WBY', 'WEATH': 'WBY', 'GOVERNMENT': 'GOVT', 'GOV': 'GOVT', 'AUTOMATIC': 'AUTO',
           'SPECIAL': 'SPL', 'SPEC': 'SPL', 'SHORT': 'S', 'SAVAGE': 'SAV', 'BROWNING': 'BROWN', 'SWEDISH': 'SE'}


def loose_key(name):
    s = name.upper().replace(',', '.').replace('’', '').replace("'", '').replace('”', '').replace('"', '')
    s = s.replace('HOLLAND & HOLLAND', 'H&H').replace('HOLLAND&HOLLAND', 'H&H').replace('SMITH & WESSON', 'S&W').replace('SMITH &WESSON', 'S&W')
    toks = re.findall(r'\d+(?:\.\d+)?|[A-Z&+]+', s)
    out = []
    for t in toks:
        t = WORDMAP.get(t, t)
        out.append(t)
    k = ''.join(out)
    k = re.sub(r'(\d)MM', r'\1', k)
    return k


# ----------------------------------------------------------------------------------------------
# Records
# ----------------------------------------------------------------------------------------------
IN_TOL_DIA = 0.0015   # in: SAAMI vs CIP diameters differing by more than this are recorded as conflicts
IN_TOL_LEN = 0.02     # in: lengths


def r4(x):
    return None if x is None else round(x, 4)


def build():
    meta_docs = []
    for k, d in SAAMI_DOCS.items():
        meta_docs.append({'url': d['url'], 'localPath': os.path.join(SRC, d['local']), 'title': d['title'], 'date': d['date']})
    entries, vp_problems = saami_collect()
    records = {}
    order = []
    log = {'vpProblems': vp_problems, 'saamiWarnings': {}, 'cipWarnings': {}, 'linking': []}

    def conflict(rec, field, a, asrc, b, bsrc):
        rec['conflicts'].append({'field': field, 'values': [{'value': a, 'source': asrc}, {'value': b, 'source': bsrc}]})

    # ---------------- SAAMI records
    for e in entries:
        doc = e['docInfo']
        name = e.get('fullName') or e['name']
        rid = slug(name)
        vp = e['vp']
        stdname = 'SAAMI ' + e['doc']
        rec = records.get(rid)
        new = rec is None
        if new:
            rec = {'id': rid, 'name': name, 'aliases': [], 'type': doc['kind'], 'standards': [],
                   'bulletDiameterIn': None, 'boreDiameterIn': None, 'grooveDiameterIn': None,
                   'caseLengthMaxIn': None, 'trimLengthIn': None, 'maxCoalIn': None,
                   'saamiMapPsi': None, 'saamiMapCup': None, 'cipPmaxBar': None,
                   'saamiTwist': None, 'saamiTwistDirection': None, 'primerSize': None, 'transducerLocation': None,
                   'sources': [], 'evidence': '', 'conflicts': [], 'notes': [], 'fieldSources': {},
                   'saami': {}, 'cip': None}
            records[rid] = rec
            order.append(rid)
        if doc['kind'] == 'handgun':
            rec['type'] = 'handgun'
        rec['standards'].append(stdname)
        paren = re.findall(r'\(([^()]*\d[^()]*)\)', name)   # e.g. '7mm Mauser (7x57)' -> '7x57'
        for a in [e['name'], e.get('abbrev')] + paren:
            if a and a != rec['name'] and a not in rec['aliases']:
                rec['aliases'].append(a)
        ev = []
        srcs = [src(doc['url'], 'standard', vp['pdfPage'])]
        ev.append(f"[{stdname} p.{vp['pdfPage']} V&P table] {vp['evidence']}")
        psi = vp.get('mapPsi100')
        cup = vp.get('mapCup100')
        sd = {'document': doc['title'], 'vpTablePage': vp['pdfPage'],
              'mapPsiPer100AsPrinted': psi, 'mapCupPer100AsPrinted': cup,
              'psiMapMplmMpsmPer100': vp.get('psiTriple100'), 'cupMapMplmMpsmPer100': vp.get('cupTriple100')}
        if e.get('mapFootnoteText') or vp.get('mapPsiFootnote'):
            sd['mapPsiFootnote'] = {'marker': vp.get('mapPsiFootnote'), 'text': e.get('mapFootnoteText')}
            rec['notes'].append(f"{stdname}: MAP psi carries footnote ({vp.get('mapPsiFootnote')}): {e.get('mapFootnoteText')}")
        for fld, val in (('saamiMapPsi', psi * 100 if psi is not None else None), ('saamiMapCup', cup * 100 if cup is not None else None)):
            if val is None:
                continue
            if rec[fld] is None:
                rec[fld] = val
                rec['fieldSources'][fld] = stdname
            elif rec[fld] != val:
                conflict(rec, fld, rec[fld], rec['fieldSources'][fld], val, stdname)
        dr = e.get('drawing')
        if dr:
            srcs.append(src(doc['url'], 'standard', e['drawingPage']))
            dev = []
            sd['drawingPage'] = e['drawingPage']
            sd['drawingTitle'] = e['drawingTitle']
            sd['drawingMetricOrigin'] = e['metricOrigin']
            if e['metricOrigin']:
                rec['notes'].append(f"{stdname} drawing p.{e['drawingPage']} is METRIC ORIGIN: the inch values used are the inch equivalents printed in the drawing; the printed mm values are in the evidence")
            if dr['bullets']:
                sd['bulletDiameterVariantsIn'] = [{'in': b['in'], 'mm': b['mm'], 'minusTolIn': b['tolIn'], 'variant': b['variant']} for b in dr['bullets']]
            for fld, k, evk in (('bulletDiameterIn', 'bulletIn', 'bulletEv'), ('boreDiameterIn', 'boreIn', 'boreEv'),
                                ('grooveDiameterIn', 'grooveIn', 'grooveEv'), ('caseLengthMaxIn', 'caseIn', 'caseEv'),
                                ('maxCoalIn', 'coalIn', 'coalEv'), ('saamiTwist', 'twistIn', 'twistEv')):
                v = dr.get(k)
                if v is None:
                    continue
                dev.append(f'{fld}: {dr[evk]}')
                if rec[fld] is None:
                    rec[fld] = v
                    rec['fieldSources'][fld] = stdname + ' drawing p.%d' % e['drawingPage']
                    if fld == 'saamiTwist':
                        rec['saamiTwistDirection'] = dr['twistDir']
                elif abs(rec[fld] - v) > 1e-6:
                    conflict(rec, fld, rec[fld], rec['fieldSources'][fld], v, stdname + ' drawing p.%d' % e['drawingPage'])
            if dr.get('coalMinIn') is not None:
                sd['coalMinIn'] = dr['coalMinIn']
            if dr.get('caseTolIn') is not None:
                sd['caseLengthTolIn'] = -dr['caseTolIn']
            ev.append(f"[{stdname} p.{e['drawingPage']} drawing] " + ' || '.join(dev) if dev else f"[{stdname} p.{e['drawingPage']} drawing] (no machine-readable dimension accepted)")
            if dr['warnings']:
                log['saamiWarnings'].setdefault(rid, []).extend(f'{stdname} drawing p.{e["drawingPage"]}: ' + w for w in dr['warnings'])
        tl = e.get('transducer')
        if tl:
            srcs.append(src(doc['url'], 'standard', e['barrelPage']))
            t = {'saamiFromBreechFaceIn': tl['in'], 'saamiFromBreechFaceMm': tl['mm'], 'saamiToleranceIn': -tl['tolIn'] if tl['tolIn'] else None,
                 'saamiSource': f"{stdname} V&P test barrel drawing p.{e['barrelPage']}",
                 'description': 'distance from breech face to transducer centre line (SAAMI test barrel)'}
            if rec['transducerLocation'] is None:
                rec['transducerLocation'] = t
            elif abs(rec['transducerLocation'].get('saamiFromBreechFaceIn', 0) - tl['in']) > 1e-6:
                conflict(rec, 'transducerLocation', rec['transducerLocation'].get('saamiFromBreechFaceIn'),
                         rec['transducerLocation'].get('saamiSource'), tl['in'], t['saamiSource'])
            ev.append(f"[{stdname} p.{e['barrelPage']} V&P test barrel] {tl['ev']}")
        if e.get('namesEv'):
            ev.append(f"[{stdname} p.{e['namesPage']} names list] {e['namesEv']}")
            srcs.append(src(doc['url'], 'standard', e['namesPage']))
        if e['warnings']:
            log['saamiWarnings'].setdefault(rid, []).extend(f'{stdname}: ' + w for w in e['warnings'])
        rec['saami'][e['doc']] = sd
        rec['sources'] += srcs
        rec['evidence'] = (rec['evidence'] + ' ### ' if rec['evidence'] else '') + ' ### '.join(ev)

    # ---------------- C.I.P.
    cip_rows = cip_table_rows()
    saami_ids = list(order)
    exact_idx, loose_idx = {}, {}
    for rid in saami_ids:
        rec = records[rid]
        for n in [rec['name']] + rec['aliases']:
            exact_idx.setdefault(norm_key(n), set()).add(rid)
            loose_idx.setdefault(loose_key(n), set()).add(rid)
    linked = {}
    for row in cip_rows:
        sheet = None
        pdf_url = CIP_BASE + row['enPdf'] if row['enPdf'] else None
        if row['enPdf']:
            lp = cip_pdf_local(row['enPdf'])
            if os.path.exists(lp):
                sheet = cip_sheet(lp)
            else:
                log['cipWarnings'].setdefault(row['name'], []).append('EN sheet not downloaded')
        row['sheet'] = sheet
        row['pdfUrl'] = pdf_url
        row['pmax'] = int(row['cells']['Pmax']) if re.match(r'^\d+$', row['cells'].get('Pmax', '')) else None
        row['M'] = cip_num(row['cells'].get('M'))
        # name check: sheet header vs listed name
        if sheet and sheet.get('header') is not None:
            dig_l = re.findall(r'\d+', row['name'])
            dig_h = re.findall(r'\d+', sheet['header'])
            if sheet['header'] and dig_l != dig_h[:len(dig_l)] and norm_key(row['name']) not in norm_key(sheet['header']):
                sheet['warnings'].append(f'sheet header "{sheet["header"]}" does not match list name "{row["name"]}"')
        # candidate SAAMI link
        nk, lk = norm_key(row['name']), loose_key(row['name'])
        cand = exact_idx.get(nk) or set()
        how = 'exact'
        if not cand:
            cand = loose_idx.get(lk) or set()
            how = 'loose'
        row['link'] = None
        if len(cand) == 1:
            rid = next(iter(cand))
            rec = records[rid]
            # dimension cross-check before linking
            checks = []
            if sheet:
                if sheet.get('G1') is not None and rec['bulletDiameterIn'] is not None:
                    checks.append(abs(sheet['G1'] / 25.4 - rec['bulletDiameterIn']) <= 0.004)
                if sheet.get('L3') is not None and rec['caseLengthMaxIn'] is not None:
                    checks.append(abs(sheet['L3'] / 25.4 - rec['caseLengthMaxIn']) <= 0.06)
            if checks and not all(checks):
                log['linking'].append(f'NOT linked ({how} name match but dimensions disagree): CIP "{row["name"]}" vs SAAMI "{rec["name"]}"')
            elif how == 'loose' and not checks:
                log['linking'].append(f'NOT linked (loose name match without dimensional confirmation): CIP "{row["name"]}" vs SAAMI "{rec["name"]}"')
            elif rid in linked:
                log['linking'].append(f'NOT linked (SAAMI record already linked to CIP "{linked[rid]}"): CIP "{row["name"]}"')
            else:
                row['link'] = rid
                linked[rid] = row['name']
                log['linking'].append(f'linked ({how}, dims checked: {len(checks)}): CIP "{row["name"]}" -> SAAMI "{rec["name"]}"')
        elif len(cand) > 1:
            log['linking'].append(f'NOT linked (ambiguous): CIP "{row["name"]}" -> {sorted(cand)}')

    used_ids = set(records)
    for row in cip_rows:
        sheet = row['sheet']
        if row['link']:
            rec = records[row['link']]
        else:
            rid = slug(row['name'])
            if rid in used_ids:
                rid = rid + '-cip'
            k = 2
            base = rid
            while rid in used_ids:
                rid = f'{base}-{k}'
                k += 1
            used_ids.add(rid)
            rec = {'id': rid, 'name': row['name'], 'aliases': [], 'type': 'handgun' if row['tab'] == 4 else 'rifle',
                   'standards': [], 'bulletDiameterIn': None, 'boreDiameterIn': None, 'grooveDiameterIn': None,
                   'caseLengthMaxIn': None, 'trimLengthIn': None, 'maxCoalIn': None,
                   'saamiMapPsi': None, 'saamiMapCup': None, 'cipPmaxBar': None,
                   'saamiTwist': None, 'saamiTwistDirection': None, 'primerSize': None, 'transducerLocation': None,
                   'sources': [], 'evidence': '', 'conflicts': [], 'notes': [], 'fieldSources': {},
                   'saami': None, 'cip': None}
            rec['notes'].append('type inferred from C.I.P. table: ' + row['tabName'])
            records[rid] = rec
            order.append(rid)
        if row['name'] != rec['name'] and row['name'] not in rec['aliases']:
            rec['aliases'].append(row['name'])
        rec['standards'].append('C.I.P.')
        listurl = cip_tab_url(row['tab'])
        rec['sources'].append(src(listurl, 'standard', None))
        ev = [f"[C.I.P. list] {row['evidence']}"]
        cd = {'name': row['name'], 'table': row['tabName'], 'date': row['date'], 'revision': row['rev'] or None,
              'countryOfOrigin': row['country'], 'listUrl': listurl, 'sheetUrl': row['pdfUrl'],
              'pmaxBar': row['pmax'], 'pkBar': cip_num(row['cells'].get('PK')), 'peBar': cip_num(row['cells'].get('PE')),
              'proofEnergyMinJ': cip_num(row['cells'].get('EE')), 'pressureTakeLocationMm': row['M']}
        if row['pmax'] is not None:
            rec['cipPmaxBar'] = row['pmax']
            rec['fieldSources']['cipPmaxBar'] = 'C.I.P. TDCC list'
        else:
            rec['notes'].append('C.I.P. list gives no Pmax for this entry')
        if row['M'] is not None:
            t = rec['transducerLocation'] or {}
            t['cipPressureTakeFromBreechMm'] = row['M']
            t['cipPressureTakeFromBreechIn'] = r4(row['M'] / 25.4)
            t['cipSource'] = 'C.I.P. TDCC list column M (location of the pressure take, mm); inch value converted from mm'
            rec['transducerLocation'] = t
        if sheet:
            rec['sources'].append(src(row['pdfUrl'], 'standard', 1))
            cd['sheetMethod'] = sheet.get('method')
            cd['sheetDimsMm'] = {k: sheet.get(k) for k in ('L3', 'L6', 'G1', 'F', 'Z')}
            cd['sheetHeader'] = sheet.get('header')
            sev = []
            for k in ('Pmax', 'method', 'M', 'L3', 'L6', 'G1', 'F', 'Z', 'u'):
                if k in sheet['ev']:
                    sev.append(f'{k}: {sheet["ev"][k]}')
            ev.append('[C.I.P. TDCC sheet] ' + ' || '.join(sev))
            if sheet.get('Pmax') is not None and row['pmax'] is not None and sheet['Pmax'] != row['pmax']:
                conflict(rec, 'cipPmaxBar', row['pmax'], 'C.I.P. TDCC list', sheet['Pmax'], 'C.I.P. TDCC sheet ' + row['pdfUrl'])
            if sheet.get('Pmax') is not None and row['pmax'] is None:
                rec['cipPmaxBar'] = sheet['Pmax']
                rec['fieldSources']['cipPmaxBar'] = 'C.I.P. TDCC sheet'
            if sheet.get('M') is not None and row['M'] is not None and abs(sheet['M'] - row['M']) > 1e-6:
                conflict(rec, 'transducerLocation.cipPressureTakeFromBreechMm', row['M'], 'C.I.P. TDCC list', sheet['M'], 'C.I.P. TDCC sheet')
            if sheet.get('u') is not None:
                cd['sheetTwistMm'] = sheet['u'] if sheet['u'] >= 100 else None
                if sheet['u'] < 100:
                    rec['notes'].append(f'C.I.P. sheet twist value u = {sheet["u"]} is implausible as mm; not used')
            for fld, k, tol in (('caseLengthMaxIn', 'L3', IN_TOL_LEN), ('maxCoalIn', 'L6', IN_TOL_LEN),
                                ('bulletDiameterIn', 'G1', IN_TOL_DIA), ('boreDiameterIn', 'F', IN_TOL_DIA),
                                ('grooveDiameterIn', 'Z', IN_TOL_DIA)):
                mm = sheet.get(k)
                if mm is None:
                    continue
                inch = r4(mm / 25.4)
                if rec[fld] is None:
                    rec[fld] = inch
                    rec[fld[:-2] + 'Mm'] = mm
                    rec['fieldSources'][fld] = f'C.I.P. TDCC sheet {k} (mm, converted to inch)'
                    if 'C.I.P. dimensions converted from mm (inch = mm / 25.4, rounded to 0.0001 in); original mm kept in <field>Mm' not in rec['notes']:
                        rec['notes'].append('C.I.P. dimensions converted from mm (inch = mm / 25.4, rounded to 0.0001 in); original mm kept in <field>Mm')
                elif abs(rec[fld] - mm / 25.4) > tol:
                    conflict(rec, fld, rec[fld], rec['fieldSources'][fld], inch, f'C.I.P. TDCC sheet {k} = {mm} mm (converted from mm)')
            if sheet['warnings']:
                log['cipWarnings'].setdefault(row['name'], []).extend(sheet['warnings'])
        rec['cip'] = cd
        rec['evidence'] = (rec['evidence'] + ' ### ' if rec['evidence'] else '') + ' ### '.join(ev)

    # ---------------- finish
    out = []
    for rid in order:
        rec = records[rid]
        rec['standards'] = sorted(set(rec['standards']))
        rec['notes'] = rec['notes'] + [f'parse warning: {w}' for w in log['saamiWarnings'].get(rid, [])]
        if rec.get('cip') and rec['cip']['name'] in log['cipWarnings']:
            rec['notes'] += [f'C.I.P. parse warning: {w}' for w in log['cipWarnings'][rec['cip']['name']]]
        if rec['saami'] and not rec['cip']:
            pass
        if rec['saami'] and len(rec['saami']) > 1:
            rec['notes'].append('listed in both SAAMI Z299.3 (pistol & revolver) and Z299.4 (rifle); primary values from Z299.3, differing Z299.4 values are in conflicts')
        if rec['caseLengthMaxIn'] and rec['maxCoalIn'] and rec['maxCoalIn'] <= rec['caseLengthMaxIn']:
            rec['notes'].append('max cartridge length is not greater than max case length as printed in the source (values kept as printed)')
        if rec['bulletDiameterIn'] and rec['grooveDiameterIn'] and abs(rec['bulletDiameterIn'] - rec['grooveDiameterIn']) > 0.012:
            rec['notes'].append('bullet diameter and groove diameter differ by more than 0.012 in as printed in the source (values kept as printed)')
        rec['notes'] = '; '.join(rec['notes']) if rec['notes'] else None
        seen = set()
        uniq = []
        for s_ in rec['sources']:
            k = (s_['url'], s_['page'])
            if k not in seen:
                seen.add(k)
                uniq.append(s_)
        rec['sources'] = uniq
        rec['evidence'] = ws(rec['evidence'])
        out.append(rec)
    return out, meta_docs, cip_rows, log


# ----------------------------------------------------------------------------------------------
# self-check
# ----------------------------------------------------------------------------------------------

def nums_in(text):
    return {float(x.replace(',', '.')) for x in re.findall(r'(?<![\d.])(\d*[.,]?\d+)(?![\d])', text) if re.search(r'\d', x)}


def self_check(recs, warn=None):
    bad = []
    warn = [] if warn is None else warn
    for r in recs:
        ns = nums_in(r['evidence'])
        def has(v):
            return any(abs(v - n) < 1e-9 for n in ns)
        for fld in ('bulletDiameterIn', 'boreDiameterIn', 'grooveDiameterIn', 'caseLengthMaxIn', 'maxCoalIn', 'saamiTwist'):
            v = r[fld]
            if v is None:
                continue
            mm = r.get(fld[:-2] + 'Mm')
            if mm is not None:
                if not has(mm) or abs(mm / 25.4 - v) > 0.00006:
                    bad.append((r['id'], fld, v, 'mm value not in evidence / conversion mismatch'))
            elif not has(v):
                bad.append((r['id'], fld, v, 'value not in evidence'))
        for fld in ('saamiMapPsi', 'saamiMapCup'):
            v = r[fld]
            if v is not None and not has(v / 100):
                bad.append((r['id'], fld, v, 'psi/100 or CUP/100 value not in evidence'))
        if r['cipPmaxBar'] is not None and not has(r['cipPmaxBar']):
            bad.append((r['id'], 'cipPmaxBar', r['cipPmaxBar'], 'not in evidence'))
        t = r['transducerLocation']
        if t:
            if t.get('saamiFromBreechFaceIn') is not None and not has(t['saamiFromBreechFaceIn']):
                bad.append((r['id'], 'transducerLocation.saami', t['saamiFromBreechFaceIn'], 'not in evidence'))
            if t.get('cipPressureTakeFromBreechMm') is not None and not has(t['cipPressureTakeFromBreechMm']):
                bad.append((r['id'], 'transducerLocation.cip', t['cipPressureTakeFromBreechMm'], 'not in evidence'))
        # V&P triples must be strictly increasing (MAP < MPLM < MPSM), else a wrong column was read
        for dk, sd in (r['saami'] or {}).items():
            for tk in ('psiMapMplmMpsmPer100', 'cupMapMplmMpsmPer100'):
                tr = sd.get(tk)
                if tr and not (tr[0] < tr[1] < tr[2]):
                    bad.append((r['id'], tk, tr, 'MAP/MPLM/MPSM not increasing'))
        # sanity relations (reported as warnings: values are kept as printed)
        if r['bulletDiameterIn'] and r['grooveDiameterIn'] and abs(r['bulletDiameterIn'] - r['grooveDiameterIn']) > 0.012:
            warn.append((r['id'], 'bullet/groove', (r['bulletDiameterIn'], r['grooveDiameterIn']), 'bullet vs groove differ > 0.012 in (as printed)'))
        if r['boreDiameterIn'] and r['grooveDiameterIn'] and not (0 < r['grooveDiameterIn'] - r['boreDiameterIn'] < 0.03):
            bad.append((r['id'], 'bore/groove', (r['boreDiameterIn'], r['grooveDiameterIn']), 'groove-bore not in (0,0.03)'))
        if r['caseLengthMaxIn'] and r['maxCoalIn'] and not (r['maxCoalIn'] > r['caseLengthMaxIn']):
            warn.append((r['id'], 'case/coal', (r['caseLengthMaxIn'], r['maxCoalIn']), 'COAL <= case length'))
    return bad


def main():
    if '--download' in sys.argv:
        download_all()
    recs, meta_docs, cip_rows, log = build()
    for row in cip_rows:
        if row['sheet'] is not None:
            meta_docs.append({'url': row['pdfUrl'], 'localPath': cip_pdf_local(row['enPdf']),
                              'title': f"C.I.P. TDCC sheet {row['tabName'].split(' - ')[0]}: {row['name']} (EN)",
                              'date': row['rev'] or row['date']})
    for t, tn in CIP_TABS.items():
        meta_docs.append({'url': cip_tab_url(t), 'localPath': cip_tab_local(t),
                          'title': f'C.I.P. public TDCC list, {tn}', 'date': RETRIEVED + ' (retrieved)'})
    n_cip_sheets = sum(1 for r in cip_rows if r['sheet'] is not None)
    n_cip_missing = sum(1 for r in cip_rows if r['enPdf'] and r['sheet'] is None)
    notes = (
        'SAAMI: MAP values are read from the Velocity & Pressure Data tables (printed as psi/100 and CUP/100; multiplied by 100 here). '
        'saamiMapPsi = transducer (piezo) MAP; saamiMapCup = copper crusher MAP (CUP, not psi). '
        'Dimensions (bullet/bore/groove diameter, max case length, max COAL, twist) are read from the cartridge & chamber drawings by pairing each inch value with its millimetre twin '
        '(inch*25.4 == mm within rounding); values failing plausibility gates were dropped (null) and the reason is in the record notes. '
        'Bullet diameter = maximum bullet diameter (minus tolerance shown in saami.bulletDiameterVariantsIn). Case length = maximum case length (drawing shows max with minus tolerance). '
        'saamiTwist = inches per turn as printed on the drawing, direction in saamiTwistDirection. '
        'transducerLocation.saamiFromBreechFaceIn is the breech-face-to-transducer-centreline dimension from the SAAMI V&P test barrel drawing. '
        'C.I.P.: Pmax, PK, PE, EE and the pressure-take location M come from the public TDCC list (bobp.cip-bobp.org/en/tdcc_public); '
        'L3 (max case length), L6 (max cartridge length), G1 (projectile diameter), F (barrel field/bore diameter) and Z (groove diameter) come from the EN TDCC sheets (mm). '
        'Where a cartridge has SAAMI dimensions, the inch fields hold the SAAMI value; C.I.P. values that differ beyond rounding '
        f'(>{IN_TOL_DIA} in for diameters, >{IN_TOL_LEN} in for lengths) are listed in conflicts. Where only C.I.P. gives a dimension, the inch field is mm/25.4 and the mm value is kept in <field>Mm. '
        'SAAMI and C.I.P. entries were merged only on an exact (or word-normalised) name match whose dimensions agree; see meta.linking. '
        'trimLengthIn is null throughout: no trim-to length appears in the parsed SAAMI drawings or C.I.P. sheets. primerSize is null throughout: the parsed documents do not assign a primer size per cartridge (SAAMI only shows generic primer/pocket drawings). '
        'cipPmaxBar is C.I.P. maximum (average) pressure Pmax in bar, measured per C.I.P. method (sheet "Method", usually Transducer); it is not directly comparable to SAAMI MAP. '
        f'C.I.P. sheets parsed: {n_cip_sheets}; listed sheets not downloaded: {n_cip_missing}.')
    out = {'meta': {'documents': meta_docs, 'notes': notes, 'retrieved': RETRIEVED,
                    'linking': log['linking'], 'vpTableProblems': log['vpProblems']},
           'cartridges': recs}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    # ---- self-check
    warn = []
    bad = self_check(recs, warn)
    print(f'records: {len(recs)}  (SAAMI-bearing: {sum(1 for r in recs if r["saami"])}, '
          f'C.I.P.-bearing: {sum(1 for r in recs if r["cip"])}, both: {sum(1 for r in recs if r["saami"] and r["cip"])})')
    for fld in ('saamiMapPsi', 'saamiMapCup', 'cipPmaxBar', 'bulletDiameterIn', 'boreDiameterIn', 'grooveDiameterIn',
                'caseLengthMaxIn', 'maxCoalIn', 'saamiTwist', 'transducerLocation'):
        print(f'  {fld}: {sum(1 for r in recs if r[fld] is not None)}')
    print('  records with conflicts:', sum(1 for r in recs if r['conflicts']))
    print('self-check relation warnings (values kept as printed):', warn)
    print('self-check problems:', len(bad))
    for b in bad[:40]:
        print('   ', b)
    rnd = random.Random(int(os.environ.get('SEED', '7')))
    for r in rnd.sample(recs, 5):
        print('-----', r['id'], {k: r[k] for k in ('saamiMapPsi', 'saamiMapCup', 'cipPmaxBar', 'bulletDiameterIn', 'grooveDiameterIn', 'caseLengthMaxIn', 'maxCoalIn')})
        print('     evidence:', r['evidence'][:900])
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
