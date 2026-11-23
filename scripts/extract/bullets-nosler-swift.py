#!/usr/bin/env python3
"""Extract Nosler and Swift bullet specifications (key: bullets-nosler-swift).

Sources (all public, fetched with plain curl and its default user agent):

Nosler (https://www.nosler.com, Magento storefront)
  * https://www.nosler.com/robots.txt -> no Crawl-delay; product pages allowed.
  * https://www.nosler.com/sitemap.xml -> list of product URLs.
  * every bullet product page in the sitemap (root-level *.html slugs naming a
    grain weight, excluding ammunition, brass, factory seconds / blems).
    Each page carries the maker's "More Information" spec table
    (<th class="col label">..</th><td class="col data">..</td>):
    Product Name, Box Qty, BC G1, BC G7, Overall Length (OAL) (in.),
    Sectional Density (SD.), Diameter, Cannelure/Band, Manufacturer SKU, Type,
    Bullet Base, Bullet Profile, Bullet Type, Bullet Weight, Caliber, Lead Free.
  * https://www.nosler.com/catalog-request.html links the 2026 product guide
    https://www.nosler.com/media/binaryanvil/media_library/2026-Catalog-Layout_Web.pdf
    which is parsed (pdftotext -layout) as a second, independent source for
    SD / BC / OAL / part number and minimum-twist notes; disagreements with the
    product page are recorded in "conflicts".

  Checks applied to every Nosler record (none of them fills a value from
  outside the maker's documents):
    - weight claims (product name, "Product Name" row, "Bullet Weight" row,
      catalog header): on disagreement all go to "conflicts" and the value is
      kept only if the printed SD corroborates exactly one, else null;
    - printed SD vs w/(7000 d^2) (QA note only);
    - catalog vs product page for diameter, OAL, SD, G1, G7, twist (a value
      blank on the page is taken from the catalog cell, with a note);
    - Part # vs Manufacturer SKU; factory-second ("BLEM") pages are skipped;
    - saboted muzzleloader bullet: catalog states ".458” Diameter ... Packaged
      in 50 Caliber Sabot" while the page/table print the 0.500 sabot caliber;
    - descriptions that belong to another product (Premium Brass) are ignored.

Swift (https://www.swiftbullets.com, Shopify storefront)
  * https://www.swiftbullets.com/robots.txt -> /products/ pages allowed, no
    Crawl-delay.  (Only public HTML product pages are used; no store APIs.)
    The site answered bursts with HTTP 429, so requests are spaced 45 s and a
    429 stops further requests to the host for that run (re-run to resume).
  * https://www.swiftbullets.com/sitemap.xml -> sitemap_products_1.xml and
    sitemap_collections_1.xml (bullet collection pages, for wording).
  * every product whose sitemap image title names a bullet (not ammunition).
    Each page prints "Caliber:", "Diameter:", "Weight:", "Profile:",
    "Density:", "Ballistic:", "Product Count:", "Brand:", "Type:".

Usage:
  python3 -I bullets-nosler-swift.py --download   # fetch missing documents
  python3 -I bullets-nosler-swift.py              # parse cache, write JSON
  python3 -I bullets-nosler-swift.py --check      # self-check written JSON

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

SRC = '/tmp/claude-0/-home-user-ORKA/29ce603d-ccc3-55ef-b8fe-c585397ac7c1/scratchpad/sources/bullets-nosler-swift'
OUT = '/home/user/ORKA/research/raw2/bullets-nosler-swift.json'
RETRIEVED = '2026-11-23'
DELAY = 1.5

NOSLER = 'https://www.nosler.com'
NOSLER_SITEMAP = NOSLER + '/sitemap.xml'
NOSLER_CATREQ = NOSLER + '/catalog-request.html'
NOSLER_CATALOG = NOSLER + '/media/binaryanvil/media_library/2026-Catalog-Layout_Web.pdf'
SWIFT = 'https://www.swiftbullets.com'
SWIFT_SITEMAP = SWIFT + '/sitemap.xml'

L_NOSLER_SITEMAP = os.path.join(SRC, 'nosler-sitemap.xml')
L_NOSLER_CATREQ = os.path.join(SRC, 'nosler-catalog-request.html')
L_NOSLER_CATALOG = os.path.join(SRC, 'nosler-2026-catalog.pdf')
L_NOSLER_CATALOG_TXT = os.path.join(SRC, 'nosler-2026-catalog.txt')
L_SWIFT_SITEMAP = os.path.join(SRC, 'swift-sitemap.xml')
L_SWIFT_SITEMAP_PRODUCTS = os.path.join(SRC, 'swift-sitemap-products.xml')
NOSLER_PAGES = os.path.join(SRC, 'nosler-pages')
SWIFT_PAGES = os.path.join(SRC, 'swift-pages')
SWIFT_COLLECTIONS = os.path.join(SRC, 'swift-collections')
L_SWIFT_SITEMAP_COLLECTIONS = os.path.join(SRC, 'swift-sitemap-collections.xml')

_last = {}
# Per-host politeness delay (s).  Swift answered one burst with HTTP 429, so it
# gets a much slower pace; after a 429 the host is left alone for this run.
HOST_DELAY = {'www.swiftbullets.com': 45.0}
_blocked = set()


def fetch(url, dest, force=False):
    """Download url to dest with plain curl (default UA); >= delay s per host."""
    if os.path.exists(dest) and os.path.getsize(dest) > 0 and not force:
        return True
    host = re.match(r'https?://([^/]+)', url).group(1)
    if host in _blocked:
        return False
    wait = HOST_DELAY.get(host, DELAY) - (time.time() - _last.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + '.part'
    r = subprocess.run(['curl', '-sS', '-L', '--max-time', '120', '-o', tmp,
                        '-w', '%{http_code}', url], capture_output=True, text=True)
    _last[host] = time.time()
    code = r.stdout.strip()
    if code != '200':
        sys.stderr.write('FETCH %s -> %s %s\n' % (url, code, r.stderr.strip()))
        record_failure(url, code)
        if os.path.exists(tmp):
            os.remove(tmp)
        if code == '429':
            sys.stderr.write('  rate-limited: leaving %s alone for this run\n' % host)
            _blocked.add(host)
        return False
    os.replace(tmp, dest)
    return True


FAILURES = os.path.join(SRC, 'fetch-failures.json')


def record_failure(url, code):
    try:
        d = json.load(open(FAILURES, encoding='utf-8')) if os.path.exists(FAILURES) else {}
    except ValueError:
        d = {}
    d[url] = {'http': code, 'when': time.strftime('%Y-%m-%dT%H:%M:%S')}
    with open(FAILURES, 'w', encoding='utf-8') as fh:
        json.dump(d, fh, indent=1)


def failure_of(url):
    try:
        return json.load(open(FAILURES, encoding='utf-8')).get(url) if os.path.exists(FAILURES) else None
    except ValueError:
        return None


def slug_of(url):
    return url.rstrip('/').rsplit('/', 1)[-1]


# ---------------------------------------------------------------- URL lists
def nosler_product_urls():
    xml = open(L_NOSLER_SITEMAP, encoding='utf-8').read()
    locs = re.findall(r'<loc>([^<]+)</loc>', xml)
    out = []
    for u in locs:
        u = htmlmod.unescape(u)
        m = re.match(r'^https://www\.nosler\.com/([^/]+)\.html$', u)
        if not m:
            continue
        s = m.group(1).lower()
        if not (re.search(r'\d+gr', s) or 'straight-wall' in s or 'solid-base' in s):
            continue
        if re.search(r'ammunition|ammo|brass|blem|factory|seconds', s):
            continue
        if u not in out:
            out.append(u)
    return out


def swift_product_urls():
    xml = open(L_SWIFT_SITEMAP_PRODUCTS, encoding='utf-8').read()
    out = []
    for block in re.findall(r'<url>(.*?)</url>', xml, flags=re.S):
        m = re.search(r'<loc>([^<]+)</loc>', block)
        if not m:
            continue
        loc = htmlmod.unescape(m.group(1))
        if '/products/' not in loc:
            continue
        titles = [htmlmod.unescape(t) for t in re.findall(r'<image:title>(.*?)</image:title>', block)]
        title = titles[0] if titles else ''
        if re.search(r'bullet', title, re.I) and 'bullet board' not in title.lower() \
                and not re.search(r'ammunition', title, re.I):
            out.append((loc, title))
        elif re.search(r'zephyr', loc + title, re.I) and not re.search(r'ammunition', title, re.I):
            out.append((loc, title))
    return out


def swift_collection_urls():
    if not os.path.exists(L_SWIFT_SITEMAP_COLLECTIONS):
        return []
    xml = open(L_SWIFT_SITEMAP_COLLECTIONS, encoding='utf-8').read()
    out = []
    for loc in re.findall(r'<loc>([^<]+)</loc>', xml):
        loc = htmlmod.unescape(loc)
        if '/collections/' in loc and re.search(r'bullet', loc.split('/collections/', 1)[1], re.I) \
                and loc not in out:
            out.append(loc)
    return out


def download(which=('nosler', 'swift')):
    if 'nosler' in which:
        fetch(NOSLER + '/robots.txt', os.path.join(SRC, 'nosler-robots.txt'))
        fetch(NOSLER_SITEMAP, L_NOSLER_SITEMAP)
        fetch(NOSLER_CATREQ, L_NOSLER_CATREQ)
        fetch(NOSLER_CATALOG, L_NOSLER_CATALOG)
        if not os.path.exists(L_NOSLER_CATALOG_TXT):
            subprocess.run(['pdftotext', '-layout', L_NOSLER_CATALOG, L_NOSLER_CATALOG_TXT], check=True)
        urls = nosler_product_urls()
        for i, u in enumerate(urls):
            ok = fetch(u, os.path.join(NOSLER_PAGES, slug_of(u)))
            if i % 25 == 0:
                print('nosler %d/%d %s %s' % (i, len(urls), ok, u), flush=True)
    if 'swift' in which:
        fetch(SWIFT + '/robots.txt', os.path.join(SRC, 'swift-robots.txt'))
        fetch(SWIFT_SITEMAP, L_SWIFT_SITEMAP)
        sm = open(L_SWIFT_SITEMAP, encoding='utf-8').read()
        prod_sm = [htmlmod.unescape(u) for u in re.findall(r'<loc>([^<]+)</loc>', sm)
                   if 'sitemap_products' in u]
        if prod_sm:
            fetch(prod_sm[0], L_SWIFT_SITEMAP_PRODUCTS)
        for loc, _t in swift_product_urls():
            fetch(loc, os.path.join(SWIFT_PAGES, slug_of(loc) + '.html'))
        # bullet collection pages (for the maker's construction wording)
        coll_sm = [htmlmod.unescape(u) for u in re.findall(r'<loc>([^<]+)</loc>', sm)
                   if 'sitemap_collections' in u]
        if coll_sm and fetch(coll_sm[0], L_SWIFT_SITEMAP_COLLECTIONS):
            for loc in swift_collection_urls():
                fetch(loc, os.path.join(SWIFT_COLLECTIONS, slug_of(loc) + '.html'))
    print('download done', which, flush=True)




# ---------------------------------------------------------------- helpers
def ws(s):
    return ' '.join((s or '').split())


def strip_tags(h):
    h = re.sub(r'<(script|style)\b.*?</\1>', ' ', h or '', flags=re.S | re.I)
    h = re.sub(r'<[^>]+>', ' ', h)
    return ws(htmlmod.unescape(h))


NUM_RE = re.compile(r'^\d*\.\d+$|^\d+$')


def num(v):
    """Parse a plain decimal number as printed ('.308', '0.525', '168'); else None."""
    if v is None:
        return None
    v = v.strip().rstrip('"”').strip()
    if NUM_RE.match(v):
        return float(v)
    return None


def src(url, typ='manufacturer', page=None):
    return {'url': url, 'type': typ, 'page': page, 'retrieved': RETRIEVED}


def twist_from_text(text):
    """'Requires a Minimum 1-12" Twist' -> ('1-12"', 12.0, phrase)."""
    m = re.search(r'(?:Requires a )?Minimum\s+(1-(\d+(?:\.\d+)?)\s*["”]?)\s*Twist', text or '', re.I)
    if not m:
        m = re.search(r'requires\s+(1-(\d+(?:\.\d+)?)\s*["”]?)\s*barrel twist', text or '', re.I)
    if not m:
        return None
    return {'text': m.group(1).replace('”', '"'), 'inches': float(m.group(2)), 'phrase': m.group(0)}


def sd_calc(w, d):
    return w / 7000.0 / (d * d)


# ---------------------------------------------------------------- Nosler catalog (PDF)
CAT_DATA = re.compile(r'\(\.(\d{3})[”"]\)\s+SD\.\s*([\d.]+)\s+BC\.\s*([\d.]+)\s+OAL\.\s*([\d.]+)[”"]?')
CAT_CT = re.compile(r'(\d+)\s*Ct\.\s*(\d{4,6})\b')
CAT_TWIST = re.compile(r'(?:Requires a )?Minimum 1-[\d.]+\s*[”"]\s*Twist')
# Section (product line) printed on each catalog page.  Pages mixing lines are
# resolved per cell from the cell's own header wording (see cat_line()).
CAT_PAGE_LINE = {3: 'Solid Base', 4: 'Partition', 5: 'AccuBond', 6: 'AccuBond Long Range',
                 7: 'Ballistic Tip Hunting', 8: 'Ballistic Silver Tip', 9: 'Expansion Tip',
                 10: None, 11: None, 12: 'RDF', 13: 'Custom Competition', 14: None}


LINE_CAT_PAGE = dict([(v, k) for k, v in CAT_PAGE_LINE.items() if v] + [
    ('Varmageddon', 10), ('Ballistic Tip Varmint', 10), ('Ballistic Tip Lead Free', 11),
    ('Ballistic Tip Muzzle Loader', 11), ('Sporting Handgun', 14), ('Assured Stopping Power', 14),
    ('Straight Wall', 3), ('Ballistic Silvertip', 8)])


def cat_line(page, header, diam):
    h = header or ''
    if page in CAT_PAGE_LINE and CAT_PAGE_LINE[page]:
        if page == 3 and re.search(r'LGND|Protected Point', h):
            return 'Straight Wall'
        return CAT_PAGE_LINE[page]
    if page == 10:
        return 'Varmageddon' if re.search(r'FB Tipped|FBHP', h) else 'Ballistic Tip Varmint'
    if page == 11:
        if re.search(r'Metallic', h):
            return 'Ballistic Tip Lead Free'
        if h.startswith('50 Cal'):
            return 'Ballistic Tip Muzzle Loader'
        return None
    return None   # page 14 mixes Sporting Handgun and ASP; not resolvable from the cell


def parse_catalog():
    """Return list of catalog cells with header, numbers, part numbers, twist, G1/G7 and verbatim text."""
    if not os.path.exists(L_NOSLER_CATALOG_TXT):
        return [], []
    pages = open(L_NOSLER_CATALOG_TXT, encoding='utf-8').read().split('\f')
    cells, problems = [], []
    for pno, pg in enumerate(pages, 1):
        lines = pg.split('\n')
        rows = []   # (line index, [cells])
        for li, l in enumerate(lines):
            ms = list(CAT_DATA.finditer(l))
            if ms:
                rows.append((li, ms))
        for ri, (li, ms) in enumerate(rows):
            next_li = rows[ri + 1][0] if ri + 1 < len(rows) else len(lines)
            for k, m in enumerate(ms):
                start = m.start()
                end = ms[k + 1].start() if k + 1 < len(ms) else 10 ** 6
                lo, hi = max(0, start - 6), end - 6
                # header: closest line above (max 4) whose cell segment names a grain weight
                header, header_raw = None, None
                prev_li = rows[ri - 1][0] if ri > 0 else -1
                for lj in range(li - 1, max(li - 13, prev_li), -1):
                    seg = lines[lj][lo:hi] if hi < 10 ** 5 else lines[lj][lo:]
                    chunk = re.split(r'\s{14,}', seg.strip())[0] if seg.strip() else ''
                    if re.search(r'\d+\s*Gr\.', chunk):
                        header, header_raw = ws(chunk), seg
                        break
                counts, twist, ct_lines = [], None, []
                g1g7 = None
                for lj in range(li + 1, min(next_li, li + 8)):
                    L = lines[lj]
                    for c in CAT_CT.finditer(L):
                        if lo <= c.start() < hi:
                            counts.append({'count': int(c.group(1)), 'part': c.group(2)})
                            ct_lines.append(c.group(0))
                    for tw in CAT_TWIST.finditer(L):
                        if lo <= tw.start() < hi:
                            twist = tw.group(0)
                    if 'G1 Ballistic Coefficient' in L and g1g7 is None and lj + 1 < len(lines):
                        labs = [(x.start(), 'G1') for x in re.finditer(r'G1 Ballistic Coefficient', L)] + \
                               [(x.start(), 'G7') for x in re.finditer(r'G7 Ballistic Coefficient', L)]
                        vals = [(x.start(), x.group(0)) for x in re.finditer(r'\b0?\.\d{3}\b', lines[lj + 1])]
                        mine = {}
                        for vpos, v in vals:
                            lab = min(labs, key=lambda t: abs(t[0] + 12 - vpos))
                            if lo - 4 <= lab[0] < hi:
                                mine.setdefault(lab[1], []).append(v)
                        if mine:
                            g1g7 = {'G1': mine.get('G1'), 'G7': mine.get('G7'),
                                    'raw': ws(L[lo:hi] if hi < 10 ** 5 else L[lo:]) + ' / ' +
                                    ws(lines[lj + 1][lo:hi] if hi < 10 ** 5 else lines[lj + 1][lo:])}
                cell = {
                    'page': pno, 'header': header, 'diam': '.' + m.group(1), 'sd': m.group(2),
                    'bc': m.group(3), 'oal': m.group(4), 'counts': counts, 'twist': twist,
                    'g1g7': g1g7, 'data_text': ws(m.group(0)), 'ct_text': ct_lines,
                }
                cell['line'] = cat_line(pno, header, cell['diam'])
                cell['evidence'] = 'catalog p.%d: %s | %s | %s%s' % (
                    pno, header or '(header not parsed)', cell['data_text'],
                    ' '.join(ct_lines) or '(part # not parsed)',
                    (' | ' + twist) if twist else '')
                if not counts:
                    problems.append('catalog p.%d: no part number associated with "%s" (%s)'
                                    % (pno, cell['data_text'], header))
                if num(cell['bc']) is None or not cell['bc'].startswith(('0.', '.')):
                    problems.append('catalog p.%d: BC printed as "%s" for %s (catalog typo; ignored)'
                                    % (pno, cell['bc'], header))
                    cell['bc_bad'] = True
                cells.append(cell)
    return cells, problems


def catalog_raw_pages():
    """Reading-order text (pdftotext -raw) of each catalog page, whitespace-collapsed (for wording)."""
    raw = os.path.join(SRC, 'nosler-2026-catalog.raw.txt')
    if not os.path.exists(raw) and os.path.exists(L_NOSLER_CATALOG):
        subprocess.run(['pdftotext', '-raw', L_NOSLER_CATALOG, raw], check=True)
    if not os.path.exists(raw):
        return []
    return [ws(p) for p in open(raw, encoding='utf-8').read().split('\f')]


# ---------------------------------------------------------------- Nosler product pages
def parse_nosler_page(path):
    t = open(path, encoding='utf-8', errors='replace').read()
    out = {}
    m = re.search(r'itemprop="name">(.*?)</span>', t)
    out['title'] = strip_tags(m.group(1)) if m else None
    m = re.search(r'<div class="value" itemprop="description">(.*?)</div>', t, re.S)
    out['overview'] = strip_tags(m.group(1)) if m else None
    m = re.search(r'Part #</strong>\s*<div class="value" itemprop="sku">(.*?)</div>', t, re.S)
    out['partno'] = strip_tags(m.group(1)) if m else None
    i = t.find('class="product attribute description"')
    j = t.find('id="tab-label-additional"', i) if i >= 0 else -1
    out['description'] = strip_tags(t[t.find('>', i) + 1:j]) if i >= 0 and j > i else ''
    # drop the trailing tab-label fragment that strip_tags leaves from the cut
    out['description'] = re.sub(r'\s*<div class="data item title.*$', '', out['description'])
    rows = re.findall(r'<th class="col label" scope="row">(.*?)</th>\s*<td class="col data"[^>]*>(.*?)</td>',
                      t, re.S)
    out['specs'] = [(strip_tags(a), strip_tags(b)) for a, b in rows]
    return out


# Construction, from the maker's own wording.  Each product line names the
# phrase(s) that must be found in that bullet's product description or, failing
# that, in the reading-order text of the catalog page that lists its part number.
CONSTRUCTION_RULES = {
    'Partition': [(r"Nosler[’']s integral partition", 'partition'),
                  (r"Nosler[’']s Integral Partition", 'partition')],
    'AccuBond': [(r"(?:proprietary|exclusive) bonding process", 'bonded')],
    'AccuBond Long Range': [(r"proprietary bonding process", 'bonded'),
                            (r"lead core is bonded to the copper jacket", 'bonded')],
    'Expansion Tip': [(r"Solid Copper-Alloy Construction", 'monolithic-copper')],
    'Ballistic Tip Hunting': [(r"Fully-Tapered Jacket and Special Lead-Alloy Core", 'cup-and-core')],
    'Ballistic Silvertip': [(r"Fully Tapered Jacket and Special Lead-Alloy Core", 'cup-and-core')],
    'Ballistic Silver Tip': [(r"Fully Tapered Jacket and Special Lead-Alloy Core", 'cup-and-core')],
    'Varmageddon': [(r"special lead-alloy core combines with the copper-alloy jacket", 'cup-and-core'),
                    (r"Varmageddon bullets are made with a lead-alloy core and feature a copper-alloy jacket",
                     'cup-and-core')],
    'Shots': [(r"Shots bullets are made with a lead-alloy core and feature a copper-alloy jacket", 'cup-and-core')],
    'Custom Competition': [(r"Custom Competition(?:®)? bullet jackets with (?:our|its) own ultra-precise, lead-alloy cores",
                            'cup-and-core')],
    'RDF': [],
    'Solid Base': [(r"Tapered Copper-Alloy jacket.{0,120}?Lead-? ?alloy core", 'cup-and-core')],
    'Sporting Handgun': [(r"pure lead core is copper-alloy jacketed", 'cup-and-core')],
    'Assured Stopping Power': [(r"pure lead core is encased in the copper-alloy jacket", 'cup-and-core')],
}
# Lines whose wording names a construction outside the schema's vocabulary.
CONSTRUCTION_NOTE_RULES = {
    'Ballistic Tip Lead Free': (r"Fragmenting Copper Core(?:™)? Technology.{0,300}?ultra-thin copper jacket",
                                'jacketed copper-core design; not one of the schema construction classes'),
    'Solid': (r"lead-free alloy construction", 'alloy not named (copper vs brass); not classified'),
    'Ballistic Tip Muzzle Loader': (r"Lead-Alloy Core: Engineered for balanced expansion",
                                    'core named but the jacket is not described; not classified'),
}


def find_construction(line, texts):
    """Search order: (1) the line's phrases in the bullet's own description, (2) in the catalog page that
    lists its part number, (3) any line's phrase in its own description, (4) the line's phrases in the
    catalog section page of its line (parts not in the catalog).  texts: [(label, text)]."""
    def rules_hit(rules, cands):
        for pat, cons in rules:
            for label, text in cands:
                m = re.search(pat, text or '', re.I | re.S)
                if m:
                    return cons, label, ws(m.group(0))
        return None
    own = [(lb, tx) for lb, tx in texts if lb == 'product description']
    part_page = [(lb, tx) for lb, tx in texts if lb.startswith('catalog') and 'section)' not in lb]
    section = [(lb, tx) for lb, tx in texts if 'section)' in lb]
    line_rules = CONSTRUCTION_RULES.get(line, [])
    for cands in (own, part_page):
        h = rules_hit(line_rules, cands)
        if h:
            return h[0], '%s: "%s"' % (h[1], h[2])
    for other, rules in CONSTRUCTION_RULES.items():
        if other == line:
            continue
        h = rules_hit(rules, own)
        if h:
            return h[0], '%s: "%s" (wording of the %s line; page labels this part "%s")' % (h[1], h[2], other, line)
    h = rules_hit(line_rules, section)
    if h:
        return h[0], '%s: "%s"' % (h[1], h[2])
    nr = CONSTRUCTION_NOTE_RULES.get(line)
    if nr:
        for label, text in texts:
            m = re.search(nr[0], text or '', re.I | re.S)
            if m:
                return None, '%s: "%s" (%s; left null)' % (label, ws(m.group(0)), nr[1])
    return None, None


TIP_RE = re.compile(r"\b((?:(?:unique|aerodynamic|streamlined|signature|metallic-colored|white|orange|"
                    r"od green|high-performance|sleek)\s+)*polymer tip(?:\s*\(color coded by caliber\))?)", re.I)


def nosler_firearm(line):
    if re.search(r'Handgun|ASP|Assured Stopping Power', line or '', re.I):
        return 'handgun'
    if re.search(r'Muzzle', line or '', re.I):
        return 'muzzleloader'
    return 'rifle'


def nosler_line(bullet_type, title):
    """Product line as the page's 'Bullet Type' prints it (fallback: title)."""
    bt = (bullet_type or '').strip()
    return bt or None


