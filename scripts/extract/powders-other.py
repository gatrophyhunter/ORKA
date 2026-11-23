#!/usr/bin/env python3
"""Extract powder catalog data (and burn-rate chart orderings) for the "other" powder makers.

Covered publishers (all public pages / PDFs, fetched with plain curl and its default user agent):
  * Vihtavuori (vihtavuori.com): Reloading Guide 2026 (package-info page lists bulk density and
    energy content per powder), Burning Rate Chart (tabloid PDF), product pages (grain dimensions,
    base, temperature claims), series pages and the RELO safety data sheets (composition ranges).
  * Norma (www.norma-ammunition.com): gunpowder product pages (bulk density min, energy J/g).
  * Reload Swiss (www.reload-swiss.com): product data sheets (EN PDFs) + product pages
    (explosion heat, bulk density, grain dimensions) and the burn-rate chart PDF.
  * Shooters World (shootersworldpowder.com, robots.txt Crawl-delay 10): product pages,
    the Shooters World reloading manual PDF (powder descriptions, base classes, burn chart).
  * Accurate/Ramshot (westernpowders.com) and ADI (adi-powders.com.au): NOT reachable from this
    environment (TLS reset / proxy 502), recorded in meta.blocked.

Usage:
  python3 -I powders-other.py --download   # fetch missing source documents, then parse
  python3 -I powders-other.py              # parse cached documents and write JSON + self-check

Every value is parsed with code from `pdftotext -layout` text or page HTML; nothing is typed in.
Each record carries the verbatim (whitespace-collapsed) evidence text the values came from.
"""
import html as htmlmod
import json
import os
import random
import re
import subprocess
import sys
import time

SRC = '/tmp/claude-0/-home-user-ORKA/29ce603d-ccc3-55ef-b8fe-c585397ac7c1/scratchpad/sources/powders-other'
OUT = '/home/user/ORKA/research/raw2/powders-other.json'
RETRIEVED = '2026-11-23'

POWDER_NAME_VV = r'(?:N\d{3}|\d{1,2}N\d{2})'

# --------------------------------------------------------------------------------------------
# Document registry
# --------------------------------------------------------------------------------------------
DOCS = {}


def reg(key, url, local, title, date=None, stype='manufacturer'):
    DOCS[key] = {'url': url, 'localPath': os.path.join(SRC, local), 'title': title,
                 'date': date, 'type': stype}
    return key


VV_GUIDE = reg('vv-guide', 'https://vihtavuori.com/wp-content/uploads/2026/04/Vihtavuori_Reloading_Guide_2026_ENG_web.pdf',
               'vv/Vihtavuori_Reloading_Guide_2026_ENG_web.pdf', 'Vihtavuori Reloading Guide 2026 (ENG, web)',
               '2026 (PDF created 2026-03-24)')
VV_CHART = reg('vv-chart', 'https://vihtavuori.com/wp-content/uploads/2025/11/Vihtavuori_BurningRateChart_Tabloid.pdf',
               'vv/Vihtavuori_BurningRateChart_Tabloid.pdf', 'Vihtavuori Burning Rate Chart (tabloid)',
               'PDF created 2025-11-25')
VV_SDS_NG = reg('vv-sds-n500', 'https://vihtavuori.com/wp-content/uploads/2026/08/N-Powder-High-Energy-N500-series-RELO-19-01-2026-en.pdf',
                'vv/N-Powder-High-Energy-N500-series-RELO-19-01-2026-en.pdf',
                'Safety Data Sheet: N-Powder High Energy, N500-series (RELO)', '2026-01-19')
VV_OVERVIEW = reg('vv-overview', 'https://vihtavuori.com/powders-and-primers/powders/vihtavuori-powders/',
                  'vv/pages/powders-and-primers__powders__vihtavuori-powders.html', 'Vihtavuori Powders (overview page)')
VV_SITEMAP_URL = 'https://vihtavuori.com/powder-sitemap.xml'
VV_SITEMAP_LOCAL = os.path.join(SRC, 'vv/powder-sitemap.xml')
VV_DOWNLOADS_URL = 'https://vihtavuori.com/resources/news-media/downloads/'
VV_DOWNLOADS_LOCAL = os.path.join(SRC, 'vv/downloads.html')

NORMA_LIST = reg('norma-list', 'https://www.norma-ammunition.com/products/components/gunpowder',
                 'norma/pages/gunpowder.html', 'Norma Gunpowder (product listing)')
NORMA_PRODUCTS = ['norma-1211---10902117', 'norma-1214---10902147', 'norma-1219---10902197',
                  'norma-200---20902005', 'norma-201---20902015', 'norma-202---20902025',
                  'norma-203-b---20902035', 'norma-204---20902045', 'norma-217---20902175',
                  'norma-mrp---20902155', 'norma-urp---20902195']
NORMA_SITEMAP_URL = 'https://www.norma-ammunition.com/products/sitemap/sitemap-products-en.xml'

RS_NUMS = ['12', '14', '20', '24', '30', '36', '40', '50', '52', '60', '62', '70', '76', '80']
RS_CHART = reg('rs-chart', 'https://www.reload-swiss.com/Reload%20Swiss/Service/Reload-Swiss-Burn-rate-chart.pdf',
               'rs/pdf/Reload-Swiss-Burn-rate-chart.pdf', 'Reload Swiss Abbrenngeschwindigkeit / Burn Rate Chart',
               '2024 (PDF created 2024-11-05)')
RS_SITEMAP_URL = 'https://www.reload-swiss.com/sitemap.site_9.xml'
RS_SITEMAP_LOCAL = os.path.join(SRC, 'rs/sitemap.xml')

SW_LIST = reg('sw-list', 'https://shootersworldpowder.com/products/', 'sw/pages/products.html',
              'Shooters World Products (listing)')
SW_MANUAL = reg('sw-manual', 'https://shootersworldpowder.com/wp-content/uploads/2023/06/ShootersWorldManualInterior_CHRIS_WITH-COVER__RUSS-REVISED.pdf',
                'sw/pdf/ShootersWorldManual.pdf', 'Shooters World Reloading Guide (manual PDF)', 'PDF created 2023-05-25')

BLOCKED = [
    {'url': 'https://www.westernpowders.com/robots.txt', 'reason': 'TLS connection reset (proxy: ws_closed_mid_exchange); site not reachable from this environment'},
    {'url': 'https://westernpowders.com/robots.txt', 'reason': 'TLS connection reset; not reachable'},
    {'url': 'https://www.adi-powders.com.au/robots.txt', 'reason': 'proxy 502 connect_unreachable'},
    {'url': 'https://adi-powders.com.au/robots.txt', 'reason': 'proxy 502 connect_unreachable'},
    {'url': 'https://web.archive.org/cdx/search/cdx?url=westernpowders.com/*', 'reason': 'host web.archive.org refused by egress proxy (403)'},
    {'url': 'https://archive.org/download/Accurate_Smokeless_Powder_2003/Accurate_Smokeless_Powder_2003.pdf',
     'reason': 'redirects to a dnXXXX.*.archive.org storage host which the egress proxy refuses (403)'},
]

# --------------------------------------------------------------------------------------------
# Download helpers (plain curl, default UA, per-host delay; robots.txt checked by hand:
# vihtavuori.com: only /wp-admin/ disallowed; norma: Allow /; reload-swiss: only utm/_Dummy
# disallowed; shootersworldpowder.com: Crawl-delay 10, Disallow /*? (no query URLs used).
# --------------------------------------------------------------------------------------------
_last = {}
HOST_DELAY = {'shootersworldpowder.com': 10.5}


def fetch(url, local, force=False):
    if not force and os.path.exists(local) and os.path.getsize(local) > 0:
        return True
    host = url.split('/')[2]
    delay = HOST_DELAY.get(host, 1.5)
    wait = _last.get(host, 0) + delay - time.time()
    if wait > 0:
        time.sleep(wait)
    os.makedirs(os.path.dirname(local), exist_ok=True)
    tmp = local + '.part'
    r = subprocess.run(['curl', '-sS', '-L', '-m', '300', '-o', tmp, '-w', '%{http_code}', url],
                       capture_output=True, text=True)
    _last[host] = time.time()
    code = r.stdout.strip()
    if code == '200' and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
        os.replace(tmp, local)
        print(f'  fetched {url} -> {local}')
        return True
    if os.path.exists(tmp):
        os.remove(tmp)
    print(f'  FAILED {url}: http {code} {r.stderr.strip()[:200]}')
    return False


def vv_product_urls():
    if not os.path.exists(VV_SITEMAP_LOCAL):
        return []
    s = open(VV_SITEMAP_LOCAL, encoding='utf-8').read()
    return [u for u in re.findall(r'<loc>([^<]+)</loc>', s) if '/powder/' in u and 'wp-content' not in u]


def vv_page_local(url):
    rel = url.replace('https://vihtavuori.com/', '').strip('/').replace('/', '__')
    return os.path.join(SRC, 'vv/pages', rel + '.html')


def rs_product_urls():
    if not os.path.exists(RS_SITEMAP_LOCAL):
        return []
    s = open(RS_SITEMAP_LOCAL, encoding='utf-8').read()
    return [u for u in re.findall(r'<loc>([^<]+)</loc>', s) if re.search(r'/en/product/(pistol|rifle)/rs\d\d', u)]


def rs_page_local(url):
    rel = url.replace('https://www.reload-swiss.com/', '').strip('/').replace('/', '__')
    return os.path.join(SRC, 'rs/pages', rel + '.html')


def sw_product_urls():
    p = DOCS[SW_LIST]['localPath']
    if not os.path.exists(p):
        return []
    s = open(p, encoding='utf-8').read()
    return sorted(set(re.findall(r'href="(https://shootersworldpowder\.com/portfolio_page/[^"#?]+)"', s)))


def sw_page_local(url):
    import urllib.parse
    slug = urllib.parse.unquote(url.rstrip('/').rsplit('/', 1)[1]).replace('½', 'half')
    return os.path.join(SRC, 'sw/pages', 'pp_' + slug + '.html')


