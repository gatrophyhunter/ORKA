#!/usr/bin/env python3
"""Extract Hornady rifle and handgun bullet specifications from www.hornady.com.

Sources (public pages, fetched with plain curl, default user agent):
  * https://www.hornady.com/sitemap.xml  -> list of bullet product pages under
    /bullets/rifle/<slug> and /bullets/handgun/<slug>.
  * Each product page. Its server-rendered HTML contains the visible title, the
    "Item #NNNN | NN/Box" line and an inline <script> "var item = {...}" object that
    the page itself uses to render its specification table (sku, weight, caliber
    diameter, sectional density, G1/G7 BC, twist, discontinued flag, features text).
    We parse that inline object from the saved HTML (no private API is called).
  * https://www.hornady.com/bc - Hornady's published Mach 2.25 / 2.0 / 1.75 G1/G7 BC
    table for ELD Match, ELD-X, A-Tip Match and ELD-VT bullets.
robots.txt (https://www.hornady.com/robots.txt) disallows only /assets/components/,
/assets/libraries/, /c/, /gears/, /js/, /cron; no Crawl-delay. We sleep 1.5 s between
requests.

The annual catalog PDFs are on static.hornady.media, which is not reachable from this
container (proxy-blocked), so they are not used.

Usage:
  python3 -I bullets-hornady.py --download   # fetch any missing pages (cached)
  python3 -I bullets-hornady.py              # parse cached pages and write JSON
  python3 -I bullets-hornady.py --check      # self-check the written JSON
"""
import html as htmlmod
import json
import os
import random
import re
import subprocess
import sys
import time

KEY = 'bullets-hornady'
SRC = '/tmp/claude-0/-home-user-ORKA/29ce603d-ccc3-55ef-b8fe-c585397ac7c1/scratchpad/sources/' + KEY
OUT = '/home/user/ORKA/research/raw2/' + KEY + '.json'
RETRIEVED = '2026-11-23'
BASE = 'https://www.hornady.com'
SITEMAP_URL = BASE + '/sitemap.xml'
BC_URL = BASE + '/bc'
DELAY = 1.5

_last = [0.0]


def fetch(url, local):
    if os.path.exists(local) and os.path.getsize(local) > 0:
        return True
    wait = _last[0] + DELAY - time.time()
    if wait > 0:
        time.sleep(wait)
    os.makedirs(os.path.dirname(local), exist_ok=True)
    tmp = local + '.part'
    r = subprocess.run(['curl', '-sS', '-L', '-m', '120', '-o', tmp, '-w', '%{http_code}', url],
                       capture_output=True, text=True)
    _last[0] = time.time()
    code = r.stdout.strip()
    if code == '200' and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
        os.replace(tmp, local)
        return True
    if os.path.exists(tmp):
        os.remove(tmp)
    print(f'FETCH FAIL {code} {url} {r.stderr.strip()}', file=sys.stderr)
    return False


def product_urls():
    sm = open(os.path.join(SRC, 'sitemap.xml'), encoding='utf-8').read()
    urls = re.findall(r'<loc>([^<]+)</loc>', sm)
    out = []
    for u in urls:
        m = re.match(r'^https://www\.hornady\.com/bullets/(rifle|handgun)/([^/#?]+)$', u)
        if m:
            out.append((m.group(1), m.group(2), u))
    seen = set()
    res = []
    for t in out:
        if t[2] not in seen:
            seen.add(t[2])
            res.append(t)
    return res


def local_page(kind, slug):
    safe = re.sub(r'[^A-Za-z0-9._()-]+', '_', slug)
    return os.path.join(SRC, 'pages', kind, safe + '.html')


def download():
    fetch(SITEMAP_URL, os.path.join(SRC, 'sitemap.xml'))
    fetch(BC_URL, os.path.join(SRC, 'bc.html'))
    urls = product_urls()
    print(f'{len(urls)} product URLs in sitemap')
    for i, (kind, slug, u) in enumerate(urls):
        fetch(u, local_page(kind, slug))
        if i % 25 == 0:
            print(f'  {i}/{len(urls)}', flush=True)


# ---------------------------------------------------------------- parsing helpers

def collapse(s):
    return re.sub(r'\s+', ' ', s).strip()