def close(a, b, tol=0.0005):
    return a is not None and b is not None and abs(a - b) <= tol


def build_nosler(problems):
    urls = nosler_product_urls()
    cells, cat_problems = parse_catalog()
    problems.extend(cat_problems)
    raw_pages = catalog_raw_pages()
    by_part = {}
    for c in cells:
        for ct in c['counts']:
            by_part.setdefault(ct['part'], []).append((c, ct))
    records, seen_parts, skipped = [], set(), []
    bc_agree = [0, 0]
    for u in urls:
        path = os.path.join(NOSLER_PAGES, slug_of(u))
        if not os.path.exists(path):
            fl = failure_of(u)
            problems.append('nosler page not downloaded: %s%s' % (u, (' (HTTP %s; listed in sitemap.xml)' % fl['http'])
                                                                   if fl else ''))
            continue
        p = parse_nosler_page(path)
        spec = dict(p['specs'])
        if spec.get('Type') != 'Bullet':
            skipped.append('%s (Type=%s)' % (u, spec.get('Type')))
            continue
        if re.search(r'\bBLEM\b|Factory Second', ' '.join([p['overview'] or '', p['title'] or '',
                                                             spec.get('Product Name', '')]), re.I):
            skipped.append('%s (factory second / blem: %s)' % (u, p['title']))
            continue
        sku = spec.get('Manufacturer SKU') or p['partno']
        notes, conflicts = [], []
        if p['partno'] and sku and p['partno'] != sku:
            problems.append('%s: Part # %s != Manufacturer SKU %s' % (u, p['partno'], sku))
            conflicts.append({'field': 'sku', 'values': [
                {'value': p['partno'], 'source': u + ' (Part #)'},
                {'value': sku, 'source': u + ' (Manufacturer SKU)'}]})
        wm = re.match(r'^\s*(\d+(?:\.\d+)?)\s*gr\b', spec.get('Bullet Weight', ''), re.I)
        weight = float(wm.group(1)) if wm else None
        diam = num(spec.get('Diameter'))
        oal = num(spec.get('Overall Length (OAL) (in.)'))
        g1 = num(spec.get('BC G1'))
        g7 = num(spec.get('BC G7'))
        sd = num(spec.get('Sectional Density (SD.)'))
        line = nosler_line(spec.get('Bullet Type'), p['title'])
        # evidence: the spec-table rows as rendered ("label value"), plus title / Part #
        keep = ['Product Name', 'Box Qty', 'BC G1', 'BC G7', 'Overall Length (OAL) (in.)',
                'Sectional Density (SD.)', 'Diameter', 'Cannelure/Band', 'Manufacturer SKU', 'Type',
                'Bullet Base', 'Bullet Profile', 'Bullet Type', 'Bullet Weight', 'Caliber', 'Lead Free']
        ev = ['Part # %s' % p['partno'], p['overview'] or p['title'] or '']
        ev += ['%s %s' % (k, v) for k, v in p['specs'] if k in keep]
        if re.search(r'Premium Brass', p['description'] or ''):
            notes.append('QA: the page\'s description text is about Nosler Premium Brass (another product); '
                         'it was not used')
            p['description'] = ''
        tw = twist_from_text(p['description']) or twist_from_text(p['overview'])
        if tw:
            ev.append(tw['phrase'])
        # catalog cross-check by part number
        cat_hits = by_part.get(sku, [])
        cat_src = None
        cat_twist = None
        if cat_hits:
            c, ct = cat_hits[0]
            cat_src = src(NOSLER_CATALOG, 'manufacturer', c['page'])
            seen_parts.update(x['part'] for x in c['counts'])
            ev.append(c['evidence'])
            if c['twist']:
                cat_twist = twist_from_text(c['twist'])
            for field, pv, cv in [('diameterIn', diam, num(c['diam'])), ('lengthIn', oal, num(c['oal'])),
                                  ('sectionalDensity', sd, num(c['sd'])),
                                  ('bcG1', g1, None if c.get('bc_bad') else num(c['bc']))]:
                if field == 'bcG1' and pv is not None and cv is not None:
                    bc_agree[0] += 1
                    bc_agree[1] += int(close(pv, cv))
                if pv is not None and cv is not None and not close(pv, cv):
                    conflicts.append({'field': field, 'values': [
                        {'value': pv, 'source': u},
                        {'value': cv, 'source': '%s p.%d' % (NOSLER_CATALOG, c['page'])}]})
                elif pv is None and cv is not None:
                    notes.append('%s blank on product page; taken from catalog p.%d (%s)' % (field, c['page'], cv))
                    if field == 'lengthIn':
                        oal = cv
                    elif field == 'bcG1':
                        g1 = cv
                    elif field == 'sectionalDensity':
                        sd = cv
                    elif field == 'diameterIn':
                        diam = cv
            if c['g1g7']:
                ev.append('catalog p.%d: %s' % (c['page'], c['g1g7']['raw']))
                for field, pv, cvs in [('bcG1', g1, c['g1g7']['G1']), ('bcG7', g7, c['g1g7']['G7'])]:
                    cv = num(cvs[0]) if cvs and len(cvs) == 1 else None
                    if pv is None and cv is not None and field == 'bcG7':
                        notes.append('bcG7 blank on product page; taken from catalog p.%d G1/G7 panel (%s)'
                                     % (c['page'], cv))
                        g7 = cv
                    if pv is not None and cv is not None and not close(pv, cv):
                        conflicts.append({'field': field, 'values': [
                            {'value': pv, 'source': u},
                            {'value': cv, 'source': '%s p.%d (G1/G7 panel)' % (NOSLER_CATALOG, c['page'])}]})
        # weight: the page states it up to three times (name, "Product Name" row, "Bullet Weight" row) and the
        # catalog header once.  Disagreements go to conflicts; the value is kept only when the printed
        # sectional density (page or catalog) corroborates exactly one candidate, else weightGr is null.
        claims = []
        for label, text, pat in [('"Bullet Weight" row', spec.get('Bullet Weight'), r'^\s*(\d+(?:\.\d+)?)\s*gr\b'),
                                 ('product name', p['overview'] or p['title'], r'(\d+(?:\.\d+)?)\s*gr\b'),
                                 ('"Product Name" row', spec.get('Product Name'), r'(\d+(?:\.\d+)?)\s*gr\b')]:
            mm = re.search(pat, text or '', re.I)
            if mm:
                claims.append((float(mm.group(1)), '%s (%s)' % (u, label)))
        if cat_hits:
            mm = re.search(r'(\d+)\s*Gr\.', cat_hits[0][0]['header'] or '')
            if mm:
                claims.append((float(mm.group(1)), '%s p.%d' % (NOSLER_CATALOG, cat_hits[0][0]['page'])))
        distinct = sorted({w for w, _ in claims})
        if len(distinct) > 1:
            conflicts.append({'field': 'weightGr', 'values': [{'value': w, 'source': sname} for w, sname in claims]})
            sds = [x for x in (sd, num(cat_hits[0][0]['sd']) if cat_hits else None) if x is not None]
            ok = [w for w in distinct if diam and sds and all(abs(sd_calc(w, diam) - x) <= 0.0015 for x in sds)]
            if len(ok) == 1:
                notes.append('weight: sources on the page/catalog disagree (%s); kept %sgr because the printed SD '
                             '(%s) at diameter %.3f matches only it' % (
                                 ', '.join('%sgr' % ('%g' % w) for w in distinct), '%g' % ok[0],
                                 '/'.join('%.3f' % x for x in sds), diam))
                weight = ok[0]
            else:
                notes.append('weight: sources disagree (%s) and the printed SD does not single one out; '
                             'weightGr left null' % ', '.join('%sgr' % ('%g' % w) for w in distinct))
                weight = None
        elif distinct:
            weight = distinct[0]
        # saboted muzzleloader bullets: the catalog states the bullet's own diameter and the sabot caliber
        diam_note = None
        if cat_hits and 0 < cat_hits[0][0]['page'] <= len(raw_pages):
            sm = re.search(r'\.(\d{3})[”"] Diameter (\d+)gr\. [^.]{0,40}?Packaged in (\d+) Caliber Sabot',
                           raw_pages[cat_hits[0][0]['page'] - 1])
            if sm and weight is not None and float(sm.group(2)) == weight:
                bd = float('0.' + sm.group(1))
                ev.append('catalog p.%d: %s' % (cat_hits[0][0]['page'], sm.group(0)))
                if diam is not None and not close(bd, diam):
                    conflicts.append({'field': 'diameterIn', 'values': [
                        {'value': diam, 'source': u + ' (Diameter = sabot/bore caliber)'},
                        {'value': bd, 'source': '%s p.%d ("%s")' % (NOSLER_CATALOG, cat_hits[0][0]['page'],
                                                                    sm.group(0))}]})
                    diam_note = ('diameterIn %.3f is the bullet diameter stated by the catalog ("%s"); the '
                                 'product page / table value %.3f is the sabot (bore) caliber' % (bd, sm.group(0), diam))
                    diam = bd
        if diam_note:
            notes.append(diam_note)
        # SD sanity check (derived, not used to fill anything; after sabot/catalog resolution)
        if weight and diam and sd is not None and abs(sd_calc(weight, diam) - sd) > 0.0015:
            notes.append('QA: printed SD %.3f differs from w/(7000*d^2)=%.4f' % (sd, sd_calc(weight, diam)))
        # twist
        twist = None
        if tw:
            twist = 'minimum 1-%s" (page: "%s")' % (('%g' % tw['inches']), tw['phrase'])
        if cat_twist:
            if tw and abs(tw['inches'] - cat_twist['inches']) > 1e-9:
                conflicts.append({'field': 'recommendedTwist', 'values': [
                    {'value': tw['phrase'], 'source': u},
                    {'value': cat_twist['phrase'], 'source': '%s p.%d' % (NOSLER_CATALOG, cat_hits[0][0]['page'])}]})
            elif not tw:
                twist = 'minimum 1-%s" (catalog p.%d: "%s")' % (('%g' % cat_twist['inches']),
                                                                 cat_hits[0][0]['page'], cat_twist['phrase'])
        # construction from wording
        texts = [('product description', p['description'])]
        if cat_hits and 0 < cat_hits[0][0]['page'] <= len(raw_pages):
            texts.append(('catalog p.%d' % cat_hits[0][0]['page'], raw_pages[cat_hits[0][0]['page'] - 1]))
        elif LINE_CAT_PAGE.get(line) and LINE_CAT_PAGE[line] <= len(raw_pages):
            # part not in the catalog: use the catalog section page of its product line
            texts.append(('catalog p.%d (%s section)' % (LINE_CAT_PAGE[line], line),
                          raw_pages[LINE_CAT_PAGE[line] - 1]))
        cons, cons_ev = find_construction(line, texts)
        if cons_ev:
            notes.append('construction wording: ' + cons_ev)
        else:
            notes.append('construction: no construction wording found for line "%s"; left null' % line)
        # tip
        tip = None
        tm = TIP_RE.search(p['description'] or '')
        if tm and not re.search(r'Hollow Point|Soft Point|Flat Nose|Round Nose', spec.get('Bullet Profile', '') or '')\
                or (tm and 'Tip' in (line or '')):
            tip = ws(tm.group(1))
        if cat_hits:
            tc = re.search(r'\(([^()]*Tip)\)', cat_hits[0][0]['header'] or '')
            if tc:
                tip = (tip + '; ' if tip else '') + tc.group(1) + ' (catalog)'
        if spec.get('Cannelure/Band'):
            notes.append('Cannelure/Band: %s' % spec.get('Cannelure/Band'))
        if spec.get('Lead Free'):
            notes.append('Lead Free: %s' % spec.get('Lead Free'))
        profile = spec.get('Bullet Profile')
        if spec.get('Bullet Base'):
            profile = '%s; base: %s' % (profile, spec.get('Bullet Base'))
        sources = [src(u, 'manufacturer', None)]
        if cat_src:
            sources.append(cat_src)
        status = 'current (nosler.com product page%s; retrieved %s)' % (
            ', listed in 2026 Product Guide' if cat_hits else ', not found in 2026 Product Guide', RETRIEVED)
        name = ws(re.sub(r'\*{2,}[^*]*\*{2,}', '', p['overview'] or ''))
        name = ws(re.sub(r'\s*NOTE:.*$', '', name))
        if len(re.sub(r'[^A-Za-z0-9]', '', name)) < 5:
            name = p['title']
        firearm = nosler_firearm(line)
        if firearm == 'rifle' and ((cat_hits and cat_hits[0][0]['page'] == 14) or
                                   re.search(r'\bhandgun\b', p['description'] or '', re.I)):
            firearm = 'handgun'
        rec = {
            'id': 'nosler-%s' % sku,
            'manufacturer': 'Nosler',
            'line': line,
            'name': name,
            'sku': sku,
            'caliberLabel': spec.get('Caliber'),
            'diameterIn': diam,
            'weightGr': weight,
            'lengthIn': oal,
            'boatTailLengthIn': None,
            'baseToOgiveIn': None,
            'bcG1': g1,
            'bcG7': g7,
            'bcNotes': None,
            'profile': profile,
            'tip': tip,
            'construction': cons,
            'recommendedTwist': twist,
            'status': status,
            'firearm': firearm,
            'sectionalDensity': sd,
            'boxCount': int(spec['Box Qty']) if (spec.get('Box Qty') or '').isdigit() else None,
            'sources': sources,
            'evidence': ' | '.join(x for x in ev if x),
            'notes': '; '.join(notes) if notes else None,
            'conflicts': conflicts,
        }
        if not oal:
            rec['notes'] = (rec['notes'] + '; ' if rec['notes'] else '') + 'no overall length published on page'
        records.append(rec)
    # catalog-only bullets (part number in the 2026 guide, no product page parsed)
    page_skus = {r['sku'] for r in records}
    for c in cells:
        parts = [x['part'] for x in c['counts']]
        if not parts or any(pn in page_skus for pn in parts):
            continue
        hw = re.search(r'(\d+)\s*Gr\.', c['header'] or '')
        d = num(c['diam'])
        sdv = num(c['sd'])
        if not hw or d is None or sdv is None:
            problems.append('catalog-only cell skipped (header/numbers not parsed): %s' % c['evidence'])
            continue
        w = float(hw.group(1))
        cell_notes = ['catalog-only: part number(s) %s not among the product pages parsed' % ', '.join(
            '%s (%d ct)' % (x['part'], x['count']) for x in c['counts'])]
        if abs(sd_calc(w, d) - sdv) > 0.0015:
            cell_notes.append('QA: printed SD %.3f differs from w/(7000*d^2)=%.4f' % (sdv, sd_calc(w, d)))
        bc = None if c.get('bc_bad') else num(c['bc'])
        g7 = None
        if c['g1g7'] and c['g1g7']['G7'] and len(c['g1g7']['G7']) == 1:
            g7 = num(c['g1g7']['G7'][0])
        tw = twist_from_text(c['twist']) if c['twist'] else None
        tc = re.search(r'\(([^()]*Tip)\)', c['header'] or '')
        line = c['line']
        texts = [('catalog p.%d' % c['page'], raw_pages[c['page'] - 1] if c['page'] <= len(raw_pages) else '')]
        cons, cons_ev = find_construction(line, texts) if line else (None, None)
        if cons_ev:
            cell_notes.append('construction wording: ' + cons_ev)
        if c['g1g7'] and c['g1g7']['G1'] and bc is not None and num(c['g1g7']['G1'][0]) == bc:
            cell_notes.append('catalog prints this BC as "G1 Ballistic Coefficient" in the G1/G7 panel')
        else:
            cell_notes.append('catalog BC printed as "BC." (legend: "BC = Ballistic Coefficient"); stored as G1 '
                              'because nosler.com labels the same catalog figures "BC G1"')
        pm = re.search(r'\d+\s*Gr\.\s*(.*?)\s*(?:\([^()]*\))?\s*$', c['header'])
        cat_profile = (pm.group(1).strip() or None) if pm else None
        records.append({
            'id': 'nosler-%s' % parts[0],
            'manufacturer': 'Nosler',
            'line': line,
            'name': c['header'],
            'sku': parts[0],
            'caliberLabel': re.split(r'\s+\d+\s*Gr\.', c['header'])[0].strip(),
            'diameterIn': d,
            'weightGr': w,
            'lengthIn': num(c['oal']),
            'boatTailLengthIn': None,
            'baseToOgiveIn': None,
            'bcG1': bc,
            'bcG7': g7,
            'bcNotes': None,
            'profile': cat_profile,
            'tip': tc.group(1) + ' (catalog)' if tc else None,
            'construction': cons,
            'recommendedTwist': ('minimum 1-%s" (catalog p.%d: "%s")' % ('%g' % tw['inches'], c['page'], tw['phrase'])
                                 if tw else None),
            'status': 'listed in Nosler 2026 Product Guide (no nosler.com product page parsed)',
            'firearm': 'handgun' if c['page'] == 14 else ('muzzleloader' if line and 'Muzzle' in line else 'rifle'),
            'sectionalDensity': sdv,
            'boxCount': c['counts'][0]['count'],
            'sources': [src(NOSLER_CATALOG, 'manufacturer', c['page'])],
            'evidence': c['evidence'] + ((' | catalog p.%d: %s' % (c['page'], c['g1g7']['raw'])) if c['g1g7'] else ''),
            'notes': '; '.join(cell_notes),
            'conflicts': [],
        })
    # box-count variants without a published length: point to sibling parts (hint only, no value copied)
    for r in records:
        if r['lengthIn'] is None and r['diameterIn'] and r['weightGr']:
            sib = [x['id'] for x in records if x is not r and x['lengthIn'] is not None and x['line'] == r['line']
                   and x['diameterIn'] == r['diameterIn'] and x['weightGr'] == r['weightGr']
                   and x['profile'] == r['profile']]
            if sib:
                r['notes'] = (r['notes'] + '; ' if r['notes'] else '') + (
                    'no length published for this part; same line/diameter/weight/profile with a published length: %s '
                    '(value not copied)' % ', '.join(sib))
    return records, skipped, bc_agree, cells


