#!/usr/bin/env python3
"""Extract Barnes and Speer component-bullet specifications (key: bullets-barnes-speer).

Sources (all public, fetched with plain curl and its DEFAULT user agent, >= 2 s
between requests to a host; robots.txt of both hosts read first and obeyed):

Barnes (https://barnesbullets.com, BigCommerce storefront)
  * https://barnesbullets.com/robots.txt  -> generic "User-agent: *" group has
    no Crawl-delay; product pages are not disallowed.
  * https://barnesbullets.com/xmlsitemap.php?type=products&page=1 -> product
    URLs.  Component bullets are the slugs that start with the diameter
    ("0-308-...") or with a muzzleloader caliber ("50-cal-...").
  * every such product page.  Each page embeds (in the public HTML, inside the
    window.stencilBootstrap("product", ...) call) two copies of the maker's spec
    sheet: "customFields" (flat list, one group per Item #) and "specsJson"
    (dict keyed by Item #, used by the page's "Specs" tab).  Both are parsed
    and compared field by field; any disagreement goes to "conflicts" and the
    value is left null (no guessing which copy is right).
  * https://barnesbullets.com/catalog/ only offers the 2026 catalog as a
    raster poster image (barnes-bullet-poster-page-0001.jpg, WebP).  It prints
    TYPE / DIA / WGT / S.D. / B.C. / CAT.# but no bullet length; it is
    downloaded and listed in meta but NOT parsed (OCR of a raster poster is not
    reliable enough for safety-critical numbers).

Speer (https://www.speer.com, Salesforce Commerce Cloud storefront)
  * https://www.speer.com/robots.txt -> no Crawl-delay; category and product
    .html pages are allowed (only refinement/sort parameters are disallowed;
    the listings are fetched with the plain start/sz page-size parameters the
    site's own permalink uses).
  * https://www.speer.com/catalog.html -> 2026 catalog PDF
    (SP160_Speer2026_Catalog_web.pdf), pages 16-25 hold the component-bullet
    tables (Part No., Diameter, Weight, Bullet Type, BC, SD, Box Count; the
    Impact table prints G1 BC, G7 BC and a velocity band).  No bullet length.
  * the bullet line category pages (sitemap_0.xml, /bullets/rifle-bullets/*
    and /bullets/handgun-bullets/*) -> product .html pages.  Each product page
    prints a "Specs" table: Caliber, Grain Weight, Bullet Style, Ballistic
    Coefficient, Bullet Length In, Sectional Density, Diameter In, ...
    The product page is the primary source (it is the only one with bullet
    length); the catalog row of the same Part # is a second, independent
    source.  Disagreements -> "conflicts"; the field is then null.

Usage:
  python3 -I bullets-barnes-speer.py --download   # fetch missing documents
  python3 -I bullets-barnes-speer.py              # parse cache, write JSON
  python3 -I bullets-barnes-speer.py --check      # self-check written JSON

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

SRC = '/tmp/claude-0/-home-user-ORKA/29ce603d-ccc3-55ef-b8fe-c585397ac7c1/scratchpad/sources/bullets-barnes-speer'
OUT = '/home/user/ORKA/research/raw2/bullets-barnes-speer.json'
RETRIEVED = '2026-11-23'
DELAY = 2.0

BARNES = 'https://barnesbullets.com'
BARNES_ROBOTS = BARNES + '/robots.txt'
BARNES_SITEMAP = BARNES + '/xmlsitemap.php?type=products&page=1'
BARNES_CATALOG_PAGE = BARNES + '/catalog/'
BARNES_POSTER = BARNES + '/images/stencil/original/image-manager/barnes-bullet-poster-page-0001.jpg'

SPEER = 'https://www.speer.com'
SPEER_ROBOTS = SPEER + '/robots.txt'
SPEER_SITEMAP = SPEER + '/sitemap_0.xml'
SPEER_CATALOG_PAGE = SPEER + '/catalog.html'

L_BARNES_ROBOTS = os.path.join(SRC, 'barnes-robots.txt')
L_BARNES_SITEMAP = os.path.join(SRC, 'barnes-sitemap-products.xml')
L_BARNES_CATALOG_PAGE = os.path.join(SRC, 'barnes-catalog-page.html')
L_BARNES_POSTER = os.path.join(SRC, 'barnes-bullet-poster-page-0001.jpg')
BARNES_PAGES = os.path.join(SRC, 'barnes-pages')

L_SPEER_ROBOTS = os.path.join(SRC, 'speer-robots.txt')
L_SPEER_SITEMAP = os.path.join(SRC, 'speer-sitemap-0.xml')
L_SPEER_CATALOG_PAGE = os.path.join(SRC, 'speer-catalog.html')
L_SPEER_CATALOG = os.path.join(SRC, 'speer-2026-catalog.pdf')
L_SPEER_CATALOG_TXT = os.path.join(SRC, 'speer-2026-catalog.txt')
SPEER_LISTS = os.path.join(SRC, 'speer-lists')
SPEER_PAGES = os.path.join(SRC, 'speer-pages')

_last = {}


# --------------------------------------------------------------------------- download
def fetch(url, path, force=False):
    """curl with its default user agent; >= DELAY s between requests per host."""
    if os.path.exists(path) and os.path.getsize(path) > 0 and not force:
        return True
    host = re.match(r'https?://([^/]+)', url).group(1)
    wait = DELAY - (time.time() - _last.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.part'
    r = subprocess.run(['curl', '-s', '-L', '--max-time', '120', '-o', tmp, '-w', '%{http_code}', url],
                       capture_output=True, text=True)
    _last[host] = time.time()
    code = r.stdout.strip()
    if code != '200':
        print(f'  HTTP {code} {url}', file=sys.stderr)
        if os.path.exists(tmp):
            os.remove(tmp)
        return False
    os.replace(tmp, path)
    return True


def barnes_slug_is_bullet(slug):
    if not re.match(r'^(0-\d{3}-|\d{2}-cal-)', slug):
        return False
    if 'aligner-tool' in slug:   # a loading tool, not a bullet
        return False
    return True


def barnes_bullet_urls():
    xml = open(L_BARNES_SITEMAP, encoding='utf-8').read()
    urls = []
    for u in re.findall(r'<loc>([^<]+)</loc>', xml):
        u = htmlmod.unescape(u).strip()
        m = re.match(r'https://barnesbullets\.com/([^/?#]+)/?$', u)
        if m and barnes_slug_is_bullet(m.group(1)):
            urls.append(u)
    return sorted(set(urls))


def speer_line_urls():
    xml = open(L_SPEER_SITEMAP, encoding='utf-8').read()
    out = []
    for u in re.findall(r'<loc>([^<]+)</loc>', xml):
        u = htmlmod.unescape(u).strip()
        if re.match(r'https://www\.speer\.com/bullets/(rifle|handgun)-bullets/[a-z0-9-]+/$', u):
            out.append(u)
    return sorted(set(out))


def speer_list_path(line_url):
    return os.path.join(SPEER_LISTS, line_url.rstrip('/').split('/')[-1] + '.html')


def speer_product_links(list_html):
    return sorted(set(re.findall(r'href="(/bullets/(?:rifle|handgun)-bullets/[a-z0-9-]+/[0-9A-Za-z-]+\.html)"', list_html)))


def speer_page_path(rel):
    return os.path.join(SPEER_PAGES, rel.strip('/').replace('/', '__'))


def barnes_page_path(url):
    return os.path.join(BARNES_PAGES, url.rstrip('/').split('/')[-1] + '.html')


def download():
    # Barnes
    fetch(BARNES_ROBOTS, L_BARNES_ROBOTS)
    fetch(BARNES_SITEMAP, L_BARNES_SITEMAP)
    fetch(BARNES_CATALOG_PAGE, L_BARNES_CATALOG_PAGE)
    fetch(BARNES_POSTER, L_BARNES_POSTER)
    urls = barnes_bullet_urls()
    print(f'Barnes bullet product pages: {len(urls)}')
    for i, u in enumerate(urls):
        ok = fetch(u, barnes_page_path(u))
        if i % 20 == 0:
            print(f'  barnes {i}/{len(urls)} ok={ok}', flush=True)
    # Speer
    fetch(SPEER_ROBOTS, L_SPEER_ROBOTS)
    fetch(SPEER_SITEMAP, L_SPEER_SITEMAP)
    fetch(SPEER_CATALOG_PAGE, L_SPEER_CATALOG_PAGE)
    cat = open(L_SPEER_CATALOG_PAGE, encoding='utf-8').read()
    m = re.search(r'href="([^"]*SP160_Speer2026_Catalog_web\.pdf)"', cat)
    if m:
        fetch(SPEER + htmlmod.unescape(m.group(1)), L_SPEER_CATALOG)
    if os.path.exists(L_SPEER_CATALOG) and not os.path.exists(L_SPEER_CATALOG_TXT):
        subprocess.run(['pdftotext', '-layout', L_SPEER_CATALOG, L_SPEER_CATALOG_TXT], check=True,
                       stderr=subprocess.DEVNULL)
    lines = speer_line_urls()
    print(f'Speer bullet line pages: {len(lines)}')
    rels = []
    for u in lines:
        p = speer_list_path(u)
        fetch(u + '?start=0&sz=60', p)
        if os.path.exists(p):
            rels += speer_product_links(open(p, encoding='utf-8').read())
    rels = sorted(set(rels))
    print(f'Speer product pages: {len(rels)}')
    for i, rel in enumerate(rels):
        ok = fetch(SPEER + rel, speer_page_path(rel))
        if i % 20 == 0:
            print(f'  speer {i}/{len(rels)} ok={ok}', flush=True)




# --------------------------------------------------------------------------- helpers
def ws(s):
    return re.sub(r'\s+', ' ', s or '').strip()


def strip_tags(s):
    return ws(htmlmod.unescape(re.sub(r'<[^>]+>', ' ', s or '')))


def num(s):
    """Parse a printed number ('.484', '0.484', '1,500'); None if not a plain number."""
    if s is None:
        return None
    t = str(s).strip().replace('"', '').replace(',', '')
    if not re.fullmatch(r'\d*\.?\d+', t):
        return None
    return float(t)


def same(a, b):
    return a is not None and b is not None and abs(a - b) < 1e-9


def src(url, typ='manufacturer', page=None):
    return {'url': url, 'type': typ, 'page': page, 'retrieved': RETRIEVED}


def kebab(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def twist_text(v, who):
    if v is None:
        return None
    return f'1:{v:g} minimum ({who})'


# --------------------------------------------------------------------------- Barnes
BARNES_MATERIAL = {
    # Barnes' own "Bullet Material" category wording -> construction enum.
    '100% Copper': 'monolithic-copper',
    'Solid Brass': 'monolithic-brass',
    'Jacketed Lead Core': 'cup-and-core',
    'Jacketed Non-Lead': None,   # no enum value fits (non-lead core inside a jacket)
}
BARNES_STYLE = {'BT': 'boat-tail', 'FB': 'flat-base'}
B_FIELDS = [  # (record field, specsJson key, customFields keys)
    ('weightGr', 'Bullet Weight (Grains)', ('Bullet Weight', 'Bullet Weight (Grains)')),
    ('diameterIn', 'Diameter', ('Diameter',)),
    ('bcG1', 'G1 BC', ('G1 BC',)),
    ('bcG7', 'G7 BC', ('G7 BC',)),
    ('sectionalDensity', 'Sectional Density', ('Sectional Density',)),
    ('lengthIn', 'Length', ('Length', 'Bullet Length')),
    ('minTwistIn', 'Minimum Twist Rate', ('Minimum Twist Rate',)),
    ('boxCount', 'Box Quantity', ('Box Quantity', 'Rounds Per Box')),
]


def barnes_bootstrap(t):
    tag = 'window.stencilBootstrap("product", '
    i = t.find(tag)
    if i < 0:
        return None
    s, _ = json.JSONDecoder().raw_decode(t, i + len(tag))
    return json.loads(s)


def barnes_cf_groups(cf):
    """Group the flat customFields list by 'Item #'.  A field is attributed to an
    item only when its id directly continues that item's run of ids (fields that
    were appended later, with a far id, are attributed only on single-item pages)."""
    items = [f for f in cf if f['name'] == 'Item #']
    groups = {}
    if not items:
        return groups, []
    cur = None
    last_id = None
    loose = []
    pre = []
    for f in cf:
        fid = int(f['id'])
        if f['name'] == 'Item #':
            cur = groups.setdefault(f['value'].strip(), {'_fields': []})
            last_id = fid
            if pre and len(items) == 1:
                for g in pre:
                    cur['_fields'].append(g)
            elif pre and int(pre[-1]['id']) == fid - 1:
                for g in pre:   # page-level block printed right before the first item
                    cur['_fields'].append(g)
            pre = []
            continue
        if cur is None:
            pre.append(f)
            continue
        if last_id is not None and fid == last_id + 1:
            cur['_fields'].append(f)
            last_id = fid
        else:
            loose.append(f)
    if len(items) == 1:
        only = next(iter(groups.values()))
        only['_fields'] += [f for f in loose if f['name'] != '__customLabel']
        loose = []
    for g in groups.values():
        for f in g['_fields']:
            g.setdefault(f['name'], f['value'])
    return groups, loose


def barnes_spec_text(spec_raw, item):
    """Verbatim (whitespace-collapsed) text of one item's block in the decoded specsJson."""
    m = re.search(r'"%s"\s*:\s*\{[^{}]*\}' % re.escape(item), spec_raw)
    return ws(m.group(0)) if m else None


