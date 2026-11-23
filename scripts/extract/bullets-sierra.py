#!/usr/bin/env python3
"""Extract Sierra Bullets product specifications (key: bullets-sierra).

Sources (all public, fetched with plain curl and its default user agent):
  * https://sierrabullets.com/xmlsitemap.php?type=products&page=1 (product URL list)
  * every bullet product page listed there (https://sierrabullets.com/<slug>/).
    Each product page embeds the manufacturer's own spec table as JSON in the
    BigCommerce `window.stencilBootstrap("product", ...)` call: `customFields`
    and `specsJson` (Item #, Bullet Type, Bullet Diameter, Bullet Weight,
    G1 BC, G7 BC, Bullet Material, Tipped/Non-Tipped, ...).

robots.txt (https://sierrabullets.com/robots.txt) allows product pages; it sets
Crawl-delay: 10 for AI crawlers, so we sleep >= 10 s between requests.

Usage:
  python3 -I bullets-sierra.py --download   # fetch any missing source documents
  python3 -I bullets-sierra.py              # parse cached documents and write JSON
  python3 -I bullets-sierra.py --check      # self-check the written JSON

Everything is parsed with code from the cached HTML; nothing is typed in.
"""
import html as htmlmod
import json
import os
import random
import re
import subprocess
import sys
import time

SRC = '/tmp/claude-0/-home-user-ORKA/29ce603d-ccc3-55ef-b8fe-c585397ac7c1/scratchpad/sources/bullets-sierra'
OUT = '/home/user/ORKA/research/raw2/bullets-sierra.json'
RETRIEVED = '2026-11-23'
BASE = 'https://sierrabullets.com'
SITEMAP_URL = BASE + '/xmlsitemap.php?type=products&page=1'
SITEMAP_LOCAL = os.path.join(SRC, 'sitemap-products.xml')
PROD_DIR = os.path.join(SRC, 'products')
DELAY = 10.5

_last_request = [0.0]