def download_all():
    fetch(VV_SITEMAP_URL, VV_SITEMAP_LOCAL)
    fetch(VV_DOWNLOADS_URL, VV_DOWNLOADS_LOCAL)
    for k in (VV_GUIDE, VV_CHART, VV_SDS_NG, VV_OVERVIEW):
        fetch(DOCS[k]['url'], DOCS[k]['localPath'])
    for u in vv_product_urls():
        fetch(u, vv_page_local(u))
    fetch(DOCS[NORMA_LIST]['url'], DOCS[NORMA_LIST]['localPath'])
    for p in NORMA_PRODUCTS:
        fetch('https://www.norma-ammunition.com/products/components/gunpowder/' + p,
              os.path.join(SRC, 'norma/pages', p + '.html'))
    fetch(RS_SITEMAP_URL, RS_SITEMAP_LOCAL)
    fetch(DOCS[RS_CHART]['url'], DOCS[RS_CHART]['localPath'])
    for u in rs_product_urls():
        fetch(u, rs_page_local(u))
    for n in RS_NUMS:
        fetch(f'https://www.reload-swiss.com/Reload%20Swiss/Produkte/RS{n}/RS{n}-EN.pdf',
              os.path.join(SRC, f'rs/pdf/RS{n}-EN.pdf'))
    fetch(DOCS[SW_LIST]['url'], DOCS[SW_LIST]['localPath'])
    fetch(DOCS[SW_MANUAL]['url'], DOCS[SW_MANUAL]['localPath'])
    for u in sw_product_urls():
        fetch(u, sw_page_local(u))


# --------------------------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------------------------
def collapse(s):
    return ' '.join(s.split())


_pdf_cache = {}


def pdf_pages(local, layout=True):
    """Return list of page texts (1-based page i is index i-1)."""
    key = (local, layout)
    if key in _pdf_cache:
        return _pdf_cache[key]
    args = ['pdftotext'] + (['-layout'] if layout else []) + [local, '-']
    r = subprocess.run(args, capture_output=True, text=True)
    pages = r.stdout.split('\f')
    _pdf_cache[key] = pages
    return pages


def html_lines(local):
    s = open(local, encoding='utf-8', errors='replace').read()
    s = re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>', ' ', s)
    s = re.sub(r'(?is)<(br|/p|/div|/li|/h\d|/tr|/td|/th|/dt|/dd|/span)[^>]*>', '\n', s)
    t = re.sub(r'<[^>]+>', ' ', s)
    t = htmlmod.unescape(t)
    out = []
    for ln in t.split('\n'):
        c = collapse(ln)
        if c:
            out.append(c)
    return out


def html_title(local):
    s = open(local, encoding='utf-8', errors='replace').read()
    m = re.search(r'<title>([^<]*)</title>', s)
    return collapse(htmlmod.unescape(m.group(1))) if m else None


def sentences_with(text, pattern):
    """Sentences (split on '. ' boundaries, keeping decimal commas/points) matching pattern."""
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9“"(])', text)
    return [p for p in parts if re.search(pattern, p, re.I)]


def num(s):
    return float(s.replace(',', '.'))


def int_thousands(s):
    """'3’750', "3'750", '3.750', '1’000', '3750' -> int. Only for values printed as integers."""
    t = re.sub(r"[’'.,  ]", '', s)
    if not t.isdigit():
        raise ValueError(f'not an integer with thousands separators: {s!r}')
    return int(t)


def kebab(s):
    s = s.replace('½', '-1-2')
    s = re.sub(r'[^A-Za-z0-9]+', '-', s).strip('-').lower()
    return re.sub(r'-+', '-', s)


def src(docKey, page=None, url=None, extra=None):
    d = DOCS[docKey]
    o = {'url': url or d['url'], 'type': d['type'], 'page': page, 'retrieved': RETRIEVED}
    if extra:
        o.update(extra)
    return o


def new_record(mfr, brand, name, manufacturer):
    return {
        'id': f'{kebab(brand if brand else mfr)}-{kebab(name)}',
        'manufacturer': manufacturer,
        'brand': brand,
        'name': name,
        'form': None,
        'base': None,
        'containsNitroglycerin': None,
        'nitroglycerinPct': None,
        'nitroglycerinPctRange': None,
        'applications': None,
        'temperatureStableClaim': None,
        'bulkDensityGcc': None,
        'bulkDensityStated': None,
        'heatOfExplosionJg': None,
        'heatOfExplosionLabel': None,
        'grainDimensions': None,
        'relativeBurnRate': None,
        'aliases': [],
        'status': None,
        'description': None,
        'sources': [],
        'evidence': '',
        'conflicts': [],
        'notes': '',
        '_ev': [],
    }


def add_ev(rec, text):
    t = collapse(text)
    if t and t not in rec['_ev']:
        rec['_ev'].append(t)


def add_src(rec, s):
    for e in rec['sources']:
        if e['url'] == s['url'] and e.get('page') == s.get('page'):
            return
    rec['sources'].append(s)


def add_note(rec, text):
    rec['notes'] = (rec['notes'] + ' ' + text).strip() if rec['notes'] else text


def add_conflict(rec, field, values):
    rec['conflicts'].append({'field': field, 'values': values})


def set_or_conflict(rec, field, value, source_label, current_label):
    """Set rec[field] if empty; if set and different, record a conflict (keep first value)."""
    if value is None:
        return
    cur = rec.get(field)
    if cur is None:
        rec[field] = value
        rec.setdefault('_fieldsrc', {})[field] = source_label
        return
    if cur != value:
        add_conflict(rec, field, [{'value': cur, 'source': rec.get('_fieldsrc', {}).get(field, current_label)},
                                  {'value': value, 'source': source_label}])


# --------------------------------------------------------------------------------------------
# Vihtavuori
# --------------------------------------------------------------------------------------------
VV_MFR = None  # set from the guide statement


