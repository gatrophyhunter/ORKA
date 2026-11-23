#!/usr/bin/env python3
"""Extract Berger and Lapua bullet specifications (key: bullets-berger-lapua).

Sources (public pages / documents, fetched with plain curl and its default
user agent; robots.txt of both hosts allows these paths and sets no Crawl-delay,
we still sleep >= 1.5 s between requests):

Berger (bergerbullets.com)
  * 2026 English catalog PDF (newest edition, linked from the "2026 Catalogs"
    nav item https://bergerbullets.com/berger_catalog/):
    https://bergerbullets.com/wp-content/uploads/2026/03/English-Berger-Catalog-2026.pdf
    Product tables: part #, sectional density, G1, G7, G7 form factor, minimum twist.
    This edition has NO dimension (OAL / boat tail / base-to-ogive) columns.
  * Web "Bullet Reference Charts" page (live, retrieved 2026-11-23):
    https://bergerbullets.com/information/lines-and-designs/bullet-reference-charts/
    Part #, description, Cal (Dia), OAL, boat tail, nose length, base to ogive,
    bearing surface, SD, G1, G7, G7 form factor, minimum twist.
  * 2024 catalog PDF (older edition; reference charts on PDF pages 18-21 with
    the same dimension columns, product tables with "ogive design"):
    https://bergerbullets.com/wp-content/uploads/2024/01/Berger-Catalog-2024-Website.pdf
  * A few individual product pages (discontinued items, items not in the 2026
    catalog, items whose weight is not in the name, items with conflicts).

Lapua (www.lapua.com)
  * 2026 English catalog PDF (from https://www.lapua.com/support/downloads_/):
    https://www.lapua.com/wp-content/uploads/2026/06/Lapua_Catalog_2026_ENG_web.pdf
    p.18 "COMPONENTS - CENTERFIRE RIFLE / HANDGUN" (product no., bullet name,
    type, code, diameter mm/in, weight g/gr, BC G1, BC G7);
    p.12 velocity-banded G1 BCs of tactical bullets; p.9 bullet line descriptions.
  * Bullet product pages listed at https://www.lapua.com/products/bullets/
    (WooCommerce attribute table: caliber, product no., bullet, bullet code,
    diameter, type, weight, purpose, BC G1, BC G7).
  * QuickTARGET Unlimited Lapua Edition bundle QTU.zip from the downloads page;
    its data/bullets/lapua.bul ("Data used by permission of LAPUA LTD", dated
    3-Feb-15) is the only Lapua-distributed file found that carries bullet
    lengths. Its columns are unlabeled; the third quoted field is QuickTARGET's
    bullet-length field (inches). Lengths taken from it are flagged
    lengthConfidence="low" and only used when bullet code AND weight match.

Usage:
  python3 -I bullets-berger-lapua.py --download   # fetch any missing source documents
  python3 -I bullets-berger-lapua.py              # parse cached documents and write JSON
  python3 -I bullets-berger-lapua.py --check      # self-check the written JSON

Everything is parsed with code from the cached documents; nothing is typed in.
"""
import html as htmlmod
import json
import os
import random
import re
import subprocess
import sys
import time
import zipfile

SRC = '/tmp/claude-0/-home-user-ORKA/29ce603d-ccc3-55ef-b8fe-c585397ac7c1/scratchpad/sources/bullets-berger-lapua'
OUT = '/home/user/ORKA/research/raw2/bullets-berger-lapua.json'
RETRIEVED = '2026-11-23'
DELAY = 1.6

B = 'https://bergerbullets.com'
L = 'https://www.lapua.com'

BERGER_2026_URL = B + '/wp-content/uploads/2026/03/English-Berger-Catalog-2026.pdf'
BERGER_2024_URL = B + '/wp-content/uploads/2024/01/Berger-Catalog-2024-Website.pdf'
BERGER_CHART_URL = B + '/information/lines-and-designs/bullet-reference-charts/'
BERGER_CATALOG_PAGE_URL = B + '/berger_catalog/'

BERGER_2026_PDF = os.path.join(SRC, 'Berger-Catalog-2026-English.pdf')
BERGER_2024_PDF = os.path.join(SRC, 'Berger-Catalog-2024-Website.pdf')
BERGER_CHART_HTML = os.path.join(SRC, 'berger-bullet-reference-charts.html')
BERGER_CATALOG_PAGE_HTML = os.path.join(SRC, 'berger_catalog.html')
BERGER_PROD_DIR = os.path.join(SRC, 'berger-products')

# Berger product pages consulted individually (slugs from https://bergerbullets.com/product-sitemap.xml)
BERGER_PRODUCT_SLUGS = [
    'discontinued-20-caliber-55-grain-lr-varmint',
    'discontinued-22-caliber-64-grain-fb-varmint',
    'discontinued-22-caliber-82-grain-long-range-target',
    'discontinued-6-mm-69-grain-high-bc-fb-varmint',
    'discontinued-30-caliber-155-grain-very-low-drag-vld-target',
    'discontinued-30-caliber-210-grain-long-range-target',
    '30-caliber-175-grain-very-low-drag-vld-target',
    '6-mm-120-grain-long-range-hybrid-target-rifle-bullet',
    '270-caliber-150-grain-hybrid-target-rifle-bullet',
    '30-caliber-217-grain-elite-hunter-rifle-bullet',
    '22-caliber-69-grain-bt-target-rifle-bullet',
    '375-caliber-379-grain-elr-match-solid-bullets',
    '375-caliber-407-grain-elr-match-solid-bullets',
    '7-mm-190-grain-long-range-hybrid-target',
    '30-caliber-200-20x-hybrid-target',
    '6-mm-br-column-target',
]

LAPUA_CAT_URL = L + '/wp-content/uploads/2026/06/Lapua_Catalog_2026_ENG_web.pdf'
LAPUA_CAT_PDF = os.path.join(SRC, 'lapua', 'Lapua_Catalog_2026_ENG_web.pdf')
LAPUA_DOWNLOADS_URL = L + '/support/downloads_/'
LAPUA_QTU_URL = L + '/wp-content/uploads/2020/07/QTU.zip'
LAPUA_QTU_ZIP = os.path.join(SRC, 'lapua', 'qtu', 'QTU.zip')
LAPUA_BUL_MEMBER = 'data/bullets/lapua.bul'
LAPUA_LIST_URLS = [L + '/products/bullets/'] + [L + '/products/bullets/?product-page=%d' % n for n in range(2, 6)]
LAPUA_PROD_DIR = os.path.join(SRC, 'lapua', 'products')
LAPUA_MAXRT_URL = L + '/maxrt/'
LAPUA_TRX_URL = L + '/trx/'

_last = {}


def fetch(url, dest):
    """Download url to dest with plain curl (default UA), sleeping between requests per host."""
    host = url.split('/')[2]
    wait = DELAY - (time.time() - _last.get(host, 0))
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
        print(f'  fetched {url}')
        return True
    if os.path.exists(tmp):
        os.remove(tmp)
    print(f'  ! {url} -> HTTP {code} {r.stderr.strip()}', file=sys.stderr)
    return False


def lapua_list_local(url):
    m = re.search(r'product-page=(\d+)', url)
    return os.path.join(SRC, 'lapua', 'products-bullets%s.html' % ('-p' + m.group(1) if m else ''))


def lapua_product_urls():
    urls = []
    for lu in LAPUA_LIST_URLS:
        p = lapua_list_local(lu)
        if not os.path.exists(p):
            continue
        t = open(p, encoding='utf-8').read()
        for u in re.findall(r'href="(https://www\.lapua\.com/product/[^"]+)"', t):
            if u not in urls:
                urls.append(u)
    return urls


def slug_of(url):
    return url.rstrip('/').rsplit('/', 1)[-1]


def download():
    plan = [
        (BERGER_CATALOG_PAGE_URL, BERGER_CATALOG_PAGE_HTML),
        (BERGER_2026_URL, BERGER_2026_PDF),
        (BERGER_2024_URL, BERGER_2024_PDF),
        (BERGER_CHART_URL, BERGER_CHART_HTML),
        (LAPUA_DOWNLOADS_URL, os.path.join(SRC, 'lapua', 'downloads.html')),
        (LAPUA_CAT_URL, LAPUA_CAT_PDF),
        (LAPUA_QTU_URL, LAPUA_QTU_ZIP),
        (LAPUA_MAXRT_URL, os.path.join(SRC, 'lapua', 'page-maxrt.html')),
        (LAPUA_TRX_URL, os.path.join(SRC, 'lapua', 'page-trx.html')),
    ]
    plan += [(B + '/product/%s/' % s, os.path.join(BERGER_PROD_DIR, s + '.html')) for s in BERGER_PRODUCT_SLUGS]
    plan += [(u, lapua_list_local(u)) for u in LAPUA_LIST_URLS]
    for url, dest in plan:
        if not os.path.exists(dest):
            fetch(url, dest)
    for u in lapua_product_urls():
        dest = os.path.join(LAPUA_PROD_DIR, slug_of(u) + '.html')
        if not os.path.exists(dest):
            fetch(u, dest)