# ---------------------------------------------------------------- Swift product pages
def page_lines(path):
    t = open(path, encoding='utf-8', errors='replace').read()
    s = re.sub(r'<(script|style)\b.*?</\1>', '\n', t, flags=re.S | re.I)
    s = re.sub(r'<[^>]+>', '\n', s)
    s = htmlmod.unescape(s)
    return [ws(x) for x in s.split('\n') if ws(x)]


SWIFT_FIELDS = ['Caliber', 'Diameter', 'Weight', 'Profile', 'Density', 'Ballistic', 'Product Count']


def parse_swift_page(path):
    lines = page_lines(path)
    try:
        i = lines.index('Home')
    except ValueError:
        return None
    j = next((k for k in range(i, len(lines)) if lines[k].startswith('WARNING')), min(len(lines), i + 40))
    block = lines[i + 1:j]
    out = {'title': block[0] if block else None, 'fields': {}, 'block': block}
    for k, l in enumerate(block):
        m = re.match(r'^(%s):\s*(.*)$' % '|'.join(re.escape(f) for f in SWIFT_FIELDS), l)
        if m:
            out['fields'][m.group(1)] = m.group(2).strip()
        for lab in ('Brand', 'Type'):
            if l == lab + ':' and k + 1 < len(block):
                out['fields'][lab] = block[k + 1]
    if 'Categories:' in block:
        k = block.index('Categories:')
        cats, cur = [], []
        for l in block[k + 1:]:
            cur.append(l)
            if l.startswith('|'):
                cats.append(re.sub(r'\s+([®™])', r'\1', ' '.join(cur)))
                cur = []
        out['categories'] = cats
    ev = [out['title']] + [l for l in block if re.match(r'^(%s):' % '|'.join(SWIFT_FIELDS), l)]
    if 'Brand' in out['fields']:
        ev.append('Brand: %s' % out['fields']['Brand'])
    if 'Type' in out['fields']:
        ev.append('Type: %s' % out['fields']['Type'])
    out['evidence'] = ' | '.join(ev)
    return out