def fetch(url, dest):
    """Download url to dest with plain curl (default UA), honoring the crawl delay."""
    wait = DELAY - (time.time() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + '.part'
    r = subprocess.run(['curl', '-sS', '-L', '-o', tmp, '-w', '%{http_code}', url],
                       capture_output=True, text=True)
    _last_request[0] = time.time()
    code = r.stdout.strip()
    if code == '200' and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
        os.replace(tmp, dest)
        return True
    if os.path.exists(tmp):
        os.remove(tmp)
    print(f'  ! {url} -> HTTP {code} {r.stderr.strip()}', file=sys.stderr)
    return False


def product_urls():
    xml = open(SITEMAP_LOCAL, encoding='utf-8').read()
    urls = [htmlmod.unescape(u) for u in re.findall(r'<loc>([^<]+)</loc>', xml)]
    # bullet products have "<n>-gr-" in their slug; the rest are apparel/banners/manual
    return [u for u in urls if re.search(r'-\d+-gr-', u)]


def slug_of(url):
    return url.rstrip('/').rsplit('/', 1)[-1]


def local_of(url):
    return os.path.join(PROD_DIR, slug_of(url) + '.html')


# Other public pages consulted (catalog page, its "Download" link, new-products and outlet pages)
EXTRA_DOCS = {
    BASE + '/catalog/': os.path.join(SRC, 'catalog.html'),
    BASE + '/images/stencil/original/image-manager/sierra-bullet-poster-page-0001.jpg':
        os.path.join(SRC, 'catalog-poster', 'sierra-bullet-poster-page-0001.jpg'),
    BASE + '/2026-new-products/': os.path.join(SRC, 'pages', '2026-new-products.html'),
    BASE + '/factory-outlet/': os.path.join(SRC, 'pages', 'factory-outlet.html'),
    BASE + '/bullet-101/': os.path.join(SRC, 'pages', 'bullet-101.html'),
}


# A subset of Sierra's own load-data PDFs (Sierra Reloading Manual, 6th ed. pages, linked from
# https://sierrabullets.com/load-data/). Each bullet section starts with a header line such as
# "#1700 .264" 85gr. HP 2.670"" (item #, diameter, weight, type, C.O.A.L.), which we use ONLY to
# cross-check the product pages' diameter and weight for the same item number.
LOADDATA_PAGE = BASE + '/load-data/'
LOADDATA_PATHS = [
    'rifle/204/204-ruger.pdf', 'rifle/224/22-hornet.pdf', 'rifle/224/223-remington-(bolt-gun).pdf',
    'rifle/224/22-250-remington.pdf', 'rifle/224/22-Creedmoor.pdf', 'rifle/243-6mm/243-winchester.pdf',
    'rifle/243-6mm/6mm-Creedmoor.pdf', 'rifle/257/25-06-remington.pdf', 'rifle/257/25-Creedmoor.pdf',
    'rifle/264-6.5mm/6.5-Creedmoor.pdf', 'rifle/264-6.5mm/6.5-PRC.pdf', 'rifle/277/270-winchester.pdf',
    'rifle/277/6.8-western.pdf', 'rifle/284/7mm-remington-magnum.pdf', 'rifle/284/7mm-PRC.pdf',
    'rifle/308/30-06-springfield.pdf', 'rifle/308/308-winchester.pdf', 'rifle/308/300-winchester-magnum.pdf',
    'rifle/308/300-prc.pdf', 'rifle/308/30-30-winchester.pdf', 'rifle/311/303 British.pdf',
    'legacy/323-8mm/8x57mm-(JS)-mauser.pdf', 'rifle/338/338-lapua-magnum.pdf', 'rifle/338/338-winchester-magnum.pdf',
    'rifle/357-358/35-whelen.pdf', 'rifle/375/375-h&h-magnum.pdf', 'rifle/458/45-70-GOVT.pdf',
    'handgun/308/30-Carbine.pdf', 'handgun/312/327-Federal-Magnum.pdf', 'handgun/355-9mm/9mm-Luger.pdf',
    'handgun/357/357-Remington-Magnum.pdf', 'handgun/400-10mm/10mm-Auto.pdf',
    'handgun/410/41-Remington-Magnum.pdf', 'handgun/429/44-remington-magnum.pdf',
    'handgun/451/45-Auto-(ACP).pdf', 'handgun/451/454-Casull.pdf', 'handgun/500/500-S&W-Magnum.pdf',
]


def loaddata_url(path):
    from urllib.parse import quote
    return BASE + '/content/load-data/' + quote(path, safe='/()&-.')


def loaddata_local(path):
    return os.path.join(SRC, 'loaddata', path.replace('/', '__'))


def download():
    if not os.path.exists(SITEMAP_LOCAL):
        fetch(SITEMAP_URL, SITEMAP_LOCAL)
    for u, p in EXTRA_DOCS.items():
        if not os.path.exists(p):
            fetch(u, p)
    if not os.path.exists(os.path.join(SRC, 'load-data.html')):
        fetch(LOADDATA_PAGE, os.path.join(SRC, 'load-data.html'))
    for lp in LOADDATA_PATHS:
        if not os.path.exists(loaddata_local(lp)):
            ok = fetch(loaddata_url(lp), loaddata_local(lp))
            print(f'{"ok " if ok else "ERR"} {loaddata_url(lp)}', flush=True)
    urls = product_urls()
    todo = [u for u in urls if not os.path.exists(local_of(u))]
    print(f'{len(urls)} bullet product URLs, {len(todo)} to fetch', flush=True)
    for i, u in enumerate(todo, 1):
        ok = fetch(u, local_of(u))
        print(f'[{i}/{len(todo)}] {"ok " if ok else "ERR"} {u}', flush=True)


# ----------------------------------------------------------------------------- parsing

def ws(s):
    return ' '.join(str(s).split())


BOOT_RE = re.compile(r'window\.stencilBootstrap\("product", "((?:[^"\\]|\\.)*)"')


def load_product(path):
    """Return (bootstrap_dict, bootstrap_text, page_html) for a cached product page."""
    page = open(path, encoding='utf-8').read()
    m = BOOT_RE.search(page)
    if not m:
        return None, None, page
    boot_text = json.loads('"' + m.group(1) + '"')   # undo the JS string escaping
    return json.loads(boot_text), boot_text, page


def description_text(page):
    """Visible text of the 'Product Details' tab (manufacturer's description)."""
    i = page.find('id="tab-description-content"')
    if i < 0:
        return ''
    j = page.find('<div class="tab-content"', i)
    frag = page[page.find('>', i) + 1: j if j > 0 else i + 20000]
    frag = re.sub(r'<(script|style)\b.*?</\1>', ' ', frag, flags=re.S)
    frag = re.sub(r'<br\s*/?>|</p>|</li>|</h\d>', '\n', frag)
    txt = htmlmod.unescape(re.sub(r'<[^>]+>', ' ', frag))
    return '\n'.join(ws(l) for l in txt.split('\n') if ws(l))


def sentences(txt):
    out = []
    for line in txt.split('\n'):
        out += [ws(s) for s in re.split(r'(?<=[.!?])\s+(?=[A-Z#(])', line) if ws(s)]
    return out


def spec_block_text(specs_text, sku):
    """Verbatim (whitespace-collapsed) text of one SKU's block in the specsJson string."""
    m = re.search(r'"' + re.escape(sku) + r'"\s*:\s*\{[^{}]*\}', specs_text)
    return ws(m.group(0)) if m else None


NUM = r'(\d*\.\d+|\d+)'


def num(s):
    if s is None:
        return None
    m = re.fullmatch(r'\s*' + NUM + r'\s*"?\s*', str(s))
    return float(m.group(1)) if m else None


def parse_bc(raw):
    """Return (value, bandNotes). Plain number -> (float, None); banded text -> (first, text)."""
    if raw is None or ws(raw) == '':
        return None, None
    v = num(raw)
    if v is not None:
        return v, None
    nums = re.findall(NUM, str(raw))
    # velocity-banded / multi-value text: keep the full text, take nothing we cannot be sure of
    return None, ws(raw)


TWIST_PATTERNS = [
    # e.g. "1:7 twist", "1:7" twist", "1-in-7" twist", "1 in 8 inch twist", "7" twist", "twist of 1:8"
    re.compile(r'\b1\s*(?:[:/×xX-]|-?in-?|\s+in\s+)\s*(\d{1,2}(?:\.\d+)?)\s*(?:"|”|″|\'\'|-?\s*inch(?:es)?|in\.)?\s*(?:or (?:faster|quicker))?\s*(?:barrel\s+)?twist', re.I),
    re.compile(r'twist[^.]{0,40}?\b1\s*(?:[:/×xX-]|-?in-?|\s+in\s+)\s*(\d{1,2}(?:\.\d+)?)', re.I),
    re.compile(r'\b(\d{1,2}(?:\.\d+)?)\s*(?:"|”|″|-?\s*inch)\s*(?:or (?:faster|quicker)\s*)?(?:barrel\s+)?twist', re.I),
]


def find_twists(desc):
    """Return list of (twistInches, sentence) for sentences that state a twist rate."""
    out = []
    for s in sentences(desc):
        if 'twist' not in s.lower():
            continue
        found = []
        for p in TWIST_PATTERNS:
            for m in p.finditer(s):
                found.append(float(m.group(1)))
        if found:
            out.append((sorted(set(found)), s))
        else:
            out.append(([], s))
    return out


def field_map(boot):
    """customFields -> dict name -> list of values (in page order)."""
    out = {}
    for c in boot.get('customFields') or []:
        out.setdefault(c['name'], []).append(c['value'])
    return out


def family_from_categories(cats):
    fams = [c.split('/', 2)[2] for c in cats if c.startswith('Bullets/Product Family/')]
    return fams


def caliber_label(name):
    m = re.match(r'^\s*(.*?)\s+\d+(?:\.\d+)?\s*GR\b', name, re.I)
    return ws(m.group(1)) if m else None


def name_weight(name):
    m = re.search(r'\b(\d+(?:\.\d+)?)\s*GR\b', name, re.I)
    return float(m.group(1)) if m else None


def construction_of(btype, material):
    bt = (btype or '').lower()
    mat = (material or '').strip().lower()
    if 'full metal jacket' in bt or re.search(r'\bfmj', bt):
        return 'FMJ'
    if 'full profile jacket' in bt or re.search(r'\bfpj\b', bt):
        return None   # Sierra's own term; neither "FMJ" nor plain cup-and-core wording -> leave unmapped
    if mat == 'jacketed lead':
        return 'cup-and-core'
    if mat in ('lead', 'cast lead'):
        return 'lead'
    if mat in ('copper', 'solid copper', 'monolithic copper'):
        return 'monolithic-copper'
    return None


def kebab(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


GENERIC_KEYS = {
    'length': re.compile(r'\blength\b', re.I),
    'twist': re.compile(r'\btwist\b', re.I),
    'ogive': re.compile(r'ogive', re.I),
    'boattail': re.compile(r'boat\s*tail\s*length', re.I),
}


SPEC_FIELDS = [
    # (record field, specsJson key(s), customFields key)
    ('diameterIn', ('Bullet Diameter',), 'Bullet Diameter'),
    ('weightGr', ('Bullet Weight (Grains)', 'Bullet Weight'), 'Bullet Weight'),
    ('bcG1', ('G1 BC',), 'G1 BC'),
    ('bcG7', ('G7 BC',), 'G7 BC'),
    ('profile', ('Bullet Type',), 'Bullet Type'),
    ('material', ('Bullet Material',), 'Bullet Material'),
    ('tipped', ('Tipped/Non-Tipped',), 'Tipped/Non-Tipped'),
]
NUMERIC = {'diameterIn', 'weightGr', 'bcG1', 'bcG7'}


def first_key(d, keys):
    for k in keys:
        if k in d and ws(d[k]) != '':
            return d[k]
    return None


def same(a, b, numeric):
    if a is None or b is None:
        return True
    if numeric:
        na, nb = num(a), num(b)
        if na is not None and nb is not None:
            return abs(na - nb) < 1e-9
    return ws(a).lower() == ws(b).lower()


def custom_field_raw(boot_text, name):
    """Verbatim JSON objects for a custom field in the decoded bootstrap text."""
    return [ws(m) for m in re.findall(r'\{"id":"\d+","name":"' + re.escape(name) + r'","value":"(?:[^"\\]|\\.)*"\}',
                                        boot_text)]


BC_DESC_RES = [
    # "ballistic coefficient of 0.505 (G1)", "BC of .xxx"
    re.compile(r'(?:ballistic coefficient|\bB\.?C\.?)(?![a-z])[^.\d]{0,40}?(?<![\d.])(0?\.\d{3})(?!\d)\s*\(?(G1|G7)?\)?', re.I),
    # ".543 G1 B.C."
    re.compile(r'(?<![\d.])(0?\.\d{3})(?!\d)\s*(G1|G7)\s*(?:B\.?C\.?|ballistic coefficient)', re.I),
]
PROFILE_DESC_RE = re.compile(r'\b\d+(?:\.\d+)?\s*(?:caliber|cal\.?)\s+(?:\w+\s+)?(?:ogive|secant|tangent)|\b\d+(?:\.\d+)?\s*degree\s+boat\s*tail', re.I)
TIP_DESC_RE = re.compile(r'\b(acetal resin|polymer|resin|plastic|nylon|polycarbonate)\s+tip', re.I)
ITEM_RE = re.compile(r'#\s?(\d{4}[A-Z]{0,3})\b')


def build_record(url, path):
    boot, boot_text, page = load_product(path)
    if boot is None:
        return None, f'no stencilBootstrap product JSON in {path}'
    sku = ws(boot['productSKU'])
    name = ws(htmlmod.unescape(boot['productName']))
    cats = boot.get('productCategory') or []
    fm = field_map(boot)
    specs_text = boot.get('specsJson') or ''
    specs = json.loads(specs_text) if specs_text.strip() else {}
    base = specs.get(sku)
    notes, conflicts, evidence = [], [], []

    if base is None and specs:
        notes.append(f'specsJson has no entry for productSKU {sku}; keys: {sorted(specs)}')
    blk = spec_block_text(specs_text, sku) if base is not None else None
    if blk:
        evidence.append(blk)

    vals = {}
    for field, skeys, ckey in SPEC_FIELDS:
        sv = first_key(base, skeys) if base else None
        cvs = [v for v in fm.get(ckey, []) if ws(v) != '']
        cv = cvs[0] if cvs else None
        chosen = sv if sv is not None else cv
        if sv is None and cv is not None:
            evidence += custom_field_raw(boot_text, ckey)[:1]
        # disagreement between the two copies of the maker's spec table on the same page
        distinct = []
        for label, v in [('specsJson[' + sku + ']', sv)] + [('customFields', x) for x in cvs]:
            if v is None:
                continue
            if not any(same(v, d[1], field in NUMERIC) for d in distinct):
                distinct.append((label, v))
        if len(distinct) > 1:
            conflicts.append({'field': field, 'values': [
                {'value': (num(v) if field in NUMERIC and num(v) is not None else ws(v)),
                 'source': url + ' (' + lab + ')'} for lab, v in distinct]})
            evidence += [x for x in custom_field_raw(boot_text, ckey) if x not in evidence]
        vals[field] = chosen

    # other SKUs (packagings) on the same page must carry the same ballistic data
    variants = []
    for vsku, vd in specs.items():
        if vsku == sku:
            continue
        variants.append(f"{vsku} ({ws(vd.get('Box Quantity', '?'))} ct)")
        for field, skeys, _ in SPEC_FIELDS:
            vv = first_key(vd, skeys)
            if vv is not None and vals.get(field) is not None and not same(vv, vals[field], field in NUMERIC):
                conflicts.append({'field': field, 'values': [
                    {'value': num(vals[field]) if field in NUMERIC else ws(vals[field]),
                     'source': url + f' (specsJson[{sku}])'},
                    {'value': num(vv) if field in NUMERIC else ws(vv), 'source': url + f' (specsJson[{vsku}])'}]})
                b2 = spec_block_text(specs_text, vsku)
                if b2 and b2 not in evidence:
                    evidence.append(b2)
    box = ws(base.get('Box Quantity')) if base and base.get('Box Quantity') else None

    # any length / twist / ogive keys published in the spec table (none seen in 2026, handled if added)
    extra = {}
    allkeys = set(base or {}) | set(fm)
    for k in allkeys:
        for tag, rx in GENERIC_KEYS.items():
            if rx.search(k):
                extra.setdefault(tag, []).append((k, (base or {}).get(k, (fm.get(k) or [None])[0])))

    desc = description_text(page)
    sents = sentences(desc)

    # BC statements in the description, cross-checked against the spec table
    for s in sents:
        hits = {}
        for rx in BC_DESC_RES:
            for m in rx.finditer(s):
                hits[(m.start(1), m.group(1))] = (m.group(2) or '').upper() or None
        for (_, sv), kind in sorted(hits.items()):
            v = float(sv)
            target = 'bcG7' if kind == 'G7' else 'bcG1'
            tv = num(vals.get(target))
            if tv is None or abs(tv - v) > 1e-9:
                conflicts.append({'field': target, 'values': [
                    {'value': tv, 'source': url + ' (spec table)'},
                    {'value': v, 'source': url + ' (product description text' + ('' if kind else ', BC type not stated') + ')'}]})
                if s not in evidence:
                    evidence.append(s)

    # item numbers referenced in the description
    own = {sku.upper()} | {k.upper() for k in specs} | {ws(v).upper() for v in fm.get('Item #', [])}
    other_items = sorted({m.group(1) for s in sents for m in ITEM_RE.finditer(s)} - own)
    if other_items:
        notes.append('Product description also references item number(s) ' + ', '.join('#' + x for x in other_items)
                     + ' (description text may be shared with/compare to another product).')

    # twist statements
    twist = None
    tw = find_twists(desc)
    rec_words = re.compile(r'recommend|require|minimum|at least|need|necessary|stabiliz|or faster|or quicker|faster than|best in|designed for', re.I)
    tw_vals = sorted({v for vs, s in tw for v in vs if rec_words.search(s)})
    if tw:
        for vs, s in tw:
            if s not in evidence:
                evidence.append(s)
        if len(tw_vals) == 1:
            twist = '1:' + ('%g' % tw_vals[0])
            notes.append('recommendedTwist taken from the product description sentence quoted in evidence (not from the spec table).')
        else:
            notes.append('Product description mentions twist but no single recommended rate could be parsed unambiguously; see evidence.')
    if 'twist' in extra:
        notes.append('Spec table twist field(s): ' + '; '.join(f'{k}={v}' for k, v in extra['twist']))

    length = None
    if 'length' in extra:
        for k, v in extra['length']:
            if num(v) is not None and not re.search(r'ogive|boat', k, re.I):
                length = num(v)
        notes.append('Spec table length field(s): ' + '; '.join(f'{k}={v}' for k, v in extra['length']))

    g1, g1notes = parse_bc(vals.get('bcG1'))
    g7, g7notes = parse_bc(vals.get('bcG7'))
    bcnotes = '; '.join(x for x in [('G1: ' + g1notes) if g1notes else None, ('G7: ' + g7notes) if g7notes else None] if x) or None

    fams = family_from_categories(cats)
    pf = [ws(v) for v in fm.get('Product Family', [])]
    line = fams[0] if len(fams) == 1 else (pf[0] if pf else (' / '.join(fams) or None))
    if len(fams) > 1:
        notes.append('Listed in several product-family categories: ' + ', '.join(fams))

    tipped = ws(vals['tipped']) if vals.get('tipped') else None
    tip = 'Tipped' if tipped and tipped.lower() == 'tipped' else None
    if tip:
        mats = []
        for s in sents:
            for m in TIP_DESC_RE.finditer(s):
                if m.group(1).lower() not in mats:
                    mats.append(m.group(1).lower())
                    if s not in evidence:
                        evidence.append(s)
        if len(mats) == 1:
            tip = mats[0] + ' tip'
        elif mats:
            notes.append('Description names several tip materials: ' + ', '.join(mats) + '.')
    elif any(TIP_DESC_RE.search(s) for s in sents):
        notes.append('Spec table says Non-Tipped/blank but the description mentions a tip; see description.')
    prof = [s for s in sents if PROFILE_DESC_RE.search(s)]
    if prof:
        evidence += [s for s in prof if s not in evidence]
        notes.append('Profile details from the product description (quoted in evidence): '
                     + '; '.join(m.group(0) for s in prof for m in PROFILE_DESC_RE.finditer(s)) + '.')
    material = ws(vals['material']) if vals.get('material') else None
    profile = ws(vals['profile']) if vals.get('profile') else None
    construction = construction_of(profile, material)
    if material:
        notes.append(f'Maker\'s "Bullet Material": {material}' + (f' -> construction "{construction}"' if construction else ' (not mapped to a construction class)') + '.')
    if tipped:
        notes.append(f'Maker\'s "Tipped/Non-Tipped": {tipped}.')
    if variants:
        notes.append('Other packagings on the same page (same spec table): ' + ', '.join(variants) + '.')
    if box:
        notes.append(f'Base item #{sku}: box quantity {box}.')
    nw = name_weight(name)
    if nw is not None and num(vals.get('weightGr')) is not None and abs(nw - num(vals['weightGr'])) > 1e-9:
        conflicts.append({'field': 'weightGr', 'values': [
            {'value': num(vals['weightGr']), 'source': url + ' (spec table)'},
            {'value': nw, 'source': url + ' (product name)'}]})
    calcats = [c.split('/', 2)[2] for c in cats if c.startswith('Bullets/Rifle Calibers/') or c.startswith('Bullets/Pistol Calibers/')]
    firearm = 'rifle' if any(c.startswith('Bullets/Rifle Calibers/') for c in cats) or 'Rifle' in cats else \
              ('handgun' if any(c.startswith('Bullets/Pistol Calibers/') for c in cats) or 'Pistol' in cats else None)
    if len(calcats) > 1:
        notes.append('Listed under several caliber categories: ' + ', '.join(calcats) + '.')
    outlet = [c for c in cats if 'outlet' in c.lower() or 'closeout' in c.lower() or 'discontinu' in c.lower()]
    status = 'current (offered on sierrabullets.com product page, retrieved 2026-11-23)'
    if outlet:
        status = 'listed in ' + ', '.join(outlet) + ' (sierrabullets.com, retrieved 2026-11-23)'

    rec = {
        'id': 'sierra-' + kebab(sku),
        'manufacturer': 'Sierra Bullets',
        'line': line,
        'name': name,
        'sku': sku,
        'caliberLabel': caliber_label(name),
        'diameterIn': num(vals.get('diameterIn')),
        'weightGr': num(vals.get('weightGr')),
        'lengthIn': length,
        'boatTailLengthIn': None,
        'baseToOgiveIn': None,
        'bcG1': g1,
        'bcG7': g7,
        'bcNotes': bcnotes,
        'profile': profile,
        'tip': tip,
        'construction': construction,
        'recommendedTwist': twist,
        'status': status,
        'firearm': firearm,
        'sources': [{'url': url, 'type': 'manufacturer', 'page': None, 'retrieved': RETRIEVED}],
        'evidence': ' | '.join(ws(e) for e in evidence),
        'notes': ' '.join(notes) or None,
    }
    if conflicts:
        rec['conflicts'] = conflicts
    if rec['diameterIn'] is None and vals.get('diameterIn'):
        rec['notes'] = (rec['notes'] or '') + f' Unparsed diameter text: {vals["diameterIn"]!r}.'
    if rec['weightGr'] is None and vals.get('weightGr'):
        rec['notes'] = (rec['notes'] or '') + f' Unparsed weight text: {vals["weightGr"]!r}.'
    return rec, None


LD_LINE_RE = re.compile(r'#(\d{4}[A-Z]{0,2})\s+(0?\.\d{3,4})\s*(?:["”″]|\'\')?\s+(\d+(?:\.\d+)?)\s*gr\.?\s+(\S.*?)\s{2,}(\d\.\d{3})\s*(?:["”″]|\'\')?')


def loaddata_index():
    """item# -> list of {url, page, diameter, weight, line} from the cached load-data PDFs."""
    idx = {}
    for lp in LOADDATA_PATHS:
        local = loaddata_local(lp)
        if not os.path.exists(local):
            continue
        txt = subprocess.run(['pdftotext', '-layout', local, '-'], capture_output=True, text=True).stdout
        for pno, ptxt in enumerate(txt.split('\f'), 1):
            for line in ptxt.split('\n'):
                for m in LD_LINE_RE.finditer(line):
                    idx.setdefault(m.group(1).upper(), []).append({
                        'url': loaddata_url(lp), 'page': pno,
                        'diameter': float(m.group(2)), 'weight': float(m.group(3)),
                        'type': ws(m.group(4)), 'line': ws(m.group(0))})
    return idx


def apply_loaddata_crosscheck(recs, idx):
    n_conf = n_ok = 0
    for r in recs:
        hits = idx.get(r['sku'].upper(), [])
        if not hits:
            continue
        agree, disagree = [], []
        for h in hits:
            okd = r['diameterIn'] is not None and abs(h['diameter'] - r['diameterIn']) < 1e-9
            okw = r['weightGr'] is not None and abs(h['weight'] - r['weightGr']) < 1e-9
            (agree if (okd and okw) else disagree).append((h, okd, okw))
        if agree:
            n_ok += 1
            seen = {s['url'] for s in r['sources']}
            for h, _, _ in agree:
                if h['url'] not in seen:
                    r['sources'].append({'url': h['url'], 'type': 'manufacturer', 'page': h['page'],
                                         'retrieved': RETRIEVED})
                    seen.add(h['url'])
            h0 = agree[0][0]
            r['evidence'] += ' | [load data p.%d] %s' % (h0['page'], h0['line'])
            r['notes'] = ((r['notes'] or '') + ' Diameter and weight confirmed by the bullet header line for #%s in '
                          '%d Sierra load-data PDF page(s) (sources[1:]).' % (r['sku'], len(agree))).strip()
        for h, okd, okw in disagree:
            n_conf += 1
            rc = r.setdefault('conflicts', [])
            if not okd:
                rc.append({'field': 'diameterIn', 'values': [
                    {'value': r['diameterIn'], 'source': r['sources'][0]['url']},
                    {'value': h['diameter'], 'source': '%s (PDF page %d)' % (h['url'], h['page'])}]})
            if not okw:
                rc.append({'field': 'weightGr', 'values': [
                    {'value': r['weightGr'], 'source': r['sources'][0]['url']},
                    {'value': h['weight'], 'source': '%s (PDF page %d)' % (h['url'], h['page'])}]})
            r['evidence'] += ' | [load data p.%d, disagrees] %s' % (h['page'], h['line'])
    return n_ok, n_conf


def flag_diameter_outliers(recs):
    """Flag (never change) a diameter that differs from the majority of the same caliber label."""
    groups = {}
    for r in recs:
        if r['caliberLabel'] and r['diameterIn'] is not None:
            groups.setdefault(r['caliberLabel'].upper(), []).append(r)
    for lab, rs in groups.items():
        counts = {}
        for r in rs:
            counts[r['diameterIn']] = counts.get(r['diameterIn'], 0) + 1
        if len(counts) < 2:
            continue
        top = max(counts.values())
        for r in rs:
            if counts[r['diameterIn']] < top:
                others = ', '.join('%g (x%d)' % (d, c) for d, c in sorted(counts.items()))
                r['notes'] = ((r['notes'] or '') + f' CHECK: diameter {r["diameterIn"]} differs from the most common '
                              f'diameter among Sierra "{lab}" products on the site ({others}).').strip()


def build():
    urls = product_urls()
    recs, problems = [], []
    for u in urls:
        p = local_of(u)
        if not os.path.exists(p):
            problems.append(f'not downloaded: {u}')
            continue
        r, err = build_record(u, p)
        if err:
            problems.append(err)
            continue
        recs.append(r)
    # duplicate ids (same SKU on two URLs)
    seen = {}
    for r in recs:
        if r['id'] in seen:
            problems.append(f'duplicate id {r["id"]}: {seen[r["id"]]} and {r["sources"][0]["url"]}')
            r['id'] += '-' + kebab(slug_of(r['sources'][0]['url']))
        seen[r['id']] = r['sources'][0]['url']
    flag_diameter_outliers(recs)
    ld = loaddata_index()
    n_ok, n_conf = apply_loaddata_crosscheck(recs, ld)
    print(f'load-data cross-check: {len(ld)} item numbers indexed; {n_ok} records corroborated; {n_conf} disagreeing lines')
    recs.sort(key=lambda r: (r['firearm'] or 'z', r['diameterIn'] or 0, r['weightGr'] or 0, r['sku']))
    docs = [{'url': SITEMAP_URL, 'localPath': SITEMAP_LOCAL,
             'title': 'Sierra Bullets XML product sitemap (list of product pages)', 'date': RETRIEVED}]
    for r in recs:
        u = r['sources'][0]['url']
        docs.append({'url': u, 'localPath': local_of(u), 'title': 'Sierra Bullets product page: ' + r['name'],
                     'date': RETRIEVED})
    for lp in LOADDATA_PATHS:
        if os.path.exists(loaddata_local(lp)):
            docs.append({'url': loaddata_url(lp), 'localPath': loaddata_local(lp),
                         'title': 'Sierra load data PDF (Sierra Reloading Manual 6th ed. pages): ' + lp.rsplit('/', 1)[-1],
                         'date': None})
    out = {
        'meta': {
            'key': 'bullets-sierra',
            'retrieved': RETRIEVED,
            'documents': docs,
            'notes': META_NOTES,
            'problems': problems,
        },
        'bullets': recs,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write('\n')
    print(f'wrote {len(recs)} records to {OUT}; problems: {len(problems)}')
    for p in problems:
        print('  problem:', p)
    return out


META_NOTES = (
    'Source: every bullet product page listed in the sierrabullets.com product sitemap on 2026-11-23. '
    'Values come from the manufacturer spec table that each product page embeds as JSON '
    '(window.stencilBootstrap "specsJson" and "customFields": Item #, Bullet Type, Bullet Diameter, '
    'Bullet Weight (Grains), G1 BC, G7 BC, Bullet Material, Tipped/Non-Tipped); evidence quotes that '
    'JSON text verbatim (JS string escaping undone, whitespace collapsed). '
    'Sierra\'s current site publishes ONE G1 and (for some bullets) ONE G7 BC per bullet; it does not publish '
    'velocity-banded BCs, bullet length, base-to-ogive, boat-tail length or recommended twist in its spec '
    'tables, so those fields are null unless a product description states them (twist, when parsed, is '
    'quoted in evidence). The "2026 catalog" offered on https://sierrabullets.com/catalog/ is a single JPEG '
    'poster image, not a PDF, and was not used for numbers. construction is mapped from the maker\'s '
    '"Bullet Material" wording ("Jacketed Lead" -> cup-and-core; Bullet Type containing Full Metal Jacket -> FMJ); '
    'the raw wording is kept in notes. "firearm" (rifle/handgun) is from the site category the product is listed in. '
    'Conflicts list disagreements between the two copies of the spec table on a page, between packaging '
    'variants, or between the spec table and the product description text/name. Notes starting with "CHECK:" '
    'flag a diameter that differs from other products with the same caliber label (flag only; value kept as published).'
)


def self_check(out=None, nsample=5, seed=None):
    if out is None:
        out = json.load(open(OUT, encoding='utf-8'))
    recs = out['bullets']
    print(f'records: {len(recs)}')
    by = {}
    for r in recs:
        by[r['firearm']] = by.get(r['firearm'], 0) + 1
    print('by firearm:', by)
    for f in ['diameterIn', 'weightGr', 'lengthIn', 'bcG1', 'bcG7', 'recommendedTwist', 'construction', 'tip', 'bcNotes']:
        print(f'  {f}: {sum(1 for r in recs if r.get(f) is not None)} non-null')
    print('  with conflicts:', sum(1 for r in recs if r.get('conflicts')))
    bad = 0
    for r in recs:
        toks = [float(t) for t in re.findall(r'\d*\.\d+|\d+', r['evidence'])]
        for f in ['diameterIn', 'weightGr', 'lengthIn', 'bcG1', 'bcG7']:
            v = r.get(f)
            if v is not None and not any(abs(v - t) < 1e-9 for t in toks):
                bad += 1
                print(f'  !! {r["id"]}: {f}={v} not found in evidence')
        if r.get('recommendedTwist'):
            tv = float(r['recommendedTwist'].split(':')[1])
            if not any(abs(tv - t) < 1e-9 for t in toks):
                bad += 1
                print(f'  !! {r["id"]}: twist {r["recommendedTwist"]} not in evidence')
        for k in ['id', 'manufacturer', 'name', 'sku', 'sources', 'evidence']:
            if not r.get(k):
                bad += 1
                print(f'  !! {r.get("id")}: missing {k}')
    print('evidence check failures:', bad)
    rnd = random.Random(seed)
    for r in rnd.sample(recs, min(nsample, len(recs))):
        print('-' * 100)
        print(json.dumps({k: r[k] for k in ['id', 'name', 'caliberLabel', 'diameterIn', 'weightGr', 'bcG1', 'bcG7',
                                              'profile', 'tip', 'construction', 'recommendedTwist', 'line']},
                         ensure_ascii=False))
        print('EVIDENCE:', r['evidence'][:1200])
        if r.get('conflicts'):
            print('CONFLICTS:', json.dumps(r['conflicts'], ensure_ascii=False))
        if r.get('notes'):
            print('NOTES:', r['notes'][:600])
    return bad


if __name__ == '__main__':
    if '--download' in sys.argv:
        download()
    elif '--check' in sys.argv:
        sys.exit(1 if self_check() else 0)
    else:
        o = build()
        self_check(o)