# ----------------------------------------------------------------------------
# generic helpers
# ----------------------------------------------------------------------------

def collapse(s):
    return re.sub(r'\s+', ' ', s).strip()


def num(s):
    """Parse a printed number ('0.224', '.224', '0,335', '1.06') -> float; None for N/A, '-', '–', ''."""
    if s is None:
        return None
    s = s.strip().replace(',', '.')
    if s in ('', 'N/A', 'NA', '-', '–', '—'):
        return None
    m = re.fullmatch(r'\d*\.?\d+', s)
    return float(s) if m else None


def pdftotext_pages(pdf, mode='-layout'):
    """Return list of page texts (1-based index i -> pages[i-1])."""
    r = subprocess.run(['pdftotext', mode, pdf, '-'], capture_output=True, text=True)
    return r.stdout.split('\f')


def pdf_words(pdf, page):
    """Words with bounding boxes on one PDF page: list of (x0, y0, x1, y1, text)."""
    r = subprocess.run(['pdftotext', '-f', str(page), '-l', str(page), '-bbox', pdf, '-'],
                       capture_output=True, text=True)
    out = []
    for x0, y0, x1, y1, w in re.findall(
            r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>', r.stdout):
        out.append((float(x0), float(y0), float(x1), float(y1), htmlmod.unescape(w)))
    return out


def woo_attrs(path):
    """WooCommerce attribute table (label, value) pairs from a product page."""
    t = open(path, encoding='utf-8').read()
    pairs = []
    for a, b in re.findall(r'<th class="woocommerce-product-attributes-item__label"[^>]*>(.*?)</th>\s*'
                           r'<td class="woocommerce-product-attributes-item__value">(.*?)</td>', t, flags=re.S):
        pairs.append((collapse(htmlmod.unescape(re.sub(r'<[^>]+>', ' ', a))),
                      collapse(htmlmod.unescape(re.sub(r'<[^>]+>', ' ', b)))))
    return pairs


def page_title(path):
    t = open(path, encoding='utf-8').read()
    m = re.search(r'<title>(.*?)</title>', t, flags=re.S)
    return collapse(htmlmod.unescape(m.group(1))) if m else None


def page_lines(path):
    t = open(path, encoding='utf-8').read()
    t = re.sub(r'<script.*?</script>', '', t, flags=re.S)
    t = re.sub(r'<style.*?</style>', '', t, flags=re.S)
    t = htmlmod.unescape(re.sub(r'<[^>]+>', '\n', t))
    return [collapse(l) for l in t.split('\n') if collapse(l)]


def src(url, typ='manufacturer', page=None):
    return {'url': url, 'type': typ, 'page': page, 'retrieved': RETRIEVED}


def same(a, b, tol=1e-9):
    if a is None or b is None:
        return a is b
    if isinstance(a, str) or isinstance(b, str):
        return str(a) == str(b)
    return abs(a - b) <= tol


def twist_inches(s):
    if not s:
        return None
    m = re.search(r'1\s*[:\-]\s*(\d+(?:\.\d+)?)', s)
    return float(m.group(1)) if m else None


# ----------------------------------------------------------------------------
# Berger
# ----------------------------------------------------------------------------

BERGER_2026_SECTIONS = {
    # pdf page -> (line name, heading text that must be on the page)
    4: ('Long Range Hybrid Target', 'RANGE HYBRID TARGET'),
    5: ('VLD Target', 'VLD TARGET'),
    6: ('Hybrid Target', 'HYBRID TARGET'),
    7: ('OTM Tactical', 'TACTICAL'),
    8: ('Tangent Target', 'TANGENT TARGET'),
    9: ('Elite Hunter', 'ELITE HUNTER'),
    10: ('Classic Hybrid Hunter', 'CLASSIC HYBRID HUNTER'),
    11: ('VLD Hunting', 'VLD HUNTING'),
    12: ('Varmint', 'VARMINT BULLETS'),
}

RE_B26 = re.compile(r'^(?P<desc>.+?) (?P<part>\d{5}) (?P<sd>\d?\.\d{3}) (?P<g1>\d?\.\d{3}) '
                    r'(?P<g7>\d?\.\d{3}|N/A|NA) (?P<ff>\d?\.\d{3}|N/A|NA) (?P<twist>1:[\d.]+")$')


def parse_berger_2026():
    pages = pdftotext_pages(BERGER_2026_PDF)
    rows = {}
    for pno, (line, heading) in BERGER_2026_SECTIONS.items():
        text = pages[pno - 1]
        assert heading in text.upper(), (pno, heading)
        for raw in text.split('\n'):
            c = collapse(raw)
            m = RE_B26.match(c)
            if not m:
                continue
            d = m.groupdict()
            desc = d['desc']
            is_new = desc.endswith(' NEW')
            if is_new:
                desc = desc[:-4]
            ln = 'ELR Match Solid' if 'ELR Match Solid' in desc else line
            assert d['part'] not in rows, d['part']
            rows[d['part']] = {
                'part': d['part'], 'desc': desc, 'isNew': is_new, 'line': ln, 'page': pno,
                'sd': num(d['sd']), 'g1': num(d['g1']), 'g7': num(d['g7']), 'ff': num(d['ff']),
                'twist': d['twist'], 'evidence': c,
            }
    return rows


def parse_berger_web_chart():
    t = open(BERGER_CHART_HTML, encoding='utf-8').read()
    rows = {}
    header = None
    for r in re.findall(r'<tr[^>]*>(.*?)</tr>', t, flags=re.S):
        cells = [collapse(htmlmod.unescape(re.sub(r'<[^>]+>', ' ', c)))
                 for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, flags=re.S)]
        if cells and cells[0] == 'Part #':
            header = cells
            continue
        if len(cells) != 13 or not re.fullmatch(r'\d{5}', cells[0]):
            continue
        assert header == ['Part #', 'Bullet Description', 'Cal (Dia)', 'OAL', 'Boat Tail', 'Nose Length',
                          'Base to Ogive', 'Bearing Surface', 'Sectional Density', 'G1 BC', 'G7 BC',
                          'G7 Form Factor', 'Minimum Twist'], header
        m = re.fullmatch(r'(.+?) \((0\.\d{3})\)', cells[2])
        assert m, cells
        part = cells[0]
        assert part not in rows, part
        rows[part] = {
            'part': part, 'desc': cells[1], 'cal': m.group(1), 'dia': num(m.group(2)),
            'oal': num(cells[3]), 'bt': None if cells[4] == 'FB' else num(cells[4]), 'fb': cells[4] == 'FB',
            'nose': num(cells[5]), 'bto': num(cells[6]), 'bearing': num(cells[7]), 'sd': num(cells[8]),
            'g1': num(cells[9]), 'g7': num(cells[10]), 'ff': num(cells[11]),
            'twist': cells[12].replace('″', '"'), 'evidence': ' | '.join(cells),
        }
    return rows


RE_B24_REF = re.compile(
    r'^(?P<part>\d{5}) (?P<desc>.+?) (?P<cal>\d+(?:\.\d+)? ?(?:Cal|mm)) (?P<dia>0\.\d{3}) (?P<oal>\d\.\d{3}) '
    r'(?P<bt>FB|0\.\d{3}) (?P<nose>\d\.\d{3}) (?P<bto>\d\.\d{3}) (?P<bear>\d\.\d{3}) (?P<sd>0\.\d{3}) '
    r'(?P<g1>\d?\.\d{3}) (?P<g7>0\.\d{3}|N/A|NA) (?P<ff>\d\.\d{3}|N/A|NA) (?P<twist>1:[\d.]+”)$')
RE_B24_PROD = re.compile(r'(?P<part>\d{5}) (?P<dia>\.\d{3})”? (?P<ogive>Tangent|Secant|Hybrid) '
                         r'(?P<g1>\d?\.\d{3})(?: (?P<g7>\d?\.\d{3}|–))?')


def parse_berger_2024():
    pages = pdftotext_pages(BERGER_2024_PDF)
    ref, prod = {}, {}
    for pno, text in enumerate(pages, 1):
        for raw in text.split('\n'):
            c = collapse(raw)
            m = RE_B24_REF.match(c)
            if m:
                d = m.groupdict()
                assert d['part'] not in ref, d['part']
                ref[d['part']] = {
                    'part': d['part'], 'desc': d['desc'], 'cal': d['cal'], 'dia': num(d['dia']),
                    'oal': num(d['oal']), 'bt': None if d['bt'] == 'FB' else num(d['bt']), 'fb': d['bt'] == 'FB',
                    'nose': num(d['nose']), 'bto': num(d['bto']), 'bearing': num(d['bear']), 'sd': num(d['sd']),
                    'g1': num(d['g1']), 'g7': num(d['g7']), 'ff': num(d['ff']),
                    'twist': d['twist'].replace('”', '"'), 'page': pno, 'evidence': c}
                continue
            for m in RE_B24_PROD.finditer(c):
                d = m.groupdict()
                # description = the layout cell just before the part number (if it looks like one)
                cells = [x.strip() for x in re.split(r'\s{3,}', raw) if x.strip()]
                desc = None
                for i, cell in enumerate(cells):
                    if cell == d['part'] and i > 0 and re.search(r'\b(?:gr|Column)\b', cells[i - 1]):
                        desc = cells[i - 1]
                if d['part'] in prod:
                    continue
                prod[d['part']] = {'part': d['part'], 'desc': desc, 'dia': num(d['dia']), 'ogive': d['ogive'],
                                   'g1': num(d['g1']), 'g7': num(d['g7']) if d['g7'] else None,
                                   'page': pno, 'evidence': c}
    return ref, prod