def barnes_records(log):
    recs = []
    docs = []
    for url in barnes_bullet_urls():
        p = barnes_page_path(url)
        if not os.path.exists(p):
            log.append(f'Barnes page missing (not downloaded): {url}')
            continue
        t = open(p, encoding='utf-8').read()
        d = barnes_bootstrap(t)
        if not d:
            log.append(f'Barnes page without product data: {url}')
            continue
        name = ws(d.get('productName'))
        docs.append({'url': url, 'localPath': p, 'title': f'Barnes product page: {name}', 'date': None})
        cats = d.get('productCategory') or []
        fam = [c.split('/')[-1] for c in cats if c.startswith('Bullets/Product Family/')]
        mats = [c.split('/')[-1] for c in cats if c.startswith('Bullets/Bullet Material/')]
        new_cat = '2026 New Products' in cats
        dm = re.search(r'id="tab-description-content"[^>]*>(.*?)</div>', t, re.S)
        desc = strip_tags(dm.group(1)) if dm else ''
        spec_raw = d.get('specsJson') or ''
        dupkeys = []

        def hook(pairs, _dk=dupkeys):
            out = {}
            for k, v in pairs:
                if k in out and out[k] != v:
                    _dk.append((k, out[k], v))
                out[k] = v
            return out
        try:
            spec = json.loads(spec_raw, object_pairs_hook=hook) if spec_raw.strip() else {}
        except ValueError:
            spec = {}
            log.append(f'Barnes specsJson not parseable: {url}')
        groups, loose = barnes_cf_groups(d.get('customFields') or [])
        # the items sold on this page are the customFields "Item #" values
        item_ids = list(groups.keys()) or list(spec.keys())
        for extra in [k for k in spec if k not in item_ids]:
            log.append(f'Barnes {url}: specsJson also holds item {extra} '
                       f'({spec[extra].get("Bullet Weight (Grains)")} gr) which is not an item of this page; ignored here')
        page_recs = []
        for item in item_ids:
            sj = spec.get(item)
            cg = groups.get(item, {})
            notes = []
            conflicts = []
            vals = {}
            for k, a, b in dupkeys:
                notes.append(f'specsJson prints key "{k}" twice on this page ("{a}" / "{b}")')
            wcands = []
            origin = {}
            for fld, sk, ck in B_FIELDS:
                if fld == 'weightGr':
                    a_raw = sj.get(sk) if sj else None
                    b_raw = next((cg[k] for k in ck if k in cg), None)
                    if num(a_raw) is not None:
                        wcands.append((num(a_raw), f'{url} (page data "specsJson", item {item}, "{sk}": "{a_raw}")'))
                    if num(b_raw) is not None:
                        wcands.append((num(b_raw), f'{url} (page data "customFields", item {item}, "Bullet Weight": "{b_raw}")'))
                    continue
                a_raw = sj.get(sk) if sj else None
                b_raw = next((cg[k] for k in ck if k in cg), None)
                a, b = num(a_raw), num(b_raw)
                if a_raw not in (None, '') and a is None:
                    notes.append(f'specsJson "{sk}" printed as {a_raw!r} (not a number; ignored)')
                if a is not None and b is not None and not same(a, b):
                    conflicts.append({'field': fld, 'values': [
                        {'value': a, 'source': f'{url} (page data "specsJson", item {item}, "{sk}": "{a_raw}")'},
                        {'value': b, 'source': f'{url} (page data "customFields", item {item}, "{ck[0]}": "{b_raw}")'}]})
                    vals[fld] = None
                else:
                    vals[fld] = a if a is not None else b
                    origin[fld] = 'both' if (a is not None and b is not None) else 'specsJson' if a is not None else 'customFields' if b is not None else None
                    if a is None and b is not None:
                        notes.append(f'{fld} taken from customFields (absent in specsJson)')
            line = (sj or {}).get('Product Line') or cg.get('Product Line') or (fam[0] if fam else None)
            style = (sj or {}).get('Bullet Style') or cg.get('Bullet Style')
            if not sj:
                notes.append('item absent from specsJson; values from customFields only')
            # weight: specsJson, customFields and the weight printed in the product name must agree;
            # on disagreement keep a value only if the printed sectional density corroborates exactly one.
            nm_w = re.search(r'(\d+)\s*GR\b', name, re.I)
            if nm_w and len(item_ids) == 1:
                wcands.append((float(nm_w.group(1)), f'{url} (product name "{name}")'))
            distinct = sorted({w for w, _ in wcands})
            vals['weightGr'] = distinct[0] if len(distinct) == 1 else None
            if len(distinct) > 1:
                conflicts.append({'field': 'weightGr', 'values': [{'value': w, 'source': s_} for w, s_ in wcands]})
                sd, dia = vals.get('sectionalDensity'), vals.get('diameterIn')
                ok = [w for w in distinct if sd is not None and dia and abs(w / (7000 * dia * dia) - sd) <= 0.0015]
                if len(ok) == 1:
                    vals['weightGr'] = ok[0]
                    notes.append(f'weight sources disagree ({", ".join(f"{w:g}" for w in distinct)}); {ok[0]:g} gr kept because '
                                 f'the printed sectional density {sd:.3f} matches {ok[0]:g}/(7000*{dia:.3f}^2) and no other candidate')
                    # a copy whose weight was wrong is not trusted for values nobody else confirms
                    bad_copies = {('specsJson' if 'specsJson' in s_ else 'customFields' if 'customFields' in s_ else 'name')
                                  for w, s_ in wcands if not same(w, ok[0])}
                    for fld in ('lengthIn', 'bcG1', 'bcG7', 'minTwistIn', 'diameterIn'):
                        if vals.get(fld) is not None and origin.get(fld) in bad_copies:
                            notes.append(f'{fld} {vals[fld]:g} printed only in the {origin[fld]} copy whose weight was wrong; left null')
                            vals[fld] = None
                else:
                    notes.append(f'weight sources disagree ({", ".join(f"{w:g}" for w in distinct)}); left null')
            ev_parts = [f'productName: {name}']
            st = barnes_spec_text(spec_raw, item) if sj else None
            if st:
                ev_parts.append(f'specsJson: {st}')
            cf_txt = '; '.join(f'{f["name"]}: {f["value"]}' for f in cg.get('_fields', []) if f['name'] != '__customLabel')
            if cg:
                ev_parts.append(f'customFields: Item #: {item}; {cf_txt}' if cf_txt else f'customFields: Item #: {item}')
            construction = BARNES_MATERIAL.get(mats[0]) if len(mats) == 1 else None
            if len(mats) == 1:
                notes.append(f'Barnes "Bullet Material" category: {mats[0]}')
            elif mats:
                notes.append(f'Barnes "Bullet Material" categories: {", ".join(mats)} (construction not set)')
            tip = 'polymer' if re.search(r'polymer tip', desc, re.I) else None
            if desc:
                notes.append(f'Product Details: {desc}')
            pursuit = (sj or {}).get('Pursuit') or cg.get('Pursuit')
            purpose = (sj or {}).get('Purpose') or cg.get('Purpose')
            if purpose or pursuit:
                notes.append(f'Purpose: {purpose}; Pursuit: {pursuit}')
            if vals['boxCount'] is not None:
                notes.append(f'Box quantity {vals["boxCount"]:g}')
            upc = (sj or {}).get('Box UPC') or cg.get('Box UPC')
            if upc:
                notes.append(f'Box UPC {upc}')
            if vals['sectionalDensity'] is not None:
                notes.append(f'Printed sectional density {vals["sectionalDensity"]:.3f}')
            cal = re.sub(r'^0?\.\d{3}"\s*', '', name)
            if line:
                cal = re.split(r'\s+' + re.escape(line) + r'\b', cal, flags=re.I)[0]
            cal = re.sub(r'\b\d+\s*GR\b', '', cal, flags=re.I).strip(' ()')
            cal = ws(cal) or None
            prof = None
            if style and style.strip():
                style = ws(style)
                kinds = [BARNES_STYLE[t] for t in style.split() if t in BARNES_STYLE]
                prof = style + (f' ({", ".join(kinds)})' if kinds else '')
            rec = {
                'id': f'barnes-{kebab(item)}',
                'manufacturer': 'Barnes',
                'line': line,
                'name': name,
                'sku': item,
                'caliberLabel': cal,
                'diameterIn': vals['diameterIn'],
                'weightGr': vals['weightGr'],
                'lengthIn': vals['lengthIn'],
                'boatTailLengthIn': None,
                'baseToOgiveIn': None,
                'bcG1': vals['bcG1'],
                'bcG7': vals['bcG7'],
                'bcNotes': None,
                'profile': prof,
                'tip': tip,
                'construction': construction,
                'recommendedTwist': twist_text(vals['minTwistIn'], 'Barnes "Minimum Twist Rate"'),
                'status': 'current',
                'sources': [src(url)],
                'evidence': ws(' | '.join(ev_parts)),
                'notes': None,
                'conflicts': conflicts,
                '_notes': notes,
                '_sd': vals['sectionalDensity'],
                '_style': style,
                '_new': new_cat,
            }
            page_recs.append(rec)
        # same bullet in several box counts on one page must print identical specs
        by_key = {}
        for r in page_recs:
            by_key.setdefault((r['diameterIn'], r['weightGr'], r['_style'], r['line']), []).append(r)
        for k, rs in by_key.items():
            if len(rs) < 2 or k[1] is None:
                continue
            for fld in ('lengthIn', 'bcG1', 'bcG7', '_sd'):
                vs = {r[fld] for r in rs if r[fld] is not None}
                if len(vs) > 1:
                    vals_ = [{'value': o[fld], 'source': f'{url} (item {o["sku"]}; same {k[1]:g} gr {k[2]} bullet in another box count)'} for o in rs]
                    for r in rs:
                        r['conflicts'].append({'field': 'sectionalDensity' if fld == '_sd' else fld, 'values': vals_})
                        r[fld] = None
                        r['_notes'].append(f'{fld.strip("_")} differs between box-count variants of the same {k[1]:g} gr bullet on this page; left null')
        recs += page_recs
    return recs, docs