def vv_parse(records, charts, problems):
    global VV_MFR
    guide = DOCS[VV_GUIDE]['localPath']
    pages = pdf_pages(guide, layout=True)
    raw_pages = pdf_pages(guide, layout=False)
    vv = {}

    # Manufacturer statement (preface)
    for pi, p in enumerate(pages):
        m = re.search(r'The Vihtavuori powders are manufactured by (Nammo Vihtavuori Oy)', p)
        if m:
            VV_MFR = m.group(1)
            vv_mfr_ev = (pi + 1, m.group(0))
            break
    else:
        problems.append('VV: manufacturer statement not found')
        vv_mfr_ev = None

    def get(name):
        if name not in vv:
            r = new_record('vihtavuori', 'Vihtavuori', name, VV_MFR)
            if vv_mfr_ev:
                add_ev(r, vv_mfr_ev[1])
                add_src(r, src(VV_GUIDE, vv_mfr_ev[0]))
            vv[name] = r
        return vv[name]

    # ---- Package-info page: bulk density (g/l) and energy content (J/g) tables
    tables_found = 0
    for pi, p in enumerate(pages):
        if 'Energy content (J/g)' not in p:
            continue
        lines = p.split('\n')
        for i, ln in enumerate(lines):
            m = re.match(r'^\s*((?:' + POWDER_NAME_VV + r'\s+){2,}' + POWDER_NAME_VV + r')(?=\s|$)', ln)
            if not m:
                continue
            names = m.group(1).split()
            # title line above (e.g. "Reloading Powders for Rifles")
            title = None
            for j in range(i - 1, max(-1, i - 6), -1):
                mt = re.search(r'((?:High Energy )?Reloading Powders for (?:Rifles|Handguns))', lines[j])
                if mt:
                    title = (j, mt.group(1))
                    break
            bd = en = None
            for j in range(i + 1, min(len(lines), i + 6)):
                mb = re.match(r'^\s*Bulk density \(g/l\)((?:\s+\d{3,4})+)', lines[j])
                me = re.match(r'^\s*Energy content \(J/g\)((?:\s+\d{3,4})+)', lines[j])
                if mb:
                    bd = (j, [int(x) for x in mb.group(1).split()])
                if me:
                    en = (j, [int(x) for x in me.group(1).split()])
            if not (bd and en):
                problems.append(f'VV guide p{pi+1}: header {names} without both value rows')
                continue
            if len(bd[1]) != len(names) or len(en[1]) != len(names):
                problems.append(f'VV guide p{pi+1}: column count mismatch {names} {bd[1]} {en[1]}')
                continue
            tables_found += 1
            # printed page numbers: spread pages; the package-info page is the left page of the spread
            for k, nm in enumerate(names):
                r = get(nm)
                ev_lines = ([lines[title[0]]] if title else []) + [ln, lines[bd[0]], lines[en[0]]]
                for e in ev_lines:
                    add_ev(r, e)
                add_src(r, src(VV_GUIDE, pi + 1, extra={'printedPage': '148', 'section': 'Package info / powder table'}))
                set_or_conflict(r, 'bulkDensityStated', {'value': bd[1][k], 'unit': 'g/l', 'qualifier': None,
                                                         'column': k + 1, 'columns': len(names)}, 'VV guide 2026', 'VV guide 2026')
                r['bulkDensityGcc'] = round(bd[1][k] / 1000.0, 4)
                r['heatOfExplosionJg'] = en[1][k]
                r['heatOfExplosionLabel'] = 'Energy content (J/g)'
                r['_fieldsrc'] = {**r.get('_fieldsrc', {}), 'heatOfExplosionJg': 'VV guide 2026 p148',
                                  'bulkDensityGcc': 'VV guide 2026 p148'}
                if title:
                    r['_guideTable'] = title[1]
    if tables_found != 3:
        problems.append(f'VV guide: expected 3 package-info tables, found {tables_found}')

    # ---- Series statements (overview page)
    ov = DOCS[VV_OVERVIEW]['localPath']
    ov_lines = html_lines(ov)
    ov_text = ' '.join(ov_lines)
    series_stmt = {}
    m1 = re.search(r'Vihtavuori N100 offers traditional single base propellants for rifle calibers\.', ov_text)
    m3 = re.search(r'Vihtavuori N300 offers porous single base gun powders and precise measuring for pistol cartridges and shotgun shells,', ov_text)
    m5 = re.search(r'The energy released from double-base smokeless powders \(such as the Vihtavuori N500 rifle powders\) is derived from both nitrocellulose and nitroglycerine\.', ov_text)
    m5b = re.search(r'Vihtavuori N500 series powders are special high energy rifle propellants enhanced with nitroglycerin for extra ballistic performance\.', ov_text)
    if m1:
        series_stmt['N100'] = {'base': 'single', 'applications': ['rifle'], 'ev': [m1.group(0)]}
    if m3:
        series_stmt['N300'] = {'base': 'single', 'applications': ['handgun', 'shotgun'], 'ev': [m3.group(0)], 'porous': True}
    if m5 and m5b:
        series_stmt['N500'] = {'base': 'double', 'applications': ['rifle'], 'ev': [m5.group(0), m5b.group(0)], 'ng': True}
    if len(series_stmt) != 3:
        problems.append(f'VV overview: series statements found {list(series_stmt)}')
    table_series = {'Reloading Powders for Rifles': 'N100', 'Reloading Powders for Handguns': 'N300',
                    'High Energy Reloading Powders for Rifles': 'N500'}
    for nm, r in vv.items():
        ser = table_series.get(r.get('_guideTable'))
        r['_series'] = ser
        st = series_stmt.get(ser)
        if st:
            r['base'] = st['base']
            r['applications'] = list(st['applications'])
            if st.get('ng'):
                r['containsNitroglycerin'] = True
            for e in st['ev']:
                add_ev(r, e)
            add_src(r, src(VV_OVERVIEW))
            add_note(r, f'Series {ser} membership from the Reloading Guide 2026 package-info table "{r["_guideTable"]}"; '
                        f'base/applications from the Vihtavuori series statement on the powders overview page.')
    # N105: listed with the N300 powders in the consumer-package chart on the overview page
    pk = [ln for ln in ov_lines if re.fullmatch(r'N310, N320 ?,? ?N330, N340, N350, 3N37, 3N38, N105', ln)]
    if pk:
        r = get('N105')
        add_ev(r, pk[0])
        add_src(r, src(VV_OVERVIEW))
        add_note(r, 'N105 has no product page and is not in the guide\'s bulk density / energy table; it appears in the '
                    'consumer-package chart together with the N300 powders and in the guide\'s shotgun load data.')
        # guide shotgun data line(s)
        for pi, p in enumerate(pages):
            for ln in p.split('\n'):
                if re.match(r'^\s*N105\s+Fio\. 616', ln):
                    add_ev(r, re.match(r'^\s*(N105\s+Fio\. 616.*?Roll Crimp)', ln).group(1))
                    add_src(r, src(VV_GUIDE, pi + 1, extra={'section': 'Shotgun reloading data'}))
                    break
            else:
                continue
            break

    # ---- Product pages
    same_claims = []
    for url in vv_product_urls():
        local = vv_page_local(url)
        if not os.path.exists(local):
            problems.append(f'VV product page missing: {url}')
            continue
        s = open(local, encoding='utf-8', errors='replace').read()
        mt = re.search(r'<h1 class="prod_title[^"]*">([^<]+)</h1>', s)
        if not mt:
            problems.append(f'VV: no title in {url}')
            continue
        title = collapse(htmlmod.unescape(mt.group(1)))
        mn = re.search(r'\b(' + POWDER_NAME_VV + r')\b', title)
        name = mn.group(1)
        body = s[mt.end():]
        cut = body.find('Reloading data available')
        if cut > 0:
            body = body[:cut]
        paras = [collapse(htmlmod.unescape(re.sub(r'<[^>]+>', ' ', p)))
                 for p in re.findall(r'(?is)<p class="wp-block-paragraph">(.*?)</p>', body)]
        paras = [p for p in paras if p]
        text = ' '.join(paras)
        r = get(name)
        add_src(r, src(VV_GUIDE, None, url=url) | {'type': 'manufacturer'})
        if paras:
            r['description'] = paras[0]
        # grain dimensions
        pats = [
            r'(\d+[,.]\d+)\s*mm\s*(?:in\s+)?length\s+(?:and|x|by)\s+(\d+[,.]\d+)\s*mm\s*(?:in\s+)?diameter',
            r'(\d+[,.]\d+)\s*mm\s*x\s*(\d+[,.]\d+)\s*mm\s*\(length x diameter\)',
        ]
        dims = None
        for pat in pats:
            for sent in sentences_with(text, pat):
                md = re.search(pat, sent)
                if md:
                    dims = (num(md.group(1)), num(md.group(2)), sent)
                    break
            if dims:
                break
        if dims:
            set_or_conflict(r, 'grainDimensions', {'lengthMm': dims[0], 'diameterMm': dims[1]}, url, url)
            add_ev(r, dims[2])
        # form keywords from powder-type sentences
        form_sents = sentences_with(text, r'\b(tubular|porous|extruded|single[- ]perforated|cylindrical)\b')
        form_sents = [x for x in form_sents if name in x or re.search(r'\b(It|This)\b', x)]
        kws = []
        for kw, kpat in (('single-perforated', r'\bsingle[- ]perforated\b'), ('cylindrical', r'\bcylindrical\b'),
                         ('extruded', r'\bextruded\b'), ('tubular', r'\btubular\b'), ('porous', r'\bporous\b')):
            if any(re.search(kpat, x, re.I) for x in form_sents):
                kws.append(kw)
        if kws:
            r['form'] = ', '.join(kws)
            for x in form_sents:
                add_ev(r, x)
        # explicit base statement on product page
        for sent in sentences_with(text, r'single[- ]based?\b'):
            if name in sent or sent.startswith(('It', 'These')):
                add_ev(r, sent)
                if r['base'] and r['base'] != 'single':
                    add_conflict(r, 'base', [{'value': r['base'], 'source': 'series statement'},
                                             {'value': 'single', 'source': url}])
                r['base'] = r['base'] or 'single'
        for sent in sentences_with(text, r'nitroglycerine'):
            add_ev(r, sent)
            r['containsNitroglycerin'] = True
        # temperature claims
        tclaims = sentences_with(text, r'temperature[- ](stable|stability|insensitive)|insensitiv\w* in extreme weather|temperature stable')
        if tclaims:
            r['temperatureStableClaim'] = ' '.join(tclaims)
            for x in tclaims:
                add_ev(r, x)
        # energy content / bulk density statements on the page (cross-check with guide)
        for sent in sentences_with(text, r'J/g|g/l'):
            me = re.search(r'energy content(?: of ' + name + r')? (?:is|of) (\d{4}) J/g', sent)
            mb = re.search(r'bulk density (?:is|of) (\d{3,4}) g/l', sent)
            if me or mb:
                add_ev(r, sent)
            if me:
                v = int(me.group(1))
                if r['heatOfExplosionJg'] is None:
                    r['heatOfExplosionJg'] = v
                    r['heatOfExplosionLabel'] = 'energy content (J/g)'
                elif r['heatOfExplosionJg'] != v:
                    add_conflict(r, 'heatOfExplosionJg', [{'value': r['heatOfExplosionJg'], 'source': DOCS[VV_GUIDE]['url']},
                                                          {'value': v, 'source': url}])
            if mb:
                v = int(mb.group(1))
                if r['bulkDensityStated'] is None:
                    r['bulkDensityStated'] = {'value': v, 'unit': 'g/l', 'qualifier': None}
                    r['bulkDensityGcc'] = round(v / 1000.0, 4)
                elif r['bulkDensityStated']['value'] != v:
                    add_conflict(r, 'bulkDensityGcc', [{'value': r['bulkDensityGcc'], 'source': DOCS[VV_GUIDE]['url']},
                                                       {'value': round(v / 1000.0, 4), 'source': url}])
        # former names
        for sent in sentences_with(text, r'known as'):
            ma = re.search(r'(?:formerly )?known as ([0-9A-Z]{2,6}(?: and [0-9A-Z]{2,6})*)', sent)
            if ma and name in sent:
                for a in ma.group(1).split(' and '):
                    r['aliases'].append({'name': a, 'relation': 'former name'})
                add_ev(r, sent)
        for sent in sentences_with(text, r'exactly the same'):
            others = [x for x in re.findall(r'\b' + POWDER_NAME_VV + r'\b', sent) if x != name]
            sd = None
            for pat in pats:
                md = re.search(pat, sent)
                if md:
                    sd = {'lengthMm': num(md.group(1)), 'diameterMm': num(md.group(2))}
                    break
            if others:
                same_claims.append((name, url, sent, sd, others))
        r['_productPage'] = url

    # ---- cross statements "X has exactly the same grain size as Y" vs Y's own stated dimensions.
    # Only sentences that print numbers create conflict values; number-less sentences only add notes.
    claims_by = {}
    for name, url, sent, sd, others in same_claims:
        group = [name] + sorted(set(others))
        for g in group:
            rg = vv.get(g)
            if rg is None:
                continue
            add_ev(rg, sent)
            add_src(rg, src(VV_GUIDE, None, url=url))
            if sd and g != name:
                claims_by.setdefault(g, []).append((sd, url))
        if not sd:
            stated = {g: ((vv[g]['grainDimensions']['lengthMm'], vv[g]['grainDimensions']['diameterMm'])
                          if g in vv and vv[g]['grainDimensions'] else None) for g in group}
            if len({d for d in stated.values() if d}) > 1:
                for g in sorted(set(group)):
                    if g in vv:
                        add_note(vv[g], f"The {name} product page says {', '.join(sorted(set(group)))} have exactly the same grain "
                                        f'dimensions, but the product pages state different (length, diameter) values: {stated}.')
    for g, cl in claims_by.items():
        rg = vv[g]
        own = rg['grainDimensions']
        if own:
            ownv = {'lengthMm': own['lengthMm'], 'diameterMm': own['diameterMm']}
            diff = [(c, u) for c, u in cl if c != ownv]
            if diff:
                vals = [{'value': ownv, 'source': rg.get('_productPage') or 'own product page'}]
                for c, u in diff:
                    vals.append({'value': c, 'source': u, 'basis': f'that page states its grains are exactly the same size as {g}\'s'})
                add_conflict(rg, 'grainDimensions', vals)
        else:
            for c, u in cl:
                add_note(rg, f'No own grain-dimension statement for {g}; {u} says its grains ({c["lengthMm"]} mm length x '
                             f'{c["diameterMm"]} mm diameter) are exactly the same as {g}\'s (not copied into grainDimensions).')

    # ---- Guide raw text (page 2): 24N41 grain size + relative burning rate index
    for pi, p in enumerate(raw_pages[:6]):
        t = collapse(p)
        m = re.search(r'Vihtavuori 24N41 is a single-based treated rifle powder very similar to the 20N29\. It has a very large grain size \(length (\d+,\d+) mm by diameter (\d+,\d+) mm\)', t)
        if m:
            r = get('24N41')
            add_ev(r, m.group(0))
            add_src(r, src(VV_GUIDE, pi + 1, extra={'printedPage': '3'}))
            set_or_conflict(r, 'grainDimensions', {'lengthMm': num(m.group(1)), 'diameterMm': num(m.group(2))},
                            'VV guide 2026 p3', 'VV guide 2026 p3')
            if r['base'] is None:
                r['base'] = 'single'
        m = re.search(r'Of the two, 24N41 is slightly faster than 20N29, with a renewed relative burning rate of (\d+) for the 24N41 compared to (\d+) for the 20N29, when N110 is given the index (\d+)\.', t)
        if m:
            for nm, v in (('24N41', int(m.group(1))), ('20N29', int(m.group(2)))):
                r = get(nm)
                add_ev(r, m.group(0))
                add_src(r, src(VV_GUIDE, pi + 1, extra={'printedPage': '3'}))
                r['relativeBurnRate'] = {'value': v, 'scale': 'Vihtavuori relative burning rate index',
                                         'reference': 'N110', 'referenceValue': int(m.group(3))}
        m = re.search(r'20N29 is a single-based, surface treated powder with grain dimensions of (\d+,\d+) mm length and (\d+,\d+) mm diameter\.', t)
        if m:
            r = get('20N29')
            add_ev(r, m.group(0))
            add_src(r, src(VV_GUIDE, pi + 1, extra={'printedPage': '3'}))
            set_or_conflict(r, 'grainDimensions', {'lengthMm': num(m.group(1)), 'diameterMm': num(m.group(2))},
                            'VV guide 2026 p3', 'VV guide 2026 p3')

    # ---- SDS: nitroglycerin concentration range for the N500 series
    sds = DOCS[VV_SDS_NG]['localPath']
    sp = pdf_pages(sds, layout=True)
    names_line = None
    for pi, p in enumerate(sp[:1]):
        mm = re.search(r'1\.1\s+Product identifier:\s+(N-Powder High Energy, N500-series \(RELO\))\s*\n\s*((?:' + POWDER_NAME_VV + r',\s*)+' + POWDER_NAME_VV + r')', p)
        if mm:
            names_line = (pi + 1, mm.group(0), re.findall(POWDER_NAME_VV, mm.group(2)))
    ng = None
    for pi, p in enumerate(sp):
        lines = p.split('\n')
        for i, ln in enumerate(lines):
            if re.search(r'CAS:\s*55-63-0\s+Nitroglycerin', ln):
                for j in range(i, min(len(lines), i + 3)):
                    mr = re.search(r'(\d+(?:[.,]\d+)?)\s*-\s*<\s*(\d+(?:[.,]\d+)?)\s*%\s*$', lines[j])
                    if mr:
                        ng = (pi + 1, [ln, lines[j]], num(mr.group(1)), num(mr.group(2)))
                        break
            if ng:
                break
        if ng:
            break
    if names_line and ng:
        for nm in names_line[2]:
            if nm in vv:
                r = vv[nm]
                r['nitroglycerinPctRange'] = {'min': ng[2], 'max': ng[3], 'maxExclusive': True,
                                              'basis': 'SDS section 3 concentration range for the whole N500 RELO family (not a per-powder value)'}
                r['containsNitroglycerin'] = True
                add_ev(r, names_line[1])
                for e in ng[1]:
                    add_ev(r, e)
                add_src(r, src(VV_SDS_NG, names_line[0]))
                add_src(r, src(VV_SDS_NG, ng[0]))
    else:
        problems.append('VV SDS: NG range or product list not parsed')

    # status
    for nm, r in vv.items():
        r['status'] = 'current'
        add_note(r, 'Status "current": listed in the Vihtavuori Reloading Guide 2026 / vihtavuori.com (retrieved 2026-11-23).')
        if r['bulkDensityStated']:
            add_note(r, 'bulkDensityGcc converted from the stated g/l value (/1000). heatOfExplosionJg is the value Vihtavuori labels "Energy content (J/g)".')
        r.pop('_guideTable', None)
        r.pop('_series', None)
        r.pop('_productPage', None)
    records.extend(vv.values())

    # ---- Burn-rate charts (Vihtavuori column only, in printed top-to-bottom order)
    def vv_col(text):
        out = []
        for ln in text.split('\n'):
            m = re.match(r'^\s*(' + POWDER_NAME_VV + r')(?=\s|$)', ln)
            if m and m.group(1) not in out:
                out.append(m.group(1))
        return out
    cp = pdf_pages(DOCS[VV_CHART]['localPath'], layout=True)
    names = vv_col(cp[0])
    ev = [collapse(ln) for ln in cp[0].split('\n') if re.match(r'^\s*(' + POWDER_NAME_VV + r')(?=\s|$)', ln)]
    head = [collapse(ln) for ln in cp[0].split('\n') if 'BURNING RATE' in ln or 'Current canister powders' in ln]
    charts.append({'publisher': 'Vihtavuori', 'edition': 'Burning Rate Chart (tabloid PDF, created 2025-11-25)',
                   'url': DOCS[VV_CHART]['url'], 'page': 1, 'column': 'Vihtavuori',
                   'orderedNames': names, 'evidence': ' | '.join(head + ev), '_doc': VV_CHART,
                   'notes': 'Chart also has columns for Norma, RWS, Vectan, Reload Swiss, IMR, Hodgdon, Accurate, W-W, Alliant and '
                            'Ramshot; those cross-brand columns (multi-name and line-wrapped cells) were not machine-parsed.'})
    for pi, p in enumerate(pages):
        if 'BURNING RATE CHART' in p and 'Current canister powders' in p:
            names2 = vv_col(p)
            ev2 = [collapse(ln) for ln in p.split('\n') if re.match(r'^\s*(' + POWDER_NAME_VV + r')(?=\s|$)', ln)]
            head2 = [collapse(ln) for ln in p.split('\n') if 'BURNING RATE CHART' in ln or 'Current canister powders' in ln]
            charts.append({'publisher': 'Vihtavuori', 'edition': 'Reloading Guide 2026, Burning Rate Chart (printed p.150)',
                           'url': DOCS[VV_GUIDE]['url'], 'page': pi + 1, 'column': 'Vihtavuori',
                           'orderedNames': names2, 'evidence': ' | '.join(head2 + ev2), '_doc': VV_GUIDE,
                           'notes': 'Same layout as the tabloid chart; only the Vihtavuori column was parsed.'})
            break