def parse_berger_products():
    out = {}
    for slug in BERGER_PRODUCT_SLUGS:
        path = os.path.join(BERGER_PROD_DIR, slug + '.html')
        if not os.path.exists(path):
            continue
        pairs = woo_attrs(path)
        a = {}
        for k, v in pairs:
            a.setdefault(k, v)
        part_keys = [k for k in a if re.fullmatch(r'\d+ct Part #', k)]
        title = page_title(path)
        name = re.sub(r'\s*\|\s*Berger Bullets\s*\|?\s*', '|', title).strip('|')
        name = [x for x in name.split('|') if x.strip()][0].strip()
        rec = {
            'slug': slug, 'url': B + '/product/%s/' % slug, 'title': title, 'name': name,
            'discontinued': title.upper().startswith('DISCONTINUED'),
            'parts': {k: a[k] for k in part_keys},
            'part': a[part_keys[0]] if part_keys else None,
            'weight': num(re.sub(r'\s*Grain$', '', a.get('Bullet Weight', ''))) if a.get('Bullet Weight') else None,
            'line': a.get('Product Line'), 'g1': num(a.get('G1 BC')), 'g7': num(a.get('G7 BC')),
            'ff': num(a.get('G7 Form Factor')), 'twist': a.get('Minimum Twist (or faster)'),
            'ogive': a.get('Ogive Style'), 'base': a.get('Base Style'), 'jacket': a.get('Jacket'),
            'sd': num(a.get('Sectional Density')), 'dia': num(a.get('Bullet Dia.')), 'oal': num(a.get('OAL')),
            'bto': num(a.get('Base to Ogive')), 'nose': num(a.get('Nose Length')),
            'bearing': num(a.get('Bearing Surface')),
            'bt': None if a.get('Boat Tail Length') in (None, 'FB') else num(a.get('Boat Tail Length')),
            'fb': a.get('Boat Tail Length') == 'FB' or a.get('Base Style') == 'Flat Base',
            'cal': a.get('Caliber'),
            'evidence': '; '.join(f'{k}: {v}' for k, v in pairs),
        }
        out[rec['part']] = rec
    return out


def norm_desc(s):
    s = s.lower().replace('″', '"')
    s = re.sub(r'\bgrain\b', 'gr', s)
    s = re.sub(r'\blr\b', 'long range', s)
    s = re.sub(r'\b(\d(?:\.\d)?) mm\b', r'\1mm', s)
    s = s.replace('classic hybrid hunter', 'classic hunter').replace(' eol ', ' ').replace(' bullets', '')
    s = s.replace('6.8mm / 270 cal', '270 cal')
    return collapse(s)