def strip_tags(s):
    s = re.sub(r'<sup>.*?</sup>', lambda m: re.sub(r'<[^>]+>', '', m.group(0)), s, flags=re.S)
    s = re.sub(r'<[^>]+>', ' ', s)
    return collapse(htmlmod.unescape(s))


def extract_item_raw(h):
    """Return the raw text of the inline 'var item = {...};' object (balanced braces)."""
    i = h.find('var item = {')
    if i < 0:
        return None
    j = h.index('{', i)
    depth = 0
    in_str = False
    esc = False
    for k in range(j, len(h)):
        c = h[k]
        if in_str:
            if esc:
                esc = False
            elif c == '\\':
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return h[j:k + 1]
    return None


def raw_field(raw, key):
    """Exact raw text of a top-level '"key":value' pair inside the item object."""
    m = re.search(r'"' + re.escape(key) + r'":("(?:[^"\\]|\\.)*"|-?[0-9.]+|null|true|false)', raw)
    return m.group(0) if m else None


def num(s):
    if s is None:
        return None
    s = str(s).strip()
    if s in ('', '-', '0', '0.0', '.0'):
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return v if v != 0 else None


# Profile abbreviations as printed in Hornady product names (kept verbatim; no expansion).
PROFILE_TOKENS = ['BTHP', 'SPBT', 'SPSP', 'SP-RP', 'HP/XTP', 'FMJ-BT', 'FMJ-RN', 'FMJ-FP', 'FMJ BT',
                  'FMJ RN', 'FMJ FP', 'FMJ-FN', 'FMJ', 'BT', 'HP', 'SP', 'RN', 'FP', 'FN', 'SWC', 'HBWC',
                  'LRN', 'DEWC', 'RNSP', 'TSX', 'JFP', 'JHP', 'ENC', 'FPJ']


def profile_from_name(name):
    toks = re.findall(r'[A-Za-z][A-Za-z/-]*', name)
    hits = []
    for t in toks:
        tu = t.strip('-/')
        if tu in PROFILE_TOKENS and tu not in hits:
            hits.append(tu)
    return ' '.join(hits) if hits else None


def visible_title_and_item_line(h):
    """The H1/H2 product title and the 'Item #NNNN | NN/Box' line from the visible HTML."""
    body = h[h.find('<body'):]
    body = re.sub(r'<script.*?</script>', ' ', body, flags=re.S)
    body = re.sub(r'<style.*?</style>', ' ', body, flags=re.S)
    m = re.search(r'Item\s*#\s*[^<|]*\|[^<]*', body)
    item_line = collapse(htmlmod.unescape(re.sub(r'<[^>]+>', ' ', m.group(0)))) if m else None
    return item_line


# ---------------------------------------------------------------- /bc page

def parse_bc_page():
    path = os.path.join(SRC, 'bc.html')
    if not os.path.exists(path):
        return []
    h = open(path, encoding='utf-8', errors='replace').read()
    rows = []
    for tbl in re.finditer(r'<table.*?</table>', h, flags=re.S):
        t = tbl.group(0)
        # table heading: nearest preceding "Expanded BC Values for ..." text
        before = h[:tbl.start()]
        hm = list(re.finditer(r'Expanded BC Values for(.*?)</', before, flags=re.S))
        heading = None
        if hm:
            seg = before[hm[-1].start():]
            seg = re.sub(r'<[^>]+>', ' ', seg)
            heading = collapse(htmlmod.unescape(seg))
            heading = re.split(r'Mach 2\.25', heading)[0].strip()
        for tr in re.findall(r'<tr.*?</tr>', t, flags=re.S):
            cells = [strip_tags(c) for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, flags=re.S)]
            line = collapse(' '.join(cells))
            vals = re.findall(r'(\d?\.\d+)\s*(G1|G7)', line)
            if len(vals) != 6:
                continue
            label = collapse(re.split(r'\d?\.\d+\s*G[17]', line)[0])
            rows.append({'heading': heading, 'label': label, 'cells': cells, 'text': line,
                         'values': vals})
    return rows