# --------------------------------------------------------------------------- Speer catalog
SPEER_TABLE_RE = re.compile(r'^\s*([A-Z][A-Z0-9 ®&\-]*?BULLETS?)\s*$')
SPEER_SKIP_TABLES = ('PLASTIC', 'ROUND BALL')
SPEER_ROW_RE = re.compile(
    r'^\s*(?P<new>NEW\s+)?(?P<cal>\S.*?)\s{2,}(?P<part>[0-9][0-9A-Z]*|TB[0-9A-Z]+)\s+(?P<dia>0\.\s?\d{3})\s+(?P<wt>\d{2,3})\s+'
    r'(?P<type>\S.*?)\s+(?P<bc>0\.\d{3})\s+(?P<sd>0\.\d{3})\s+(?P<box>\d+)\s*$')
SPEER_IMPACT_RE = re.compile(
    r'^\s*(?P<new>NEW\s+)?(?P<cal>\S.*?)\s{2,}(?P<part>TB[0-9A-Z]+)\s+(?P<dia>0\.\d{3})\s+(?P<wt>\d{2,3})\s+'
    r'(?P<type>Impact)\s+(?P<vel>[\d,]+\s*[–-]\s*[\d,]+)\s+(?P<g1>0\.\d{3})\s+(?P<g7>0\.\d{3})\s+(?P<box>\d+)\s*$')