def berger_records():
    c26 = parse_berger_2026()
    web = parse_berger_web_chart()
    ref24, prod24 = parse_berger_2024()
    pp = parse_berger_products()

    # Map web-chart part numbers that appear in no other source onto a catalog item with the same description
    web_alias = {}
    known = set(c26) | set(ref24) | set(pp)
    for part, w in web.items():
        if part in known:
            continue
        cands = [p for p, r in c26.items() if norm_desc(r['desc']) == norm_desc(w['desc']) and p not in web]
        if len(cands) == 1:
            web_alias[part] = cands[0]
    web_by_part = {}
    for part, w in web.items():
        web_by_part[web_alias.get(part, part)] = w

    parts = sorted(set(c26) | set(web_by_part) | set(ref24) | set(pp))
    recs = []
    for part in parts:
        a = c26.get(part)
        w = web_by_part.get(part)
        r24 = ref24.get(part)
        p24 = prod24.get(part)
        p = pp.get(part)
        sources, evid, conflicts, notes = [], [], [], []
        if a:
            sources.append(src(BERGER_2026_URL, page=a['page'])); evid.append(a['evidence'])
        if w:
            sources.append(src(BERGER_CHART_URL)); evid.append(w['evidence'])
        if p:
            sources.append(src(p['url'])); evid.append(p['evidence'])
        if r24:
            sources.append(src(BERGER_2024_URL, page=r24['page'])); evid.append(r24['evidence'])
        if p24:
            sources.append(src(BERGER_2024_URL, page=p24['page'])); evid.append(p24['evidence'])

        def lab(kind, page=None):
            return {'2026': 'Berger 2026 catalog p.%s' % page, 'web': 'bergerbullets.com Bullet Reference Charts page',
                    'pp': 'bergerbullets.com product page', 'r24': 'Berger 2024 catalog reference chart p.%s' % page,
                    'p24': 'Berger 2024 catalog product table p.%s' % page}[kind]

        cand = []  # (kind, dict, page)
        if a: cand.append(('2026', a, a['page']))
        if w: cand.append(('web', w, None))
        if p: cand.append(('pp', p, None))
        if r24: cand.append(('r24', r24, r24['page']))
        if p24: cand.append(('p24', p24, p24['page']))

        field_src = {}
        kind_idx = {k: i for i, (k, d, pg) in enumerate(cand)}

        def pick(field, order, out_field=None, tol=1e-9):
            vals = [(k, d[field], pg) for k, d, pg in cand if field in d and d[field] is not None]
            ordered = sorted(vals, key=lambda v: order.index(v[0]) if v[0] in order else 99)
            ordered = [v for v in ordered if v[0] in order]
            if not ordered:
                return None
            field_src[out_field or field] = kind_idx[ordered[0][0]]
            distinct = []
            for k, v, pg in vals:
                if not any(same(v, x, tol) for x in distinct):
                    distinct.append(v)
            if len(distinct) > 1:
                conflicts.append({'field': out_field or field,
                                  'values': [{'value': v, 'source': lab(k, pg)} for k, v, pg in vals]})
            return ordered[0][1]

        # sku conflict (web chart alias)
        for wp, cp in web_alias.items():
            if cp == part:
                conflicts.append({'field': 'sku', 'values': [
                    {'value': cp, 'source': lab('2026', a['page']) if a else 'catalog'},
                    {'value': wp, 'source': lab('web')}] + ([{'value': p['part'], 'source': lab('pp')}] if p else [])})
                notes.append('Reference-chart web page lists this bullet as part #%s; the 2026 catalog%s give #%s.'
                             % (wp, ' and product page' if p else '', cp))

        DIM = ['web', 'pp', 'r24']
        BAL = ['2026', 'web', 'pp', 'r24']
        dia = pick('dia', ['web', 'pp', 'r24', 'p24'], 'diameterIn')
        oal = pick('oal', DIM, 'lengthIn')
        bt = pick('bt', DIM, 'boatTailLengthIn')
        nose = pick('nose', DIM, 'noseLengthIn')
        bto = pick('bto', DIM, 'baseToOgiveIn')
        bear = pick('bearing', DIM, 'bearingSurfaceIn')
        sd = pick('sd', BAL, 'sectionalDensity')
        g1 = pick('g1', BAL + ['p24'], 'bcG1')
        g7 = pick('g7', BAL + ['p24'], 'bcG7')
        ff = pick('ff', BAL, 'g7FormFactor')
        twist = pick('twist', BAL, 'recommendedTwist')
        fb_flags = {d.get('fb') for k, d, pg in cand if 'fb' in d}
        flat_base = True in fb_flags and False not in fb_flags

        # Dimension consistency: Berger's dimensions satisfy OAL ~= nose + bearing + boat tail for most bullets.
        # If the primary (web) value breaks it badly and a conflicting catalog value restores it, use that value.
        def resid(o, n, b, t):
            if None in (o, n, b):
                return None
            return round(o - (n + b + (t or 0.0)), 3)
        res = resid(oal, nose, bear, bt)
        if res is not None and abs(res) > 0.05 and 'ELR Match Solid' not in ((a or {}).get('desc') or (w or {}).get('desc') or ''):
            fixed = False
            for fld, cur in (('nose', nose), ('bearing', bear), ('bt', bt), ('oal', oal)):
                for k, d, pg in cand:
                    alt = d.get(fld)
                    if alt is None or same(alt, cur):
                        continue
                    trial = dict(o=oal, n=nose, b=bear, t=bt)
                    trial[{'nose': 'n', 'bearing': 'b', 'bt': 't', 'oal': 'o'}[fld]] = alt
                    r2 = resid(trial['o'], trial['n'], trial['b'], trial['t'])
                    if r2 is not None and abs(r2) <= 0.03:
                        notes.append('Sources disagree on %s (%s vs %s). Selected %s from %s because with it '
                                     'OAL - (nose + bearing + boat tail) = %s in, versus %s in with the reference-chart '
                                     'web value (the identity holds within 0.03 in for most Berger bullets).'
                                     % (fld, cur, alt, alt, lab(k, pg), r2, res))
                        if fld == 'nose': nose = alt
                        elif fld == 'bearing': bear = alt
                        elif fld == 'bt': bt = alt
                        else: oal = alt
                        field_src[{'nose': 'noseLengthIn', 'bearing': 'bearingSurfaceIn', 'bt': 'boatTailLengthIn',
                                   'oal': 'lengthIn'}[fld]] = kind_idx[k]
                        fixed = True
                        break
                if fixed:
                    break
            if not fixed:
                notes.append('Dimension check: OAL - (nose + bearing + boat tail) = %s in (typically <= 0.03 in for '
                             'Berger bullets); verify dimensions by measurement.' % res)
        elif res is not None and abs(res) > 0.05:
            notes.append('ELR Match Solid: OAL - (nose + bearing + boat tail) = %s in as published; the maker\'s '
                         'nose/bearing definitions evidently differ for this solid design.' % res)

        # names / labels
        desc = (a or {}).get('desc') or (w or {}).get('desc') or (r24 or {}).get('desc') or (p or {}).get('name')
        if p and p['discontinued']:
            notes.append('Product page title: "%s".' % p['title'])
        weight = None
        if p and p.get('weight') is not None:
            weight = p['weight']
            field_src['weightGr'] = kind_idx['pp']
        else:
            for kk, x in (('2026', a), ('web', w), ('r24', r24), ('p24', p24)):
                if not x or not x.get('desc'):
                    continue
                m = re.search(r'\b(\d+(?:\.\d+)?) (?:Grain|gr)\b', x['desc'])
                if m:
                    weight = float(m.group(1))
                    field_src['weightGr'] = kind_idx[kk]
                    break
        wvals = set()
        for x in (a, w, r24, p24):
            if x and x.get('desc'):
                m = re.search(r'\b(\d+(?:\.\d+)?) (?:Grain|gr)\b', x['desc'])
                if m:
                    wvals.add(float(m.group(1)))
        if p and p.get('weight') is not None:
            wvals.add(p['weight'])
        if len(wvals) > 1:
            conflicts.append({'field': 'weightGr', 'values': [{'value': v, 'source': 'description/product page'} for v in sorted(wvals)]})
        cal_label = (w or {}).get('cal') or (r24 or {}).get('cal') or (p or {}).get('cal')
        line = (a or {}).get('line')
        if not line and p and p.get('line'):
            line = p['line']
            notes.append('Line taken from the product page "Product Line" field (bullet not in the 2026 catalog).')
        if not line:
            for kw, ln in (('LR Hybrid', 'Long Range Hybrid Target'), ('VLD Target', 'VLD Target'),
                           ('Hybrid Target', 'Hybrid Target'), ('Elite Hunter', 'Elite Hunter'),
                           ('Classic Hunter', 'Classic Hybrid Hunter'), ('VLD Hunting', 'VLD Hunting'),
                           ('Varmint', 'Varmint'), ('OTM Tactical', 'OTM Tactical')):
                if kw in (desc or ''):
                    line = ln
                    notes.append('Line inferred from the printed description "%s".' % desc)
                    break

        ogive = (p24 or {}).get('ogive') or (p or {}).get('ogive')
        if p24 and p and p.get('ogive') and not p['ogive'].lower().startswith(p24['ogive'].lower()) \
                and not (p24['ogive'] == 'Secant' and 'VLD' in p['ogive']):
            notes.append('Ogive style: 2024 catalog "%s", product page "%s".' % (p24['ogive'], p['ogive']))
        base = 'flat base' if flat_base else ('boat tail' if (bt is not None or (p and p.get('base') == 'Boat Tail')) else None)
        profile_bits = []
        if ogive:
            profile_bits.append('%s ogive' % ogive)
        if base:
            profile_bits.append(base)
        profile = ', '.join(profile_bits) or None
        tip = 'open tip match (OTM)' if re.search(r'\bOTM\b', desc or '') else None

        solid = 'ELR Match Solid' in (desc or '')
        if solid:
            construction = 'monolithic-copper'
            notes.append('Construction from 2026 catalog p.5 wording: "EXTREME LONG RANGE MATCH SOLID - Solid Copper '
                         'Projectiles ... Each bullet is individually CNC machine lathed".')
        else:
            construction = 'cup-and-core'
            notes.append('Construction mapped from 2026 catalog wording: "Every Berger Bullet is built with a J4 '
                         'jacket", "We use only the highest-grade copper and lead", "All jackets, cores, and bullets '
                         'within a lot are produced using the same die".'
                         + (' Product page: Jacket = %s.' % p['jacket'] if p and p.get('jacket') else ''))

        if a:
            status = 'current (listed in Berger 2026 catalog%s)' % (', marked NEW' if a['isNew'] else '')
        elif p and p['discontinued']:
            status = 'discontinued (bergerbullets.com product page titled "DISCONTINUED")'
        elif w:
            status = 'listed on bergerbullets.com Bullet Reference Charts (retrieved %s) but not in the 2026 catalog' % RETRIEVED
        else:
            status = 'listed in Berger 2024 catalog only (not in 2026 catalog nor web reference chart)'

        if twist:
            notes.append('Berger publishes twist as MINIMUM twist ("All twist rates represent listed number or faster"); '
                         'use the Berger twist calculator for the optimum.')
        if p and len(p['parts']) > 1:
            notes.append('Box part numbers: ' + ', '.join('%s %s' % (k.replace(' Part #', ''), v) for k, v in p['parts'].items()) + '.')

        rec = {
            'id': 'berger-%s' % part,
            'manufacturer': 'Berger Bullets',
            'line': line,
            'name': desc,
            'sku': part,
            'caliberLabel': cal_label,
            'diameterIn': dia,
            'weightGr': weight,
            'lengthIn': oal,
            'lengthConfidence': 'high' if oal is not None else None,
            'boatTailLengthIn': None if flat_base else bt,
            'baseToOgiveIn': bto,
            'noseLengthIn': nose,
            'bearingSurfaceIn': bear,
            'sectionalDensity': sd,
            'bcG1': g1,
            'bcG7': g7,
            'g7FormFactor': ff,
            'bcNotes': None,
            'profile': profile,
            'tip': tip,
            'construction': construction,
            'recommendedTwist': twist,
            'twistInches': twist_inches(twist),
            'status': status,
            'firearm': 'rifle',
            'sources': sources,
            'evidence': ' || '.join(evid),
            'fieldSourceIndex': field_src,
            'conflicts': conflicts,
            'notes': ' '.join(notes) or None,
        }
        recs.append(rec)
    meta_docs = [
        {'url': BERGER_2026_URL, 'localPath': BERGER_2026_PDF,
         'title': 'Berger Bullets 2026 catalog (English) - newest edition, linked from "2026 Catalogs" nav item',
         'date': '2026-01-21 (PDF creation date)'},
        {'url': BERGER_CHART_URL, 'localPath': BERGER_CHART_HTML,
         'title': 'Berger Bullets - Bullet Reference Charts (web page, dimensions)', 'date': RETRIEVED},
        {'url': BERGER_2024_URL, 'localPath': BERGER_2024_PDF,
         'title': 'Berger Bullets 2024 catalog (website version) - older edition with reference charts', 'date': '2024'},
        {'url': BERGER_CATALOG_PAGE_URL, 'localPath': BERGER_CATALOG_PAGE_HTML,
         'title': 'Berger "2026 Catalogs" page (links to English/French/German 2026 catalog PDFs)', 'date': RETRIEVED},
    ] + [{'url': p['url'], 'localPath': os.path.join(BERGER_PROD_DIR, p['slug'] + '.html'),
          'title': 'Berger product page: %s' % p['name'], 'date': RETRIEVED} for p in pp.values()]
    stats = {'berger2026Rows': len(c26), 'bergerWebChartRows': len(web), 'berger2024RefRows': len(ref24),
             'berger2024ProductTableRows': len(prod24), 'bergerProductPages': len(pp), 'webAliases': web_alias}
    return recs, meta_docs, stats


# ----------------------------------------------------------------------------
# Lapua
# ----------------------------------------------------------------------------

RE_LCODE = re.compile(r'^(?:GB|G|B|S|E|N|D|C)\d{2,3}$')


def _expect(words, text, x, y=None, tol=6):
    hits = [w for w in words if w[4] == text and abs(w[0] - x) <= tol and (y is None or abs(w[1] - y) <= tol)]
    assert hits, ('layout changed: expected %r near x=%s y=%s' % (text, x, y))
    return hits[0]


