#!/usr/bin/env python3
"""Extract cartridge-brass makers and per-cartridge case data (key: brass).

Sources (public pages only, fetched with plain curl and its DEFAULT user agent,
robots.txt read first and obeyed, >= 1.5 s between requests to one host):

  Lapua (Nammo Lapua Oy)       https://www.lapua.com/products/cartridge-cases/ (3 listing pages)
                               every case product page linked there (WooCommerce attribute table:
                               Caliber / Product no. / Primer / Bullet diameter)
                               https://www.lapua.com/wp-content/uploads/2026/06/Lapua_Catalog_2026_ENG_web.pdf
                               ("LAPUA CENTERFIRE CASES" table: caliber + product no.)
                               robots.txt only disallows /wp-admin/.
  Norma (Norma Precision AB)   https://www.norma-ammunition.com/products/sitemap/sitemap-products-en.xml
                               -> every /products/components/norma-brass/ page (schema.org Product
                               JSON-LD: name, sku, Caliber). Norma's /reloading/ pages currently say
                               "Load data being updated" (no case data). robots.txt: Allow /.
  Peterson Cartridge           https://petersoncartridge.com/ballistician-testing-data
                               (per-lot table: Average Empty Weight (Grains), Average Internal
                               Volume (Grains of H20), ...). Drawings/PDFs live under /files/,
                               which robots.txt disallows -> not fetched.
  Starline Brass               https://www.starlinebrass.com/rifle-brass/ and /pistol-brass/
                               listing pages -> every product page (part #, name, primer, length).
                               robots.txt disallows /*?* -> no query-string URLs are fetched.
  AccurateShooter (3rd party)  https://www.accurateshooter.com/cartridge-guides/* (18 guides);
                               measured tables in the .223 Rem guide (case weight vs. H20 capacity,
                               with the measuring method stated in its footnotes) and in
                               "6XC for competitive shooting" (Table One), plus a few explicit
                               measured statements in prose (.308 Win, 6mm BR).
  Alpha Munitions              https://www.alphamunitions.com/ answers HTTP 429 "Vercel Security
                               Checkpoint" to curl -> blocked, NOT circumvented, no data.

Usage:
  python3 -I brass.py --download [lapua|norma|peterson|starline|accurateshooter|all]
  python3 -I brass.py            # parse cached documents and write JSON
  python3 -I brass.py --check    # self-check the written JSON

Every number is parsed by code from the cached documents; nothing is typed in.
The only hand-written content is the list of prose sentences (ANCHORS) to pick from
AccurateShooter pages and how to interpret them (brand / condition); the numbers in
those records are still parsed from the verbatim sentence.
"""
import html as htmlmod
import json
import os
import random
import re
import statistics
import subprocess
import sys
import time
from html.parser import HTMLParser
from urllib.parse import urlparse

SRC = '/tmp/claude-0/-home-user-ORKA/29ce603d-ccc3-55ef-b8fe-c585397ac7c1/scratchpad/sources/brass'
OUT = '/home/user/ORKA/research/raw2/brass.json'
RETRIEVED = '2026-11-23'

DELAY = {
    'www.lapua.com': 1.5,
    'www.norma-ammunition.com': 2.0,
    'petersoncartridge.com': 1.5,
    'www.starlinebrass.com': 1.5,
    'www.accurateshooter.com': 1.5,
}
_last = {}


