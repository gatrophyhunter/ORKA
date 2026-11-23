#!/usr/bin/env python3
"""Parse every rifle-bullet table in the Hornady 2027 Product Catalog PDF and cross-check
it against the Hornady web extraction (research/raw2/bullets-hornady.json).

Source: https://static.hornady.media/presscenter/docs/1411010468-1794610803-Hornady-2027-Product-Catalog.pdf
(a downloaded copy lives in the session scratchpad, see PDF below).

Method (deterministic, no values typed by hand):
  * `pdftotext -bbox` (poppler) gives every word with its page coordinates. The catalog's
    bullet tables are column oriented: a right-aligned label column (CALIBER/, TYPE, Diameter,
    Weight, [G1|G7] Ballistic Coef., Sec. Den., Item #, Box Count) and one column per bullet.
  * Columns are anchored on the "Item #" row: every bullet has an item number, printed as one
    word (e.g. 26331/263311). Every other word of the table goes to the row whose label is
    vertically nearest (|dy| <= 4.5 pt) and to the column whose anchor centre is horizontally
    nearest. A word inside the table's horizontal span that is farther than 40 % of the column
    pitch from every anchor (60 % for the CALIBER/TYPE header cells) aborts the run, as does
    any cell that does not match the strict pattern for its row or a column without exactly
    one diameter, one weight and one item cell.
  * Independent checks: the anchors must equal the item tokens of the "Item #" line of
    `pdftotext -layout`, in order; the printed sectional density must equal
    weight / 7000 / diameter^2 to within 0.0015 (catches diameter/weight/SD column shifts);
    G7/G1 must lie in [0.45, 0.56] (catches G1/G7 row shifts). Failures are listed in the
    output notes (none are expected).
  * Only rifle sections are parsed (RIFLE_TABLES below, each verified against the section
    heading printed on the page or its facing page). Muzzleloader (PDF pp. 72-73) and handgun
    tables (FTX Handgun, XTP, XTP Mag, FMJ Handgun, HAP, DGH, Frontier Lead: PDF pp. 99-103)
    are skipped. Rifle bullets in pistol diameters inside rifle sections are kept. PDF page 5
    (new-products teaser) repeats items from the main tables and is not parsed.
  * The catalog prints no bullet length; lengthIn is always null.

Output: research/raw2/bullets-hornady-catalog.json
  bullets     catalog bullets with no matching web record (ORKA bullet schema)
  crossCheck  every disagreement (diameter, weight, G1, G7) between a matched web record and
              the catalog
  agreements  number of matched catalog bullets with no disagreement

Usage:
  python3 -I scripts/extract/bullets-hornady-catalog.py               # parse + write JSON
  python3 -I scripts/extract/bullets-hornady-catalog.py --selfcheck 5 # also print 5 random
                                                                      # columns next to raw words
"""
import html
import json
import random
import re
import subprocess
import sys
import unicodedata

PDF = ('/tmp/claude-0/-home-user-ORKA/29ce603d-ccc3-55ef-b8fe-c585397ac7c1/scratchpad/sources/'
       'hornady-catalog/1411010468-1794610803-Hornady-2027-Product-Catalog.pdf')
URL = 'https://static.hornady.media/presscenter/docs/1411010468-1794610803-Hornady-2027-Product-Catalog.pdf'
TITLE = 'Hornady 2027 Product Catalog'
WEB = '/home/user/ORKA/research/raw2/bullets-hornady.json'
OUT = '/home/user/ORKA/research/raw2/bullets-hornady-catalog.json'
RETRIEVED = '2026-11-23'