def bc_row_key(label):
    """(caliber token, weight, twist) from a /bc row label such as
    '30 Cal 225 gr. ELD Match 1 in 7" Twist', '6mm 90gr ELD-X' or '.25 cal 134 ELD-Match'."""
    w = re.search(r'(\d+)\s*gr', label) or re.search(r'cal\s+(\d+)\s+ELD', label, flags=re.I)
    weight = int(w.group(1)) if w else None
    cal = label.split()[0].lower().lstrip('.')
    tw = re.search(r'1 in ([\d.]+)"?\s*Twist', label)
    return cal, weight, (tw.group(0) if tw else None)


def bc_line_key(heading, label):
    hl = (heading or '').lower() + ' ' + label.lower()
    if 'eld-vt' in hl or 'eld‑vt' in hl:
        return 'eld-vt'
    if 'a-tip' in hl or 'a‑tip' in hl:
        return 'a-tip'
    if 'eld-x' in label.lower() or ('eld-x' in (heading or '').lower() and 'match' not in label.lower()):
        return 'eld-x'
    if 'match' in hl:
        return 'eld match'
    return None


# ---------------------------------------------------------------- construction / tip wording

def _sent(pat, text):
    m = re.search(r'[^.!?<>]*(?:' + pat + r')[^.!?<>]*[.!?]?', text, flags=re.I)
    return collapse(m.group(0)) if m else None


def find_construction(feature_text, name, line):
    """Return (construction, evidence) only when the page's own wording says so.
    Rules, in order: 'FMJ' printed in the product name or line; monolithic copper/brass
    wording; 'bonded' wording (not negated); lead bullets (line 'Lead Bullets' or a lead
    profile abbreviation in the name, plus 'lead' wording); InterLock ring or a jacket +
    (swaged/lead) core description -> cup-and-core."""
    low_name = (name + ' ' + (line or '')).lower()
    if re.search(r'\bfmj\b', low_name):
        return 'FMJ', name
    for pat, val in (
        (r'\bmonolithic\b[^.!?<>]*\bbrass\b|\bbrass\b[^.!?<>]*\bmonolithic\b|\bsolid brass\b', 'monolithic-brass'),
        (r'\bmonolithic\b[^.!?<>]*\bcopper\b|\bcopper\b[^.!?<>]*\bmonolithic\b|\bsolid copper\b|'
         r'\b100% copper\b|\ball[- ]copper\b', 'monolithic-copper'),
    ):
        ev = _sent(pat, feature_text)
        if ev:
            return val, ev
    ev = _sent(r'\bbonded\b|\bbonding\b', feature_text)
    if ev and not re.search(r'\bnot bonded\b|\bnon-?bonded\b|\bunbonded\b', ev, flags=re.I):
        return 'bonded', ev
    if re.search(r'\b(lrn|swc|hbwc|dewc|lead)\b', low_name):
        ev = _sent(r'\blead (?:pistol |rifle )?bullets?\b|\bcold-swaged\b', feature_text)
        if ev:
            return 'lead', ev
    ev = _sent(r'\bInterLock\b', feature_text)
    if ev:
        return 'cup-and-core', ev
    if re.search(r'\bjacket', feature_text, flags=re.I):
        ev = _sent(r'\b(?:swaged|lead) cores?\b|\bcores?\b[^.!?<>]*\bswaged\b', feature_text)
        if ev:
            ev2 = _sent(r'\bjacket', feature_text)
            return 'cup-and-core', ev + ' / ' + ev2
    return None, None


TIP_PATTERNS = [
    (r'Heat Shield', 'Heat Shield polymer tip'),
    (r'\bA-?Tip\b|aluminum tip', 'aluminum tip'),
    (r'Flex Tip|FlexTip', 'Flex Tip (elastomer)'),
    (r'polymer tip|polymer-tip|polymer tipped', 'polymer tip'),
]


def find_tip(feature_text, name, line):
    for pat, val in TIP_PATTERNS:
        for src in (name + ' ' + (line or ''), feature_text):
            m = re.search(r'[^.<>]*(?:' + pat + r')[^.<>]*', src, flags=re.I)
            if m:
                return val, collapse(m.group(0))
    return None, None


# ---------------------------------------------------------------- main parse