def fetch(url, dest, force=False):
    """Download url -> dest with plain curl (default UA) unless cached."""
    if os.path.exists(dest) and os.path.getsize(dest) > 0 and not force:
        return True
    host = urlparse(url).netloc
    wait = DELAY.get(host, 2.0) - (time.time() - _last.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + '.part'
    r = subprocess.run(['curl', '-sS', '-L', '-o', tmp, '-w', '%{http_code}', url],
                       capture_output=True, text=True)
    _last[host] = time.time()
    code = r.stdout.strip()
    if code == '200' and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
        os.replace(tmp, dest)
        print(f'  + {url}', file=sys.stderr)
        return True
    if os.path.exists(tmp):
        os.remove(tmp)
    print(f'  ! {url} -> HTTP {code} {r.stderr.strip()}', file=sys.stderr)
    return False


def read(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        return f.read()


def ws(s):
    return re.sub(r'\s+', ' ', s or '').strip()


def para_lines(raw):
    """HTML -> paragraphs (breaks only at block-level tags, inline links stay in the sentence)."""
    t = re.sub(r'<script.*?</script>', '', raw, flags=re.S)
    t = re.sub(r'<style.*?</style>', '', t, flags=re.S)
    t = re.sub(r'</?(p|div|li|h\d|section|ul|ol|table|tr|td|th|header|footer|nav)\b[^>]*>|<br\s*/?>', '\n', t)
    t = re.sub(r'<[^>]+>', '', t)
    t = htmlmod.unescape(t)
    return [ws(l) for l in t.split('\n') if ws(l)]


def text_lines(raw):
    """HTML -> list of whitespace-collapsed text lines (block-level breaks)."""
    t = re.sub(r'<script.*?</script>', '', raw, flags=re.S)
    t = re.sub(r'<style.*?</style>', '', t, flags=re.S)
    t = re.sub(r'<br\s*/?>', '\n', t)
    t = re.sub(r'</?(p|div|li|tr|h\d|table|td|th|section|ul|ol|span|a)\b[^>]*>', '\n', t)
    t = re.sub(r'<[^>]+>', '', t)
    t = htmlmod.unescape(t)
    return [ws(l) for l in t.split('\n') if ws(l)]


class TableParser(HTMLParser):
    """Collect every <table> as a list of rows (list of cell texts)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self._stack = []
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self._stack.append([])
        elif tag == 'tr' and self._stack:
            self._row = []
        elif tag in ('td', 'th') and self._row is not None:
            self._cell = []
        elif tag == 'br' and self._cell is not None:
            self._cell.append(' ')

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self._cell is not None and self._row is not None:
            self._row.append(ws(''.join(self._cell)))
            self._cell = None
        elif tag == 'tr' and self._row is not None and self._stack:
            if self._row:
                self._stack[-1].append(self._row)
            self._row = None
        elif tag == 'table' and self._stack:
            self.tables.append(self._stack.pop())

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def tables_of(raw):
    p = TableParser()
    p.feed(raw)
    return p.tables


def num(s):
    m = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(?:gr)?\s*', s or '')
    return float(m.group(1)) if m else None


def src(url, typ, page=None):
    return {'url': url, 'type': typ, 'page': page, 'retrieved': RETRIEVED}


def local_name(url):
    p = urlparse(url)
    path = p.path.strip('/').replace('/', '_') or 'index'
    if p.query:
        path += '__' + re.sub(r'[^A-Za-z0-9]+', '_', p.query)
    return path + ('' if re.search(r'\.(html|pdf|xml)$', path) else '.html')


# --------------------------------------------------------------------------- Lapua
LAPUA = 'https://www.lapua.com'
LAPUA_LIST = [LAPUA + '/products/cartridge-cases/',
              LAPUA + '/products/cartridge-cases/?product-page=2',
              LAPUA + '/products/cartridge-cases/?product-page=3']
LAPUA_CATALOG = LAPUA + '/wp-content/uploads/2026/06/Lapua_Catalog_2026_ENG_web.pdf'
LAPUA_ABOUT = LAPUA + '/more/about/'
LDIR = os.path.join(SRC, 'lapua')


def lapua_listing_local(u):
    return os.path.join(LDIR, 'listing', local_name(u))


def lapua_product_urls():
    urls = []
    for u in LAPUA_LIST:
        p = lapua_listing_local(u)
        if not os.path.exists(p):
            continue
        for h in re.findall(r'href="(https://www\.lapua\.com/product/[^"]+)"', read(p)):
            if h not in urls:
                urls.append(h)
    return urls


def lapua_product_local(u):
    return os.path.join(LDIR, 'products', u.rstrip('/').rsplit('/', 1)[-1] + '.html')


def download_lapua():
    for u in LAPUA_LIST:
        fetch(u, lapua_listing_local(u))
    for u in lapua_product_urls():
        fetch(u, lapua_product_local(u))
    fetch(LAPUA_CATALOG, os.path.join(LDIR, 'Lapua_Catalog_2026_ENG_web.pdf'))
    fetch(LAPUA_ABOUT, os.path.join(LDIR, 'about.html'))


def lapua_catalog_cases():
    """Parse the 'LAPUA CENTERFIRE CASES' two-column table of the 2026 catalog."""
    pdf = os.path.join(LDIR, 'Lapua_Catalog_2026_ENG_web.pdf')
    txt = os.path.join(LDIR, 'Lapua_Catalog_2026_ENG_web.txt')
    if not os.path.exists(pdf):
        return {}, None
    if not os.path.exists(txt):
        subprocess.run(['pdftotext', '-layout', pdf, txt], check=True, capture_output=True)
    # find page number of the table
    pages = read(txt).split('\f')
    out = {}
    page_no = None
    for pi, pg in enumerate(pages):
        if 'LAPUA® CENTERFIRE CASES' not in pg and 'LAPUA® CENTERFIRE CASES' not in pg:
            continue
        page_no = pi + 1
        seg = pg[pg.find('CENTERFIRE CASES'):]
        seg = seg[:seg.find('SCAN THE QR-CODES FOR MORE DETAILS ABOUT OUR CASES')]
        lines = seg.split('\n')
        pend = None  # "6.5 Creedmoor  6.5 mm (.264)" line followed by "(Small Rifle Primer)  4PH6011 ..."
        pend_lines = []
        for ln in lines:
            cells = [c for c in re.split(r'\s{2,}', ln.strip()) if c]
            if not cells:
                continue
            ev_line = ws(' '.join(pend_lines + [ln])) if pend else ws(ln)
            # entries are triplets name / caliber / product-no; product no. like 4PH5002 or 4PH6060C
            i = 0
            buf = []
            while i < len(cells):
                buf.append(cells[i])
                if re.fullmatch(r'4PH\d{4}C?', cells[i]):
                    if len(buf) >= 3:
                        name, cal, pn = buf[-3], buf[-2], buf[-1]
                    elif len(buf) == 2 and pend:
                        name, cal, pn = pend[0] + ' ' + buf[0], pend[1], buf[1]
                        pend = None
                    elif len(buf) == 1 and pend:
                        name, cal, pn = pend[0], pend[1], buf[0]
                        pend = None
                    else:
                        name, cal, pn = None, None, cells[i]
                    out[pn] = {'catalogName': name, 'catalogCaliber': cal, 'evidence': ev_line}
                    buf = []
                i += 1
            if pend is None:
                pend_lines = []
            if buf and len(buf) == 2 and re.search(r'mm \(\.\d+\)', buf[1]):
                pend = (buf[0], buf[1])
                pend_lines = [ln]
            elif buf and len(buf) == 1 and re.fullmatch(r'\((Small|Large) Rifle Primer\)', buf[0]) and pend:
                pend = (pend[0] + ' ' + buf[0], pend[1])
                pend_lines.append(ln)
        break
    return out, page_no


def lapua_parse():
    cases, docs = [], []
    cat, cat_page = lapua_catalog_cases()
    if cat:
        docs.append({'url': LAPUA_CATALOG, 'localPath': os.path.join(LDIR, 'Lapua_Catalog_2026_ENG_web.pdf'),
                     'title': 'Lapua Catalog 2026 (ENG, web)', 'date': '2026-03-23 (PDF CreationDate)'})
    for u in LAPUA_LIST:
        if os.path.exists(lapua_listing_local(u)):
            docs.append({'url': u, 'localPath': lapua_listing_local(u),
                         'title': 'Lapua - Cartridge cases (product listing)', 'date': None})
    seen = set()
    for u in lapua_product_urls():
        p = lapua_product_local(u)
        if not os.path.exists(p):
            continue
        raw = read(p)
        attrs = {}
        for tab in tables_of(raw):
            for row in tab:
                if len(row) == 2:
                    attrs[row[0]] = row[1]
        title = re.search(r'<h1[^>]*>(.*?)</h1>', raw, re.S)
        title = ws(htmlmod.unescape(re.sub(r'<[^>]+>', '', title.group(1)))) if title else None
        docs.append({'url': u, 'localPath': p, 'title': title, 'date': None})
        cats = re.search(r'Categories:(.*?)</', raw, re.S)
        if 'Product no.' not in attrs:
            continue
        pn_listed = attrs['Product no.']
        pn = re.sub(r'\s+', '', pn_listed)  # some pages print "4 PH 6060C"; catalog prints "4PH6060C"
        if pn in seen:
            continue
        seen.add(pn)
        primer = attrs.get('Primer')
        psize = None
        if primer:
            m = re.search(r'(Small|Large) (Rifle|Pistol)', primer)
            psize = (m.group(1) + ' ' + m.group(2)).lower() if m else None
        ev = ' | '.join(f'{k} {v}' for k, v in attrs.items())
        # any capacity / weight statement in the description?
        desc_lines = [l for l in text_lines(raw)
                      if re.search(r'(?i)\d[\d.,]*\s*(gr\.?|grains?)\s*(of\s*)?(water|H2O|H20)'
                                   r'|\d[\d.,]*\s*(cm3|cm³|ml)\b', l)]
        rec = {
            'brandId': 'lapua',
            'cartridge': attrs.get('Designation') or attrs.get('Caliber'),
            'sku': pn,
            'skuAsListed': pn_listed,
            'caseWeightGr': None,
            'waterCapacityGrH2O': None,
            'capacityCondition': 'unknown',
            'capacityTo': 'unknown',
            'primerSize': psize,
            'primerPocketType': None,
            'basis': 'manufacturer',
            'productName': title,
            'bulletDiameter': attrs.get('Bullet diameter'),
            'sources': [src(u, 'manufacturer')],
            'evidence': ev,
            'notes': 'Lapua product page lists Caliber, Product no., Primer, Purpose and Bullet diameter only; '
                     'no case weight or water capacity is published on it.',
        }
        if desc_lines:
            rec['notes'] += ' Description mentions capacity: ' + ' / '.join(desc_lines)
        if pn in cat:
            rec['sources'].append(src(LAPUA_CATALOG, 'manufacturer', cat_page))
            rec['evidence'] += ' || catalog: ' + cat[pn]['evidence']
            rec['catalogName'] = cat[pn]['catalogName']
            cm = re.search(r'\((Small|Large) Rifle Primer\)', cat[pn]['catalogName'] or '')
            if cm and psize and (cm.group(1) + ' rifle').lower() != psize:
                rec['conflicts'] = [{'field': 'primerSize', 'values': [
                    {'value': psize, 'source': u},
                    {'value': (cm.group(1) + ' rifle').lower(), 'source': LAPUA_CATALOG}]}]
        cases.append(rec)
    # catalog-only entries (product numbers listed in the catalog but no product page parsed)
    for pn, c in cat.items():
        if pn in seen:
            continue
        cases.append({
            'brandId': 'lapua', 'cartridge': c['catalogName'], 'sku': pn,
            'caseWeightGr': None, 'waterCapacityGrH2O': None,
            'capacityCondition': 'unknown', 'capacityTo': 'unknown',
            'primerSize': ('small rifle' if 'Small Rifle Primer' in (c['catalogName'] or '') else
                           'large rifle' if 'Large Rifle Primer' in (c['catalogName'] or '') else None),
            'primerPocketType': None, 'basis': 'manufacturer',
            'bulletDiameter': c['catalogCaliber'],
            'sources': [src(LAPUA_CATALOG, 'manufacturer', cat_page)],
            'evidence': c['evidence'],
            'notes': 'Listed in the Lapua 2026 catalog case table (caliber + product no. only); '
                     'no product page was found in the cartridge-cases listing.',
        })
    brand = None
    ap = os.path.join(LDIR, 'about.html')
    if os.path.exists(ap):
        docs.append({'url': LAPUA_ABOUT, 'localPath': ap, 'title': 'About Lapua', 'date': None})
        brand = (ap, para_lines(read(ap)))
    return cases, docs, brand


# --------------------------------------------------------------------------- Norma
NORMA = 'https://www.norma-ammunition.com'
NORMA_SITEMAP = NORMA + '/products/sitemap/sitemap-products-en.xml'
NORMA_ABOUT = NORMA + '/about-norma'
NORMA_RELOAD = [NORMA + '/reloading/norma-brass-308-win', NORMA + '/reloading/norma-brass-6-5-creedmoor',
                NORMA + '/reloading/norma-brass-300-win-mag']
NDIR = os.path.join(SRC, 'norma')


def norma_brass_urls():
    p = os.path.join(NDIR, 'sitemap-products-en.xml')
    if not os.path.exists(p):
        return []
    urls = re.findall(r'<loc>([^<]+)</loc>', read(p))
    return [htmlmod.unescape(u) for u in urls if '/products/components/norma-brass/' in u]


def norma_local(u):
    return os.path.join(NDIR, 'products', u.rstrip('/').rsplit('/', 1)[-1] + '.html')


def download_norma():
    fetch(NORMA_SITEMAP, os.path.join(NDIR, 'sitemap-products-en.xml'))
    for u in norma_brass_urls():
        fetch(u, norma_local(u))
    fetch(NORMA_ABOUT, os.path.join(NDIR, 'about-norma.html'))
    for u in NORMA_RELOAD:
        fetch(u, os.path.join(NDIR, 'reloading', u.rsplit('/', 1)[-1] + '.html'))


def norma_jsonld(raw):
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', raw, re.S):
        try:
            d = json.loads(m.group(1))
        except Exception:
            continue
        if isinstance(d, dict) and d.get('@type') == 'Product':
            return d
    return None


def norma_parse():
    cases, docs = [], []
    p = os.path.join(NDIR, 'sitemap-products-en.xml')
    if os.path.exists(p):
        docs.append({'url': NORMA_SITEMAP, 'localPath': p, 'title': 'Norma products sitemap (en)', 'date': None})
    for u in norma_brass_urls():
        lp = norma_local(u)
        if not os.path.exists(lp):
            continue
        raw = read(lp)
        d = norma_jsonld(raw)
        # Product JSON-LD is also embedded (escaped) in the RSC payload; additionalProperty carries Caliber
        props = {}
        m = re.search(r'additionalProperty\\+":\[(.*?)\]', raw)
        if m:
            blob = m.group(1).replace('\\\\\\"', '"').replace('\\"', '"').replace('\\\\', '')
            for pm in re.finditer(r'"name":"([^"]+)","value":"([^"]*)"', blob):
                props[pm.group(1)] = pm.group(2)
        if not d:
            continue
        docs.append({'url': u, 'localPath': lp, 'title': d.get('name'), 'date': None})
        ev = f'name: {d.get("name")} | sku: {d.get("sku")}'
        if props:
            ev += ' | ' + ' | '.join(f'{k}: {v}' for k, v in props.items())
        manu = (d.get('manufacturer') or {}).get('name') if isinstance(d.get('manufacturer'), dict) else None
        cases.append({
            'brandId': 'norma',
            'cartridge': props.get('Caliber') or re.sub(r'^Norma Brass\s+', '', d.get('name') or '') or None,
            'sku': d.get('sku'),
            'caseWeightGr': None, 'waterCapacityGrH2O': None,
            'capacityCondition': 'unknown', 'capacityTo': 'unknown',
            'primerSize': None, 'primerPocketType': None,
            'basis': 'manufacturer',
            'productName': d.get('name'),
            'productType': props.get('Product Type'),
            'manufacturerName': manu,
            'sources': [src(u, 'manufacturer')],
            'evidence': ev,
            'notes': 'Norma brass product page (schema.org Product data) gives name, product no. and caliber only; '
                     'no primer size, case weight or capacity is published. Norma /reloading/ pages checked '
                     '(308 Win, 6.5 Creedmoor, 300 Win Mag) show "Load data being updated".',
        })
    reload_status = []
    for u in NORMA_RELOAD:
        rp = os.path.join(NDIR, 'reloading', u.rsplit('/', 1)[-1] + '.html')
        if os.path.exists(rp):
            upd = 'Load data being updated' in read(rp)
            reload_status.append(upd)
            docs.append({'url': u, 'localPath': rp, 'title': 'Norma reloading data page (shows "Load data being '
                         'updated")' if upd else 'Norma reloading data page', 'date': None})
    if reload_status and not all(reload_status):
        print('  ! a Norma reloading page now has data - review it for case data', file=sys.stderr)
    brand = None
    ap = os.path.join(NDIR, 'about-norma.html')
    if os.path.exists(ap):
        docs.append({'url': NORMA_ABOUT, 'localPath': ap, 'title': 'About Norma', 'date': None})
        brand = (ap, para_lines(re.sub(r'\{\\"_id\\":\\"reseller-[^}]*\}', '', read(ap))))
    return cases, docs, brand


# --------------------------------------------------------------------------- Peterson
PET = 'https://petersoncartridge.com'
PET_DATA = PET + '/ballistician-testing-data'
PET_TECH = PET + '/technical-resources'
PET_DRAW = PET + '/drawings-and-prints'
PET_ABOUT = PET + '/about'
PDIR = os.path.join(SRC, 'peterson')


def download_peterson():
    fetch(PET_DATA, os.path.join(PDIR, 'ballistician-testing-data.html'))
    fetch(PET_TECH, os.path.join(PDIR, 'technical-resources.html'))
    fetch(PET_DRAW, os.path.join(PDIR, 'drawings-and-prints.html'))
    fetch(PET_ABOUT, os.path.join(PDIR, 'about.html'))


PET_COLS = ['Caliber', 'Ballistician Inspection Date', 'Lot #', 'QC #', 'Average Empty Weight (Grains)',
            'Average Internal Volume (Grains of H20)', 'Shoulder Diameter', 'Base Diameter',
            'Neck Wall Thickness', 'Loaded Neck Diameter', 'AMP Aztec Code', 'AMP Pilot #', 'AMP Machine']


def peterson_parse():
    p = os.path.join(PDIR, 'ballistician-testing-data.html')
    docs, cases = [], []
    if not os.path.exists(p):
        return cases, docs, None
    raw = read(p)
    docs.append({'url': PET_DATA, 'localPath': p, 'title': 'Peterson Cartridge - Ballistician Testing Data',
                 'date': None})
    tabs = [t for t in tables_of(raw) if t and t[0][:2] == ['Caliber', 'Ballistician Inspection Date']]
    assert len(tabs) == 1, 'Peterson table not found'
    head, rows = tabs[0][0], tabs[0][1:]
    assert head == PET_COLS, head
    intro = [l for l in text_lines(raw) if 'in-house ballistician has begun' in l]
    for r in rows:
        if len(r) != len(head):
            print('  ! Peterson row with', len(r), 'cells:', r, file=sys.stderr)
            continue
        d = dict(zip(head, r))
        cal = d['Caliber']
        srp = '(SRP)' in cal
        wt = num(d['Average Empty Weight (Grains)'])
        vol = num(d['Average Internal Volume (Grains of H20)'])

        def f(k):
            return num(d[k])
        cases.append({
            'brandId': 'peterson',
            'cartridge': ws(re.sub(r'\(SRP\)', '', cal)),
            'cartridgeKey': ws(re.sub(r'\s*\((Winchester Short Magnum|Remington Ultra Magnum|Shooting Times '
                                      r'Westerner)\)', '', re.sub(r'\(SRP\)', '', cal))).replace('33 XC', '33XC'),
            'sku': None,
            'caseWeightGr': wt,
            'waterCapacityGrH2O': vol,
            'capacityCondition': 'new',
            'capacityConditionInferred': True,
            'capacityTo': 'unknown',
            'primerSize': 'small rifle' if srp else None,
            'primerPocketType': None,
            'basis': 'manufacturer',
            'lot': d['Lot #'],
            'qcNumber': d['QC #'],
            'inspectionDate': d['Ballistician Inspection Date'],
            'shoulderDiameterIn': f('Shoulder Diameter'),
            'baseDiameterIn': f('Base Diameter'),
            'neckWallThicknessIn': f('Neck Wall Thickness'),
            'loadedNeckDiameterIn': f('Loaded Neck Diameter'),
            'calibreAsListed': cal,
            'sources': [src(PET_DATA, 'manufacturer')],
            'evidence': ' | '.join(f'{k}: {v}' for k, v in d.items()),
            'notes': ('Per-lot manufacturer QC data (lot averages). Column header reads "Average Internal Volume '
                      '(Grains of H20)"; Peterson does not state the fill point (mouth vs neck) nor sample size, so '
                      'capacityTo is "unknown". capacityCondition "new" is INFERRED (the page describes inspection data '
                      'for production lots of casings; it does not literally say "new" or "unfired"). Primer size only set where the listed caliber carries '
                      '"(SRP)"; other lots do not state the primer size in this table. Diameters/thickness are '
                      'assumed inches (column headers carry no unit).'),
        })
    tp = os.path.join(PDIR, 'technical-resources.html')
    brand = None
    if os.path.exists(tp):
        docs.append({'url': PET_TECH, 'localPath': tp, 'title': 'Peterson Cartridge - Technical Resources',
                     'date': None})
        brand = (tp, text_lines(read(tp)) + intro)
    abp = os.path.join(PDIR, 'about.html')
    if os.path.exists(abp):
        docs.append({'url': PET_ABOUT, 'localPath': abp, 'title': 'About Peterson Cartridge', 'date': None})
        brand = (abp, para_lines(read(abp)) + (brand[1] if brand else []))
    dp = os.path.join(PDIR, 'drawings-and-prints.html')
    if os.path.exists(dp):
        docs.append({'url': PET_DRAW, 'localPath': dp, 'title': 'Peterson Cartridge - Technical Drawings And Prints',
                     'date': None})
    return cases, docs, brand


# --------------------------------------------------------------------------- Starline
STAR = 'https://www.starlinebrass.com'
STAR_LIST = [STAR + '/rifle-brass/', STAR + '/pistol-brass/']
STAR_ABOUT = STAR + '/about/'
SDIR = os.path.join(SRC, 'starline')


def starline_listing():
    """[(part#, caliber, url, category)] from listing pages."""
    out = []
    for u in STAR_LIST:
        p = os.path.join(SDIR, u.rstrip('/').rsplit('/', 1)[-1] + '.html')
        if not os.path.exists(p):
            continue
        raw = read(p)
        for m in re.finditer(r'<a href="([^"]+)" class="product-link">\s*<span class="part-number">(#\d+)</span>\s*</a>'
                             r'\s*<a href="\1" class="product-link">\s*<span class="caliber">([^<]+)</span>', raw):
            out.append((m.group(2), ws(htmlmod.unescape(m.group(3))), m.group(1), u))
    return out


def starline_local(u):
    return os.path.join(SDIR, 'products', urlparse(u).path.strip('/').replace('/', '_') + '.html')


def download_starline():
    for u in STAR_LIST:
        fetch(u, os.path.join(SDIR, u.rstrip('/').rsplit('/', 1)[-1] + '.html'))
    for part, cal, u, _ in starline_listing():
        if '?' in u:
            continue  # robots.txt: Disallow /*?*
        fetch(u, starline_local(u))
    fetch(STAR_ABOUT, os.path.join(SDIR, 'about.html'))


def starline_parse():
    cases, docs = [], []
    for u in STAR_LIST:
        p = os.path.join(SDIR, u.rstrip('/').rsplit('/', 1)[-1] + '.html')
        if os.path.exists(p):
            docs.append({'url': u, 'localPath': p, 'title': 'Starline Brass - ' + u.rstrip('/').rsplit('/', 1)[-1],
                         'date': None})
    seen = set()
    for part, cal, u, cat in starline_listing():
        if part in seen:
            continue
        seen.add(part)
        lp = starline_local(u)
        rec = {
            'brandId': 'starline', 'cartridge': re.sub(r'\s+Brass$', '', cal), 'sku': part.lstrip('#'),
            'caseWeightGr': None, 'waterCapacityGrH2O': None,
            'capacityCondition': 'unknown', 'capacityTo': 'unknown',
            'primerSize': None, 'primerPocketType': None, 'basis': 'manufacturer',
            'category': 'rifle' if 'rifle' in cat else 'pistol',
            'sources': [src(cat, 'manufacturer')],
            'evidence': f'listing: {part} {cal}',
            'notes': 'Starline publishes part number, name, primer type and a case-length range on product pages; '
                     'no case weight or water capacity.',
        }
        if os.path.exists(lp):
            raw = read(lp)
            L = text_lines(raw)
            docs.append({'url': u, 'localPath': lp, 'title': 'Starline ' + cal, 'date': None})
            try:
                i = next(k for k, l in enumerate(L) if l == part)
            except StopIteration:
                i = None
            if i is not None:
                # header block: "#2440" / "- 308 Win Brass" / [aliases] / "2.002 - 2.009 O.A.L." / "Large Rifle Primer"
                PRIMER_RX = (r'(?i)^(magnum\s+)?(small|large)\s+(rifle|pistol)(\s+magnum)?'
                             r'(\s+or\s+(small|large)\s+(rifle|pistol)(\s+magnum)?)?\s+primers?\b.*$'
                             r'|^.*\bberdan\b.*$')
                window = L[i:i + 7]
                pidx = next((k for k, l in enumerate(window) if k >= 2 and re.match(PRIMER_RX, l)), None)
                lidx = next((k for k, l in enumerate(window) if k >= 2 and re.search(r'O\.A\.L\.', l)), None)
                stop = pidx if pidx is not None else lidx if lidx is not None else 1
                block = window[:stop + 1]
                prim = [block[pidx]] if pidx is not None else []
                lens = [block[lidx]] if lidx is not None and lidx <= stop else []
                if prim:
                    sizes = re.findall(r'(?i)\b(small|large)\s+(rifle|pistol)(\s+magnum)?\b', prim[0])
                    mag_lead = re.match(r'(?i)magnum\b', prim[0]) is not None
                    parts = []
                    for sz, kind, mg in sizes:
                        ps = (sz + ' ' + kind).lower()
                        if mg or (mag_lead and len(sizes) == 1):
                            ps += ' magnum'
                        parts.append(ps)
                    if parts:
                        rec['primerSize'] = ' or '.join(parts)
                    rec['primerAsListed'] = prim[0]
                if lens:
                    m = re.search(r'(\d*\.\d+)\s*[”"]?\s*-\s*(\d*\.\d+)\s*[”"]?\s*-?\s*O\.A\.L\.', lens[0])
                    if m:
                        rec['caseLengthMinIn'] = float(m.group(1))
                        rec['caseLengthMaxIn'] = float(m.group(2))
                    else:
                        m = re.search(r'(\d*\.\d+)\s*[”"]?\s*O\.A\.L\.', lens[0])
                        if m:
                            rec['caseLengthIn'] = float(m.group(1))
                    rec['caseLengthAsListed'] = lens[0]
                if len(block) > 2 and not re.search(r'O\.A\.L\.', block[2]) and not re.match(PRIMER_RX, block[2]):
                    rec['aliases'] = block[2]
                rec['productName'] = ws(block[1].lstrip('- ')) if len(block) > 1 else None
                rec['evidence'] = ' | '.join(block)
                rec['sources'] = [src(u, 'manufacturer'), src(cat, 'manufacturer')]
                rec['notes'] += (' "O.A.L." on Starline pages is the case length range (in inches) as printed.'
                                 if lens else '')
        cases.append(rec)
    ap = os.path.join(SDIR, 'about.html')
    brand = None
    if os.path.exists(ap):
        docs.append({'url': STAR_ABOUT, 'localPath': ap, 'title': 'Starline Brass - About', 'date': None})
        brand = (ap, para_lines(read(ap)))
    return cases, docs, brand


# --------------------------------------------------------------------------- AccurateShooter
AS = 'https://www.accurateshooter.com'
AS_INDEX = AS + '/cartridge-guides/'
ADIR = os.path.join(SRC, 'accurateshooter')


def as_guide_urls():
    p = os.path.join(ADIR, 'cat-cartridge-guides.html')
    if not os.path.exists(p):
        return []
    return sorted(set(re.findall(r'href="(https://www\.accurateshooter\.com/cartridge-guides/[^"]+/)"', read(p))))


def as_local(u):
    return os.path.join(ADIR, 'pages', urlparse(u).path.strip('/').replace('/', '_') + '.html')


def download_accurateshooter():
    fetch(AS_INDEX, os.path.join(ADIR, 'cat-cartridge-guides.html'))
    for u in as_guide_urls():
        fetch(u, as_local(u))


# headstamp name in a table -> (brandId, brand display name, extra note)
AS_BRANDS = {
    'Lapua (new lot)': ('lapua', 'Lapua', 'new lot'),
    'Lapua (old lot)': ('lapua', 'Lapua', 'old lot'),
    'Hornady': ('hornady', 'Hornady', None),
    'Federal': ('federal', 'Federal', None),
    "Lake City '04": ('lake-city', 'Lake City', "headstamp year '04"),
    'Lake City ’04': ('lake-city', 'Lake City', "headstamp year '04"),
    'Lake City 04': ('lake-city', 'Lake City', "headstamp year 04"),
    'Lake City 06': ('lake-city', 'Lake City', "headstamp year 06"),
    'Lake City 02': ('lake-city', 'Lake City', "headstamp year 02"),
    'WCC 99': ('wcc', 'WCC (Winchester military headstamp)', "headstamp WCC 99"),
    'WCC99': ('wcc', 'WCC (Winchester military headstamp)', "headstamp WCC99"),
    'IMG (Guatemalan)': ('img', 'IMG (Guatemalan)', None),
    'PMP': ('pmp', 'PMP', None),
    'Radway': ('radway', 'Radway Arsenal', None),
    'Radway Arsenal': ('radway', 'Radway Arsenal', None),
    'PMC': ('pmc', 'PMC', None),
    'Remington': ('remington', 'Remington', None),
    'Winchester': ('winchester', 'Winchester', None),
    'Sellier & Belloit': ('sellier-bellot', 'Sellier & Bellot', 'spelled "Sellier & Belloit" in source'),
    'Hirtenberger': ('hirtenberger', 'Hirtenberger', None),
    'Olympic': ('olympic', 'Olympic', None),
    'FNM 93-1': ('fnm', 'FNM', 'headstamp FNM 93-1'),
    'Norma 6XC': ('norma', 'Norma', None),
    'Norma 22-250': ('norma', 'Norma', 'reformed 22-250 brass'),
    'Remington 22-250': ('remington', 'Remington', 'reformed 22-250 brass'),
    'Winchester 22-250': ('winchester', 'Winchester', 'reformed 22-250 brass'),
    'Tubb 6XC (3rd Gen)': ('tubb-sss', 'Tubb / Superior Shooting Systems', '3rd generation'),
}


def as_parse_223(cases, docs):
    u = AS + '/cartridge-guides/223rem/'
    p = as_local(u)
    if not os.path.exists(p):
        return
    raw = read(p)
    L = text_lines(raw)
    foot1 = next((l for l in L if l.startswith('* Average case weight')), None)
    foot2 = next((l for l in L if l.startswith('** Case capacity of three sample cases')), None)
    assert foot1 and foot2, '223 footnotes missing'
    docs.append({'url': u, 'localPath': p, 'title': '.223 Remington Cartridge Guide (AccurateShooter.com)',
                 'date': None})
    for tab in tables_of(raw):
        flat = [c for r in tab for c in r]
        # (a) weight-uniformity table
        if tab and tab[0][:2] == ['Brass Manufacturer', 'Aver. Wt. (Sample)']:
            for r in tab[1:]:
                if len(r) != 4:
                    continue
                m = re.fullmatch(r'(\d+(?:\.\d+)?) \((\d+)\)', r[1])
                es = re.fullmatch(r'(\d+(?:\.\d+)?) ?gr', r[2])
                sd = re.fullmatch(r'(\d+(?:\.\d+)?) ?gr', r[3])
                if not m:
                    continue
                b = AS_BRANDS.get(r[0])
                cases.append({
                    'brandId': b[0] if b else None, 'brandAsListed': r[0], 'cartridge': '.223 Remington',
                    'sku': None, 'caseWeightGr': float(m.group(1)), 'waterCapacityGrH2O': None,
                    'capacityCondition': 'new' if 'new lot' in r[0] else 'unknown', 'capacityTo': 'unknown',
                    'primerSize': None, 'primerPocketType': None, 'basis': 'third-party measured',
                    'sampleSize': int(m.group(2)),
                    'caseWeightExtremeSpreadGr': float(es.group(1)) if es else None,
                    'caseWeightSdGr': float(sd.group(1)) if sd else None,
                    'measurementMethod': 'Average case weight of a sample (sample size in parentheses), extreme '
                                         'spread and standard deviation; AccurateShooter / Graymist table. Text says '
                                         '"new lots of Lapua .223 brass ... we measured 100 Lapua cases as opposed to '
                                         '50 with other brands". Condition of non-Lapua samples not stated for this '
                                         'table.',
                    'sources': [src(u, 'third-party')],
                    'evidence': 'Brass Manufacturer | Aver. Wt. (Sample) | Extreme Spread | Standard Deviation || '
                                + ' | '.join(r),
                    'notes': (b[2] if b and b[2] else None),
                })
        # (b) weight vs capacity (and .223 AI) table
        if '.223 Rem Case Weight vs. Capacity' in flat:
            section = '.223 Remington'
            for r in tab:
                if r == ['.223 Rem Case Weight vs. Capacity'] or (len(r) == 1 and 'Weight vs. Capacity' in r[0]):
                    section = '.223 Remington'
                    continue
                if len(r) >= 1 and r[0] == '.223 AI Case Capacities':
                    section = '.223 Remington Ackley Improved'
                    continue
                if len(r) != 3 or num(r[1]) is None or num(r[2]) is None:
                    continue
                b = AS_BRANDS.get(r[0])
                newlot = 'new lot' in r[0]
                if section == '.223 Remington':
                    cond = 'new' if newlot else 'fired'
                    meth = ('Weight: ' + foot1 + ' Capacity: ' + foot2)
                    note = ('Condition per footnote: sized, deprimed, once-fired brass except the new Lapua lot '
                            '(new). Capacity is the average of 3 cases closest to the brand average weight, '
                            'full-length sized, trimmed to 1.750 in, spent primer in pocket, distilled water to '
                            'top of case mouth.')
                else:
                    cond = 'fired'
                    meth = ('Table ".223 AI Case Capacities" (fire-formed .223 AI cases). Same table footnotes: '
                            + foot1 + ' ' + foot2)
                    note = ('.223 AI section of the same table; the cases had been fire-formed to .223 Ackley '
                            'Improved, so capacity is "fired". The footnote method (water to top of case mouth) '
                            'is assumed to apply to this section as well.')
                cases.append({
                    'brandId': b[0] if b else None, 'brandAsListed': r[0], 'cartridge': section,
                    'sku': None, 'caseWeightGr': num(r[1]), 'waterCapacityGrH2O': num(r[2]),
                    'capacityCondition': cond, 'capacityTo': 'case mouth',
                    'primerSize': None, 'primerPocketType': None, 'basis': 'third-party measured',
                    'sampleSize': 3, 'measurementMethod': meth,
                    'sources': [src(u, 'third-party')],
                    'evidence': ('Case Manufacturer | Case Weight* | H20 Capacity** || ' + ' | '.join(r)),
                    'notes': ((b[2] + '. ') if b and b[2] else '') + note,
                })


def as_parse_6xc(cases, docs):
    u = AS + '/cartridge-guides/6xc-for-competitive-shooting/'
    p = as_local(u)
    if not os.path.exists(p):
        return
    raw = read(p)
    L = text_lines(raw)
    intro = next((l for l in L if l.startswith('Internal capacity of Remington 22-250')), None)
    assert intro
    docs.append({'url': u, 'localPath': p, 'title': '6XC for Competitive Shooting (AccurateShooter.com)',
                 'date': None})
    for tab in tables_of(raw):
        if not tab or not tab[0] or tab[0][0] != 'Brass Type':
            continue
        head = tab[0]
        if head[1:3] != ['Water Capacity (Grains)', 'Avg. Case Weight (Grains)']:
            continue
        for r in tab[1:]:
            if len(r) != len(head) or num(r[1]) is None:
                continue
            b = AS_BRANDS.get(r[0])
            cases.append({
                'brandId': b[0] if b else None, 'brandAsListed': r[0], 'cartridge': '6XC',
                'sku': None, 'caseWeightGr': num(r[2]), 'waterCapacityGrH2O': num(r[1]),
                'capacityCondition': 'fired', 'capacityTo': 'unknown',
                'primerSize': None, 'primerPocketType': None, 'basis': 'third-party measured',
                'neckThicknessAsListed': r[3], 'loadedNeckDiameterAsListed': r[4],
                'measurementMethod': 'TABLE ONE - Case Capacity Comparison (German Salazar). ' + intro,
                'sources': [src(u, 'third-party')],
                'evidence': ' | '.join(head) + ' || ' + ' | '.join(r),
                'notes': ((b[2] + '. ') if b and b[2] else '') +
                         'All cases fire-formed in the author\'s 6XC chamber (22-250 brass reformed to 6XC). '
                         'Fill point (mouth vs neck base) and sample size are not stated.',
            })


# prose statements: (page, sentence-start anchor, regex, [(group, brandId, brandAsListed, cartridge, cond, note)])
AS_PROSE = [
    ('/cartridge-guides/308win/', 'The most important thing to remember about military brass',
     r'cases hold (\d+(?:\.\d+)?) grains of H20 on average compared to (\d+(?:\.\d+)?) grains for fire-formed Winchester',
     [(2, 'winchester', 'fire-formed Winchester', '.308 Winchester', 'fired',
       'Reader "Montana Marine" report quoted by AccurateShooter; average of his fire-formed cases. Same report: '
       'his fire-formed military-surplus cases (no single headstamp) hold the first value on average.')]),
    ('/cartridge-guides/308win/', 'The most important thing to remember about military brass',
     r'Fired, my IMI Match brass runs with an ICC of (\d+(?:\.\d+)?)gr .*?LAPUA runs an average of (\d+(?:\.\d+)?)gr '
     r'and Federal runs an average of (\d+(?:\.\d+)?)gr ICC',
     [(1, 'imi', 'IMI Match', '.308 Winchester', 'fired',
       'Reader Kevin Beggs quoted by AccurateShooter: "Fired, my IMI Match brass runs with an ICC of 55.0gr" '
       '(ICC = internal case capacity; unit "gr" = grains of water assumed from context). Bumping the shoulder '
       'back .001" gave 54.0gr per the same quote.'),
      (2, 'lapua', 'LAPUA', '.308 Winchester', 'unknown',
       'Same quote (Kevin Beggs): "LAPUA runs an average of 54.4gr ... ICC". Condition not stated explicitly for '
       'Lapua (the sentence follows his fired IMI measurement).'),
      (3, 'federal', 'Federal', '.308 Winchester', 'unknown',
       'Same quote (Kevin Beggs): "Federal runs an average of 54.3gr ICC". Condition not stated explicitly.')]),
]


def as_parse_prose(cases, docs):
    for path, anchor, rx, items in AS_PROSE:
        u = AS + path
        p = as_local(u)
        if not os.path.exists(p):
            continue
        L = text_lines(read(p))
        line = next((l for l in L if l.startswith(anchor)), None)
        if not line:
            print('  ! prose anchor not found', path, anchor, file=sys.stderr)
            continue
        m = re.search(rx, line)
        if not m:
            print('  ! prose regex not matched', path, rx, file=sys.stderr)
            continue
        if not any(d['url'] == u for d in docs):
            docs.append({'url': u, 'localPath': p, 'title': 'AccurateShooter cartridge guide ' + path, 'date': None})
        for g, bid, blisted, cart, cond, note in items:
            cases.append({
                'brandId': bid, 'brandAsListed': blisted, 'cartridge': cart, 'sku': None,
                'caseWeightGr': None, 'waterCapacityGrH2O': float(m.group(g)),
                'capacityCondition': cond, 'capacityTo': 'unknown',
                'primerSize': None, 'primerPocketType': None, 'basis': 'third-party measured',
                'measurementMethod': 'Reader report quoted in prose (method, fill point and sample size not stated).',
                'sources': [src(u, 'third-party')],
                'evidence': line,
                'notes': note,
            })
    # Lapua 6mm BR: a stated range, kept as range, single value null
    u = AS + '/cartridge-guides/6mmbr/'
    p = as_local(u)
    if os.path.exists(p):
        L = text_lines(read(p))
        line = next((l for l in L if 'The case capacity of Lapua brass is about' in l), None)
        if line:
            m = re.search(r'The case capacity of Lapua brass is about (\d+(?:\.\d+)?)-(\d+(?:\.\d+)?) grains of H20, '
                          r'after fire-forming\.', line)
            sent = re.search(r'[^.]*The case capacity of Lapua brass is about.*?after fire-forming\.'
                             r'[^.]*\.[^.]*\.', line)
            if m:
                docs.append({'url': u, 'localPath': p, 'title': '6mm BR Norma Cartridge Guide (AccurateShooter.com)',
                             'date': None})
                cases.append({
                    'brandId': 'lapua', 'brandAsListed': 'Lapua', 'cartridge': '6mm BR Norma', 'sku': None,
                    'caseWeightGr': None, 'waterCapacityGrH2O': None,
                    'waterCapacityRangeGrH2O': [float(m.group(1)), float(m.group(2))],
                    'capacityCondition': 'fired', 'capacityTo': 'unknown',
                    'primerSize': None, 'primerPocketType': None, 'basis': 'third-party measured',
                    'measurementMethod': 'Editorial statement of an approximate range ("about"), after fire-forming; '
                                         'no method stated.',
                    'sources': [src(u, 'third-party')],
                    'evidence': ws(sent.group(0)) if sent else line,
                    'notes': 'Range only ("about 38-39.5 grains of H20, after fire-forming ... depends on your gun\'s '
                             'chamber and the brass lot"); single-value field left null.',
                })


def accurateshooter_parse():
    cases, docs = [], []
    p = os.path.join(ADIR, 'cat-cartridge-guides.html')
    if os.path.exists(p):
        docs.append({'url': AS_INDEX, 'localPath': p, 'title': 'AccurateShooter.com - Cartridge Guides index',
                     'date': None})
    as_parse_223(cases, docs)
    as_parse_6xc(cases, docs)
    as_parse_prose(cases, docs)
    return cases, docs


# --------------------------------------------------------------------------- brands
def find_line(lines, rx):
    for l in lines or []:
        if re.search(rx, l):
            return l
    return None


def build_brands(lapua_b, norma_b, pet_b, star_b, norma_cases, as_cases):
    brands = []

    def add(rec):
        brands.append(rec)

    # Lapua
    if lapua_b:
        ap, L = lapua_b
        ev = [l for l in [find_line(L, r'is part of the large Nammo Group'),
                          find_line(L, r'All Lapua centerfire components and cartridges are produced'),
                          find_line(L, r'Nammo is an international aerospace and defense company')] if l]
        country = None
        if any(re.search(r'centerfire components and cartridges are produced at the factory site located in '
                         r'Lapua, Finland', l) for l in ev):
            country = 'Finland'
        parent = None
        for l in ev:
            m = re.search(r'is part of the large (Nammo Group)', l)
            if m:
                parent = m.group(1)
        add({'id': 'lapua', 'name': 'Lapua', 'country': country, 'parent': parent,
             'productLines': ['Lapua centerfire cartridge cases'],
             'notes': ('Official company name per about page: Nammo Lapua Oy (centerfire, Lapua, Finland) and '
                       'Nammo Schönebeck (rimfire, Germany). Country = where centerfire components (incl. cases) '
                       'are produced.') if ev else None,
             'sources': [src(LAPUA_ABOUT, 'manufacturer'), src(LAPUA_CATALOG, 'manufacturer', lapua_catalog_cases()[1])],
             'evidence': ' || '.join(dict.fromkeys(ev)) + ' || catalog heading: LAPUA® CENTERFIRE CASES'})
    # Norma
    if norma_b:
        ap, L = norma_b
        manu = next((c.get('manufacturerName') for c in norma_cases if c.get('manufacturerName')), None)
        ev = [l for l in [find_line(L, r'^Headquarters and production are located in Åmotfors'),
                          find_line(L, r'^Norma was founded in 1902')] if l]
        footer = find_line(L, r'^Beretta Holding$')
        country = 'Sweden' if any(re.search(r'located in Åmotfors, Värmland in the middle of Sweden', l)
                                  for l in ev) else None
        add({'id': 'norma', 'name': 'Norma', 'country': country, 'parent': None,
             'productLines': ['Norma Brass'],
             'notes': ((f'schema.org manufacturer on brass product pages: {manu}. ' if manu else '') +
                       ('The site footer shows a "Beretta Holding" group link, but no page fetched here states the '
                        'ownership in words, so parent is left null.' if footer else '')).strip() or None,
             'sources': [src(NORMA_ABOUT, 'manufacturer')] + ([norma_cases[0]['sources'][0]] if norma_cases else []),
             'evidence': ' || '.join(dict.fromkeys(ev)) + (f' || manufacturer: {manu}' if manu else '')})
    # Peterson
    if pet_b:
        ap, L = pet_b
        ev = [l for l in [find_line(L, r'Founded in Pittsburgh, Pennsylvania'),
                          find_line(L, r'proud member of the Peterson Brothers, Inc\. team'),
                          find_line(L, r'in-house ballistician has begun')] if l]
        country = 'United States' if any(re.search(r'Pittsburgh, Pennsylvania USA', l) for l in ev) else None
        parent = None
        for l in ev:
            m = re.search(r'proud member of the (Peterson Brothers, Inc\.) team', l)
            if m:
                parent = m.group(1)
        add({'id': 'peterson', 'name': 'Peterson Cartridge', 'country': country, 'parent': parent,
             'productLines': ['Peterson rifle brass (casings), incl. small-rifle-primer (SRP) variants'],
             'notes': 'Publishes per-lot QC data (average empty weight, average internal volume in grains of H2O) '
                      'on its Ballistician Testing Data page. Technical drawings are PDFs under /files/, '
                      'disallowed by robots.txt, not fetched.',
             'sources': [src(PET_ABOUT, 'manufacturer'), src(PET_DATA, 'manufacturer')],
             'evidence': ' || '.join(ev)})
    # Starline
    if star_b:
        ap, L = star_b
        ev = [l for l in [find_line(L, r'Made in USA Since 1976'),
                          find_line(L, r'Starline Brass was founded in 1976'),
                          find_line(L, r'Starline relocated to Sedalia, Missouri'),
                          find_line(L, r'remains a family-owned business')] if l]
        country = 'United States' if any(re.search(r'Made in USA|Sedalia, Missouri', l) for l in ev) else None
        add({'id': 'starline', 'name': 'Starline Brass', 'country': country, 'parent': None,
             'productLines': ['Rifle Brass', 'Pistol Brass'],
             'notes': ('About page: founded 1976 (West Covina, California), relocated 1992 to Sedalia, Missouri; '
                       'family-owned. No parent company stated.') if len(ev) >= 3 else None,
             'sources': [src(STAR_ABOUT, 'manufacturer'), src(STAR_LIST[0], 'manufacturer'),
                         src(STAR_LIST[1], 'manufacturer')],
             'evidence': ' || '.join(dict.fromkeys(ev)) if ev else 'Rifle Brass | Pistol Brass (site navigation)'})
    # Alpha Munitions: blocked; no record (nothing stated by an accessible source)
    # third-party headstamps named in AccurateShooter tables
    have = {b['id'] for b in brands}
    for c in as_cases:
        bid = c.get('brandId')
        if not bid or bid in have:
            continue
        name = next((v[1] for k, v in AS_BRANDS.items() if v[0] == bid), c.get('brandAsListed'))
        have.add(bid)
        add({'id': bid, 'name': name, 'country': None, 'parent': None, 'productLines': [],
             'notes': 'Headstamp named in a third-party (AccurateShooter.com) measurement table; no maker page '
                      'consulted, so country/parent are not stated.',
             'sources': c['sources'], 'evidence': c['evidence']})
    return brands


# --------------------------------------------------------------------------- conflicts / stats
def add_conflicts(cases):
    """Same brand + cartridge + condition with different capacity/weight from different documents."""
    groups = {}
    for c in cases:
        if c['basis'] != 'third-party measured' and c['brandId'] != 'lapua':
            continue
        key = (c['brandId'], (c['cartridge'] or '').lower().replace('.', '').strip())
        groups.setdefault(key, []).append(c)
    for key, cs in groups.items():
        for field in ('waterCapacityGrH2O', 'caseWeightGr'):
            vals = [(c[field], c['sources'][0]['url'], c.get('brandAsListed'), c['capacityCondition'])
                    for c in cs if c.get(field) is not None]
            urls = {v[1] for v in vals}
            distinct = {v[0] for v in vals}
            if len(urls) > 1 and len(distinct) > 1:
                for c in cs:
                    if c.get(field) is None:
                        continue
                    c.setdefault('conflicts', []).append({
                        'field': field,
                        'values': [{'value': v[0], 'source': v[1], 'asListed': v[2], 'condition': v[3]}
                                   for v in vals]})


def peterson_stats(cases):
    by = {}
    for c in cases:
        if c['brandId'] == 'peterson':
            by.setdefault((c['cartridgeKey'], c['primerSize']), []).append(c)
    out = []
    for (cart, ps), cs in sorted(by.items(), key=lambda kv: (kv[0][0], kv[0][1] or '')):
        w = [c['caseWeightGr'] for c in cs if c['caseWeightGr'] is not None]
        v = [c['waterCapacityGrH2O'] for c in cs if c['waterCapacityGrH2O'] is not None]

        def st(xs):
            if not xs:
                return None
            m0 = statistics.median(xs)
            # values > 25 % away from the median are treated as suspect source entries and left out of the
            # summary (they stay verbatim in the per-lot records, flagged)
            keep = [x for x in xs if len(xs) < 3 or abs(x - m0) / m0 <= 0.25]
            return {'n': len(keep), 'min': min(keep), 'max': max(keep), 'median': round(statistics.median(keep), 3),
                    'excludedSuspect': sorted(set(xs) - set(keep)) or None}
        out.append({'brandId': 'peterson', 'cartridge': cart, 'primerSize': ps,
                    'calibresAsListed': sorted({c['calibreAsListed'] for c in cs}),
                    'lots': len(cs), 'caseWeightGr': st(w), 'waterCapacityGrH2O': st(v),
                    'derived': True,
                    'notes': 'Computed by this script from the per-lot Peterson records (no new data). Lots '
                             'grouped by cartridgeKey (listed caliber with "(SRP)" and long-form names such as '
                             '"(Winchester Short Magnum)" removed, "33 XC" == "33XC") and primer size. Different lot '
                             'generations can differ in design (e.g. older heavier cases), so min/max can span '
                             'design changes, not just lot variation.'})
    # flag lots far from their cartridge median (possible data-entry errors in the source table)
    med = {(s['cartridge'], s['primerSize']): s for s in out}
    for c in cases:
        if c['brandId'] != 'peterson':
            continue
        s = med[(c['cartridgeKey'], c['primerSize'])]
        flags = []
        for f in ('caseWeightGr', 'waterCapacityGrH2O'):
            if c[f] is None or not s[f] or s[f]['n'] < 3:
                continue
            m = s[f]['median']
            if m and abs(c[f] - m) / m > 0.25:
                flags.append(f'SUSPECT {f} {c[f]}: deviates >25% from the median {m} of {s[f]["n"]} lots of this '
                             f'cartridge; probably a data-entry error in the source table - do not use')
                c['suspectSourceValue'] = True
            elif m and abs(c[f] - m) / m > 0.05:
                flags.append(f'{f} {c[f]} deviates >5% from the median {m} of {s[f]["n"]} lots of this cartridge '
                             f'(may be a different case design/generation or lot)')
        if flags:
            c['qualityFlags'] = flags
    return out


# --------------------------------------------------------------------------- main
def build():
    lc, ld, lb = lapua_parse()
    nc, nd, nb = norma_parse()
    pc, pd, pb = peterson_parse()
    sc, sd, sb = starline_parse()
    ac, ad = accurateshooter_parse()
    cases = lc + nc + pc + sc + ac
    add_conflicts(cases)
    stats = peterson_stats(cases)
    brands = build_brands(lb, nb, pb, sb, nc, ac)
    docs = []
    seen = set()
    for d in ld + nd + pd + sd + ad:
        if d['url'] in seen:
            continue
        seen.add(d['url'])
        if d.get('date') is None and d['localPath'].endswith('.html') and os.path.exists(d['localPath']):
            raw = read(d['localPath'])
            m = (re.search(r'article:modified_time" content="([^"]+)"', raw)
                 or re.search(r'"dateModified":"([^"]+)"', raw))
            if m:
                d['date'] = m.group(1) + ' (modified, per page metadata)'
        docs.append(d)
    pet_dates = [c['inspectionDate'] for c in pc if c.get('inspectionDate')]
    if pet_dates:
        latest = max(pet_dates, key=lambda x: (x[-4:], x[:2], x[3:5]))
        for d in docs:
            if d['url'] == PET_DATA:
                d['date'] = f'table current through inspection date {latest} (latest row)'
    out = {
        'meta': {
            'key': 'brass',
            'retrieved': RETRIEVED,
            'script': '/home/user/ORKA/scripts/extract/brass.py',
            'documents': docs,
            'blocked': [
                {'url': 'https://www.alphamunitions.com/', 'reason': 'HTTP 429 "Vercel Security Checkpoint" '
                 '(bot challenge) for robots.txt and home page; not circumvented. No Alpha Munitions data.'},
                {'url': 'https://bulletin.accurateshooter.com/', 'reason': 'host not reachable from this session '
                 '(proxy CONNECT 403); AccurateShooter Daily Bulletin brass reviews not used.'},
                {'url': 'https://forum.accurateshooter.com/', 'reason': 'host not in allowed list; forum posts not used.'},
                {'url': 'https://petersoncartridge.com/files/content/*.pdf',
                 'reason': 'robots.txt Disallow: /files/ (drawings, shooter cards, load data PDFs); not fetched.'},
            ],
            'notes': (
                'Case data for cartridge brass. Manufacturer case weight / water capacity is only published by '
                'Peterson (per-lot QC table; "Average Internal Volume (Grains of H20)", fill point not stated). '
                'Lapua, Norma and Starline product pages publish product numbers, calibers and (Lapua, Starline) '
                'primer size, but no weight/capacity, so those fields are null. Third-party measurements come from '
                'AccurateShooter.com cartridge guides; measurement methods are recorded per record. '
                'Peterson per-lot values are verbatim; "petersonStats" is derived (min/median/max) and flagged '
                'derived. qualityFlags mark Peterson lots deviating >5% from their cartridge median (verbatim '
                'values kept); "SUSPECT" flags (>25% off the median, e.g. 375 CheyTac lot C160 listed with 59.4 gr '
                'H2O vs ~160 for all other lots) mark probable source data-entry errors, set suspectSourceValue=true '
                'and are excluded from petersonStats. Water capacity varies with lot, condition (new vs fired), '
                'chamber and fill point; never treat one record as a universal case volume. primerSize vocabulary: '
                '"small rifle", "large rifle", "small pistol", "large pistol", optional " magnum", or "X or Y" when '
                'the maker lists two options. Crawl: robots.txt of every host read first and obeyed (Starline '
                'Disallow /*?* -> no query URLs; Peterson Disallow /files/ -> PDFs skipped; AccurateShooter '
                'Disallow /wp-content/ -> nothing fetched there); >=1.5 s between requests per host; plain curl '
                'default user agent.'),
        },
        'brands': brands,
        'cases': cases,
        'petersonStats': stats,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f'wrote {OUT}: {len(brands)} brands, {len(cases)} cases, {len(stats)} peterson stats, '
          f'{len(docs)} documents', file=sys.stderr)
    return out


def fmt_num(x):
    s = repr(x)
    return s[:-2] if s.endswith('.0') else s


def check():
    d = json.load(open(OUT, encoding='utf-8'))
    cases = d['cases']
    from collections import Counter
    print('brands:', len(d['brands']), 'cases:', len(cases))
    print('by brand/basis:', Counter((c['brandId'], c['basis']) for c in cases))
    bad = 0
    for c in cases:
        ev = c['evidence']
        for f in ('caseWeightGr', 'waterCapacityGrH2O'):
            v = c.get(f)
            if v is None:
                continue
            cands = {fmt_num(v), f'{v:.1f}', f'{v:.2f}', f'{v:.3f}'.rstrip('0')}
            if not any(re.search(r'(?<![\d.])' + re.escape(s) + r'(?![\d])', ev) for s in cands):
                bad += 1
                print('  !! value not in evidence', f, v, ev[:200])
        if c.get('sku') and c['sku'] not in ev and c.get('skuAsListed', c['sku']) not in ev:
            bad += 1
            print('  !! sku not in evidence', c['sku'], ev[:150])
        if c.get('primerAsListed') and c['primerAsListed'] not in ev:
            bad += 1
            print('  !! primer not in evidence', c['primerAsListed'])
        for k in ('sources', 'evidence', 'capacityCondition', 'capacityTo', 'basis'):
            if k not in c or c[k] in (None, '', []):
                bad += 1
                print('  !! missing', k, c.get('brandId'), c.get('cartridge'))
        if c['capacityCondition'] not in ('new', 'fired', 'unknown'):
            bad += 1
        if c['capacityTo'] not in ('case mouth', 'base of neck', 'unknown'):
            bad += 1
        if c['basis'] not in ('manufacturer', 'third-party measured'):
            bad += 1
        if c.get('waterCapacityGrH2O') is not None and not (0.5 < c['waterCapacityGrH2O'] < 400):
            print('  !! implausible capacity', c['waterCapacityGrH2O'], c['cartridge'])
            bad += 1
        if c.get('caseWeightGr') is not None and not (20 < c['caseWeightGr'] < 2000):
            print('  !! implausible weight', c['caseWeightGr'], c['cartridge'])
            bad += 1
        if c.get('waterCapacityGrH2O') and c.get('caseWeightGr') and c['waterCapacityGrH2O'] > c['caseWeightGr']:
            print('  ?? capacity > weight', c['cartridge'], c['waterCapacityGrH2O'], c['caseWeightGr'])
    for b in d['brands']:
        if not b.get('evidence') or not b.get('sources'):
            bad += 1
            print('  !! brand without evidence', b['id'])
    rnd = random.Random(7)
    sample = rnd.sample(cases, min(5, len(cases)))
    print('--- 5 random records')
    for c in sample:
        print(json.dumps({k: c.get(k) for k in ('brandId', 'cartridge', 'sku', 'caseWeightGr', 'waterCapacityGrH2O',
                                                 'capacityCondition', 'capacityTo', 'primerSize', 'basis')},
                         ensure_ascii=False))
        print('   evidence:', c['evidence'][:400])
    flagged = [c for c in cases if c.get('qualityFlags')]
    print('--- quality-flagged records:', len(flagged))
    for c in flagged[:40]:
        print('  ', c['cartridge'], c.get('lot'), c['qualityFlags'])
    print('problems:', bad)
    return bad


if __name__ == '__main__':
    args = sys.argv[1:]
    if args and args[0] == '--download':
        which = args[1] if len(args) > 1 else 'all'
        fns = {'lapua': download_lapua, 'norma': download_norma, 'peterson': download_peterson,
               'starline': download_starline, 'accurateshooter': download_accurateshooter}
        for k, fn in fns.items():
            if which in ('all', k):
                fn()
    elif args and args[0] == '--check':
        sys.exit(1 if check() else 0)
    else:
        build()