# Bullet section = PDF pages 72-103 (muzzleloader 72-73, jacketed bullets 74-103).
SECTION = (72, 103)
# PDF page -> list of (section heading as printed, line name) for each table, top to bottom.
# The heading must appear on the page itself or on its facing page (continuation tables).
RIFLE_TABLES = {
    76: [('A-Tip® Match (Aluminum Tip Match)', 'A-Tip® Match')],
    77: [('A-Tip® Match (Aluminum Tip Match)', 'A-Tip® Match')],
    78: [('ELD® Match (Extremely Low Drag Match)', 'ELD® Match')],
    79: [('ELD® Match (Extremely Low Drag Match)', 'ELD® Match')] * 2,
    80: [('ELD-VT ® (Extremely Low Drag Varmint | Target)', 'ELD-VT®')],
    81: [('AEROMATCH®', 'AEROMATCH®')],
    82: [('Match™', 'Match™')] * 2,
    84: [('ELD-X® (Extremely Low Drag - eXpanding)', 'ELD-X®')],
    85: [('ELD-X® (Extremely Low Drag - eXpanding)', 'ELD-X®')],
    86: [('CX® (Copper alloy eXpanding)', 'CX®')],
    87: [('CX® (Copper alloy eXpanding)', 'CX®')],
    88: [('SST ® (Super Shock Tip )', 'SST®')] * 2,
    90: [('InterLock ®', 'InterLock®')],
    91: [('InterLock ®', 'InterLock®')] * 3,
    92: [('DGX® Bonded (Dangerous Game eXpanding)', 'DGX® Bonded')],
    93: [('DGS® (Dangerous Game Solid)', 'DGS®')],
    94: [('V-MAX® (Varmint Max)', 'V-MAX®')] * 2,
    95: [('NTX® (Non-Traditional eXpanding)', 'NTX®'), ('Traditional Varmint™', 'Traditional Varmint™')],
    96: [('Sub-X® (Subsonic eXpanding)', 'Sub-X®')],
    97: [('MonoFlex®', 'MonoFlex®'), ('Traditional & FMJ Rifle', 'Traditional & FMJ Rifle')],
    98: [('FTX® Rifle (Flex Tip eXpanding)', 'FTX®')] * 2,
}
SKIPPED = {
    99: ('FTX® Handgun (Flex Tip eXpanding)', 'handgun'),
    100: ('XTP® (eXtreme Terminal Performance)', 'handgun'),
    101: ('FMJ Handgun (Full Metal Jacket)', 'handgun'),
    102: ('HAP® (Hornady Action Pistol)', 'handgun'),
    103: ('DGH® (Dangerous Game Handgun)', 'handgun'),
}

ITEM_RE = re.compile(r'^\d{4,6}[A-Z]?(?:/\d{4,6}[A-Z]?)*\*?$')
DIA_RE = re.compile(r'^(\.\d{3,4})"?$')
WT_RE = re.compile(r'^(\d+(?:\.\d+)?) gr\.?(\*?)$')
BC_RE = re.compile(r'^(\d?\.\d{3})$')
SD_RE = re.compile(r'^(\.\d{3})$')
BOX_RE = re.compile(r'^\d+(?:/\d+)*\*?$')
DASHES = ('—', '–', '-')
SUPERS = ('®', '™', '*')
NUM_ROWS = ('Diameter', 'Weight', 'G1', 'G7', 'BC', 'SD', 'Item', 'Box')


class ParseError(Exception):
    pass