# --------------------------------------------------------------------------------------------
# Norma
# --------------------------------------------------------------------------------------------
def norma_parse(records, problems):
    lst = html_lines(DOCS[NORMA_LIST]['localPath'])
    disc = {}
    for ln in lst:
        m = re.fullmatch(r'Discontinued (\d{4}) (Norma .+)', ln)
        if m:
            disc[m.group(2)] = (m.group(1), ln)
    for p in NORMA_PRODUCTS:
        url = 'https://www.norma-ammunition.com/products/components/gunpowder/' + p
        local = os.path.join(SRC, 'norma/pages', p + '.html')
        lines = html_lines(local)
        try:
            i = next(k for k, ln in enumerate(lines) if ln.startswith('Prod. No:'))
        except StopIteration:
            problems.append(f'Norma: no Prod. No in {p}')
            continue
        prodno = lines[i].split(':', 1)[1].strip()
        full = lines[i + 1]
        if not full.startswith('Norma '):
            problems.append(f'Norma: unexpected name line {full!r}')
            continue
        name = full[len('Norma '):]
        # content until the generic "What is meant by" block / footer
        end = next((k for k in range(i, len(lines)) if lines[k].startswith('What is meant by') or lines[k].startswith('To the top')), len(lines))
        block = lines[i:end]
        r = new_record('norma', 'Norma', name, None)
        add_note(r, 'Manufacturer not stated on the Norma product page (brand: Norma Precision).')
        add_src(r, {'url': url, 'type': 'manufacturer', 'page': None, 'retrieved': RETRIEVED})
        add_ev(r, lines[i])
        add_ev(r, full)
        r['aliases'].append({'name': prodno, 'relation': 'Norma product number'})
        desc = []
        bd = en = None
        for ln in block[2:]:
            mb = re.fullmatch(r'Bulk density \(min(?: grams/liter)?\):\s*(\d{3,4})(?:\s*g/l)?', ln)
            me = re.fullmatch(r'Energy(?: \(Joule/gram\))?:\s*(\d{4})(?:\s*J/g)?', ln)
            if mb:
                bd = (int(mb.group(1)), ln)
            elif me:
                en = (int(me.group(1)), ln)
            elif ln.startswith('Package size') or ln in ('Intent', 'Reloading', 'Find Dealer', 'Page content', 'Details', 'About'):
                continue
            else:
                desc.append(ln)
        if desc:
            r['description'] = ' '.join(desc)
        if bd:
            r['bulkDensityStated'] = {'value': bd[0], 'unit': 'g/l', 'qualifier': 'min'}
            r['bulkDensityGcc'] = round(bd[0] / 1000.0, 4)
            add_ev(r, bd[1])
            add_note(r, 'Norma states bulk density as a minimum ("Bulk density (min)"); bulkDensityGcc = stated g/l / 1000.')
        if en:
            r['heatOfExplosionJg'] = en[0]
            r['heatOfExplosionLabel'] = 'Energy (J/g)'
            add_ev(r, en[1])
            add_note(r, 'heatOfExplosionJg is the value Norma labels "Energy" (J/g); Norma does not define the test basis.')
        if r['description']:
            for sent in sentences_with(r['description'], r'nitroglycerin'):
                r['containsNitroglycerin'] = True
                add_ev(r, sent)
                add_note(r, 'Norma describes this as a high nitroglycerin content powder; no base classification or NG percentage is stated.')
            for sent in sentences_with(r['description'], r'rifle powder'):
                r['applications'] = ['rifle']
                add_ev(r, sent)
            if 'Match powders' in r['description']:
                add_ev(r, 'Match powders')
        key = 'Norma ' + name
        if key in disc:
            r['status'] = 'discontinued'
            add_ev(r, disc[key][1])
            add_src(r, src(NORMA_LIST))
            add_note(r, f'Norma gunpowder listing marks this product "Discontinued {disc[key][0]}".')
        else:
            r['status'] = 'current'
            add_src(r, src(NORMA_LIST))
            add_note(r, 'Status "current": listed on the Norma gunpowder page without a discontinued mark (retrieved 2026-11-23).')
        if not bd and not en:
            add_note(r, 'No bulk density or energy published on the product page.')
        records.append(r)