def parse_lapua_components():
    """Catalog p.18 component tables, reconstructed from word boxes (rows are aligned by y)."""
    words = pdf_words(LAPUA_CAT_PDF, 18)
    # verify the header layout we rely on
    _expect(words, 'BULLETS', 211, 36)
    _expect(words, 'Ballistic', 495, 48)
    _expect(words, 'G7', 548, 78)
    _expect(words, 'HANDGUN', 218, 662)
    _expect(words, 'coefficient', 481, 706)
    tables = [
        # name, y-range, columns (x-start of each column), caliber-label column max x
        ('rifle', (84, 655), [('prodno', 205), ('name', 260), ('code', 336), ('type', 366), ('mm', 395),
                              ('in', 418), ('g', 440), ('gr', 466), ('g1', 490), ('g7', 530), ('extra', 566)]),
        ('handgun', (730, 760), [('prodno', 205), ('name', 255), ('code', 320), ('type', 358), ('mm', 388),
                                 ('in', 413), ('g', 434), ('gr', 458), ('g1', 475), ('extra', 560)]),
    ]
    rows = []
    for tname, (ylo, yhi), cols in tables:
        tw = [w for w in words if ylo <= w[1] <= yhi]
        maxx = 600 if tname == 'rifle' else 560
        codes = [w for w in tw if cols[2][1] - 2 <= w[0] < cols[3][1] and RE_LCODE.match(w[4])]
        # caliber group labels (left column)
        cal_lines = {}
        for w in tw:
            if w[0] < 90:
                cal_lines.setdefault(round(w[1]), []).append(w)
        cal_labels = sorted((y, collapse(' '.join(x[4] for x in sorted(ws)))) for y, ws in cal_lines.items())
        cal_labels = [(y, l) for y, l in cal_labels if re.search(r'\(\.\d{3}\)|\(7\.65 mm\)', l)]
        for cw in sorted(codes, key=lambda w: w[1]):
            y = cw[1]
            roww = [w for w in tw if abs(w[1] - y) <= 1.6 and cols[0][1] - 2 <= w[0] < maxx]
            # bullet-name cell may sit on the line just above (stacked two-line cells)
            namew = [w for w in tw if cols[1][1] - 2 <= w[0] < cols[2][1] - 2 and 0 < y - w[1] <= 3.5]
            if not any(cols[1][1] - 2 <= w[0] < cols[2][1] - 2 for w in roww):
                roww += namew
            cells = {}
            for w in sorted(roww, key=lambda w: w[0]):
                col = None
                for cname, cx in cols:
                    if w[0] >= cx - 2:
                        col = cname
                cells.setdefault(col, []).append(w[4])
            cells = {k: ' '.join(v) for k, v in cells.items()}
            cal = None
            for cy, cl in cal_labels:
                if cy <= y + 2:
                    cal = cl
            evidence = ' '.join(w[4] for w in sorted([w for w in tw if abs(w[1] - y) <= 1.6] + (namew if namew and not any(cols[1][1] - 2 <= w[0] < cols[2][1] - 2 for w in [x for x in tw if abs(x[1] - y) <= 1.6]) else []), key=lambda w: w[0]) if w[0] < maxx)
            rows.append({'table': tname, 'y': y, 'caliber': cal, 'prodno': cells.get('prodno'), 'name': cells.get('name'),
                         'code': cells.get('code'), 'type': cells.get('type'), 'mm': num(cells.get('mm')),
                         'in': cells.get('in'), 'g': num(cells.get('g')), 'gr': num(cells.get('gr')),
                         'g1': num(cells.get('g1')), 'g7': num(cells.get('g7')) if 'g7' in cells else None,
                         'extra': cells.get('extra'), 'raw': cells, 'evidence': collapse(evidence)})
    return rows


def parse_lapua_bc_bands():
    """Catalog p.12: G1 BC per velocity band and G7 BC for tactical bullets."""
    words = pdf_words(LAPUA_CAT_PDF, 12)
    _expect(words, 'BALLISTIC', 918, 64)
    right = [w for w in words if w[0] > 660]
    lines = {}
    for w in right:
        lines.setdefault(round(w[1]), []).append(w)
    ys = sorted(lines)
    out = {}
    m_hdr = None   # current m/s band header: list of (x, label)
    f_hdr = None
    for y in ys:
        ws = sorted(lines[y])
        text = ' '.join(w[4] for w in ws)
        if 'm/s' in text and re.search(r'\d{3}-\d{3}', text):
            # band labels: group words into labels split at the x of each '>'/'<' or 'ddd-ddd'
            labels = []
            cur = []
            for w in ws:
                if (w[4] in ('>', '<') or re.match(r'^[<>]?\d{3}(-\d{3})?$', w[4]) or w[4].startswith('<')) and \
                        (not cur or cur[-1][4] == 'm/s'):
                    if cur:
                        labels.append(cur)
                    cur = [w]
                else:
                    cur.append(w)
            if cur:
                labels.append(cur)
            m_hdr = [(l[0][0], ' '.join(x[4] for x in l)) for l in labels]
            continue
        if 'fps' in text and re.search(r'\d{3,4}-\d{3,4}', text):
            labels = []
            cur = []
            for w in ws:
                if cur and cur[-1][4] == 'fps':
                    labels.append(cur); cur = []
                cur.append(w)
            if cur:
                labels.append(cur)
            f_hdr = [(l[0][0], ' '.join(x[4] for x in l)) for l in labels]
            continue
        codes = [w for w in ws if 905 <= w[0] <= 925 and re.match(r'^(?:GB|B|D|N|AP|API)\d{2,3}$|^D46$', w[4])]
        if not codes or not m_hdr:
            continue
        assert len(m_hdr) == 6 and len(f_hdr) == 6, (m_hdr, f_hdr)
        code = codes[0][4]
        name_ws = [x for yy in ys if 0 < y - yy <= 3 for x in lines[yy] if x[0] < 860]
        vals = [w for w in ws if w[0] > 930]
        bands = []
        g7 = None
        for v in vals:
            # nearest header column
            i = min(range(6), key=lambda k: abs(m_hdr[k][0] - v[0]))
            if i == 5:
                g7 = (m_hdr[i][1], f_hdr[i][1], num(v[4]), v[4])
            else:
                bands.append((m_hdr[i][1], f_hdr[i][1], num(v[4]), v[4]))
        weight = ' '.join(w[4] for w in ws if 860 <= w[0] < 905)
        out[code] = {'code': code, 'name': ' '.join(w[4] for w in sorted(name_ws)), 'weight': weight,
                     'bands': bands, 'g7': g7,
                     'evidence': collapse(' '.join(w[4] for w in sorted(name_ws)) + ' ' + text)}
    return out


def parse_lapua_products():
    out = {}
    for f in sorted(os.listdir(LAPUA_PROD_DIR)):
        if not f.endswith('.html'):
            continue
        path = os.path.join(LAPUA_PROD_DIR, f)
        pairs = woo_attrs(path)
        a = {}
        for k, v in pairs:
            a.setdefault(k, v)
        code = a.get('Bullet Code')
        t = open(path, encoding='utf-8').read()
        hm = re.search(r'<h2 class="product_title entry-title">(.*?)</h2>', t, flags=re.S)
        name = collapse(htmlmod.unescape(re.sub(r'<[^>]+>', ' ', hm.group(1)))) if hm else None
        wm = re.match(r'([\d.,]+)\s*g\s*\((\d+(?:\.\d+)?)\s*gr\)', a.get('Bullet weight', ''))
        dm = re.search(r'\((\.\d{3})', a.get('Bullet diameter', ''))

        def inch(v):
            if not v:
                return None
            m = re.search(r'/\s*(\d*\.\d+)\s*[”"]', v)
            return float(m.group(1)) if m else None
        rec = {'file': f, 'url': L + '/product/%s/' % f[:-5], 'name': name, 'code': code,
               'prodno': a.get('Product no.'), 'line': a.get('Bullet'), 'type': a.get('Bullet type'),
               'caliber': a.get('Caliber'), 'purpose': a.get('Purpose'),
               'g': num(wm.group(1)) if wm else None, 'gr': num(wm.group(2)) if wm else None,
               'dia': num(dm.group(1)) if dm else None,
               'g1': num(a.get('BC G1')), 'g7': num(a.get('BC G7')),
               'twist': a.get('Twist rate'),
               'oal': inch(a.get('OAL')), 'bt': inch(a.get('Boat tail length')),
               'bearing': inch(a.get('Bearing surface length')),
               'ogiveLen': inch(a.get('Ogive length') or a.get('Ogive length(radius with tip)')),
               'attrs': a, 'evidence': ((name + ' ') if name else '') + '; '.join(f'{k}: {v}' for k, v in pairs)}
        if code:
            assert code not in out, code
            out[code] = rec
    return out


def parse_lapua_bul():
    with zipfile.ZipFile(LAPUA_QTU_ZIP) as z:
        raw = z.read(LAPUA_BUL_MEMBER).decode('latin-1')
    header = [l for l in raw.splitlines() if l.startswith(';')]
    rows = []
    for line in raw.splitlines():
        if not line.startswith('"') or '[bullet]' in line:
            continue
        f = re.findall(r'"([^"]*)"', line)
        if len(f) < 11:
            continue
        name = f[0]
        codes = re.findall(r'\b((?:GB|G|B|S|E|N|D|C|EB|AP)\d{2,3})\b', name)
        rows.append({'line': line.strip(), 'name': collapse(name), 'codes': codes, 'gr': num(f[1]),
                     'len': num(f[2]), 'dia': num(f[8]), 'bc': num(f[9]),
                     'g7row': f[6] == 'G7' or name.rstrip().endswith('G7')})
    return rows, header