def kebab(s):
    return re.sub(r'[^a-z0-9]+', '-', (s or '').lower()).strip('-')


# Swift construction wording, from the maker's bullet collection pages
SWIFT_CONSTRUCTION_RULES = [
    (r"set the standard by which all bonded bullets are measured", 'bonded'),
    (r"\bbonded\b", 'bonded'),
]


def swift_collections():
    """{collection title (e.g. 'A-Frame® | Rifle Bullets'): (url, description text)}."""
    out = {}
    for loc in swift_collection_urls():
        lp = os.path.join(SWIFT_COLLECTIONS, slug_of(loc) + '.html')
        if not os.path.exists(lp):
            continue
        title = re.sub(r'\s*\|\s*Swift Bullet Company\s*$', '', html_title(lp) or '')
        lines = page_lines(lp)
        desc = ''
        # the collection description is the first long prose line after the page heading
        for k, l in enumerate(lines):
            if l in ('Filter', 'Sort'):
                break
            if len(l) > 80 and '|' not in l and not l.startswith(('WARNING', 'Our products')) and k > 0:
                desc = l
        out[title] = (loc, desc)
    return out


def build_swift(problems):
    recs, used = [], set()
    colls = swift_collections()
    for loc, sm_title in swift_product_urls():
        path = os.path.join(SWIFT_PAGES, slug_of(loc) + '.html')
        if not os.path.exists(path):
            fl = failure_of(loc)
            problems.append('swift page not downloaded: %s%s' % (loc, (' (HTTP %s)' % fl['http']) if fl else ''))
            continue
        p = parse_swift_page(path)
        if not p or not p['fields']:
            problems.append('swift page not parsed: %s' % loc)
            continue
        f = p['fields']
        if re.search(r'ammunition', f.get('Type', ''), re.I) or not f.get('Type'):
            problems.append('swift page skipped (Type=%s): %s' % (f.get('Type'), loc))
            continue
        wm = re.match(r'^(\d+(?:\.\d+)?)\s*gr', f.get('Weight', ''), re.I)
        weight = float(wm.group(1)) if wm else None
        diam = num(f.get('Diameter'))
        sd = num(f.get('Density'))
        bc = num(f.get('Ballistic'))
        notes = []
        if weight and diam and sd is not None and abs(sd_calc(weight, diam) - sd) > 0.0015:
            notes.append('QA: printed Density %.3f differs from w/(7000*d^2)=%.4f' % (sd, sd_calc(weight, diam)))
        tm = re.match(r'^(.*?)\s*\|\s*(\d+(?:\.\d+)?)\s*gr\.?$', p['title'] or '', re.I)
        if tm and weight is not None and float(tm.group(2)) != weight:
            problems.append('swift %s: title weight %s != Weight field %s' % (loc, tm.group(2), weight))
        brand = f.get('Brand')
        typ = f.get('Type')
        cal = f.get('Caliber')
        tpart = kebab(re.sub(r'(?i)\s*bullets?$', '', typ or ''))
        if tpart == kebab(brand) or not tpart:
            tpart = None
        base_id = '-'.join(x for x in ['swift', kebab(brand), tpart, kebab(cal),
                                       ('%g' % weight) if weight else 'x'] if x)
        rid = base_id
        if rid in used:
            rid = base_id + '-' + kebab(slug_of(loc))
        used.add(rid)
        if re.search(r'muzzle', typ or '', re.I) and diam is not None:
            notes.append('page Caliber %s vs Diameter %s: muzzleloader bullet; diameterIn holds the page\'s '
                         '"Diameter" value' % (cal, f.get('Diameter')))
        cons, cons_src, cat = None, None, None
        for c in p.get('categories', []):
            if c in colls:
                curl, cdesc = colls[c]
                for pat, cv in SWIFT_CONSTRUCTION_RULES:
                    if re.search(pat, cdesc or '', re.I):
                        cons, cons_src, cat = cv, curl, c
                        notes.append('construction wording: collection page "%s" (%s): "%s"' % (c, curl, cdesc))
                        break
                if not cons:
                    notes.append('construction: collection page "%s" has no construction wording' % c)
            else:
                notes.append('construction: collection page for category "%s" not retrieved' % c)
            if cons:
                break
        if not cons:
            notes.append('construction left null')
        firearm = 'handgun' if re.search(r'revolver|pistol', typ or '', re.I) else (
            'muzzleloader' if re.search(r'muzzle', typ or '', re.I) else 'rifle')
        rec = {
            'id': rid,
            'manufacturer': 'Swift',
            'line': brand,
            'name': p['title'],
            'sku': None,
            'caliberLabel': cal,
            'diameterIn': diam,
            'weightGr': weight,
            'lengthIn': None,
            'boatTailLengthIn': None,
            'baseToOgiveIn': None,
            'bcG1': None,
            'bcG7': None,
            'bcNotes': (('Swift prints "Ballistic: %s" (ballistic coefficient; drag model not stated on the page)'
                         % f.get('Ballistic')) if bc is not None else
                        ('Swift prints "Ballistic: %s" (no BC published)' % f.get('Ballistic'))
                        if f.get('Ballistic') else None),
            'bcUnspecifiedModel': bc,
            'profile': f.get('Profile'),
            'tip': None,
            'construction': cons,
            'recommendedTwist': None,
            'status': 'current (swiftbullets.com product page; retrieved %s)' % RETRIEVED,
            'firearm': firearm,
            'sectionalDensity': sd,
            'boxCount': int(re.match(r'(\d+)', f['Product Count']).group(1))
            if re.match(r'(\d+)', f.get('Product Count', '')) else None,
            'productType': typ,
            'productGroup': (re.match(r'^(.*?)\s+Cal\.?\s', p['title'] or '').group(1)
                             if re.match(r'^(.*?)\s+Cal\.?\s', p['title'] or '') else None),
            'sources': [src(loc, 'manufacturer', None)] + ([src(cons_src, 'manufacturer', None)] if cons_src else []),
            'evidence': p['evidence'] + ((' | Categories: %s' % '; '.join(p['categories']))
                                         if p.get('categories') else '') + (
                (' | %s' % colls[cat][1]) if cons_src else ''),
            'notes': '; '.join(notes + ['no bullet length, SKU or twist published on the product page']),
            'conflicts': [],
        }
        recs.append(rec)
    return recs