# --------------------------------------------------------------------------------------------
# Reload Swiss
# --------------------------------------------------------------------------------------------
RS_MFR_PAT = r'Reload Swiss RS – a registered Trademark by (Nitrochemie Wimmis AG), Switzerland'


def rs_block(lines, label, stop_labels):
    """Return (raw_lines, joined_text) of a 'Label:' block in a datasheet."""
    out = []
    started = False
    for ln in lines:
        if not started:
            m = re.match(r'^' + re.escape(label) + r':\s*(.*)$', ln)
            if m:
                started = True
                out.append(ln)
            continue
        if any(re.match(r'^' + re.escape(s) + r':', ln) for s in stop_labels) or re.match(r'^Reload Swiss RS – ', ln):
            break
        if ln.strip():
            out.append(ln)
    raw = [collapse(x) for x in out]
    rs_block.last_raw = [re.sub(r'^' + re.escape(label) + r':', ' ' * (len(label) + 1), x) for x in out]
    body = [re.sub(r'^' + re.escape(label) + r':\s*', '', collapse(x)) for x in out]
    # de-hyphenate line breaks for the human-readable text only
    txt = ''
    for b in body:
        if txt.endswith('-') and b[:1].islower():
            txt = txt[:-1] + b
        else:
            txt = (txt + ' ' + b).strip()
    return raw, txt


def rs_parse(records, charts, problems):
    labels = ['Use', 'Standard calibres', 'Packaging units', 'Propellant type', 'Safe service life',
              'Verification tolerances', 'Key characteristics']
    page_by_num = {}
    for u in rs_product_urls():
        m = re.search(r'/rs(\d\d)-', u)
        page_by_num[m.group(1)] = u
    for n in RS_NUMS:
        name = 'RS' + n
        pdf = os.path.join(SRC, f'rs/pdf/RS{n}-EN.pdf')
        pdf_url = f'https://www.reload-swiss.com/Reload%20Swiss/Produkte/RS{n}/RS{n}-EN.pdf'
        pages = pdf_pages(pdf, layout=True)
        text = pages[0]
        lines = text.split('\n')
        r = new_record('reload-swiss', 'Reload Swiss', name, None)
        r['id'] = 'reload-swiss-' + name.lower()
        ds = {'url': pdf_url, 'type': 'manufacturer', 'page': 1, 'retrieved': RETRIEVED, 'title': f'Reload Swiss {name} data sheet (EN)'}
        add_src(r, ds)
        mm = re.search(RS_MFR_PAT, text)
        if mm:
            r['manufacturer'] = mm.group(1)
            add_ev(r, mm.group(0))
        raw_use, use = rs_block(lines, 'Use', labels)
        raw_cal, cal = rs_block(lines, 'Standard calibres', labels)
        cal_cells = []
        for ln in rs_block.last_raw:
            for cell in re.split(r'\s{2,}', ln.strip()):
                # multi-column calibre table: cells separated by 2+ spaces; drop the trailing
                # "and other calibres" / "possible" note cells (no digits)
                if cell and re.search(r'\d', cell):
                    cal_cells.append(cell)
        raw_pt, ptype = rs_block(lines, 'Propellant type', labels)
        raw_kc, _ = rs_block(lines, 'Key characteristics', labels)
        r['description'] = use or None
        if ptype:
            for e in raw_pt:
                add_ev(r, e)
            kws = []
            for kw, pat in (('porous', r'\bporous\b'), ('extruded', r'\bextruded\b'), ('single-perforated', r'single-perforated'),
                            ('flake', r'\bflake\b')):
                if re.search(pat, ptype):
                    kws.append(kw)
            r['form'] = ', '.join(kws) if kws else None
            if re.search(r'single-based', ptype):
                r['base'] = 'single'
            if re.search(r'nitro-glycerine', ptype):
                r['containsNitroglycerin'] = True
                add_note(r, 'Reload Swiss calls this powder "single-based" but states a nitroglycerine impregnation; '
                            'no NG percentage is published.')
            if r['base'] is None:
                add_note(r, f'Base not stated as single/double; maker text: "{ptype}"')
            tc = sentences_with(ptype, r'temperature behaviour')
            if tc:
                r['temperatureStableClaim'] = ' '.join(tc)
        if cal_cells:
            r['standardCalibres'] = cal_cells
            for e in raw_cal:
                add_ev(r, e)
        kc = ' '.join(raw_kc)
        for e in raw_kc:
            add_ev(r, e)
        mh = re.search(r'Explosion heat\s+approx\.\s*([\d’\'.,]+)\s*J/g', kc)
        mb = re.search(r'Bulk density\s+approx\.\s*([\d’\'.,]+)\s*g/l', kc)
        md = re.search(r'Grain diameter\s+approx\.\s*(\d+[.,]\d+)\s*mm', kc)
        ml = re.search(r'Grain length\s+approx\.\s*(\d+[.,]\d+)\s*mm', kc)
        mlwh = re.search(r'Length width × height\s+approx\.\s*(\d+[.,]\d+)\s*×\s*(\d+[.,]\d+)\s*×\s*(\d+[.,]\d+)\s*mm', kc)
        mlw = re.search(r'Length × width\s+approx\.\s*(\d+[.,]\d+)\s*×\s*(\d+[.,]\d+)\s*mm', kc)
        mt = re.search(r'Thickness\s+approx\.\s*(\d+[.,]\d+)\s*mm', kc)
        if mh:
            r['heatOfExplosionJg'] = int_thousands(mh.group(1))
            r['heatOfExplosionLabel'] = 'Explosion heat (approx.)'
        if mb:
            v = int_thousands(mb.group(1))
            r['bulkDensityStated'] = {'value': v, 'unit': 'g/l', 'qualifier': 'approx.'}
            r['bulkDensityGcc'] = round(v / 1000.0, 4)
        gd = {}
        if md and ml:
            gd = {'lengthMm': num(ml.group(1)), 'diameterMm': num(md.group(1))}
        elif mlwh:
            gd = {'lengthMm': num(mlwh.group(1)), 'widthMm': num(mlwh.group(2)), 'heightMm': num(mlwh.group(3))}
        elif mlw:
            gd = {'lengthMm': num(mlw.group(1)), 'widthMm': num(mlw.group(2))}
        if mt:
            gd['thicknessMm'] = num(mt.group(1))
        if gd:
            gd['qualifier'] = 'approx.'
            r['grainDimensions'] = gd
        if not (mh and mb and gd):
            problems.append(f'RS {name}: key characteristics incomplete: {kc}')
        pdf_dim_items = [(collapse(mx.group(1)), mx.group(2)) for mx in re.finditer(
            r'(Grain diameter|Grain length|Length width × height|Length × width|Thickness)\s+(approx\.\s*[\d.,× ]+mm)', kc)]
        # ---- product page cross-check
        url = page_by_num.get(n)
        if url and os.path.exists(rs_page_local(url)):
            pl = html_lines(rs_page_local(url))
            title = html_title(rs_page_local(url))
            add_src(r, {'url': url, 'type': 'manufacturer', 'page': None, 'retrieved': RETRIEVED})
            mt2 = re.match(r'RS\d\d (Rifle/Pistol|Pistol|Rifle) Powder', title or '')
            if mt2:
                add_ev(r, mt2.group(0))
                r['applications'] = {'Rifle/Pistol': ['rifle', 'handgun'], 'Pistol': ['handgun'], 'Rifle': ['rifle']}[mt2.group(1)]
            try:
                k0 = pl.index('Key characteristics')
                k1 = pl.index('Downloads', k0)
            except ValueError:
                problems.append(f'RS {name}: web key characteristics not found')
                k0 = k1 = None
            if k0 is not None:
                kv = pl[k0 + 1:k1]
                pairs = dict(zip(kv[0::2], kv[1::2]))
                for lab, val in pairs.items():
                    add_ev(r, f'{lab} {val}')
                web = {}
                if 'Heat of explosion' in pairs:
                    m = re.fullmatch(r'(?:approx\.|ca\.)\s*([\d.’\']+)\s*J/g', pairs['Heat of explosion'])
                    if m:
                        web['heatOfExplosionJg'] = int_thousands(m.group(1))
                if 'Bulk density' in pairs:
                    m = re.fullmatch(r'(?:approx\.|ca\.)\s*([\d.’\']+)\s*g/l', pairs['Bulk density'])
                    if m:
                        web['bulkDensityGcc'] = round(int_thousands(m.group(1)) / 1000.0, 4)
                for lab, key in (('Grain diameter', 'diameterMm'), ('Grain length', 'lengthMm'), ('Thickness', 'thicknessMm')):
                    if lab in pairs:
                        m = re.fullmatch(r'(?:approx\.|ca\.)\s*(\d+[.,]\d+)\s*mm', pairs[lab])
                        if m:
                            web[key] = num(m.group(1))
                for lab in ('Length x width x height', 'Length x width'):
                    if lab in pairs:
                        m = re.fullmatch(r'(?:approx\.|ca\.)\s*(\d+[.,]\d+)\s*x\s*(\d+[.,]\d+)(?:\s*x\s*(\d+[.,]\d+))?\s*mm', pairs[lab])
                        if m:
                            web['lengthMm'] = num(m.group(1))
                            web['widthMm'] = num(m.group(2))
                            if m.group(3):
                                web['heightMm'] = num(m.group(3))
                for key in ('heatOfExplosionJg', 'bulkDensityGcc'):
                    if key in web and web[key] != r[key]:
                        add_conflict(r, key, [{'value': r[key], 'source': pdf_url}, {'value': web[key], 'source': url}])
                web_dim_items = [(lab, val) for lab, val in pairs.items() if lab not in ('Heat of explosion', 'Bulk density')]
                pdf_nums = [num(x) for _, v in pdf_dim_items for x in re.findall(r'\d+[.,]\d+', v)]
                web_nums = [num(x) for _, v in web_dim_items for x in re.findall(r'\d+[.,]\d+', v)]
                norm_lab = lambda L: [' '.join(w for w in re.split(r'[\s×]+', l.lower()) if w not in ('x', '')) for l, _ in L]
                if pdf_nums != web_nums or norm_lab(pdf_dim_items) != norm_lab(web_dim_items):
                    add_conflict(r, 'grainDimensions', [
                        {'value': '; '.join(f'{l} {v}' for l, v in pdf_dim_items), 'source': pdf_url},
                        {'value': '; '.join(f'{l} {v}' for l, v in web_dim_items), 'source': url}])
                    if pdf_nums == web_nums:
                        add_note(r, 'Data sheet and product page give the same grain-size numbers under different labels; '
                                    'grainDimensions uses the data-sheet labels.')
                if not web:
                    problems.append(f'RS {name}: web key characteristics unparsed {pairs}')
        else:
            problems.append(f'RS {name}: product page missing')
        r['status'] = 'current'
        add_note(r, 'Status "current": product page and data sheet on reload-swiss.com (retrieved 2026-11-23). '
                    'bulkDensityGcc converted from the stated g/l value (/1000). heatOfExplosionJg is the data-sheet "Explosion heat" '
                    '(web page: "Heat of explosion").')
        records.append(r)

    # ---- chart: Reload Swiss column
    cp = pdf_pages(DOCS[RS_CHART]['localPath'], layout=True)[0]
    names, ev = [], []
    for ln in cp.split('\n'):
        m = re.match(r'^\s*(RS\d\d)(?=\s|$)', ln)
        if m:
            names.append(m.group(1))
            ev.append(collapse(ln))
    head = [collapse(ln) for ln in cp.split('\n') if 'Burn Rate Chart' in ln or 'Sequentially from top to bottom' in ln]
    charts.append({'publisher': 'Reload Swiss (Nitrochemie Wimmis AG)', 'edition': 'Abbrenngeschwindigkeit / Burn Rate Chart 2024 (PDF created 2024-11-05)',
                   'url': DOCS[RS_CHART]['url'], 'page': 1, 'column': 'Reload Swiss', 'orderedNames': names,
                   'evidence': ' | '.join(head + ev), '_doc': RS_CHART})