LAPUA_LINE_WORDING = {
    # line family -> (construction, tip, profile, wording source text)
    'Scenar-L': ('cup-and-core', 'open tip match (OTM)', 'open tip match, boat tail',
                 'Lapua: "Scenar-L (Open Tip Match)" (2026 catalog p.9); "higher standards of jacket wall concentricity" '
                 '(catalog p.9 and product page). Core material not stated; mapped to cup-and-core from the jacket wording.'),
    'Scenar': (None, 'open tip match (OTM)', 'open tip match, boat tail',
               'Lapua: "Scenar (Open Tip Match)" (catalog p.9); product page: "an open tip match bullet with a boat tail '
               'design". Jacket/core construction not stated in the sources consulted -> construction null.'),
    'MaxRange Target': (None, 'open tip match (OTM)', 'open tip match, boat tail',
                        'Lapua: type "OTM"; catalog p.9: "this boat-tailed projectile". Construction not stated -> null.'),
    'Naturalis': ('monolithic-copper', None, 'lead-free expanding (type CEX)',
                  'Lapua: "Naturalis (Lead free, expanding bullet)"; "designed and manufactured by using pure copper" '
                  '(catalog p.9/p.11); product page "Bullet type: Lead-free copper".'),
    'TrueRange Expanding': ('monolithic-copper', 'polymer tip', 'lead-free expanding, polymer tipped, boat tail',
                            'Lapua: "Solid copper TRX bullet ... solid-copper, polymer-tipped design" (catalog p.9); '
                            '"Instantly recognizable blue tip" (catalog p.2).'),
    'Mega': ('bonded', 'soft point', 'soft point',
             'Lapua: "Mega bullet is a soft point jacketed hunting bullet ... traditional lead core ... The mechanical '
             'bonding locks the lead alloy in place" (catalog p.9); "lead-core and copper jacket that are bonded" '
             '(catalog p.11); product page says "protective brass jacket". Bond is mechanical.'),
    'Soft Point': (None, 'soft point', 'soft point',
                   'Lapua: "Soft Point (Soft point bullet)" (catalog p.9). Jacket/core not stated -> construction null.'),
    'FMJ': ('FMJ', None, 'full metal jacket', 'Lapua type "FMJ" (Full Metal Jacket).'),
    'FMJ Cutting Edge': ('FMJ', None, 'full metal jacket, cutting edge', 'Lapua type "FMJCE"; product page "Full metal Jacket (FMJ)".'),
    'FMJBT': ('FMJ', None, 'full metal jacket boat tail', 'Lapua type "FMJBT" (Full Metal Jacket Boat Tail).'),
    'OT Cutting Edge': (None, 'open tip', 'open tip, cutting edge',
                        'Lapua type "OTCE"; "An open tip bullet" (catalog p.9). Construction not stated -> null.'),
    'Open Tip': (None, 'open tip', 'open tip', 'Lapua: "Open Tip (Open tip bullet)" (catalog p.9). Construction not stated -> null.'),
    'Lead Wadcutter': ('lead', None, 'wadcutter', 'Lapua: "Lead Wadcutter" (LWC).'),
}


def lapua_family(name, typ):
    n = (name or '').replace('Max Range', 'MaxRange')
    for fam in ('Scenar-L', 'Scenar', 'MaxRange Target', 'Naturalis', 'TrueRange Expanding', 'Mega', 'Soft Point',
                'FMJ Cutting Edge', 'OT Cutting Edge', 'Open Tip', 'Lead Wadcutter'):
        if n.startswith(fam):
            return fam
    if typ == 'FMJBT':
        return 'FMJBT'
    if n.startswith('FMJ'):
        return 'FMJ'
    return None