def speer_catalog_rows(log):
    txt = open(L_SPEER_CATALOG_TXT, encoding='utf-8').read()
    rows = {}
    for pno, page in enumerate(txt.split('\f'), start=1):
        table = None
        for line in page.split('\n'):
            m = SPEER_TABLE_RE.match(line)
            if m and not re.match(r'^\s*(Caliber|ABBREVIATION)', line):
                table = ws(m.group(1))
                if any(k in table for k in SPEER_SKIP_TABLES):
                    table = None
                continue
            if table is None:
                continue
            mi = SPEER_IMPACT_RE.match(line)
            mr = None if mi else SPEER_ROW_RE.match(line)
            m = mi or mr
            if not m:
                if re.search(r'\s0\.\d{3}\s+\d', line) and not re.search(r'Caliber\s+Part', line):
                    log.append(f'Speer catalog p.{pno}: unparsed row-like line: {ws(line)}')
                continue
            g = m.groupdict()
            dia_raw = g['dia']
            r = {
                'table': table, 'page': pno, 'line': ws(line), 'new': bool(g.get('new')),
                'caliber': ws(g['cal']), 'part': g['part'], 'diaRaw': dia_raw,
                'dia': num(dia_raw.replace(' ', '')), 'wt': num(g['wt']), 'type': ws(g['type']),
                'box': num(g['box']),
            }
            if mi:
                r.update({'g1': num(g['g1']), 'g7': num(g['g7']), 'vel': ws(g['vel']), 'sd': None})
            else:
                r.update({'g1': num(g['bc']), 'g7': None, 'vel': None, 'sd': num(g['sd'])})
            if r['part'] in rows:
                log.append(f'Speer catalog: part {r["part"]} printed twice (p.{rows[r["part"]]["page"]} and p.{pno})')
            rows[r['part']] = r
    return rows