# --------------------------------------------------------------------------------------------
# Shooters World (+ Vectan powders it distributes)
# --------------------------------------------------------------------------------------------
SW_CATS = ('Black Powder Substitutes', 'Handgun Powders', 'Handgun/Shotgun Powders', 'Rifle Powders')
SW_CAT_APPS = {'Black Powder Substitutes': ['black powder substitute'], 'Handgun Powders': ['handgun'],
               'Handgun/Shotgun Powders': ['handgun', 'shotgun'], 'Rifle Powders': ['rifle']}
VECTAN_NAMES = re.compile(r'^(A1|AO|AS|Ba10|Ba9|Ba9-½|Ba7-½|Ba6-½|STL|STXL|ST2XL|ST3XL)$')
SW_MANUAL_ALIASES = {'Buffalo': 'Buffalo Rifle', 'AR Plus': 'AR-Plus', 'AR-PLUS': 'AR-Plus', 'Precision Rifle': 'Precision'}


def norm_sw(n):
    return re.sub(r'[\s\-]', '', n).lower()


def sw_extract(rec, text, source_url, page, tag):
    """Parse density / Lovex / form / base / temperature statements from a description text."""
    found = {}
    name = rec['name']
    pats_density = [
        r'The density of ([A-Za-z0-9 \-]+?) is approxi(?:-\s*)?mately (\d+(?:\.\d+)?) grams?/cc',
        r'has a density of approxi(?:-\s*)?mately (\d+(?:\.\d+)?) grams?/cc',
    ]
    for pat in pats_density:
        for m in re.finditer(pat, text):
            who = m.group(1) if m.lastindex == 2 else name
            if SW_MANUAL_ALIASES.get(who, who) != name and norm_sw(SW_MANUAL_ALIASES.get(who, who)) != norm_sw(name):
                continue
            v = float(m.group(m.lastindex))
            found.setdefault('density', []).append((v, m.group(0)))
    mp = re.search(r'has a bulk density of (\d+(?:\.\d+)?)(?=[,.]?\s|$)(?!\s*(?:g|kg|lb))', text)
    if mp:
        found['bulkNoUnit'] = (float(mp.group(1)), mp.group(0))
        found['_text'] = text
    for m in re.finditer(r'Under the Lovex brand, this propellant is referred to as (D\d{3}(?:\.\d+)?|S\d{3}(?:\.\d+)?)', text):
        found.setdefault('lovex', []).append((m.group(1), m.group(0)))
    m = re.search(r'canister form of Explosia bulk and Lovex canister propellant (D\d{3}-\d+)', text)
    if m:
        found.setdefault('lovex', []).append((m.group(1), m.group(0)))
    m = re.search(r'canister form of South Africa Rheinmetall-Denel bulk and canister propellant (S\d{3})', text)
    if m:
        found['rdm'] = (m.group(1), m.group(0))
    forms = []
    for kw, pat in (('spherical', r'\bspherical\b'), ('extruded', r'\bextruded\b'), ('stick', r'\bstick powder\b'),
                    ('flake', r'\bflakes\b')):
        for sent in sentences_with(text, pat):
            forms.append((kw, sent))
            break
    if forms:
        found['form'] = forms
    for sent in sentences_with(text, r'\bsingle[- ]base\b'):
        found.setdefault('base', []).append(('single', sent))
    for sent in sentences_with(text, r'temperature sensitivity|varying temperatures|temperature[- ]stab'):
        found.setdefault('temp', []).append(sent)
    m = re.search(r'(\d+(?:\.\d+)?)\s*mm\s*x\s*(\d+(?:\.\d+)?)\s*mm\s*x\s*(\d+(?:\.\d+)?)\s*mm', text)
    if m:
        sent = [s for s in sentences_with(text, re.escape(m.group(0)))][0]
        found['dims'] = ({'lengthMm': float(m.group(1)), 'widthMm': float(m.group(2)), 'thicknessMm': float(m.group(3)),
                          'qualifier': 'approx.'}, sent)
    return found


def sw_apply(rec, found, label, source_url):
    if 'density' in found:
        for v, sent in found['density']:
            add_ev(rec, sent)
            prev = rec.get('_swdens')
            if prev is None:
                rec['_swdens'] = (v, label, source_url)
                rec['bulkDensityGcc'] = v
                rec['bulkDensityStated'] = {'value': v, 'unit': 'g/cc', 'qualifier': 'approximately',
                                            'makerWording': 'density'}
            elif prev[0] != v:
                add_conflict(rec, 'bulkDensityGcc', [{'value': prev[0], 'source': prev[2]}, {'value': v, 'source': source_url}])
    if 'bulkNoUnit' in found:
        v, frag = found['bulkNoUnit']
        sents = found.get('_text') and sentences_with(found['_text'], re.escape(frag))
        add_ev(rec, sents[0] if sents else frag)
        rec['bulkDensityStated'] = {'value': v, 'unit': None, 'qualifier': None}
        add_note(rec, f'Maker states "bulk density of {v}" without a unit; bulkDensityGcc left null.')
    for code, sent in found.get('lovex', []):
        add_ev(rec, sent)
        if not any(a['name'] == code for a in rec['aliases']):
            rec['aliases'].append({'name': code, 'brand': 'Lovex', 'relation': 'same propellant sold under the Lovex brand (per Shooters World)'})
    if 'rdm' in found:
        code, sent = found['rdm']
        add_ev(rec, sent)
        rec['aliases'].append({'name': code, 'brand': 'Rheinmetall Denel Munition', 'relation': 'canister form of this bulk/canister propellant (per Shooters World)'})
        rec['manufacturer'] = rec['manufacturer'] or 'Rheinmetall Denel Munition (per Shooters World)'
    if 'form' in found:
        kws = [k for k, _ in found['form']]
        cur = rec['form'].split(', ') if rec['form'] else []
        for k in kws:
            if k not in cur:
                cur.append(k)
        rec['form'] = ', '.join(cur)
        for _, sent in found['form']:
            add_ev(rec, sent)
    for b, sent in found.get('base', []):
        add_ev(rec, sent)
        if rec['base'] and rec['base'] != b:
            add_conflict(rec, 'base', [{'value': rec['base'], 'source': 'previous'}, {'value': b, 'source': source_url}])
        rec['base'] = rec['base'] or b
    for sent in found.get('temp', []):
        add_ev(rec, sent)
        cur = rec['temperatureStableClaim']
        if cur is None:
            rec['temperatureStableClaim'] = sent
        elif sent not in cur:
            rec['temperatureStableClaim'] = cur + ' ' + sent
    if 'dims' in found:
        d, sent = found['dims']
        add_ev(rec, sent)
        if rec['grainDimensions'] and rec['grainDimensions'] != d:
            add_conflict(rec, 'grainDimensions', [{'value': rec['grainDimensions'], 'source': 'previous'}, {'value': d, 'source': source_url}])
        rec['grainDimensions'] = rec['grainDimensions'] or d