def parse_page(kind, slug, url):
    path = local_page(kind, slug)
    h = open(path, encoding='utf-8', errors='replace').read()
    raw = extract_item_raw(h)
    if raw is None:
        return None, f'no inline item object: {url}'
    d = json.loads(raw)
    title = strip_tags(d.get('title') or '')
    line = strip_tags(d.get('linktitle') or '') or None
    sku = (d.get('sku') or '').strip() or None
    item_line = visible_title_and_item_line(h)
    feature_text = strip_tags((d.get('intro') or '') + ' ' + (d.get('content') or ''))

    # diameter: the inline "caliberdiameter" string, cross-checked against the title.
    diam = num(d.get('caliberdiameter'))
    weight = num(d.get('weight'))
    g1 = g7 = None
    bc_issue = []
    for vkey, tkey in (('ball_coef_1', 'ball_coef_type_1'), ('ball_coef_2_f', 'ball_coef_type_2')):
        v = num(d.get(vkey))
        t = (d.get(tkey) or '').strip()
        if v is None:
            continue
        if t == '(G1)':
            g1 = v
        elif t == '(G7)':
            g7 = v
        else:
            bc_issue.append(f'BC {v} has unrecognised type label {t!r}')
    twist = (d.get('twist') or '').strip()
    rec_twist = (d.get('rec_twist') or '').strip()
    twist_val = twist if twist and twist not in ('-', '0') else None
    rec_val = rec_twist if rec_twist and rec_twist not in ('-', '0') else None
    keys = ['title', 'sku', 'caliber', 'caliberdiameter', 'weight', 'sectional_density_1',
            'ball_coef_1', 'ball_coef_type_1', 'ball_coef_2_f', 'ball_coef_type_2', 'twist',
            'rec_twist', 'discontinued', 'box_count']
    ev_parts = []
    if item_line:
        ev_parts.append(item_line)
    ev_parts += [raw_field(raw, k) for k in keys if raw_field(raw, k)]
    construction, c_ev = find_construction(feature_text, title, line)
    tip, t_ev = find_tip(feature_text, title, line)
    notes = []
    if bc_issue:
        notes += bc_issue
    # title cross-checks
    if diam is not None and ('%.3f' % diam).lstrip('0') not in title.replace(' ', ''):
        notes.append(f'diameter {diam} from caliberdiameter not found in title')
    if weight is not None and not re.search(r'\b%d\s*gr' % int(weight), title):
        notes.append(f'weight {weight} not found in title as "<n> gr"')
    if rec_val and twist_val and rec_val != twist_val:
        notes.append(f'page has two twist fields: twist={twist_val!r}, rec_twist={rec_val!r}')
    if twist_val or rec_val:
        notes.append('recommendedTwist is the product page specification field "twist"'
                     ' (rec_twist used if twist empty); Hornady prints it like 1-12" (1 turn in 12 in).')
    if c_ev:
        notes.append(f'construction from page wording: "{c_ev}"')
    if t_ev:
        notes.append(f'tip from page wording: "{t_ev}"')
    sd = num(d.get('sectional_density_1') or d.get('sectional_density'))
    rec = {
        'id': f'hornady-{sku}' if sku else f'hornady-{slug}',
        'manufacturer': 'Hornady',
        'line': line,
        'name': title,
        'sku': sku,
        'caliberLabel': (d.get('caliber') or '').strip() or None,
        'diameterIn': diam,
        'weightGr': weight,
        'lengthIn': None,
        'boatTailLengthIn': None,
        'baseToOgiveIn': None,
        'bcG1': g1,
        'bcG7': g7,
        'bcNotes': None,
        'profile': profile_from_name(title),
        'tip': tip,
        'construction': construction,
        'recommendedTwist': twist_val or rec_val,
        'status': 'discontinued' if d.get('discontinued') else 'current',
        'kind': kind,
        'sectionalDensity': sd,
        'boxCount': d.get('box_count') or None,
        'sources': [{'url': url, 'type': 'manufacturer', 'page': None, 'retrieved': RETRIEVED}],
        'evidence': collapse(' | '.join(ev_parts)),
        'notes': '; '.join(notes) if notes else None,
    }
    return rec, None


def record_line_key(r):
    ln = (r['line'] or '').lower().replace('\u2011', '-')
    nm = r['name'].lower().replace('\u2011', '-')
    if 'eld-vt' in ln or 'eld-vt' in nm:
        return 'eld-vt'
    if 'a-tip' in ln:
        return 'a-tip'
    if 'eld-x' in ln:
        return 'eld-x'
    if 'eld' in ln and 'match' in ln:
        return 'eld match'
    return None