# --------------------------------------------------------------------------- Speer product pages
def speer_page(t):
    out = {}
    m = re.search(r'<h1[^>]*class="[^"]*product-name[^"]*"[^>]*>(.*?)</h1>', t, re.S)
    out['name'] = strip_tags(m.group(1)) if m else None
    m = re.search(r'Part\s*#\s*(?:</[^>]+>\s*<[^>]+>\s*)*\s*([0-9A-Z][0-9A-Za-z-]*)\s*<', t)
    out['part'] = m.group(1) if m else None
    specs = []
    m = re.search(r'<div class="spec-datasheet">(.*?)</table>', t, re.S)
    if m:
        for a, b in re.findall(r'<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*</tr>', m.group(1), re.S):
            specs.append((strip_tags(a), strip_tags(b)))
    out['specs'] = specs
    m = re.search(r'<h3 class="text-left">Product Overview</h3>\s*<p>(.*?)</p>', t, re.S)
    out['overview'] = strip_tags(m.group(1)) if m else ''
    m = re.search(r'<ol class="breadcrumb">(.*?)</ol>', t, re.S)
    out['breadcrumb'] = [strip_tags(x) for x in re.findall(r'<a[^>]*>(.*?)</a>', m.group(1), re.S)] if m else []
    return out


SPEER_TABLE_LINE = {
    'IMPACT RIFLE BULLETS': 'impact-bullet',
    'GRAND SLAM ® RIFLE BULLETS': 'grand-slam-rifle-bullet',
    'HOT-COR ® RIFLE BULLETS': 'hot-cor-rifle-bullet',
    'BOAT-TAIL RIFLE BULLETS': 'boat-tail-rifle-bullet',
    'GOLD DOT ® RIFLE BULLETS': 'gold-dot-rifle-component-bullet',
    'TNT GREEN ® BULLETS': 'tnt-green-bullet',
    'TNT ® BULLETS': 'tnt-bullet',
    'VARMINT HOLLOW POINT BULLETS': 'varmint-hollow-point-bullet',
    'VARMINT SOFT POINT BULLETS': 'varmint-soft-point-bullet',
    'JACKETED HOLLOW POINT RIFLE BULLETS': 'jacketed-hollow-point-rifle-bullet',
    'TARGET MATCH RIFLE BULLETS': 'target-match-rifle-bullet',
    'TMJ ® RIFLE BULLET': 'tmj-rifle-bullet',
    'DEEPCURL® HANDGUN HUNTING BULLETS': 'deepcurl-handgun-hunting',
    'GOLD DOT ® PERSONAL PROTECTION BULLETS': 'gold-dot-handgun-component-bullet',
    'GOLD DOT ® SHORT BARREL® PERSONAL PROTECTION BULLETS': 'gold-dot-short-barrel-personal-protection-bullet',
    'TMJ ® HANDGUN BULLETS': 'tmj-handgun-bullet',
    'JACKETED HANDGUN BULLETS': 'jacketed-handgun-bullet',
    'LEAD HANDGUN BULLETS': 'lead-handgun-bullet',
    'COPPER PLATED BULLETS': None,   # RN -> copper-plated-round-nose-cprn, FN -> copper-plated-flat-nose-cpfn
}
# Construction / tip from the 2026 catalog's own wording.  The quoted phrase must
# be present in the catalog text, otherwise the value is not set.
SPEER_LINE_RULES = {
    'impact-bullet': ('bonded', 'molecularly bonded construction', 'polymer', 'Slipstream ® polymer tip'),
    'gold-dot-rifle-component-bullet': ('bonded', 'Personal Protection rifle bullets. Their exclusive manufacturing process bonds the uniform jacket to the core', None, None),
    'gold-dot-handgun-component-bullet': ('bonded', 'All utilize our electrochemical bonding process', None, None),
    'gold-dot-short-barrel-personal-protection-bullet': ('bonded', 'All utilize our electrochemical bonding process', None, None),
    'deepcurl-handgun-hunting': ('bonded', 'electrochemically bonds the DeepCurl jacket to the lead core', None, None),
    'hot-cor-rifle-bullet': ('cup-and-core', 'Molten lead is poured into the jacket', None, None),
    'tmj-handgun-bullet': ('FMJ', 'take full metal jacket bullets to their highest level of evolution with the Total Metal Jacket', None, None),
    'tmj-rifle-bullet': ('FMJ', 'TMJ rifle bullets totally encapsulate the lead core', None, None),
    'lead-handgun-bullet': ('lead', 'Speer cold-formed lead bullets', None, None),
    'copper-plated-round-nose-cprn': ('plated', 'Copper plating encapsulates the lead core', None, None),
    'copper-plated-flat-nose-cpfn': ('plated', 'Copper plating encapsulates the lead core', None, None),
}