# ---------------------------------------------------------------- output
def pdf_date(path):
    try:
        r = subprocess.run(['pdfinfo', path], capture_output=True, text=True)
        m = re.search(r'CreationDate:\s+(.*)', r.stdout)
        if m:
            return ws(m.group(1))
    except Exception:
        pass
    return None


def html_title(path):
    try:
        t = open(path, encoding='utf-8', errors='replace').read()
        m = re.search(r'<title>(.*?)</title>', t, re.S)
        return ws(htmlmod.unescape(m.group(1))) if m else None
    except Exception:
        return None


def main():
    problems = []
    nos, skipped, bc_agree, cells = build_nosler(problems)
    swi = build_swift(problems)
    bullets = nos + swi
    ids = {}
    for r in bullets:
        ids[r['id']] = ids.get(r['id'], 0) + 1
    dups = [k for k, v in ids.items() if v > 1]
    if dups:
        problems.append('duplicate ids: %s' % dups)
    docs = [
        {'url': NOSLER_SITEMAP, 'localPath': L_NOSLER_SITEMAP, 'title': 'Nosler sitemap.xml', 'date': None},
        {'url': NOSLER_CATREQ, 'localPath': L_NOSLER_CATREQ, 'title': html_title(L_NOSLER_CATREQ), 'date': None},
        {'url': NOSLER_CATALOG, 'localPath': L_NOSLER_CATALOG,
         'title': 'Nosler 2026 Product Guide (2026-Catalog-Layout_Web.pdf)', 'date': pdf_date(L_NOSLER_CATALOG)},
        {'url': SWIFT_SITEMAP, 'localPath': L_SWIFT_SITEMAP, 'title': 'Swift sitemap.xml', 'date': None},
    ]
    sm_idx = open(L_SWIFT_SITEMAP, encoding='utf-8').read() if os.path.exists(L_SWIFT_SITEMAP) else ''
    for kind, lp, title in (('sitemap_products', L_SWIFT_SITEMAP_PRODUCTS, 'Swift product sitemap'),
                            ('sitemap_collections', L_SWIFT_SITEMAP_COLLECTIONS, 'Swift collection sitemap')):
        locs = [htmlmod.unescape(x) for x in re.findall(r'<loc>([^<]+)</loc>', sm_idx) if kind in x]
        if locs and os.path.exists(lp):
            docs.append({'url': locs[0], 'localPath': lp, 'title': title, 'date': None})
    for u in nosler_product_urls():
        lp = os.path.join(NOSLER_PAGES, slug_of(u))
        if os.path.exists(lp):
            docs.append({'url': u, 'localPath': lp, 'title': html_title(lp), 'date': None})
    for loc, _t in swift_product_urls():
        lp = os.path.join(SWIFT_PAGES, slug_of(loc) + '.html')
        if os.path.exists(lp):
            docs.append({'url': loc, 'localPath': lp, 'title': html_title(lp), 'date': None})
    for loc in swift_collection_urls():
        lp = os.path.join(SWIFT_COLLECTIONS, slug_of(loc) + '.html')
        if os.path.exists(lp):
            docs.append({'url': loc, 'localPath': lp, 'title': html_title(lp), 'date': None})
        else:
            fl = failure_of(loc)
            problems.append('swift collection page not retrieved: %s (%s)' % (
                loc, ('HTTP %s' % fl['http']) if fl else 'not attempted: host was rate-limiting (HTTP 429) and '
                                                       'was left alone'))
    n_conf = sum(1 for r in bullets if r.get('conflicts'))
    notes = (
        'Nosler: one record per Nosler part number (box-count variants such as 100/250/1000 ct are separate '
        'part numbers and therefore separate records). Primary source = the nosler.com product page '
        '"Specifications" table (BC G1, BC G7, Overall Length (OAL) (in.), Sectional Density, Diameter, Bullet '
        'Weight, Manufacturer SKU, Bullet Base/Profile/Type). The 2026 Product Guide PDF is parsed independently '
        '(pdftotext -layout, cell-by-cell by column position) and matched by part number; every numeric '
        'disagreement is kept in "conflicts" (record fields keep the product-page value). Catalog "BC." equals '
        'the product page "BC G1" for %d of %d matched bullets, so catalog-only records store the catalog BC as '
        'G1. Factory-seconds/blem pages, ammunition, brass and non-bullet products are excluded. '
        'Construction is assigned only where the maker\'s own wording (product description or the catalog page '
        'listing the part number) names it (see each record\'s notes). boatTailLengthIn and baseToOgiveIn are '
        'not published by Nosler (null). '
        'Swift: one record per swiftbullets.com bullet product page (Shopify; public HTML only). Swift publishes '
        'caliber, diameter, weight, profile code (as printed, e.g. AF/SS, BTS), Density (sectional density) and '
        '"Ballistic" (a ballistic coefficient without a stated drag model; kept in bcUnspecifiedModel and bcNotes, '
        'bcG1 left null). Swift publishes no bullet length, part number or twist on these pages (the JSON-LD '
        '"sku" is a Shopify variant id, not a maker part number, so sku is null). Construction comes only from '
        'the bullet collection page the product is filed under: "A-Frame® | Rifle Bullets" says "set the '
        'standard by which all bonded bullets are measured" (-> bonded); the A-Frame heavy-rifle, lever-action, '
        'revolver and muzzle-loader collection pages carry no construction wording, and the Scirocco, '
        'Break-Away, Zephyr and pistol collection pages could not be retrieved (HTTP 429), so those stay null. '
        'Swift answered request bursts with HTTP 429; downloads were slowed to 20-45 s/request and pages still '
        'missing are listed in problems. %d records carry conflicts.' % (bc_agree[1], bc_agree[0], n_conf))
    out = {
        'meta': {
            'key': 'bullets-nosler-swift',
            'retrieved': RETRIEVED,
            'documents': docs,
            'notes': notes,
            'problems': problems,
            'skippedNonBulletPages': skipped,
            'catalogCellsParsed': len(cells),
        },
        'bullets': bullets,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
        fh.write('\n')
    os.replace(tmp, OUT)
    print('wrote %s: %d bullets (nosler %d, swift %d); %d problems' % (OUT, len(bullets), len(nos), len(swi),
                                                                       len(problems)))


def appears(v, text):
    if v is None:
        return True
    cands = set()
    for fmt in ('%.3f', '%.4f', '%.2f', '%.1f', '%g'):
        s = fmt % v
        cands.add(s)
        if s.startswith('0.'):
            cands.add(s[1:])
    if float(v).is_integer():
        cands.add(str(int(v)))
    for c in cands:
        if re.search(r'(?<![\d.])' + re.escape(c) + r'(?!\d)', text):
            return True
    return False


def check():
    d = json.load(open(OUT, encoding='utf-8'))
    b = d['bullets']
    print('records:', len(b), {m: sum(1 for r in b if r['manufacturer'] == m) for m in ('Nosler', 'Swift')})
    print('with lengthIn:', sum(1 for r in b if r.get('lengthIn')), ' with bcG7:', sum(1 for r in b if r.get('bcG7')),
          ' with conflicts:', sum(1 for r in b if r.get('conflicts')))
    bad = []
    for r in b:
        for f in ('diameterIn', 'weightGr', 'lengthIn', 'bcG1', 'bcG7', 'sectionalDensity', 'bcUnspecifiedModel'):
            if not appears(r.get(f), r['evidence']):
                bad.append((r['id'], f, r.get(f)))
        for c in r.get('conflicts', []):
            for v in c['values']:
                if isinstance(v['value'], float) and not appears(v['value'], r['evidence']):
                    bad.append((r['id'], 'conflict:' + c['field'], v['value']))
        for k in ('sources', 'evidence'):
            if not r.get(k):
                bad.append((r['id'], k, 'missing'))
    doc_urls = {x['url'] for x in d['meta']['documents']}
    for r in b:
        for sref in r['sources']:
            if sref['url'] not in doc_urls:
                bad.append((r['id'], 'source not in meta.documents', sref['url']))
    print('values not found verbatim in evidence / undocumented sources:', len(bad))
    for x in bad[:40]:
        print('  ', x)
    rnd = random.Random(20261123)
    for r in rnd.sample(b, min(5, len(b))):
        print('-' * 80)
        print(json.dumps({k: r[k] for k in ('id', 'name', 'diameterIn', 'weightGr', 'lengthIn', 'bcG1', 'bcG7',
                                            'sectionalDensity', 'construction', 'recommendedTwist')},
                         ensure_ascii=False))
        print('EVIDENCE:', r['evidence'])
        print('NOTES:', r['notes'])
        if r.get('conflicts'):
            print('CONFLICTS:', json.dumps(r['conflicts'], ensure_ascii=False))
    return 0 if not bad else 1


if __name__ == '__main__':
    if '--download' in sys.argv:
        which = [a for a in sys.argv[1:] if a in ('nosler', 'swift')] or ['nosler', 'swift']
        download(which)
    elif '--check' in sys.argv:
        sys.exit(check())
    else:
        main()