def lapua_records():
    comp = parse_lapua_components()
    bands = parse_lapua_bc_bands()
    prods = parse_lapua_products()
    bul, bul_header = parse_lapua_bul()

    by_code = {}
    for r in comp:
        by_code.setdefault(r['code'], []).append(r)
    codes = list(by_code)
    extra_prod = [c for c in prods if c not in by_code]
    recs = []
    for code in codes + extra_prod:
        rows = by_code.get(code, [])
        p = prods.get(code)
        bb = bands.get(code)
        sources, evid, conflicts, notes = [], [], [], []
        for r in rows:
            sources.append(src(LAPUA_CAT_URL, page=18)); evid.append(r['evidence'])
        if p:
            sources.append(src(p['url'])); evid.append(p['evidence'])
        if bb:
            sources.append(src(LAPUA_CAT_URL, page=12)); evid.append(bb['evidence'])
        r0 = rows[0] if rows else None
        # prefer the row that is the plain component listing (not the "NEW!" case-row duplicate)
        for r in rows:
            if r.get('extra') != 'NEW!':
                r0 = r
                break
        field_src = {}
        i_cat = rows.index(r0) if r0 else None
        i_pp = len(rows) if p else None
        i_bb = len(rows) + (1 if p else 0) if bb else None
        for f_ in ('sku', 'diameterIn', 'diameterMm', 'weightGr', 'weightG', 'bcG1', 'bcG7'):
            field_src[f_] = i_cat if r0 else i_pp

        def chk(field, vals, out_field, tol=1e-9):
            vals = [(s, v) for s, v in vals if v is not None]
            distinct = []
            for s, v in vals:
                if not any(same(v, d, tol) for d in distinct):
                    distinct.append(v)
            if len(distinct) > 1:
                conflicts.append({'field': out_field, 'values': [{'value': v, 'source': s} for s, v in vals]})
            elif len({v for s, v in vals}) > 1:
                notes.append('%s printed with different rounding: %s.' % (out_field, '; '.join('%s %s' % (s, v) for s, v in vals)))

        CAT = 'Lapua 2026 catalog p.18 components table'
        PP = 'lapua.com product page'
        if r0:
            line_name = r0['name']
            fam = lapua_family(line_name, r0['type'])
            name = (p or {}).get('name') or collapse('%s %s %s' % (line_name, code, r0['type']))
            sku = r0['prodno']
            dia = num(r0['in'])
            dia_mm = r0['mm']
            weight_gr = r0['gr']
            weight_g = r0['g']
            g1 = r0['g1']
            g7 = r0['g7']
            cal = r0['caliber']
            typ = r0['type']
            status = 'current (Lapua 2026 catalog components table%s)' % (', marked NEW!' if any(r.get('extra') == 'NEW!' for r in rows) else '')
            firearm = 'handgun' if r0['table'] == 'handgun' else 'rifle'
            for r in rows[1:]:
                for fld, of in (('gr', 'weightGr'), ('g1', 'bcG1'), ('g7', 'bcG7'), ('in', 'diameterIn')):
                    if not same(num(r[fld]) if fld == 'in' else r[fld], num(r0[fld]) if fld == 'in' else r0[fld]):
                        conflicts.append({'field': of, 'values': [{'value': r0[fld], 'source': CAT}, {'value': r[fld], 'source': CAT + ' (second row)'}]})
            if len(rows) > 1:
                notes.append('Listed twice on catalog p.18 (product nos. %s).' % ', '.join(r['prodno'] for r in rows))
        else:
            fam = lapua_family(p.get('line'), None)
            name = p['name']; sku = p['prodno']; dia = p['dia']; dia_mm = None
            weight_gr = p['gr']; weight_g = p['g']; g1 = p['g1']; g7 = p['g7']; cal = p['caliber']; typ = p['type']
            status = 'listed on lapua.com product page (retrieved %s); not in 2026 catalog components table' % RETRIEVED
            firearm = 'handgun' if 'S&W' in (cal or '') else 'rifle'
        if p:
            hm = re.match(r'([\d,.]+)\s*g\s*/\s*(\d+)\s*gr', p.get('name') or '')
            h_g = num(hm.group(1)) if hm else None
            h_gr = num(hm.group(2)) if hm else None
            chk('gr', [(CAT, weight_gr if r0 else None), (PP + ' weight field', p['gr']), (PP + ' heading', h_gr)], 'weightGr')
            chk('g', [(CAT, weight_g if r0 else None), (PP + ' weight field', p['g']), (PP + ' heading', h_g)], 'weightG', tol=0.051)
            chk('g1', [(CAT, g1 if r0 else None), (PP, p['g1'])], 'bcG1')
            chk('g7', [(CAT, g7 if r0 else None), (PP, p['g7'])], 'bcG7')
            chk('dia', [(CAT, dia if r0 else None), (PP, p['dia'])], 'diameterIn')
        # de-duplicate identical conflict entries
        seen = set(); dedup = []
        for c in conflicts:
            k = json.dumps(c, sort_keys=True)
            if k not in seen:
                seen.add(k); dedup.append(c)
        conflicts = dedup

        bcnotes = None
        if bb:
            parts = ['%s (%s): %s' % (m_s, f_s, raw) for m_s, f_s, v, raw in bb['bands']]
            bcnotes = 'Lapua 2026 catalog p.12 G1 BC by velocity band: ' + '; '.join(parts)
            if bb['g7']:
                bcnotes += '. G7 BC %s (%s): %s' % (bb['g7'][0], bb['g7'][1], bb['g7'][3])
            bcnotes += '. Catalog p.12: "For ultimate accuracy and precision, Lapua uses radar based data for all tactical projectile ballistics."'
            if bb['g7'] and g7 is not None and not same(bb['g7'][2], g7):
                conflicts.append({'field': 'bcG7', 'values': [{'value': g7, 'source': CAT},
                                                             {'value': bb['g7'][2], 'source': 'Lapua 2026 catalog p.12 (G7 > 380 m/s)'}]
                                  + ([{'value': p['g7'], 'source': PP}] if p and p.get('g7') is not None else [])})
            if bb['g7'] and g7 is None:
                g7 = bb['g7'][2]
                field_src['bcG7'] = i_bb
                notes.append('bcG7 taken from catalog p.12 (G7 > 380 m/s); the p.18 components table gives no G7 for this bullet.')

        # length: TRX product pages publish dimensions; otherwise QuickTARGET lapua.bul (low confidence)
        length = None; length_conf = None; bt = None; bearing = None
        if p and p.get('oal') is not None:
            length = p['oal']; length_conf = 'high'
            bt = p.get('bt'); bearing = p.get('bearing')
            field_src.update({'lengthIn': i_pp, 'boatTailLengthIn': i_pp, 'bearingSurfaceIn': i_pp})
            notes.append('Dimensions from the lapua.com product page (OAL, boat tail length, bearing surface length, '
                         'ogive length given in mm and inches; inch values used).')
            if p.get('ogiveLen') is not None:
                notes.append('Product page ogive length: %s in.' % p['ogiveLen'])
        bul_used = None
        if length is None:
            cands = [b for b in bul if code in b['codes'] and not b['g7row']]
            ok = [b for b in cands if same(b['gr'], weight_gr) and dia is not None and same(b['dia'], dia)]
            if ok:
                b = ok[0]
                lens = {x['len'] for x in ok}
                if len(lens) > 1:
                    notes.append('lapua.bul has several matching entries with different lengths %s; length left null.' % sorted(lens))
                elif g1 is not None and b['bc'] is not None and abs(b['bc'] - g1) > 0.01:
                    notes.append('lapua.bul entry "%s" (length field %s in) rejected: its G1 BC %s disagrees with the '
                                 'catalog G1 %s, so it may describe an older/different design.' % (b['name'], b['len'], b['bc'], g1))
                else:
                    length = b['len']; length_conf = 'low'; bul_used = b
                    notes.append('lengthIn from Lapua-distributed QuickTARGET Unlimited Lapua Edition data file lapua.bul '
                                 '(dated 3-Feb-15, inside QTU.zip on lapua.com downloads page): third field of entry "%s". '
                                 'The file does not label its columns (QuickTARGET uses this field for bullet length in '
                                 'inches); matched on bullet code %s, weight %s gr and diameter %s in. Low confidence: '
                                 'verify by measuring.' % (b['name'], code, b['gr'], b['dia']))
            elif cands:
                notes.append('lapua.bul has entries naming %s but none matching weight %s gr and diameter %s in: %s.'
                             % (code, weight_gr, dia, '; '.join('"%s" %s gr' % (x['name'], x['gr']) for x in cands)))
        if bul_used:
            sources.append(src(LAPUA_QTU_URL, page=None)); evid.append(collapse(bul_used['line']))
            field_src['lengthIn'] = len(sources) - 1
        if p and p.get('twist'):
            field_src['recommendedTwist'] = i_pp

        cons, tip, prof, wording = LAPUA_LINE_WORDING.get(fam, (None, None, None, None))
        if wording:
            notes.append('Construction/tip/profile wording: ' + wording)
        if typ:
            notes.append('Catalog type code: %s.' % typ)
        if p and p.get('purpose'):
            notes.append('Purpose (product page): %s.' % p['purpose'])
        if p and p.get('twist'):
            notes.append('Product page twist rate: %s.' % p['twist'])
        if code == 'GB582':
            mp = os.path.join(SRC, 'lapua', 'page-maxrt.html')
            if os.path.exists(mp):
                for l in page_lines(mp):
                    if 'GB546' in l and '144 gr' in l:
                        notes.append('lapua.com/maxrt/ page quote names this 6.5 mm 144 gr MaxRange Target bullet '
                                     '"GB546" (catalog p.18 and the product page say GB582; GB546 is the 136 gr '
                                     'Scenar-L): "%s"' % l[:220])
                        break
        if p and p['file'].startswith('6-5-mm-175-gr'):
            notes.append('Product page URL slug says "175-gr" but its weight field says 9.3 g (144 gr).')

        rec = {
            'id': 'lapua-%s' % code.lower(),
            'manufacturer': 'Lapua (Nammo Lapua Oy)',
            'line': {'TrueRange Expanding': 'TrueRange Expanding (TRX)', 'FMJBT': (r0 or {}).get('name') or (p or {}).get('line'),
                     'MaxRange Target': 'MaxRange Target (MaxRT)'}.get(fam, fam) if fam else ((r0 or {}).get('name') or (p or {}).get('line')),
            'name': name,
            'sku': sku,
            'bulletCode': code,
            'caliberLabel': cal,
            'diameterIn': dia,
            'diameterMm': dia_mm,
            'weightGr': weight_gr,
            'weightG': weight_g,
            'lengthIn': length,
            'lengthConfidence': length_conf,
            'boatTailLengthIn': bt,
            'baseToOgiveIn': None,
            'bearingSurfaceIn': bearing,
            'bcG1': g1,
            'bcG7': g7,
            'bcNotes': bcnotes,
            'profile': prof,
            'tip': tip,
            'construction': cons,
            'recommendedTwist': (p or {}).get('twist'),
            'twistInches': twist_inches((p or {}).get('twist')),
            'status': status,
            'firearm': firearm,
            'sources': sources,
            'evidence': ' || '.join(evid),
            'fieldSourceIndex': field_src,
            'conflicts': conflicts,
            'notes': ' '.join(notes) or None,
        }
        recs.append(rec)
    docs = [
        {'url': LAPUA_CAT_URL, 'localPath': LAPUA_CAT_PDF, 'title': 'Lapua Catalog 2026 (English, web)',
         'date': '2026-03-23 (PDF creation date)'},
        {'url': LAPUA_DOWNLOADS_URL, 'localPath': os.path.join(SRC, 'lapua', 'downloads.html'),
         'title': 'Lapua Downloads & Press Materials page (links to catalog PDFs and QTU.zip)', 'date': RETRIEVED},
        {'url': LAPUA_QTU_URL, 'localPath': LAPUA_QTU_ZIP,
         'title': 'Lapua QTU zip file (QuickTARGET Unlimited Lapua Edition); member data/bullets/lapua.bul. Header: '
                  + ' / '.join(h.strip('; ').strip() for h in bul_header),
         'date': '2020-07-30 (Last-Modified); lapua.bul dated 3-Feb-15'},
        {'url': LAPUA_MAXRT_URL, 'localPath': os.path.join(SRC, 'lapua', 'page-maxrt.html'),
         'title': 'Lapua MaxRange Target page', 'date': RETRIEVED},
    ] + [{'url': u, 'localPath': lapua_list_local(u), 'title': 'Lapua bullets product listing', 'date': RETRIEVED}
         for u in LAPUA_LIST_URLS] \
      + [{'url': p['url'], 'localPath': os.path.join(LAPUA_PROD_DIR, p['file']),
          'title': 'Lapua product page: %s' % p['name'], 'date': RETRIEVED} for p in prods.values()]
    stats = {'lapuaComponentRows': len(comp), 'lapuaCodes': len(codes), 'lapuaProductPages': len(prods),
             'lapuaProductOnly': extra_prod, 'lapuaBandRows': len(bands), 'lapuaBulRows': len(bul)}
    return recs, docs, stats


# ----------------------------------------------------------------------------
# output + self-check
# ----------------------------------------------------------------------------

NUMERIC_FIELDS = ['diameterIn', 'weightGr', 'lengthIn', 'boatTailLengthIn', 'baseToOgiveIn', 'noseLengthIn',
                  'bearingSurfaceIn', 'sectionalDensity', 'bcG1', 'bcG7', 'g7FormFactor', 'weightG', 'diameterMm']


def number_forms(v):
    """Printed forms a parsed float may take in the evidence text."""
    forms = set()
    for nd in (0, 1, 2, 3, 4):
        s = ('%.' + str(nd) + 'f') % v
        if abs(float(s) - v) < 1e-9:
            forms.add(s)
            forms.add(s.replace('.', ','))
            if s.startswith('0.'):
                forms.add(s[1:])
                forms.add(s[1:].replace('.', ','))
    if float(v).is_integer():
        forms.add(str(int(v)))
    return forms