def sw_parse(records, charts, problems):
    lst = html_lines(DOCS[SW_LIST]['localPath'])
    cats = {}
    for i, ln in enumerate(lst[:-2]):
        if ln == 'view' and lst[i + 2] in SW_CATS:
            cats[lst[i + 1]] = lst[i + 2]
    sw = {}
    # manual: intro classes, NG range, manufacturer
    mpages = pdf_pages(DOCS[SW_MANUAL]['localPath'], layout=True)
    intro_pi = next(pi for pi, p in enumerate(mpages) if 'POWDER INFORMATION' in p)
    intro = collapse(mpages[intro_pi])
    mm = re.search(r'manual for reloading of Shooters World branded LOVEX® smokeless propellants manufactured by EXPLOSIA® Company\.', intro)
    mng = re.search(r'double base powders also contain nitroglycerin \((\d+) - (\d+) %\) as an energetic modifier\.', intro)
    classes = {}
    for lab, nxt, base in (('Rifle single base powders:', 'DOUBLE BASE POWDERS', 'single'),
                           ('Shotgun double base powder:', 'Handgun double base powders:', 'double'),
                           ('Handgun double base powders:', 'Rifle double base powders:', 'double'),
                           ('Rifle double base powders:', 'Shooters World and LOVEX', 'double')):
        m = re.search(re.escape(lab) + r'\s*(.+?)\s+' + re.escape(nxt), intro)
        if not m:
            problems.append(f'SW manual: class list {lab} not found')
            continue
        for n in re.split(r',\s*(?:&\s*)?|\s+&\s+', m.group(1)):
            n = n.strip()
            if n:
                classes.setdefault(SW_MANUAL_ALIASES.get(n, n), []).append((base, collapse(lab + ' ' + m.group(1))))

    for url in sw_product_urls():
        local = sw_page_local(url)
        if not os.path.exists(local):
            problems.append(f'SW page missing {url}')
            continue
        ls = html_lines(local)
        title = html_title(local) or ''
        mt = re.fullmatch(r'(.+?) - Shooters World', title)
        if not mt:
            problems.append(f'SW: unexpected title {title!r} in {url}')
            continue
        name = mt.group(1)
        idx = [k for k, ln in enumerate(ls) if ln == 'CONTACT']
        body = ls[idx[1] + 1:] if len(idx) >= 2 else ls[1:]
        try:
            body = body[:body.index('BACK TO ALL PRODUCTS')]
        except ValueError:
            pass
        content = [ln for ln in body if collapse(ln).upper() != collapse(name).upper()]
        text = ' '.join(content)
        is_vectan = bool(VECTAN_NAMES.match(name))
        if is_vectan:
            r = new_record('vectan', 'Vectan', name, None)
            add_note(r, 'Vectan powder distributed in the USA by Shooters World; data from the Shooters World product page.')
        else:
            r = new_record('shooters-world', 'Shooters World', name, None)
        add_src(r, {'url': url, 'type': 'manufacturer' if not is_vectan else 'third-party', 'page': None, 'retrieved': RETRIEVED})
        r['description'] = content[0] if content else None
        cat = cats.get(name)
        if cat:
            r['applications'] = SW_CAT_APPS[cat]
            add_ev(r, f'{name} {cat}')
            add_src(r, src(SW_LIST))
        else:
            problems.append(f'SW: no category for {name}')
        found = sw_extract(r, text, url, None, 'web')
        sw_apply(r, found, 'web', url)
        r['status'] = 'current'
        add_note(r, 'Status "current": listed on shootersworldpowder.com/products (retrieved 2026-11-23).')
        sw[name] = r

    # manual powder-description sections (one powder per page, several on the last description page)
    known = {norm_sw(n): n for n in sw}
    for alias, canon in SW_MANUAL_ALIASES.items():
        known[norm_sw(alias)] = canon
    desc_pages = [pi for pi, p in enumerate(mpages) if pi > intro_pi and pi < intro_pi + 20]
    for pi in desc_pages:
        lines = mpages[pi].split('\n')
        heads = [(k, known[norm_sw(ln.strip())]) for k, ln in enumerate(lines)
                 if ln.strip() and len(ln.strip()) < 40 and norm_sw(ln.strip()) in known]
        for h, (k, canon) in enumerate(heads):
            end = heads[h + 1][0] if h + 1 < len(heads) else len(lines)
            sect = collapse('\n'.join(lines[k + 1:end]))
            r = sw.get(canon)
            if r is None:
                continue
            found = sw_extract(r, sect, DOCS[SW_MANUAL]['url'], pi + 1, 'manual')
            if found:
                add_src(r, src(SW_MANUAL, pi + 1))
                sw_apply(r, found, f'manual p{pi+1}', DOCS[SW_MANUAL]['url'] + f'#page={pi+1}')
    for name, r in sw.items():
        if r['brand'] != 'Shooters World':
            continue
        in_manual = any('ShootersWorldManual' in s['url'] for s in r['sources'])
        if mm and in_manual and name != 'SOCOM' and r['manufacturer'] is None:
            r['manufacturer'] = 'Explosia'
            add_ev(r, mm.group(0))
            add_src(r, src(SW_MANUAL, intro_pi + 1))
        if name == 'SOCOM':
            add_note(r, 'Manufacturer not set: Shooters World says SOCOM is a proprietary burn speed manufactured for Southern '
                        'Ballistic Research and not carried under the Lovex brand.')
        for base, ev in classes.get(name, []):
            add_ev(r, ev)
            add_src(r, src(SW_MANUAL, intro_pi + 1))
            if r['base'] and r['base'] != base:
                add_conflict(r, 'base', [{'value': r['base'], 'source': 'product page'}, {'value': base, 'source': DOCS[SW_MANUAL]['url']}])
            r['base'] = r['base'] or base
            if base == 'double':
                r['containsNitroglycerin'] = True
                if mng:
                    add_ev(r, mng.group(0))
                    r['nitroglycerinPctRange'] = {'min': float(mng.group(1)), 'max': float(mng.group(2)), 'maxExclusive': False,
                                                  'basis': 'Class-level range stated for all Shooters World double base powders (not a per-powder value)'}
        if r['bulkDensityStated'] and r['bulkDensityStated'].get('unit') == 'g/cc':
            add_note(r, 'Shooters World states "density ... approximately N grams/cc"; recorded as bulkDensityGcc '
                        '(values 0.65-1.0 g/cc are bulk/loading densities, the maker does not say "bulk").')
        r.pop('_swdens', None)
    for r in sw.values():
        r.pop('_swdens', None)
    records.extend(sw.values())

    # ---- manual burn-rate chart: Shooters World column
    cpi = next(pi for pi, p in enumerate(mpages) if 'Burn rate charts provide an approximate comparison' in p)
    lines = mpages[cpi].split('\n')
    start = next(k for k, ln in enumerate(lines) if 'Propellants' in ln) + 1
    names, ev = [], []
    for ln in lines[start:]:
        if ln.startswith('Burn rate charts provide'):
            break
        m = re.match(r'^(\s{0,14})(\S(?:.*?\S)?)(?=\s{2,}|$)', ln)
        if m and len(m.group(1)) <= 14 and ln.strip():
            nm = m.group(2)
            names.append(nm)
            ev.append(collapse(ln))
    head = [collapse(ln) for ln in lines if ln.startswith('Burn rate charts provide')]
    charts.append({'publisher': 'Shooters World', 'edition': 'Shooters World Reloading Guide (manual PDF created 2023-05-25), burn rate chart p.2',
                   'url': DOCS[SW_MANUAL]['url'], 'page': cpi + 1, 'column': 'Shooters World', 'orderedNames': names,
                   'evidence': ' | '.join(ev + head), '_doc': SW_MANUAL,
                   'notes': 'Only the Shooters World column was parsed (Lovex, Western, Hodgdon, Winchester, Alliant, IMR and '
                            'VihtaVuori columns were not). "BMG" is printed in the chart; the current product is named "SW 50BMG". '
                            '"Sparta 100" is not on the current product list. A newer chart is published only as an image '
                            '(https://shootersworldpowder.com/wp-content/uploads/2025/03/burn-rate-chart.png) and was not transcribed.'})