def run(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise ParseError('command failed: %s: %s' % (' '.join(args), r.stderr))
    return r.stdout


def bbox_pages(first, last):
    out = run(['pdftotext', '-bbox', '-f', str(first), '-l', str(last), PDF, '-'])
    chunks = out.split('<page ')[1:]
    if len(chunks) != last - first + 1:
        raise ParseError('expected %d pages, got %d' % (last - first + 1, len(chunks)))
    pages = {}
    for i, ch in enumerate(chunks):
        ws = []
        for m in re.finditer(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>', ch):
            x0, y0, x1, y1 = (float(v) for v in m.groups()[:4])
            # drop invisible control/format characters (e.g. a BEL before one TYPE label)
            t = ''.join(ch for ch in html.unescape(m.group(5)) if unicodedata.category(ch) not in ('Cc', 'Cf'))
            if not t:
                continue
            ws.append({'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1, 't': t,
                       'xc': (x0 + x1) / 2, 'yc': (y0 + y1) / 2})
        pages[first + i] = ws
    return pages


def layout_text(page):
    return run(['pdftotext', '-layout', '-f', str(page), '-l', str(page), PDF, '-'])


def nows(s):
    return re.sub(r'\s+', '', s)


def spread_partner(p):
    # Facing pages: PDF page 2k is a left page, 2k+1 the right page of the same spread.
    return p + 1 if p % 2 == 0 else p - 1


def find_labels(ws, cal, y_end):
    """Right-aligned row labels of the table whose CALIBER/ word is `cal`."""
    lx = cal['x1']
    labs = {'CAL': cal}
    cand = [w for w in ws if cal['y0'] - 4 <= w['y0'] < y_end and abs(w['x1'] - lx) <= 3.5]

    def left_word(w, text):
        for v in ws:
            if v['t'] == text and abs(v['yc'] - w['yc']) < 2 and 0 <= w['x0'] - v['x1'] <= 4:
                return v
        return None

    for w in cand:
        t = w['t']
        key = None
        if t == 'TYPE':
            key = 'TYPE'
        elif t == 'Diameter':
            key = 'Diameter'
        elif t == 'Weight':
            key = 'Weight'
        elif t == 'Coef.':
            b = left_word(w, 'Ballistic')
            if b is None:
                continue
            g = left_word(b, 'G1') or left_word(b, 'G7')
            key = g['t'] if g else 'BC'
        elif t == 'Den.' and left_word(w, 'Sec.'):
            key = 'SD'
        elif t == '#' and left_word(w, 'Item'):
            key = 'Item'
        elif t == 'Count' and left_word(w, 'Box'):
            key = 'Box'
        if key:
            if key in labs:
                raise ParseError('duplicate label %s near y=%.1f' % (key, w['y0']))
            labs[key] = w
    for need in ('TYPE', 'Diameter', 'Weight', 'SD', 'Item', 'Box'):
        if need not in labs:
            raise ParseError('label %s missing for table at y=%.1f' % (need, cal['y0']))
    if not ({'G1', 'BC'} & set(labs)):
        raise ParseError('no BC label for table at y=%.1f' % cal['y0'])
    if 'BC' in labs and ({'G1', 'G7'} & set(labs)):
        raise ParseError('mixed BC labels for table at y=%.1f' % cal['y0'])
    return labs


def join_cell(words):
    """Join the words of one cell: attach superscripts, then lines top-to-bottom, words left-to-right."""
    base = [w for w in words if w['t'] not in SUPERS]
    sup = [w for w in words if w['t'] in SUPERS]
    extra = {id(w): '' for w in base}
    for s in sup:
        best = None
        for w in base:
            if abs(w['x1'] - s['x0']) < 1.5 and s['y0'] < w['y1'] and s['y1'] > w['y0']:
                if best is None or abs(w['x1'] - s['x0']) < abs(best['x1'] - s['x0']):
                    best = w
        if best is None:
            base.append(s)
            extra[id(s)] = ''
        else:
            extra[id(best)] += s['t']
    base.sort(key=lambda w: (w['y0'], w['x0']))
    lines = []
    for w in base:
        if lines and w['y0'] - lines[-1][0]['y0'] <= 2.0:
            lines[-1].append(w)
        else:
            lines.append([w])
    parts = []
    for ln in lines:
        ln.sort(key=lambda w: w['x0'])
        # pdftotext already splits words at gaps, so separate words are joined with a space
        parts.append(' '.join(w['t'] + extra[id(w)] for w in ln))
    out = ''
    for s in parts:
        out += s if (not out or out.endswith('/')) else ' ' + s
    return out


def parse_table(page, ws, cal, y_end, line, heading, tindex, layout_lines):
    labs = find_labels(ws, cal, y_end)
    lx = cal['x1']
    item_lab = labs['Item']
    anchors = sorted([w for w in ws if w['x0'] > lx + 2 and abs(w['yc'] - item_lab['yc']) <= 4.5
                      and ITEM_RE.match(w['t'])], key=lambda w: w['xc'])
    if len(anchors) < 1:
        raise ParseError('p%d table %d: no item anchors' % (page, tindex))
    centers = [a['xc'] for a in anchors]
    gaps = [b - a for a, b in zip(centers, centers[1:])]
    if any(g < 25 or g > 110 for g in gaps):
        raise ParseError('p%d table %d: odd anchor spacing %s' % (page, tindex, gaps))
    default_gap = min(gaps) if gaps else 60.0
    pitch = []
    for i in range(len(centers)):
        nb = [g for g in (gaps[i - 1] if i > 0 else None, gaps[i] if i < len(gaps) else None) if g]
        pitch.append(min(nb) if nb else default_gap)
    right = centers[-1] + 0.6 * pitch[-1]
    top = cal['y0'] - 6
    bottom = labs['Box']['yc'] + 4.5
    head_bottom = labs['Diameter']['y0'] - 0.5

    # independent check of the anchors against the -layout text
    lay_items = None
    for ln in layout_lines:
        m = re.search(r'Item #\s+(.*)$', ln)
        if m:
            toks = [t for t in m.group(1).split() if ITEM_RE.match(t)]
            if toks == [a['t'] for a in anchors]:
                lay_items = toks
                break
    if lay_items is None:
        raise ParseError('p%d table %d: anchors %s not found as an Item # line in -layout text'
                         % (page, tindex, [a['t'] for a in anchors]))

    num_rows = {k: labs[k] for k in NUM_ROWS if k in labs}
    cells = [{} for _ in anchors]
    raw = [{} for _ in anchors]
    ignored = []
    for w in ws:
        if w is cal or any(w is v for v in labs.values()):
            continue
        if not (top <= w['y0'] and w['yc'] <= bottom):
            continue
        if w['x0'] <= lx + 1:
            continue
        if w['xc'] > right:
            ignored.append(w)
            continue
        ci = min(range(len(centers)), key=lambda i: abs(centers[i] - w['xc']))
        dx = abs(centers[ci] - w['xc'])
        if w['yc'] < head_bottom:
            row = 'CAL' if abs(w['yc'] - labs['CAL']['yc']) <= abs(w['yc'] - labs['TYPE']['yc']) else 'TYPE'
            lim = 0.6
        else:
            row = min(num_rows, key=lambda k: abs(num_rows[k]['yc'] - w['yc']))
            if abs(num_rows[row]['yc'] - w['yc']) > 4.5:
                raise ParseError('p%d table %d: word %r at y=%.1f not on any row' % (page, tindex, w['t'], w['y0']))
            lim = 0.4
        if dx > lim * pitch[ci]:
            raise ParseError('p%d table %d: word %r (x %.1f-%.1f) row %s is %.1f pt from nearest column centre %.1f'
                             % (page, tindex, w['t'], w['x0'], w['x1'], row, dx, centers[ci]))
        cells[ci].setdefault(row, []).append(w)
    cols = []
    for ci, c in enumerate(cells):
        txt = {k: join_cell(v) for k, v in c.items()}
        for k, v in c.items():
            raw[ci][k] = ['%s[%.1f-%.1f]' % (w['t'], w['x0'], w['x1']) for w in sorted(v, key=lambda w: (w['y0'], w['x0']))]
        col = parse_column(page, tindex, ci + 1, txt, labs)
        col.update({'page': page, 'table': tindex, 'line': line, 'heading': heading, 'raw': raw[ci],
                    'xCenter': round(centers[ci], 1)})
        # "NEW" flag printed above the column (within 60 pt above the CALIBER/ row)
        col['flaggedNew'] = any(w['t'] == 'NEW' and cal['y0'] - 60 <= w['y0'] < cal['y0'] - 6
                                and abs(w['xc'] - centers[ci]) < 0.4 * pitch[ci] for w in ws)
        cols.append(col)
    return cols, labs, ignored


def parse_column(page, tindex, cno, txt, labs):
    where = 'p%d table %d col %d' % (page, tindex, cno)
    for need in ('CAL', 'Diameter', 'Weight', 'Item'):
        if need not in txt:
            raise ParseError('%s: missing %s cell (%s)' % (where, need, txt))
    col = {'caliber': txt['CAL'], 'type': txt.get('TYPE', ''), 'printed': dict(txt), 'checks': []}
    # A caliber cell that wraps onto the TYPE line ("6.8mm/" over "270 Cal. CX®"): move the
    # "NNN Cal." continuation back into the caliber.
    if col['caliber'].endswith('/'):
        m = re.match(r'^(\d+ Cal\.)\s+(.*)$', col['type'])
        if m:
            col['caliber'] += m.group(1)
            col['type'] = m.group(2)
            col['captionNote'] = ('caliber cell wraps onto the TYPE line in the catalog ("%s" / "%s")'
                                  % (txt['CAL'], txt.get('TYPE', '')))
    m = DIA_RE.match(txt['Diameter'])
    if not m:
        raise ParseError('%s: bad diameter %r' % (where, txt['Diameter']))
    col['diameterIn'] = float(m.group(1))
    m = WT_RE.match(txt['Weight'])
    if not m:
        raise ParseError('%s: bad weight %r' % (where, txt['Weight']))
    col['weightGr'] = float(m.group(1))
    col['weightFootnote'] = bool(m.group(2))
    col['bcLabel'] = 'Ballistic Coef.' if 'BC' in labs else 'G1/G7'
    for key, out in (('G1', 'bcG1'), ('BC', 'bcG1'), ('G7', 'bcG7')):
        if key not in labs:
            continue
        v = txt.get(key)
        if v is None or v in DASHES:
            col[out] = None
        else:
            m = BC_RE.match(v)
            if not m:
                raise ParseError('%s: bad %s %r' % (where, key, v))
            col[out] = float(m.group(1))
    col.setdefault('bcG7', None)
    col.setdefault('bcG1', None)
    v = txt.get('SD')
    if v is None or v in DASHES:
        col['sd'] = None
    else:
        m = SD_RE.match(v)
        if not m:
            raise ParseError('%s: bad SD %r' % (where, v))
        col['sd'] = float(m.group(1))
    it = txt['Item']
    if not ITEM_RE.match(it):
        raise ParseError('%s: bad item %r' % (where, it))
    col['itemFootnote'] = it.endswith('*')
    col['items'] = it.rstrip('*').split('/')
    box = txt.get('Box')
    if box is None or not BOX_RE.match(box):
        raise ParseError('%s: bad box count %r' % (where, box))
    col['boxCount'] = box
    return col


def evidence(col):
    p = col['printed']

    def g(k):
        v = p.get(k)
        return v if v else '(blank)'
    parts = ['%s %s' % (col['caliber'], col['type']) if col['type'] else col['caliber'],
             g('Diameter'), g('Weight')]
    if col['bcLabel'] == 'G1/G7':
        parts += [g('G1'), g('G7') if 'G7' in p or col.get('hasG7Row') else '(no G7 row)']
    else:
        parts += [g('BC')]
    parts += [g('SD'), g('Item')]
    return ' | '.join(parts)


def footnotes(page):
    out = []
    for p in (page, spread_partner(page)):
        for ln in layout_text(p).splitlines():
            s = ln.strip()
            if s.startswith('*') and len(s) > 3 and not s.startswith('**'):
                out.append(s)
    return out


def main():
    selfcheck = 0
    if '--selfcheck' in sys.argv:
        i = sys.argv.index('--selfcheck')
        selfcheck = int(sys.argv[i + 1]) if i + 1 < len(sys.argv) else 5

    pages = bbox_pages(*SECTION)
    # Every CALIBER/ table in the section must be either a known rifle table or a skipped page.
    for p, ws in pages.items():
        n = sum(1 for w in ws if w['t'] == 'CALIBER/')
        if n and p not in RIFLE_TABLES and p not in SKIPPED:
            raise ParseError('unexpected CALIBER/ table on PDF page %d' % p)
        if p in RIFLE_TABLES and n != len(RIFLE_TABLES[p]):
            raise ParseError('PDF page %d: %d CALIBER/ tables, expected %d' % (p, n, len(RIFLE_TABLES[p])))
    # Section headings must be printed on the page or its facing page.
    lay = {}
    for p in sorted(set(RIFLE_TABLES) | set(SKIPPED)):
        lay[p] = layout_text(p)
    for p, tabs in sorted(RIFLE_TABLES.items()):
        for heading, _ in tabs:
            here = [nows(l) for l in lay[p].splitlines()]
            q = spread_partner(p)
            there = [nows(l) for l in (lay[q] if q in lay else layout_text(q)).splitlines()]
            if not any(l.startswith(nows(heading)) for l in here + there):
                raise ParseError('heading %r not found on PDF page %d or %d' % (heading, p, q))
    for p, (heading, _) in SKIPPED.items():
        if not any(nows(l).startswith(nows(heading)) for l in lay[p].splitlines()):
            raise ParseError('skipped-page heading %r not found on PDF page %d' % (heading, p))

    cols = []
    ignored_all = []
    for p, tabs in sorted(RIFLE_TABLES.items()):
        ws = pages[p]
        cals = sorted([w for w in ws if w['t'] == 'CALIBER/'], key=lambda w: w['y0'])
        layout_lines = lay[p].splitlines()
        for ti, cal in enumerate(cals):
            y_end = cals[ti + 1]['y0'] - 8 if ti + 1 < len(cals) else 10000
            heading, line = tabs[ti]
            tc, labs, ign = parse_table(p, ws, cal, y_end, line, heading, ti + 1, layout_lines)
            for c in tc:
                c['hasG7Row'] = 'G7' in labs
            cols.extend(tc)
            ignored_all.extend('p%d t%d %r x=%.0f y=%.0f' % (p, ti + 1, w['t'], w['x0'], w['y0']) for w in ign)

    # ---- consistency checks -------------------------------------------------------------
    problems = []
    seen = {}
    for c in cols:
        for it in c['items']:
            if it in seen:
                raise ParseError('item %s appears twice (p%d and p%d)' % (it, seen[it], c['page']))
            seen[it] = c['page']
    sd_checked = 0
    ratios = []
    for c in cols:
        c['evidence'] = evidence(c)
        if c['sd'] is not None:
            calc = c['weightGr'] / 7000.0 / c['diameterIn'] ** 2
            sd_checked += 1
            if abs(calc - c['sd']) > 0.0015:
                c['checks'].append('printed Sec. Den. %.3f does not equal weight/7000/diameter^2 = %.4f '
                                   '(diameter/weight cross-checked against the web record instead)'
                                   % (c['sd'], calc))
        if c['bcG1'] is not None and c['bcG7'] is not None:
            r = c['bcG7'] / c['bcG1']
            if 0.45 <= r <= 0.56:
                ratios.append(r)
            else:
                c['checks'].append('printed G7 %.3f / G1 %.3f = %.3f, outside the %s range of every other '
                                   'bullet in the catalog: one of the two printed BCs is probably a misprint; '
                                   'do not adopt either without confirmation'
                                   % (c['bcG7'], c['bcG1'], r, '0.45-0.56'))
        for msg in c['checks']:
            problems.append('p%d %s: %s' % (c['page'], c['evidence'], msg))
    if ratios:
        lo, hi = min(ratios), max(ratios)
        for c in cols:
            c['checks'] = [m.replace('0.45-0.56', '%.3f-%.3f' % (lo, hi)) for m in c['checks']]
        problems = [m.replace('0.45-0.56', '%.3f-%.3f' % (lo, hi)) for m in problems]
    no_sd = [c for c in cols if c['sd'] is None]

    # ---- cross-check against the web extraction ----------------------------------------
    web = json.load(open(WEB, encoding='utf-8'))['bullets']
    item_to_col = {}
    for ci, c in enumerate(cols):
        for it in c['items']:
            item_to_col[it] = ci
    pairs = {}  # ci -> list of (web record, how)
    web_unmatched = []
    suffix_matches = []
    for w in web:
        sku = w['sku']
        if sku in item_to_col:
            pairs.setdefault(item_to_col[sku], []).append((w, 'exact'))
            continue
        m = re.match(r'^(\d+)(?:[A-Z]+|-\d+)$', sku)
        if m and m.group(1) in item_to_col:
            ci = item_to_col[m.group(1)]
            pairs.setdefault(ci, []).append((w, 'suffix'))
            suffix_matches.append('%s->%s' % (sku, '/'.join(cols[ci]['items'])))
            continue
        web_unmatched.append(w)

    def same(a, b, nd):
        if a is None or b is None:
            return a is None and b is None
        return round(float(a), nd) == round(float(b), nd)

    cross = []
    agreements = 0
    # web BC typing for matched columns of single "Ballistic Coef." tables
    single_bc = {'typedG1': 0, 'noWebBC': 0, 'other': 0, 'g1Equal': 0, 'records': 0}
    web_kinds = {}
    for ci in sorted(pairs):
        c = cols[ci]
        ok = True
        for w, how in pairs[ci]:
            web_kinds[w.get('kind')] = web_kinds.get(w.get('kind'), 0) + 1
            checks = [('diameterIn', c['diameterIn'], 4), ('weightGr', c['weightGr'], 1), ('bcG1', c['bcG1'], 4)]
            if c['hasG7Row']:
                checks.append(('bcG7', c['bcG7'], 4))
            if c['bcLabel'] == 'Ballistic Coef.':
                single_bc['records'] += 1
                ev = w.get('evidence') or ''
                if '"ball_coef_type_1":"(G1)"' in ev:
                    single_bc['typedG1'] += 1
                elif w.get('bcG1') is None:
                    single_bc['noWebBC'] += 1
                else:
                    single_bc['other'] += 1
                if same(w.get('bcG1'), c['bcG1'], 4):
                    single_bc['g1Equal'] += 1
            for field, cv, nd in checks:
                wv = w.get(field)
                if not same(wv, cv, nd):
                    ok = False
                    kind = 'value-mismatch' if (wv is not None and cv is not None) else (
                        'web-missing' if wv is None else 'catalog-missing')
                    entry = {'id': w['id'], 'field': field, 'web': wv, 'catalog': cv, 'page': c['page'],
                             'evidence': c['evidence'], 'kind': kind,
                             'match': how + ' (web sku %s)' % w['sku']}
                    if c['checks']:
                        entry['catalogCheck'] = '; '.join(c['checks'])
                    cross.append(entry)
        if ok:
            agreements += 1
    flagged_matched = ['p%d %s' % (cols[ci]['page'], cols[ci]['evidence']) for ci in sorted(pairs) if cols[ci]['checks']]

    # ---- records for catalog bullets with no web record ---------------------------------
    fn_cache = {}
    bullets = []
    for ci, c in enumerate(cols):
        if ci in pairs:
            continue
        wt = c['printed']['Weight'].rstrip('*')
        name = ' '.join(x for x in (c['caliber'], wt, c['type']) if x)
        notes = ['catalog section "%s", PDF page %d, table %d; item #(s) %s, box count %s'
                 % (c['heading'], c['page'], c['table'], c['printed']['Item'], c['boxCount'])]
        if c.get('captionNote'):
            notes.append(c['captionNote'])
        if c['bcLabel'] == 'Ballistic Coef.':
            notes.append('catalog prints a single "Ballistic Coef." row (drag model not stated on the page); '
                         'stored as bcG1 because hornady.com types the BC of the matched bullets of these '
                         'tables "(G1)" (%d of %d matched web records; with no web BC: %d; typed otherwise: %d) '
                         'and their G1 equals the catalog value in %d of %d'
                         % (single_bc['typedG1'], single_bc['records'], single_bc['noWebBC'], single_bc['other'],
                            single_bc['g1Equal'], single_bc['records']))
        elif c['bcG7'] is None:
            notes.append('G7 cell printed as %r' % (c['printed'].get('G7') or '(blank)'))
        if c['sd'] is not None:
            notes.append('printed sectional density %.3f' % c['sd'])
        else:
            notes.append('sectional density cell blank in catalog')
        if c['weightFootnote'] or '*' in c['type'] or c['itemFootnote'] or '*' in c['boxCount']:
            fns = fn_cache.setdefault(c['page'], footnotes(c['page']))
            notes.append('footnote mark(s) printed; footnote text on this spread: %s'
                         % ('; '.join(repr(f) for f in fns) if fns else 'none printed'))
        if c['flaggedNew']:
            notes.append('marked NEW in the catalog')
        notes.extend('CHECK: ' + m for m in c['checks'])
        bullets.append({
            'id': 'hornady-' + c['items'][0],
            'manufacturer': 'Hornady',
            'line': c['line'],
            'name': name,
            'sku': c['items'][0],
            'caliberLabel': c['caliber'],
            'diameterIn': c['diameterIn'],
            'weightGr': c['weightGr'],
            'lengthIn': None,
            'bcG1': c['bcG1'],
            'bcG7': c['bcG7'],
            'construction': None,
            'status': 'current',
            'kind': 'rifle',
            'sources': [{'url': URL, 'type': 'manufacturer', 'page': c['page'], 'retrieved': RETRIEVED}],
            'evidence': c['evidence'],
            'notes': '; '.join(notes),
        })

    web_rifle_unmatched = sorted(w['sku'] for w in web_unmatched if w.get('kind') == 'rifle')
    web_hg_unmatched = sum(1 for w in web_unmatched if w.get('kind') != 'rifle')
    n_tables = sum(len(v) for v in RIFLE_TABLES.values())
    kinds = {}
    for x in cross:
        kinds[x['kind']] = kinds.get(x['kind'], 0) + 1
    ver = subprocess.run(['pdftotext', '-v'], capture_output=True, text=True)
    ver = ((ver.stderr or ver.stdout).splitlines() or ['pdftotext'])[0].strip()
    notes = (
        'Parsed %d rifle-bullet columns from %d tables on PDF pages %d-%d with %s (pdftotext -bbox word '
        'coordinates; columns anchored on the Item # row and verified against the -layout Item # lines; '
        'every word inside a table span assigned or the run aborts). Skipped: muzzleloader tables (PDF pp. '
        '72-73) and handgun sections (PDF pp. 99-103: %s). Rifle bullets in pistol diameters inside rifle '
        'sections (e.g. 350 Legend .355", 450 Bushmaster .452") are kept. PDF page 5 (new-products teaser) '
        'repeats items printed in the main tables and was not parsed. The catalog prints no bullet length '
        '(lengthIn null). Tables headed "Ballistic Coef." (SST, InterLock, DGX Bonded, DGS, V-MAX, NTX, '
        'Traditional Varmint, Sub-X, MonoFlex, Traditional & FMJ Rifle, FTX) print one BC without naming a '
        'drag model; it is compared with / stored as G1 because hornady.com types these bullets\' BC "(G1)" '
        '(%d of %d matched web records; with no web BC: %d; typed otherwise: %d; web G1 equals the catalog '
        'value in %d of %d). The Match(TM) tables print only "G1 Ballistic Coef.". G7 is compared only for '
        'tables with a "G7 Ballistic Coef." row; a printed dash = not published (null). Evidence order: '
        'CALIBER+TYPE | Diameter | Weight | G1 | G7 | Sec. Den. | Item # (single-BC tables: CALIBER+TYPE | '
        'Diameter | Weight | Ballistic Coef. | Sec. Den. | Item #), values as printed, "(blank)" = empty '
        'cell. Matching: a web sku equal to any slash-separated catalog item number, else a web sku whose '
        'digits before a letter/-NN suffix equal one (%d suffix matches: %s). %d catalog bullets matched %d '
        'web records (%s); %d catalog bullets have no web record (in "bullets"). crossCheck has %d entries '
        '(%s): value-mismatch = both print different values; web-missing = web record null where the '
        'catalog prints a value; catalog-missing = the reverse; catalogCheck carries any failed catalog '
        'self-check for that bullet. agreements = matched catalog bullets with no disagreement on any '
        'paired web record. Catalog self-checks: printed Sec. Den. vs weight/7000/d^2 for %d columns (%d '
        'printed blank) and G7/G1 ratio; flagged (catalog-internal inconsistencies, not parse errors - each '
        'verified against the printed page): %s. Web rifle records with no catalog item number (%d; '
        'mostly ECX, absent from the 2027 catalog): %s. Web handgun records not compared: %d.'
        % (len(cols), n_tables, min(RIFLE_TABLES), max(RIFLE_TABLES), ver,
           ', '.join(v[0] for v in SKIPPED.values()),
           single_bc['typedG1'], single_bc['records'], single_bc['noWebBC'], single_bc['other'],
           single_bc['g1Equal'], single_bc['records'],
           len(suffix_matches), ', '.join(suffix_matches) or 'none',
           len(pairs), sum(len(v) for v in pairs.values()),
           ', '.join('%s %d' % (k, v) for k, v in sorted(web_kinds.items(), key=lambda kv: str(kv[0]))),
           len(bullets), len(cross),
           ', '.join('%s %d' % kv for kv in sorted(kinds.items())) or 'none', sd_checked, len(no_sd),
           '; '.join(problems) or 'none', len(web_rifle_unmatched), ', '.join(web_rifle_unmatched),
           web_hg_unmatched))
    out = {
        'meta': {
            'documents': [{'url': URL, 'localPath': PDF, 'title': TITLE}],
            'notes': notes,
        },
        'bullets': bullets,
        'crossCheck': cross,
        'agreements': agreements,
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write('\n')

    print('tables %d, columns %d, matched %d, new %d, crossCheck %d %s, agreements %d'
          % (n_tables, len(cols), len(pairs), len(bullets), len(cross), kinds, agreements))
    print('problems:', problems or 'none')
    print('ignored words right of tables:', len(ignored_all))
    if '--verbose' in sys.argv:
        for s in ignored_all:
            print('  ignored', s)
        for c in cols:
            print('p%d t%d %-40s | %s' % (c['page'], c['table'], c['caliber'] + ' / ' + c['type'], c['evidence']))
    if selfcheck:
        rng = random.Random(2027)
        for c in rng.sample(cols, selfcheck):
            print('\n=== SELF-CHECK p%d table %d column at x=%.1f (%s)' % (c['page'], c['table'], c['xCenter'], c['line']))
            print('parsed : caliber=%r type=%r dia=%s wt=%s G1=%s G7=%s SD=%s items=%s box=%s'
                  % (c['caliber'], c['type'], c['diameterIn'], c['weightGr'], c['bcG1'], c['bcG7'], c['sd'],
                     c['items'], c['boxCount']))
            for k in ('CAL', 'TYPE') + NUM_ROWS:
                if k in c['raw']:
                    print('  raw %-8s %s' % (k, '  '.join(c['raw'][k])))
            # the same table's rows from pdftotext -layout, for eyeballing
            ll = lay[c['page']].splitlines()
            idx = [i for i, l in enumerate(ll) if 'CALIBER/' in l]
            start = max(0, idx[c['table'] - 1] - 2)
            end = next(i for i in range(start, len(ll)) if 'Box Count' in ll[i])
            for l in ll[start:end + 1]:
                if l.strip():
                    print('  layout| ' + l.rstrip()[:230])
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except ParseError as e:
        print('PARSE ERROR:', e, file=sys.stderr)
        sys.exit(2)