def speer_records(log):
    rows = speer_catalog_rows(log)
    cat_ws = ws(open(L_SPEER_CATALOG_TXT, encoding='utf-8').read())
    m = re.search(r'href="([^"]*SP160_Speer2026_Catalog_web\.pdf)"', open(L_SPEER_CATALOG_PAGE, encoding='utf-8').read())
    cat_url = SPEER + htmlmod.unescape(m.group(1))
    docs = [{'url': cat_url, 'localPath': L_SPEER_CATALOG, 'title': 'Speer 2026 Catalog (SP160_Speer2026_Catalog_web.pdf)', 'date': '2025-12-18 (PDF CreationDate)'}]
    rules = {}
    for slug, (con, q, tip, tq) in SPEER_LINE_RULES.items():
        okc = ws(q) in cat_ws
        okt = tq is None or ws(tq) in cat_ws
        if not okc:
            log.append(f'Speer rule quote not found in catalog, construction not set for {slug}: {q}')
        rules[slug] = (con if okc else None, q if okc else None, tip if (tip and okt) else None, tq if okt else None)
    # web product pages
    pages = []
    for lu in speer_line_urls():
        lp = speer_list_path(lu)
        if not os.path.exists(lp):
            log.append(f'Speer line page missing: {lu}')
            continue
        docs.append({'url': lu, 'localPath': lp, 'title': 'Speer bullet line listing', 'date': None})
        for rel in speer_product_links(open(lp, encoding='utf-8').read()):
            pages.append((lu.rstrip('/').split('/')[-1], rel))
    seen_pages = set()
    line_names = {}
    recs = []
    used_parts = set()
    for slug, rel in sorted(set(pages)):
        if rel in seen_pages:
            continue
        seen_pages.add(rel)
        p = speer_page_path(rel)
        url = SPEER + rel
        if not os.path.exists(p):
            log.append(f'Speer product page missing: {url}')
            continue
        t = open(p, encoding='utf-8').read()
        pg = speer_page(t)
        docs.append({'url': url, 'localPath': p, 'title': f'Speer product page: {pg["name"]}', 'date': None})
        sp = dict(pg['specs'])
        if len(pg['breadcrumb']) >= 3:
            line_names.setdefault(slug, pg['breadcrumb'][-1] if pg['breadcrumb'][-1] != pg['name'] else pg['breadcrumb'][-2])
        part = pg['part']
        if not part:
            m2 = re.search(r'/(?:\d+-)?([0-9A-Za-z]+)\.html$', rel)
            log.append(f'Speer page without printed Part #: {url}')
        notes, conflicts = [], []
        w_web, d_web = num(sp.get('Grain Weight')), num(sp.get('Diameter In'))
        bc_web, sd_web, len_web = num(sp.get('Ballistic Coefficient')), num(sp.get('Sectional Density')), num(sp.get('Bullet Length In'))
        g7_web = None
        for k, v in sp.items():
            if re.search(r'G7', k, re.I):
                g7_web = num(v)
            if re.search(r'G1', k, re.I) and bc_web is None:
                bc_web = num(v)
        unknown = [k for k in sp if k not in ('Caliber', 'Grain Weight', 'Bullet Style', 'Ballistic Coefficient', 'Bullet Length In',
                                              'Sectional Density', 'Diameter In', 'Diameter Mm', 'Package Quantity', 'Usage')]
        if unknown:
            notes.append('other spec rows: ' + '; '.join(f'{k}: {sp[k]}' for k in unknown))
        row = rows.get(part) if part else None
        if row:
            used_parts.add(part)
        # name claims (".308, 180 Grain")
        nm = re.search(r',\s*\.?(\d{3}),\s*(\d+)\s*Grain', pg['name'] or '')
        vals = {}

        def pick(field, web, cat, cat_label, extra=None):
            cands = [(web, f'{url} (Specs table)')]
            if cat is not None:
                cands.append((cat, f'{cat_url} (p.{row["page"]}, {row["table"]}, Part No. {part}, "{cat_label}")'))
            if extra:
                cands.append(extra)
            present = [(v, s) for v, s in cands if v is not None]
            if len({round(v, 6) for v, _ in present}) > 1:
                conflicts.append({'field': field, 'values': [{'value': v, 'source': s} for v, s in present]})
                notes.append(f'{field}: sources disagree ({", ".join(f"{v:g}" for v, _ in present)}); left null')
                return None
            return present[0][0] if present else None

        vals['weightGr'] = pick('weightGr', w_web, row['wt'] if row else None, 'Weight',
                                (float(nm.group(2)), f'{url} (product name "{pg["name"]}")') if nm else None)
        vals['diameterIn'] = pick('diameterIn', d_web, row['dia'] if row else None, 'Diameter')
        vals['bcG1'] = pick('bcG1', bc_web, row['g1'] if row else None, 'G1 BC' if row and row['vel'] else 'BC')
        vals['bcG7'] = pick('bcG7', g7_web, row['g7'] if row else None, 'G7 BC')
        vals['sd'] = pick('sectionalDensity', sd_web, row['sd'] if row else None, 'SD')
        vals['lengthIn'] = len_web
        if row and row['diaRaw'] != f'{row["dia"]:.3f}':
            notes.append(f'catalog prints diameter as "{row["diaRaw"]}" (read as {row["dia"]:.3f})')
        if vals['bcG1'] is not None and vals['bcG7'] is not None and vals['bcG7'] >= vals['bcG1']:
            conflicts.append({'field': 'bcG7', 'values': [{'value': vals['bcG1'], 'source': 'G1 as printed'}, {'value': vals['bcG7'], 'source': 'G7 as printed'}]})
            notes.append(f'printed G7 BC {vals["bcG7"]} >= G1 BC {vals["bcG1"]} (implausible, probably transposed); both left null')
            vals['bcG1'] = vals['bcG7'] = None
        if row is None:
            notes.append('Part # not found in the 2026 catalog tables (web page only)')
        bcn = None
        if row and row['vel']:
            bcn = f'Catalog prints G1/G7 BC for velocity {row["vel"]} ft/s'
        elif bc_web is not None or (row and row['g1'] is not None):
            bcn = 'Printed as "Ballistic Coefficient"/"BC" without naming the drag model (stored as G1)'
        con, cq, tip, tq = rules.get(slug, (None, None, None, None))
        if cq:
            notes.append(f'construction per catalog wording: "{cq}"')
        if tq:
            notes.append(f'tip per catalog wording: "{tq}"')
        if pg['overview']:
            notes.append(f'Product Overview: {pg["overview"]}')
        if vals['sd'] is not None:
            notes.append(f'Printed sectional density {vals["sd"]:.3f}')
        pq = sp.get('Package Quantity')
        if pq:
            notes.append(f'Package quantity {pq}' + (f' (catalog box count {row["box"]:g})' if row and row['box'] is not None and num(pq) != row['box'] else ''))
        if row and row['new']:
            notes.append('marked NEW in the 2026 catalog')
        ev = [f'speer.com product page: {pg["name"]} | Part # {part} | ' + '; '.join(f'{k}: {v}' for k, v in pg['specs'])]
        srcs = [src(url)]
        if row:
            ev.append(f'Speer 2026 catalog p.{row["page"]} {row["table"]}: {row["line"]}')
            srcs.append(src(cat_url, page=row['page']))
        recs.append({
            'id': f'speer-{kebab(part or rel)}',
            'manufacturer': 'Speer',
            'line': None, '_slug': slug,
            'name': pg['name'],
            'sku': part,
            'caliberLabel': row['caliber'] if row else sp.get('Caliber'),
            'diameterIn': vals['diameterIn'],
            'weightGr': vals['weightGr'],
            'lengthIn': vals['lengthIn'],
            'boatTailLengthIn': None,
            'baseToOgiveIn': None,
            'bcG1': vals['bcG1'],
            'bcG7': vals['bcG7'],
            'bcNotes': bcn,
            'profile': sp.get('Bullet Style') or (row['type'] if row else None),
            'tip': tip,
            'construction': con,
            'recommendedTwist': None,
            'status': 'current',
            'sources': srcs,
            'evidence': ws(' || '.join(ev)),
            'notes': None,
            'conflicts': conflicts,
            '_notes': notes,
        })
    # catalog rows with no product page
    for part, row in rows.items():
        if part in used_parts:
            continue
        slug = SPEER_TABLE_LINE.get(row['table'])
        if row['table'] == 'COPPER PLATED BULLETS':
            slug = 'copper-plated-round-nose-cprn' if ' RN' in row['type'] else 'copper-plated-flat-nose-cpfn' if ' FN' in row['type'] else None
        con, cq, tip, tq = rules.get(slug, (None, None, None, None))
        notes = ['catalog row only (no product page found on speer.com bullet line listings); no bullet length published']
        conflicts = []
        g1, g7 = row['g1'], row['g7']
        if g1 is not None and g7 is not None and g7 >= g1:
            conflicts.append({'field': 'bcG7', 'values': [{'value': g1, 'source': f'{cat_url} p.{row["page"]} "G1 BC"'}, {'value': g7, 'source': f'{cat_url} p.{row["page"]} "G7 BC"'}]})
            notes.append(f'printed G7 BC {g7} >= G1 BC {g1} (implausible, probably transposed); both left null')
            g1 = g7 = None
        if row['diaRaw'] != f'{row["dia"]:.3f}':
            notes.append(f'catalog prints diameter as "{row["diaRaw"]}" (read as {row["dia"]:.3f})')
        if cq:
            notes.append(f'construction per catalog wording: "{cq}"')
        if tq:
            notes.append(f'tip per catalog wording: "{tq}"')
        if row['sd'] is not None:
            notes.append(f'Printed sectional density {row["sd"]:.3f}')
        if row['box'] is not None:
            notes.append(f'Box count {row["box"]:g}')
        if row['new']:
            notes.append('marked NEW in the 2026 catalog')
        recs.append({
            'id': f'speer-{kebab(part)}',
            'manufacturer': 'Speer',
            'line': None, '_slug': slug, '_table': row['table'],
            'name': ws(f'{row["caliber"]} {row["wt"]:g} gr {row["type"]}'),
            'sku': part,
            'caliberLabel': row['caliber'],
            'diameterIn': row['dia'],
            'weightGr': row['wt'],
            'lengthIn': None,
            'boatTailLengthIn': None,
            'baseToOgiveIn': None,
            'bcG1': g1,
            'bcG7': g7,
            'bcNotes': (f'Catalog prints G1/G7 BC for velocity {row["vel"]} ft/s' if row['vel'] else
                        'Printed as "BC" without naming the drag model (stored as G1)'),
            'profile': row['type'],
            'tip': tip,
            'construction': con,
            'recommendedTwist': None,
            'status': 'current',
            'sources': [src(cat_url, page=row['page'])],
            'evidence': ws(f'Speer 2026 catalog p.{row["page"]} {row["table"]}: {row["line"]}'),
            'notes': None,
            'conflicts': conflicts,
            '_notes': notes,
        })
    for r in recs:
        tbl = r.pop('_table', None)
        slug = r.pop('_slug', None)
        r['line'] = line_names.get(slug) or (ws(tbl.replace('®', '')).title() if tbl else None)
    return recs, docs