# --------------------------------------------------------------------------------------------
# Cross-reference columns of the multi-brand charts (word bounding boxes)
# --------------------------------------------------------------------------------------------
def bbox_words(local, page):
    r = subprocess.run(['pdftotext', '-bbox', '-f', str(page), '-l', str(page), local, '-'], capture_output=True, text=True)
    words = []
    for m in re.finditer(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>', r.stdout):
        words.append({'x0': float(m.group(1)), 'y0': float(m.group(2)), 'x1': float(m.group(3)), 'y1': float(m.group(4)),
                      'w': htmlmod.unescape(m.group(5))})
    return words


def cross_reference(chart, header_words, y_top, y_bottom, problems, join_gap=6.0):
    """Assign words between y_top and y_bottom to the nearest column header; group words on the same
    baseline in one column into one cell. Returns list of {brand, name, rowY} in printed order."""
    local = DOCS[chart['_doc']]['localPath']
    words = bbox_words(local, chart['page'])
    cols = []
    for hdr in header_words:
        cand = [w for w in words if w['w'] == hdr[0] and w['y0'] < y_top]
        if hdr[1] is not None:
            cand = [w for w in cand if abs(w['y0'] - hdr[1]) < 15]
        if not cand:
            problems.append(f'chart {chart["edition"]}: header {hdr} not found')
            return None
        w = cand[0]
        cols.append((hdr[2], (w['x0'] + w['x1']) / 2.0))
    body = [w for w in words if y_top < w['y0'] < y_bottom]
    cells = {}
    for w in body:
        xc = (w['x0'] + w['x1']) / 2.0
        brand = min(cols, key=lambda c: abs(c[1] - xc))[0]
        key = (brand, round(w['y0'] / 3.0))
        cells.setdefault(key, []).append(w)
    out = []
    for (brand, _), ws in cells.items():
        ws.sort(key=lambda w: w['x0'])
        # split cell into separate names where there is a large horizontal gap
        groups = [[ws[0]]]
        for w in ws[1:]:
            if w['x0'] - groups[-1][-1]['x1'] > join_gap:
                groups.append([w])
            else:
                groups[-1].append(w)
        for g in groups:
            out.append({'brand': brand, 'name': ' '.join(w['w'] for w in g), 'rowY': round(g[0]['y0'], 1)})
    out.sort(key=lambda e: (e['rowY'], [c[0] for c in cols].index(e['brand'])))
    return out


# --------------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------------
def self_check(data):
    recs = data['powders']
    print(f'\nSELF-CHECK: {len(recs)} powder records, {len(data["charts"])} charts')
    bad = 0
    for r in recs:
        ev = r['evidence']
        checks = []
        if r['heatOfExplosionJg'] is not None:
            v = r['heatOfExplosionJg']
            checks.append(('heat', [str(v), f'{v // 1000}’{v % 1000:03d}', f'{v // 1000}.{v % 1000:03d}']))
        if r['bulkDensityStated'] and r['bulkDensityStated']['value'] is not None:
            v = r['bulkDensityStated']['value']
            reps = [str(v)]
            if isinstance(v, int):
                reps += [f'{v // 1000}’{v % 1000:03d}', f'{v // 1000}.{v % 1000:03d}']
            if isinstance(v, float) and v == int(v):
                reps.append(str(int(v)))
            checks.append(('bulk', reps))
        if r['grainDimensions']:
            for k, v in r['grainDimensions'].items():
                if isinstance(v, float):
                    reps = [f'{v}', f'{v}'.replace('.', ','), f'{v:.2f}', f'{v:.2f}'.replace('.', ',')]
                    checks.append((k, reps))
        if r['nitroglycerinPctRange']:
            for k in ('min', 'max'):
                v = r['nitroglycerinPctRange'][k]
                checks.append(('ng' + k, [str(int(v)) if v == int(v) else str(v)]))
        if r['relativeBurnRate']:
            checks.append(('rbr', [str(r['relativeBurnRate']['value'])]))
        for lab, reps in checks:
            if not any(re.search(r'(?<![\d.,’])' + re.escape(x) + r'(?![\d’]|[.,]\d)', ev) for x in reps):
                bad += 1
                print(f'  !! {r["id"]}: {lab} value {reps[0]} not found in evidence')
        # derived bulk density check
        bs = r['bulkDensityStated']
        if bs and bs.get('unit') == 'g/l' and r['bulkDensityGcc'] != round(bs['value'] / 1000.0, 4):
            bad += 1
            print(f'  !! {r["id"]}: bulkDensityGcc/derivation mismatch')
        if r['heatOfExplosionJg'] is not None and not (2500 <= r['heatOfExplosionJg'] <= 5500):
            bad += 1
            print(f'  !! {r["id"]}: heat out of range {r["heatOfExplosionJg"]}')
        if r['bulkDensityGcc'] is not None and not (0.25 <= r['bulkDensityGcc'] <= 1.1):
            bad += 1
            print(f'  !! {r["id"]}: bulk density out of range {r["bulkDensityGcc"]}')
        if not r['sources']:
            bad += 1
            print(f'  !! {r["id"]}: no sources')
    for c in data['charts']:
        for n in c['orderedNames']:
            if n not in c['evidence']:
                bad += 1
                print(f'  !! chart {c["edition"]}: {n} not in evidence')
    ids = [r['id'] for r in recs]
    if len(ids) != len(set(ids)):
        bad += 1
        print('  !! duplicate ids', [i for i in ids if ids.count(i) > 1])
    random.seed(7)
    for r in random.sample(recs, min(5, len(recs))):
        print(f'\n  {r["id"]}: heat={r["heatOfExplosionJg"]} bulk={r["bulkDensityGcc"]} dims={r["grainDimensions"]} '
              f'base={r["base"]} form={r["form"]} ng={r["nitroglycerinPctRange"]}')
        print(f'    evidence: {r["evidence"][:600]}')
    print(f'\nSELF-CHECK problems: {bad}')
    return bad


def main():
    if '--download' in sys.argv:
        download_all()
    records, charts, problems = [], [], []
    vv_parse(records, charts, problems)
    norma_parse(records, problems)
    rs_parse(records, charts, problems)
    sw_parse(records, charts, problems)

    # cross-reference columns for the clean multi-brand charts (machine-parsed by word position)
    for c in charts:
        if c['_doc'] == RS_CHART:
            hdr = [('Swiss', None, 'Reload Swiss'), ('Vihtavuori', None, 'Vihtavuori'), ('Norma', None, 'Norma'),
                   ('Hodgdon', None, 'Hodgdon'), ('IMR', None, 'IMR'), ('Winchester', None, 'Winchester'),
                   ('Rottweil', None, 'Rottweil'), ('Accurate', None, 'Accurate'), ('Lovex', None, 'Lovex'),
                   ('Vectan', None, 'Vectan'), ('Alliant', None, 'Alliant'), ('Ramshot', None, 'Ramshot'), ('B', 67.0, 'B&P')]
            words = bbox_words(DOCS[RS_CHART]['localPath'], 1)
            ytop = max(w['y1'] for w in words if w['w'] in ('Vihtavuori', 'Rottweil'))
            ybot = min(w['y0'] for w in words if w['w'] in ('Reihenfolge', 'Sequentially'))
            xr = cross_reference(c, hdr, ytop, ybot, problems)
            if xr:
                c['crossReference'] = xr
                c['crossReferenceNotes'] = ('Machine-parsed from PDF word positions: each word is assigned to the nearest column '
                                            'header; words on one baseline in one column form one name. rowY is the printed vertical '
                                            'position (points from page top); equal rowY = same printed row. Verify before relying on '
                                            'cross-brand equivalence; the chart itself says it is a Nitrochemie estimate.')
                own = [e['name'] for e in xr if e['brand'] == 'Reload Swiss']
                if own != c['orderedNames']:
                    problems.append(f'RS chart: bbox own column {own} != layout column {c["orderedNames"]}')

    for r in records:
        r['evidence'] = ' | '.join(r['_ev'])
        del r['_ev']
        r.pop('_fieldsrc', None)
        if not r['aliases']:
            r['aliases'] = []
    used = {s_['url'] for r in records for s_ in r['sources']} | {c['url'] for c in charts}
    docs = []
    for k, d in DOCS.items():
        if d['url'] in used:
            docs.append({'url': d['url'], 'localPath': d['localPath'], 'title': d['title'], 'date': d['date']})
    seen = {d['url'] for d in docs}
    for r in records:
        for s in r['sources']:
            if s['url'] not in seen:
                seen.add(s['url'])
                lp = None
                if 'vihtavuori.com/powder/' in s['url']:
                    lp = vv_page_local(s['url'])
                elif 'reload-swiss.com/en/product' in s['url']:
                    lp = rs_page_local(s['url'])
                elif 'Produkte/RS' in s['url']:
                    lp = os.path.join(SRC, 'rs/pdf', s['url'].rsplit('/', 1)[1])
                elif 'norma-ammunition.com' in s['url']:
                    lp = os.path.join(SRC, 'norma/pages', s['url'].rsplit('/', 1)[1] + '.html')
                elif 'portfolio_page' in s['url']:
                    lp = sw_page_local(s['url'])
                title = s.get('title')
                if title is None and lp and lp.endswith('.html') and os.path.exists(lp):
                    title = html_title(lp)
                docs.append({'url': s['url'], 'localPath': lp, 'title': title, 'date': None})
    for c in charts:
        c.pop('_doc', None)
    data = {
        'meta': {
            'key': 'powders-other',
            'retrieved': RETRIEVED,
            'documents': docs,
            'blocked': BLOCKED,
            'notes': ('Powder catalog data for Vihtavuori, Norma, Reload Swiss, Shooters World (+ Vectan powders it distributes). '
                      'Accurate/Ramshot (westernpowders.com) and ADI (adi-powders.com.au) could not be reached from this environment, '
                      'so they are absent. Field conventions: bulkDensityGcc in g/cm3 (converted from g/l by /1000 where the maker '
                      'states g/l; bulkDensityStated keeps the printed value, unit and qualifier such as "min" or "approx."); '
                      'heatOfExplosionJg holds the maker\'s energy figure in J/g with the maker\'s own label in heatOfExplosionLabel '
                      '(Vihtavuori "Energy content", Norma "Energy", Reload Swiss "Explosion heat"/"Heat of explosion") - these labels '
                      'may not denote identical test methods. grainDimensions in mm as stated. temperatureStableClaim is the verbatim '
                      'maker claim text or null (null = no claim found, not a claim of sensitivity). nitroglycerinPct is never set '
                      'because no maker publishes a per-powder value; nitroglycerinPctRange holds a stated class/family range with its basis. '
                      'base is set only from an explicit maker statement (product, series or class level; see evidence). '
                      'containsNitroglycerin true only where the maker states NG is present. Charts: orderedNames is the publisher\'s '
                      'own column, top (fastest) to bottom (slowest) as printed; crossReference (RS chart only) is machine-parsed. '
                      'Problems seen during parsing: ' + ('; '.join(problems) if problems else 'none')),
        },
        'powders': records,
        'charts': charts,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f'wrote {OUT}: {len(records)} powders, {len(charts)} charts')
    if problems:
        print('PROBLEMS:')
        for p in problems:
            print('  -', p)
    bad = self_check(data)
    return 0 if bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