def evidence_has(ev, v):
    for f in number_forms(v):
        if re.search(r'(?<![\d.,])' + re.escape(f) + r'(?![\d])', ev):
            return True
    return False


def self_check(data, verbose=True):
    recs = data['bullets']
    problems = []
    ids = [r['id'] for r in recs]
    if len(ids) != len(set(ids)):
        problems.append('duplicate ids')
    for r in recs:
        segs = r['evidence'].split(' || ')
        if len(segs) != len(r['sources']):
            problems.append('%s: %d evidence segments vs %d sources' % (r['id'], len(segs), len(r['sources'])))
        for f in NUMERIC_FIELDS:
            v = r.get(f)
            if v is None:
                continue
            if not evidence_has(r['evidence'], v):
                problems.append('%s: %s=%s not found in evidence' % (r['id'], f, v))
            i = r.get('fieldSourceIndex', {}).get(f)
            if i is None:
                problems.append('%s: %s has no fieldSourceIndex' % (r['id'], f))
            elif i >= len(segs) or not evidence_has(segs[i], v):
                problems.append('%s: %s=%s not in the evidence segment of its source #%s' % (r['id'], f, v, i))
        if r.get('recommendedTwist') and r['recommendedTwist'] not in r['evidence'] \
                and r['recommendedTwist'].replace('"', '”') not in r['evidence']:
            problems.append('%s: twist %s not in evidence' % (r['id'], r['recommendedTwist']))
        if r['sku'] and r['sku'] not in r['evidence']:
            problems.append('%s: sku %s not in evidence' % (r['id'], r['sku']))
        if r['construction'] not in ('cup-and-core', 'bonded', 'partition', 'monolithic-copper', 'monolithic-brass',
                                     'FMJ', 'lead', 'plated', None):
            problems.append('%s: bad construction %s' % (r['id'], r['construction']))
        for c in r['conflicts']:
            for v in c['values']:
                if isinstance(v['value'], (int, float)) and not evidence_has(r['evidence'], v['value']):
                    problems.append('%s: conflict value %s=%s not in evidence' % (r['id'], c['field'], v['value']))
        # plausibility (flags only; never alters data)
        if r.get('diameterIn') and not (0.17 <= r['diameterIn'] <= 0.51):
            problems.append('%s: implausible diameter %s' % (r['id'], r['diameterIn']))
        if r.get('lengthIn') and r.get('diameterIn') and not (1.5 <= r['lengthIn'] / r['diameterIn'] <= 7.0):
            problems.append('%s: implausible length/diameter %s/%s' % (r['id'], r['lengthIn'], r['diameterIn']))
    if verbose:
        print('records: %d (Berger %d, Lapua %d)' % (len(recs), sum(r['manufacturer'].startswith('Berger') for r in recs),
                                                    sum(r['manufacturer'].startswith('Lapua') for r in recs)))
        rnd = random.Random(20261123)
        for r in rnd.sample(recs, 5):
            print('---', r['id'], '|', r['name'])
            print('   ', {k: r[k] for k in ('diameterIn', 'weightGr', 'lengthIn', 'boatTailLengthIn', 'baseToOgiveIn',
                                            'bcG1', 'bcG7', 'recommendedTwist')})
            print('    evidence:', r['evidence'][:600])
            print('    conflicts:', r['conflicts'])
        flagged = [r for r in recs if r.get('qualityFlags')]
        print('records with qualityFlags (source inconsistencies, data kept as published): %d' % len(flagged))
        for r in flagged:
            for fl in r['qualityFlags']:
                print('   flag', r['id'], '-', fl)
        nconf = sum(1 for r in recs if r['conflicts'])
        print('records with conflicts: %d' % nconf)
        print('problems: %d' % len(problems))
        for p in problems:
            print('  ', p)
    return problems


def add_quality_flags(recs):
    """Consistency checks between published numbers. They only add flags; values stay as published."""
    dims = {}
    for r in recs:
        fl = []
        if r.get('weightGr') and r.get('weightG') and abs(r['weightG'] * 15.4324 - r['weightGr']) > 1.0:
            fl.append('published grams (%s g = %.1f gr) and grains (%s gr) differ by more than 1 gr'
                      % (r['weightG'], r['weightG'] * 15.4324, r['weightGr']))
        if r.get('sectionalDensity') and r.get('weightGr') and r.get('diameterIn'):
            sd = r['weightGr'] / 7000.0 / r['diameterIn'] ** 2
            if abs(sd - r['sectionalDensity']) > 0.003:
                fl.append('published sectional density %s differs from weight/7000/diameter^2 = %.3f'
                          % (r['sectionalDensity'], sd))
        if r.get('g7FormFactor') and r.get('bcG7') and r.get('sectionalDensity'):
            ffc = r['sectionalDensity'] / r['bcG7']
            if abs(ffc - r['g7FormFactor']) > 0.01:
                fl.append('published G7 form factor %s differs from SD/G7 BC = %.3f; one of SD, G7 BC or form factor '
                          'is likely mis-printed by the maker' % (r['g7FormFactor'], ffc))
        key = tuple(r.get(k) for k in ('diameterIn', 'lengthIn', 'boatTailLengthIn', 'baseToOgiveIn', 'noseLengthIn',
                                       'bearingSurfaceIn'))
        if r['manufacturer'].startswith('Berger') and None not in key[:2] and key[2:] != (None,) * 4:
            dims.setdefault(key, []).append(r['id'])
        r['qualityFlags'] = fl
    by_id = {r['id']: r for r in recs}
    for key, ids in dims.items():
        if len(ids) > 1:
            for i in ids:
                by_id[i]['qualityFlags'].append(
                    'all published dimensions (OAL, boat tail, base to ogive, nose, bearing) are identical to those '
                    'published for %s (in each source consulted) although it is a different bullet; possible copy '
                    'error in the maker data - verify by measurement' % ', '.join(x for x in ids if x != i))


def build():
    brecs, bdocs, bstats = berger_records()
    lrecs, ldocs, lstats = lapua_records()
    add_quality_flags(brecs + lrecs)
    notes = (
        'Berger: newest edition is the 2026 catalog (English PDF dated 2026-01-21, linked from the "2026 Catalogs" nav '
        'item); it lists part #, sectional density, G1/G7 BC, G7 form factor and minimum twist but no dimensions. '
        'Dimensions (OAL = lengthIn, boat tail, nose length, base to ogive, bearing surface, diameter) come from the '
        'live bergerbullets.com "Bullet Reference Charts" page, cross-checked against the 2024 catalog reference charts '
        'and a few product pages. Value precedence: BC/SD/form factor/twist = 2026 catalog > web chart > product page '
        '> 2024 catalog; dimensions = web chart > product page > 2024 catalog, except where the web value breaks '
        'Berger\'s own OAL = nose + bearing + boat tail relation by > 0.05 in and a conflicting catalog value restores it '
        '(explained per record). Every disagreement is kept in "conflicts". Berger twist values are MINIMUM twist. '
        'Berger ammunition tables (catalog pp.13-15) are not bullets and are not extracted. '
        'Lapua: 2026 English catalog (PDF dated 2026-03-23) components tables p.18 (rifle + handgun) are primary; '
        'lapua.com product pages cross-checked; catalog p.12 velocity-banded G1 BCs go to bcNotes (military AP/API '
        'bullets on p.12 are not reloading components and are skipped). Lapua publishes bullet dimensions only for '
        'the TRX bullets (product pages, lengthConfidence "high"); other Lapua lengths come from the Lapua-distributed '
        'QuickTARGET file lapua.bul (unlabeled column, lengthConfidence "low", only when code, weight, diameter and G1 '
        'BC agree with the catalog). Lapua ids use the bullet code (lapua-gb544); sku = Lapua product no. '
        'Field conventions: evidence holds one verbatim (whitespace-collapsed) text line per source, in the same order '
        'as "sources", joined by " || " (PDF table rows rebuilt from pdftotext word boxes keep the PDF words in reading '
        'order); recommendedTwist is the string as printed, twistInches its number; construction is mapped from the '
        'maker\'s wording quoted in notes, null when the wording does not state it. Extra fields beyond the requested '
        'schema: noseLengthIn, bearingSurfaceIn, sectionalDensity, g7FormFactor, lengthConfidence, bulletCode, '
        'weightG, diameterMm, twistInches, firearm, conflicts.')
    data = {
        'meta': {
            'key': 'bullets-berger-lapua',
            'retrieved': RETRIEVED,
            'documents': bdocs + ldocs,
            'notes': notes,
            'stats': {**bstats, **lstats},
        },
        'bullets': brecs + lrecs,
    }
    return data


def main():
    if '--download' in sys.argv:
        download()
        return
    if '--check' in sys.argv:
        data = json.load(open(OUT, encoding='utf-8'))
        probs = self_check(data)
        sys.exit(1 if probs else 0)
    data = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')
    print('wrote', OUT)
    self_check(data)


if __name__ == '__main__':
    main()