# --------------------------------------------------------------------------- output
def finalize(r):
    notes = r.pop('_notes', [])
    for k in [k for k in r if k.startswith('_')]:
        r.pop(k)
    if r['conflicts']:
        notes.append('CONFLICTS: ' + '; '.join(
            f'{c["field"]}: ' + ' vs '.join(f'{v["value"]} [{v["source"]}]' for v in c['values']) for c in r['conflicts']))
    r['notes'] = ' | '.join(n for n in notes if n) or None
    if not r['conflicts']:
        r.pop('conflicts')
    return r


def main():
    log = []
    b, bdocs = barnes_records(log)
    s, sdocs = speer_records(log)
    recs = [finalize(r) for r in b + s]
    ids = {}
    for r in recs:
        ids.setdefault(r['id'], []).append(r)
    for i, rs in ids.items():
        if len(rs) > 1:
            log.append(f'duplicate id {i} ({len(rs)} records): suffixing')
            for n, r in enumerate(rs[1:], start=2):
                r['id'] = f'{i}-{n}'
    docs = [
        {'url': BARNES_ROBOTS, 'localPath': L_BARNES_ROBOTS, 'title': 'barnesbullets.com robots.txt', 'date': None},
        {'url': BARNES_SITEMAP, 'localPath': L_BARNES_SITEMAP, 'title': 'Barnes product sitemap', 'date': None},
        {'url': BARNES_CATALOG_PAGE, 'localPath': L_BARNES_CATALOG_PAGE, 'title': 'Barnes catalog page', 'date': None},
        {'url': BARNES_POSTER, 'localPath': L_BARNES_POSTER, 'title': 'Barnes 2026 bullets/ammunition poster-catalog (WebP raster; downloaded, not parsed)', 'date': '2026'},
        {'url': SPEER_ROBOTS, 'localPath': L_SPEER_ROBOTS, 'title': 'speer.com robots.txt', 'date': None},
        {'url': SPEER_SITEMAP, 'localPath': L_SPEER_SITEMAP, 'title': 'Speer sitemap', 'date': None},
        {'url': SPEER_CATALOG_PAGE, 'localPath': L_SPEER_CATALOG_PAGE, 'title': 'Speer catalog page', 'date': None},
    ] + bdocs + sdocs
    out = {
        'meta': {
            'documents': docs,
            'notes': (
                'Barnes: one record per Item # from the public product pages; values from the page\'s embedded spec sheet '
                '("specsJson", shown in the Specs tab) cross-checked against the page\'s "customFields" copy and the product name; '
                'any disagreement -> conflicts and the field is null. Evidence quotes the decoded specsJson block of the item verbatim '
                '(whitespace collapsed) plus the customFields values. Barnes "Minimum Twist Rate" is given in inches per turn. '
                'Construction mapped from the Barnes "Bullet Material" category: 100% Copper -> monolithic-copper, Solid Brass -> '
                'monolithic-brass, Jacketed Lead Core -> cup-and-core, Jacketed Non-Lead -> null. The Barnes 2026 catalog exists only '
                'as a raster poster (no bullet lengths) and was not parsed. '
                'Speer: product pages (only source with "Bullet Length In") cross-checked with the Speer 2026 catalog PDF tables '
                '(pages 16-25) by Part #; disagreements -> conflicts and null. Catalog rows without a product page are kept as '
                'catalog-only records (no length). Speer "BC" columns do not name the drag model except the Impact table (G1/G7); '
                'they are stored as bcG1 with a bcNotes remark. Lead round balls, plastic training bullets and shot capsules are '
                'excluded. No value was typed in or estimated; boatTailLengthIn and baseToOgiveIn are not published by either maker.'),
            'log': log,
            'counts': {'barnes': len(b), 'speer': len(s)},
        },
        'bullets': recs,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f'wrote {OUT}: {len(recs)} bullets (Barnes {len(b)}, Speer {len(s)})')
    for l in log:
        print('LOG', l)