def attach_bc_table(records, bc_rows):
    """Attach Mach-banded BCs from /bc to matching records.  A /bc bullet can have more than
    one row (BC differs by barrel twist); all rows go to the one record.  A conflict is logged
    when the product-page BC equals none of the /bc Mach 2.25 values for that bullet."""
    groups = {}
    for row in bc_rows:
        cal, weight, twist = bc_row_key(row['label'])
        lk = bc_line_key(row['heading'], row['label'])
        row['twist'] = twist
        groups.setdefault((lk, cal, weight), []).append(row)
    unmatched = []
    for key, rows in groups.items():
        lk, cal, weight = key
        cands = [r for r in records if record_line_key(r) == lk and r['weightGr'] == weight
                 and r['name'].split()[0].lower().lstrip('.') == cal and r['kind'] == 'rifle']
        if len(cands) > 1:
            # prefer the current (non-discontinued) product if exactly one is current
            cur = [c for c in cands if c['status'] == 'current']
            if len(cur) == 1:
                cands = cur
        if len(cands) != 1:
            unmatched.append({'bcRows': [r['label'] for r in rows], 'candidates': [c['id'] for c in cands]})
            continue
        r = cands[0]
        parts = []
        r['bcMach'] = []
        for row in rows:
            v = row['values']
            tw = f' [{row["twist"]}]' if row['twist'] else ''
            parts.append(f'Mach 2.25 (2512 fps): G1 {v[0][0]}, G7 {v[1][0]}; Mach 2.0 (2232 fps): G1 {v[2][0]}, '
                         f'G7 {v[3][0]}; Mach 1.75 (1953 fps): G1 {v[4][0]}, G7 {v[5][0]}{tw}')
            for mach, fps, a, b in ((2.25, 2512, 0, 1), (2.0, 2232, 2, 3), (1.75, 1953, 4, 5)):
                r['bcMach'].append({'mach': mach, 'fpsIcao': fps, 'g1': float(v[a][0]), 'g7': float(v[b][0]),
                                    'twistCondition': row['twist']})
            r['evidence'] += ' || ' + row['text']
        r['bcNotes'] = ('Hornady /bc table (' + (rows[0]['heading'] or '') + '), ICAO standard atmosphere: ' +
                        ' / '.join(parts) + '.')
        r['sources'].append({'url': BC_URL, 'type': 'manufacturer', 'page': None, 'retrieved': RETRIEVED})
        for fld, idx in (('bcG1', 0), ('bcG7', 1)):
            vals = [float(row['values'][idx][0]) for row in rows]
            if r[fld] is None:
                note = f'{fld} absent on product page; /bc Mach 2.25 value(s): {vals}'
                r['notes'] = (r['notes'] + '; ' if r['notes'] else '') + note
            elif not any(abs(r[fld] - x) < 1e-9 for x in vals):
                r.setdefault('conflicts', []).append({'field': fld, 'values': [
                    {'value': r[fld], 'source': r['sources'][0]['url']}] + [
                    {'value': x, 'source': BC_URL + ' (Mach 2.25 column' +
                     (', ' + row['twist'] if row['twist'] else '') + ')'} for x, row in zip(vals, rows)]})
    return unmatched


def build():
    urls = product_urls()
    records, errors = [], []
    for kind, slug, u in urls:
        p = local_page(kind, slug)
        if not os.path.exists(p):
            errors.append(f'not downloaded: {u}')
            continue
        rec, err = parse_page(kind, slug, u)
        if err:
            errors.append(err)
            continue
        records.append(rec)
    # duplicate SKUs (same product listed under two URLs): keep first, record the other URL
    by_id = {}
    final = []
    for r in records:
        if r['id'] in by_id:
            o = by_id[r['id']]
            same = all(o[k] == r[k] for k in ('weightGr', 'diameterIn', 'bcG1', 'bcG7', 'name'))
            o['sources'].append(r['sources'][0])
            if not same:
                o['notes'] = (o['notes'] + '; ' if o['notes'] else '') + \
                    f'second page {r["sources"][0]["url"]} lists same sku with different data: ' + r['evidence']
            continue
        by_id[r['id']] = r
        final.append(r)
    bc_rows = parse_bc_page()
    unmatched = attach_bc_table(final, bc_rows)
    for r in final:
        r.setdefault('conflicts', [])
        if not r['conflicts']:
            r['conflicts'] = []
    final.sort(key=lambda r: (r['kind'], r['diameterIn'] or 0, r['weightGr'] or 0, r['sku'] or ''))
    doc = {
        'meta': {
            'documents': [
                {'url': SITEMAP_URL, 'localPath': os.path.join(SRC, 'sitemap.xml'),
                 'title': 'Hornady sitemap (used to enumerate bullet product pages)', 'date': RETRIEVED},
                {'url': BC_URL, 'localPath': os.path.join(SRC, 'bc.html'),
                 'title': 'Hornady - A-Tip, ELD Match, ELD-X and ELD-VT Ballistic Coefficient Values',
                 'date': RETRIEVED},
                {'url': BASE + '/bullets/{rifle|handgun}/<slug>', 'localPath': os.path.join(SRC, 'pages'),
                 'title': f'{len(final)} Hornady bullet product pages (one per record; see record sources)',
                 'date': RETRIEVED},
            ],
            'notes': (
                'Values come from the inline "var item = {...}" object that each www.hornady.com product page '
                'embeds in its own HTML to render its specification table; evidence holds the verbatim raw '
                '"key":value text of that object plus the visible "Item # | /Box" line. bcG1/bcG7 are the '
                'product-page BCs (ball_coef_1 typed "(G1)", ball_coef_2_f typed "(G7)"). For ELD Match, ELD-X, '
                'A-Tip Match and ELD-VT, Hornady states its published BCs are Mach 2.25 (2512 fps, ICAO) values; '
                'Mach 2.25/2.0/1.75 values from https://www.hornady.com/bc are in bcNotes/bcMach. Hornady does not '
                'publish bullet length, boat-tail length or base-to-ogive on these pages, so those are null. '
                'construction/tip are set only when the page wording supports them (quoted in notes); otherwise '
                'null. profile = profile abbreviations printed in the product name, verbatim. The 2027 product '
                'catalog PDF (static.hornady.media) was not reachable (proxy-blocked host). '
                'sectionalDensity and boxCount are extra fields taken from the same page. '
                f'Unmatched /bc rows: {unmatched}. Parse errors: {errors}'),
        },
        'bullets': final,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
    print(f'wrote {len(final)} records to {OUT}; errors={len(errors)}; bc rows={len(bc_rows)}; '
          f'unmatched bc rows={unmatched}')
    for e in errors[:20]:
        print('  ERR', e)


def check():
    doc = json.load(open(OUT, encoding='utf-8'))
    recs = doc['bullets']
    print('records:', len(recs))
    bad = 0
    for r in recs:
        ev = r['evidence']
        for fld in ('weightGr', 'bcG1', 'bcG7', 'diameterIn'):
            v = r[fld]
            if v is None:
                continue
            forms = {repr(v), ('%g' % v), ('%.3f' % v).lstrip('0'), ('%.3f' % v), str(int(v)) if v == int(v) else None,
                     ('%.2f' % v).lstrip('0')}
            if not any(f and f in ev for f in forms):
                bad += 1
                print('NOT IN EVIDENCE', r['id'], fld, v)
        if r['recommendedTwist'] and json.dumps(r['recommendedTwist'])[1:-1] not in ev:
            bad += 1
            print('TWIST NOT IN EVIDENCE', r['id'], r['recommendedTwist'])
        if r['sku'] and r['sku'] not in ev:
            bad += 1
            print('SKU NOT IN EVIDENCE', r['id'])
    print('evidence mismatches:', bad)
    random.seed(7)
    for r in random.sample(recs, min(5, len(recs))):
        print(json.dumps({k: r[k] for k in ('id', 'name', 'diameterIn', 'weightGr', 'bcG1', 'bcG7',
                                              'recommendedTwist', 'construction', 'tip', 'profile',
                                              'status', 'evidence')}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    if '--download' in sys.argv:
        download()
    if '--check' in sys.argv:
        check()
    elif '--download' not in sys.argv or '--parse' in sys.argv:
        build()