def num_forms(v):
    f = set()
    f.add(f'{v:g}')
    for d in (3, 4, 1, 2):
        x = f'{v:.{d}f}'
        f.add(x)
        if x.startswith('0.'):
            f.add(x[1:])
    return f


def check():
    data = json.load(open(OUT, encoding='utf-8'))
    recs = data['bullets']
    print('records:', len(recs))
    bad = 0
    for r in recs:
        ev = re.sub(r'(\d)\.\s(\d)', r'\1.\2', r['evidence'])   # catalog typesetting "0. 321"
        for fld in ('diameterIn', 'weightGr', 'lengthIn', 'bcG1', 'bcG7'):
            v = r.get(fld)
            if v is None:
                continue
            if not any(re.search(r'(?<![\d.])' + re.escape(x) + r'(?!\d)', ev) for x in num_forms(v)):
                bad += 1
                print('NOT IN EVIDENCE', r['id'], fld, v)
        if not r['sources'] or not ev:
            bad += 1
            print('NO SOURCE/EVIDENCE', r['id'])
        d, w, L = r.get('diameterIn'), r.get('weightGr'), r.get('lengthIn')
        if L is not None and d is not None and not (d < L < 3.0):
            print('LENGTH OUT OF RANGE', r['id'], d, L)
        if r.get('bcG1') is not None and r.get('bcG7') is not None and r['bcG7'] >= r['bcG1']:
            print('G7>=G1', r['id'])
    import collections
    c = collections.Counter((r['manufacturer'], r['lengthIn'] is not None) for r in recs)
    print('with length:', dict(c))
    print('with conflicts:', sum(1 for r in recs if r.get('conflicts')))
    print('null weight/diameter:', [r['id'] for r in recs if r['weightGr'] is None or r['diameterIn'] is None])
    random.seed(7)
    for r in random.sample(recs, 5):
        print('---', r['id'], r['name'], '| d', r['diameterIn'], 'w', r['weightGr'], 'L', r['lengthIn'], 'G1', r['bcG1'], 'G7', r['bcG7'],
              '| twist', r['recommendedTwist'], '|', r['construction'])
        print('   evidence:', r['evidence'][:900])
    print('evidence mismatches:', bad)
    return bad


if __name__ == '__main__':
    if '--download' in sys.argv:
        download()
    elif '--check' in sys.argv:
        sys.exit(1 if check() else 0)
    else:
        main()
