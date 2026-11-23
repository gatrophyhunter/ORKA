#!/usr/bin/env python3
"""Extract the smokeless-powder catalog for the Hodgdon family (Hodgdon, IMR, Winchester) and Alliant,
plus the publishers' relative burn-rate charts.

Sources (public, fetched with plain curl and its default user agent):
  * hodgdonpowderco.com (robots.txt: Crawl-delay 10, no Disallow) -> we sleep >= 10.5 s between requests.
      - /reference-data/      -> "2026 Smokeless Relative Burn Rate Chart" (PDF, text layer)
                                 + archived "Hodgdon Extreme series" web-page printout (PDF, text layer, 2012)
      - /safety-data-sheets/  -> Hodgdon / IMR / Winchester SDS PDFs. These are SCANNED (no text layer); we
                                 OCR them (pdftoppm 300 dpi + tesseract --psm 6) and use ONLY the cover page
                                 (document title such as "Spherical Powders" / "Double Base Powders" and the
                                 list of product names covered). Numeric composition data in these scans is
                                 NOT used (OCR digits are not trustworthy and the tables use internal codes).
      - brand pages /hodgdon/ /imr/ /winchester/ (featured-product one-liners, family claims)
    Product pages live on shop.hodgdon.com, which is NOT reachable from this sandbox (proxy 403).
  * www.alliantpowder.com (robots.txt: no rules) -> we sleep >= 2 s between requests.
      - /products/{rifle,shotshell,handgun,muzzleloader}.aspx and every linked /products/powder/*.aspx page
      - /resources/sds.aspx -> SDS PDFs (text layer)
      - /resources/catalog.aspx -> 2023 Reloader's Guide PDF (p. 9: powders "in the order of decreasing
        burning rates" with principal/secondary use; p. 10: powder information)

Usage:
  python3 -I powders-hodgdon-alliant.py --download   # fetch any missing source documents (+ OCR cache)
  python3 -I powders-hodgdon-alliant.py              # parse cached documents and write JSON (+ self-check)

Everything is parsed with code from HTML, `pdftotext -layout` output and OCR text; nothing is typed in.
"""
import hashlib
import html as htmlmod
import json
import os
import random
import re
import subprocess
import sys
import time

SRC = '/tmp/claude-0/-home-user-ORKA/29ce603d-ccc3-55ef-b8fe-c585397ac7c1/scratchpad/sources/powders-hodgdon-alliant'
OUT = '/home/user/ORKA/research/raw2/powders-hodgdon-alliant.json'
RETRIEVED = '2026-11-23'

HODG = 'https://hodgdonpowderco.com'
ALL = 'https://www.alliantpowder.com'
DELAY = {'hodgdonpowderco.com': 10.5, 'www.alliantpowder.com': 2.0}

_last_fetch = {}


def fetch(url, local):
    """Download url to local with plain curl (default UA) unless cached. Returns True if file present."""
    if os.path.exists(local) and os.path.getsize(local) > 0:
        return True
    host = url.split('/')[2]
    wait = _last_fetch.get(host, 0) + DELAY.get(host, 2.0) - time.time()
    if wait > 0:
        time.sleep(wait)
    os.makedirs(os.path.dirname(local), exist_ok=True)
    tmp = local + '.part'
    r = subprocess.run(['curl', '-sS', '-L', '-m', '300', '-o', tmp, '-w', '%{http_code}', url],
                       capture_output=True, text=True)
    _last_fetch[host] = time.time()
    code = r.stdout.strip()
    if code == '200' and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
        os.replace(tmp, local)
        print(f'  fetched {url} -> {local}', file=sys.stderr)
        return True
    print(f'  FAILED {url}: http={code} {r.stderr.strip()}', file=sys.stderr)
    if os.path.exists(tmp):
        os.remove(tmp)
    return False


def pdftext(local):
    txt = local[:-4] + '.txt'
    if not os.path.exists(txt) or os.path.getmtime(txt) < os.path.getmtime(local):
        subprocess.run(['pdftotext', '-layout', local, txt], check=True, stderr=subprocess.DEVNULL)
    with open(txt, encoding='utf-8', errors='replace') as f:
        return f.read()


def pdfpages(local):
    """Return list of page texts (index 0 = page 1)."""
    return pdftext(local).split('\f')


def read(local):
    with open(local, encoding='utf-8', errors='replace') as f:
        return f.read()


def ws(s):
    return re.sub(r'\s+', ' ', s).strip()


def kebab(s):
    s = s.lower().replace('&', ' and ')
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')


def strip_marks(s):
    return ws(re.sub(r'[®™©]', ' ', s))


def normkey(s):
    """Matching key: uppercase alphanumerics only; marks removed; 'RELODER TS' -> 'RELODER'."""
    s = strip_marks(s).upper()
    s = re.sub(r'\bRELODER\s+TS\s*', 'RELODER ', s)
    return re.sub(r'[^A-Z0-9]', '', s)


def html_text(fragment):
    t = re.sub(r'(?s)<!--.*?-->', '', fragment)
    t = re.sub(r'(?s)<script.*?</script>|<style.*?</style>', '', t)
    t = re.sub(r'<br\s*/?>', '\n', t)
    t = re.sub(r'</(p|div|h\d|li|tr|td|span|a|ul)>', '\n', t)
    t = re.sub(r'<[^>]+>', '', t)
    t = htmlmod.unescape(t)
    lines = [ws(l) for l in t.split('\n')]
    return [l for l in lines if l]


# ---------------------------------------------------------------- document lists
HODG_PAGES = {
    'reference-data': f'{HODG}/reference-data/',
    'safety-data-sheets': f'{HODG}/safety-data-sheets/',
    'hodgdon': f'{HODG}/hodgdon/',
    'imr': f'{HODG}/imr/',
    'winchester': f'{HODG}/winchester/',
    'reloading-manuals-library': f'{HODG}/reloading-manuals-library/',
}


def annual_manual_url():
    """Latest Hodgdon Annual Manual PDF (AMnn) published on the reloading-manuals-library page."""
    links = hodg_links(read(hodg_page_local('reloading-manuals-library')), r'/AM\d\d[^/]*\.pdf$')
    return max(links, key=lambda u: int(re.search(r'/AM(\d\d)', u).group(1)))


def hodg_page_local(key):
    return os.path.join(SRC, 'hodgdon', f'page-{key}.html')


# SDS PDFs from https://hodgdonpowderco.com/safety-data-sheets/ that cover Hodgdon / IMR / Winchester smokeless powders.
# (the OEM St. Marks SDS covers OEM-only propellants, not canister powders, and is not used)
HODG_SDS_MATCH = re.compile(r'(hodgdon|imr|winchester|clays|trail-boss|bm2|extruded-rifle|spherical|700x)', re.I)
HODG_SDS_EXCLUDE = re.compile(r'(pyrodex|triple-seven|white-hots|blackhorn|safety_fuse|accurate|ramshot)', re.I)


def hodg_links(page_html, pattern):
    out = []
    for m in re.finditer(r'href="([^"]+)"', page_html):
        u = htmlmod.unescape(m.group(1))
        if re.search(pattern, u, re.I):
            if u.startswith('/'):
                u = HODG + u
            if u not in out:
                out.append(u)
    return out


def local_for(url, sub):
    return os.path.join(SRC, sub, url.rstrip('/').split('/')[-1])


ALLIANT_CATS = ['rifle', 'shotshell', 'handgun', 'muzzleloader']
ALLIANT_RES = {'sds': f'{ALL}/resources/sds.aspx', 'catalog': f'{ALL}/resources/catalog.aspx'}


def alliant_cat_local(c):
    return os.path.join(SRC, 'alliant', f'products-{c}.html')


def alliant_res_local(k):
    return os.path.join(SRC, 'alliant', f'resources-{k}.html')


def alliant_product_urls():
    urls = []
    for c in ALLIANT_CATS:
        p = alliant_cat_local(c)
        if not os.path.exists(p):
            continue
        for m in re.finditer(r'href="(?:\.\./|/products/)?(?:products/)?(powder/[^"]+\.aspx)"', read(p)):
            u = f'{ALL}/products/{m.group(1)}'
            if u not in urls:
                urls.append(u)
    return urls


def alliant_pdf_urls(res_key, pattern):
    p = alliant_res_local(res_key)
    out = []
    if not os.path.exists(p):
        return out
    for m in re.finditer(r'href="([^"]+\.pdf)"', read(p), re.I):
        u = m.group(1)
        if not re.search(pattern, u, re.I):
            continue
        if u.startswith('../'):
            u = f'{ALL}/' + u[3:]
        elif u.startswith('/'):
            u = ALL + u
        if u not in out:
            out.append(u)
    return out


def alliant_all_sds_urls():
    """SDS PDFs listed on /resources/sds.aspx plus SDS PDFs linked (not commented out) from product pages."""
    out = alliant_pdf_urls('sds', r'/sds/')
    for u in alliant_product_urls():
        local = local_for(u, 'alliant/product')
        if not os.path.exists(local):
            continue
        h = re.sub(r'(?s)<!--.*?-->', '', read(local))
        for m in re.finditer(r'href="([^"]*/downloads/sds/[^"]+\.pdf)"', h):
            x = m.group(1)
            x = ALL + '/' + re.sub(r'^(\.\./)+|^/', '', x)
            if x not in out:
                out.append(x)
    return out


def hodg_sds_urls():
    sds = read(hodg_page_local('safety-data-sheets'))
    out = []
    for u in hodg_links(sds, r'\.pdf$'):
        name = u.split('/')[-1]
        if HODG_SDS_MATCH.search(name) and not HODG_SDS_EXCLUDE.search(name):
            out.append(u)
    return out


def ocr_page(pdf, page):
    """OCR one page of a scanned PDF (cached). 300 dpi, tesseract --psm 6."""
    base = os.path.basename(pdf)[:-4]
    out = os.path.join(SRC, 'ocr', f'{base}-p{page}.txt')
    if not (os.path.exists(out) and os.path.getsize(out) > 0):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        stem = os.path.join(SRC, 'ocr', f'tmp-{base}')
        subprocess.run(['pdftoppm', '-r', '300', '-f', str(page), '-l', str(page), '-png', pdf, stem], check=True)
        imgs = sorted(p for p in os.listdir(os.path.dirname(out)) if p.startswith(f'tmp-{base}') and p.endswith('.png'))
        img = os.path.join(os.path.dirname(out), imgs[0])
        r = subprocess.run(['tesseract', img, 'stdout', '--psm', '6'], capture_output=True, text=True, check=True)
        with open(out, 'w', encoding='utf-8') as f:
            f.write(r.stdout)
        for p in imgs:
            os.remove(os.path.join(os.path.dirname(out), p))
    return read(out)


def download():
    for k, u in HODG_PAGES.items():
        fetch(u, hodg_page_local(k))
    ref = read(hodg_page_local('reference-data'))
    for u in hodg_links(ref, r'Burn-Rate-Chart.*\.pdf$|temperature-sensitivity.*\.pdf$'):
        fetch(u, local_for(u, 'hodgdon/pdf'))
    fetch(annual_manual_url(), local_for(annual_manual_url(), 'hodgdon/manual'))
    for u in hodg_sds_urls():
        if fetch(u, local_for(u, 'hodgdon/sds')):
            ocr_page(local_for(u, 'hodgdon/sds'), 1)
    for c in ALLIANT_CATS:
        fetch(f'{ALL}/products/{c}.aspx', alliant_cat_local(c))
    for k, u in ALLIANT_RES.items():
        fetch(u, alliant_res_local(k))
    for u in alliant_product_urls():
        fetch(u, local_for(u, 'alliant/product'))
    for u in alliant_all_sds_urls():
        fetch(u, local_for(u, 'alliant/sds'))
    for u in alliant_pdf_urls('catalog', r'catalog/'):
        fetch(u, local_for(u, 'alliant/pdf'))


# ---------------------------------------------------------------- parsers
DOCS = []  # meta.documents
AM_UNMATCHED = []  # Annual Manual description paragraphs that matched no record


def add_doc(url, local, title, date):
    if not any(d['url'] == url for d in DOCS):
        DOCS.append({'url': url, 'localPath': local, 'title': title, 'date': date})


def src(url, typ='manufacturer', page=None):
    return {'url': url, 'type': typ, 'page': page, 'retrieved': RETRIEVED}


CHART_BRANDS = ['VIHTAVUORI', 'WINCHESTER', 'ACCURATE', 'ALLIANT', 'HODGDON', 'RAMSHOT', 'NORMA', 'IMR']


def parse_numbered_chart(text):
    """Parse a multi-column 'N NAME' burn-rate list. Returns (title_line, entries list, raw lines)."""
    lines = text.split('\n')
    title_line = next(l for l in lines if 'RELATIVE BURN RATES' in l)
    entries = {}
    raw_line = {}
    for l in lines[lines.index(title_line) + 1:]:
        for m in re.finditer(r'(?:(?<=\s)|^)(\d{1,3}) (\S.*?)(?=\s{2,}\d{1,3} \S|\s*$)', l):
            pos = int(m.group(1))
            name = m.group(2).strip()
            if pos in entries:
                raise SystemExit(f'duplicate chart position {pos}')
            entries[pos] = name
            raw_line[pos] = ws(l)
    n = max(entries)
    assert sorted(entries) == list(range(1, n + 1)), 'chart positions not contiguous'
    out = []
    for pos in range(1, n + 1):
        printed = entries[pos]
        up = printed.upper()
        brand = next((b for b in CHART_BRANDS if up.startswith(b + ' ')), None)
        rest = printed[len(brand) + 1:].strip() if brand else printed
        out.append({'pos': pos, 'printed': printed, 'brand': brand, 'rest': rest, 'line': raw_line[pos]})
    first = raw_line[1]
    return title_line, out, first, raw_line[n]


def parse_hodgdon_chart():
    url = [u for u in hodg_links(read(hodg_page_local('reference-data')), r'Burn-Rate-Chart.*\.pdf$')][0]
    local = local_for(url, 'hodgdon/pdf')
    pages = pdfpages(local)
    title_line, out, first, last = parse_numbered_chart(pages[0])
    edition = re.search(r'\((rev\.[^)]*)\)', title_line).group(1)
    n = len(out)
    chart = {
        'publisher': 'Hodgdon Powder Company',
        'edition': f'2026 Smokeless Relative Burn Rate Chart ({edition})',
        'chartId': 'hodgdon-2026',
        'url': url,
        'orderedNames': [e['printed'] for e in out],
        'count': n,
        'evidence': ws(title_line) + ' | ' + first + ' | ... | ' + last,
        'sources': [src(url, 'manufacturer', 1)],
        'notes': 'Three-column, numbered list "FROM FASTEST TO SLOWEST"; covers Hodgdon, IMR, Winchester, Accurate, '
                 'Ramshot, Alliant, Vihtavuori and Norma powders. Names kept exactly as printed (brand prefix included). '
                 'Entry "HODGDON H4831 & H4831SC" is a single position on the chart.',
    }
    add_doc(url, local, 'Hodgdon 2026 Smokeless Relative Burn Rate Chart', edition + ' (PDF created 2026-08-17)')
    return chart, out, url


def am_pages():
    url = annual_manual_url()
    local = local_for(url, 'hodgdon/manual')
    return url, local, pdfpages(local)


def am_title(url):
    yy = re.search(r'/AM(\d\d)', url).group(1)
    return f'Hodgdon 20{yy} Annual Manual', f'20{yy}'


def parse_am_chart():
    url, local, pages = am_pages()
    pi = next(i for i, p in enumerate(pages) if 'RELATIVE BURN RATES FROM FASTEST TO SLOWEST' in p)
    title_line, out, first, last = parse_numbered_chart(pages[pi])
    title, year = am_title(url)
    chart = {
        'publisher': 'Hodgdon Powder Company',
        'edition': f'{title}, "Relative Burn Rates from Fastest to Slowest" (PDF page {pi + 1})',
        'chartId': f'hodgdon-{year}-annual-manual',
        'url': url,
        'orderedNames': [e['printed'] for e in out],
        'count': len(out),
        'evidence': ws(title_line) + ' | ' + first + ' | ... | ' + last,
        'sources': [src(url, 'manufacturer', pi + 1)],
        'notes': 'Four-column numbered list in the Annual Manual; earlier edition of the Hodgdon chart. Names kept '
                 'exactly as printed (mixed case in this edition).',
    }
    add_doc(url, local, title + ' (full PDF published on hodgdonpowderco.com/reloading-manuals-library/)',
            'PDF created 2026-02-26; Last-Modified 2026-04-16')
    return chart, out, url, pi + 1


AM_BRANDS = {'Hodgdon': 'Hodgdon', 'IMR': 'IMR', 'Winchester': 'Winchester', 'Accurate': None, 'Ramshot': None}


def parse_am_usage():
    """'Powder Usage' matrix: SHOTGUN / PISTOL / RIFLE sections, rows grouped by brand."""
    url, local, pages = am_pages()
    start = next(i for i, p in enumerate(pages) if re.search(r'^\s*Powder Usage\s*$', p, re.M))
    rows = []
    section = None
    cols = None
    header = None
    brand = None
    for pi in range(start, start + 3):
        for l in pages[pi].split('\n'):
            m = re.match(r'^\s*(SHOTGUN|PISTOL|RIFLE)\b(.*)$', l)
            if m:
                section = m.group(1)
                header = ws(l)
                cols = None
                if section in ('PISTOL', 'RIFLE'):
                    cols = [(mm.group(0), (mm.start() + mm.end() - 1) / 2)
                            for mm in re.finditer(r'[A-Z0-9]+(?: [A-Z]+)?', l[len(m.group(1)) + l.index(m.group(1)):])]
                    off = len(m.group(1)) + l.index(m.group(1))
                    cols = [(c, x + off) for c, x in cols]
                continue
            bm = re.match(r'^\s*(Hodgdon|IMR|Winchester|Accurate|Ramshot) Smokeless Propellant\s*$', l)
            if bm:
                brand = AM_BRANDS[bm.group(1)]
                continue
            rm = re.match(r'^\s*(\S.*?)\s{2,}•', l)
            if rm and section and brand:
                uses = []
                bad = False
                if cols:
                    for b in re.finditer('•', l):
                        c, x = min(cols, key=lambda cx: abs(cx[1] - b.start()))
                        if abs(x - b.start()) > 6:
                            bad = True
                        uses.append(c)
                rows.append({'brand': brand, 'name': rm.group(1).strip(), 'section': section,
                             'uses': (sorted(set(uses), key=uses.index) if cols and not bad else None),
                             'line': ws(l), 'header': header, 'page': pi + 1})
    return rows, url, local


def dehyphen(t):
    """Join words split by end-of-line hyphenation ('dou- ble-base' -> 'double-base')."""
    return re.sub(r'(\w)- (?=[a-z])', r'\1', t)


def parse_am_descriptions():
    """Per-powder description paragraphs, two-column layout, Hodgdon/IMR/Winchester sections."""
    url, local, pages = am_pages()
    first = next(i for i, p in enumerate(pages) if re.search(r'^HODGDON Smokeless Pistol and Shotgun Powders', p, re.M))
    paras = []
    brand = None
    section = None
    for pi in range(first, len(pages)):
        lines = pages[pi].split('\n')
        # right-column start: most common start index of a text run that follows >=3 spaces beyond column 50
        starts = {}
        for l in lines:
            for m in re.finditer(r'(?<=\S)\s{3,}(\S)', l):
                if m.start(1) > 50:
                    starts[m.start(1)] = starts.get(m.start(1), 0) + 1
            m = re.match(r'^(\s{50,})(\S)', l)
            if m:
                starts[m.start(2)] = starts.get(m.start(2), 0) + 1
        rc = None
        if starts:
            best = max(starts.values())
            rc = min(k for k, v in starts.items() if v >= max(2, best // 2)) if best >= 2 else None
        colbuf = {'L': [], 'R': []}

        def flush(c):
            if colbuf[c] and brand:
                paras.append({'brand': brand, 'section': section, 'page': pi + 1, 'lines': list(colbuf[c])})
            colbuf[c] = []
        stop = False
        for l in lines:
            hm = re.match(r'^(HODGDON|IMR|WINCHESTER|ACCURATE|RAMSHOT) Smokeless (.*?Powders)', l)
            if hm:
                flush('L'); flush('R')
                if hm.group(1) in ('ACCURATE', 'RAMSHOT'):
                    stop = True
                    break
                brand = {'HODGDON': 'Hodgdon', 'IMR': 'IMR', 'WINCHESTER': 'Winchester'}[hm.group(1)]
                section = ws(l.split('»')[0])
                continue
            if re.match(r'^\s*In Order of Approximate Burn', l) or re.search(r'hodgdon\.com\s*\d*\s*$', l):
                flush('L'); flush('R')
                continue
            left = l[:rc] if rc else l
            right = l[rc:] if rc and len(l) > rc else ''
            if left.strip():
                colbuf['L'].append(left.strip())
            else:
                flush('L')
            if right.strip():
                colbuf['R'].append(right.strip())
            else:
                flush('R')
        flush('L'); flush('R')
        if stop:
            break
    for p in paras:
        p['raw'] = ws(' '.join(p['lines']))
        p['text'] = dehyphen(re.sub(r'^»\s*', '', p['raw']))
    return paras, url


def parse_alliant_guide():
    url = alliant_pdf_urls('catalog', r'catalog/')[0]
    local = local_for(url, 'alliant/pdf')
    pages = pdfpages(local)
    pidx = next(i for i, p in enumerate(pages) if 'Smokeless Powders for Reloading' in p)
    page = pages[pidx]
    lines = page.split('\n')
    hdr_i = next(i for i, l in enumerate(lines) if re.match(r'\s*Powder\s+Principal Use', l))
    hdr = lines[hdr_i]
    pcol = hdr.index('Principal')
    scol = hdr.index('Secondary')
    intro = ws(' '.join(lines[next(i for i, l in enumerate(lines) if 'We currently offer' in l):hdr_i]))
    raw_rows = []
    for l in lines[hdr_i + 1:]:
        if re.match(r'\s*1\s*$', l) or 'Black Powder Substitute' in l:
            break
        if not l.strip():
            continue
        namepart = l[:pcol].rstrip()
        if namepart.strip() and len(namepart.strip()) and not re.search(r'\s{2,}\S', l[len(namepart.rstrip()):pcol] if False else ''):
            pass
        m = re.match(r'^\s*(\S.*?)(?:\s{2,}(.*))?$', l)
        lead = len(l) - len(l.lstrip())
        if lead >= pcol - 2:
            raw_rows.append({'name': None, 'text': l, 'raw': ws(l)})
            continue
        name = m.group(1)
        restcol = None
        if len(l.lstrip()) and (lead + len(name)) > pcol:
            # name overflowed into the Principal Use column (e.g. "Power Pro® 2000-MR Medium rifle loads")
            toks = name.split(' ')
            k = max(i for i, t in enumerate(toks) if re.search(r'[0-9®™]', t))
            name, overflow = ' '.join(toks[:k + 1]), ' '.join(toks[k + 1:])
            remainder = (overflow + (('  ' + m.group(2)) if m.group(2) else ''))
            restcol = remainder
        raw_rows.append({'name': name.strip(), 'text': l, 'raw': ws(l), 'overflow': restcol})

    def split_cols(l):
        p = l[pcol - 2:scol - 2].strip() if len(l) > pcol - 2 else ''
        s = l[scol - 2:].strip() if len(l) > scol - 2 else ''
        return p, s

    rows = []
    i = 0
    while i < len(raw_rows):
        r = raw_rows[i]
        if r['name'] is None:
            i += 1
            continue
        if r.get('overflow') is not None:
            parts = re.split(r'\s{2,}', r['overflow'].strip())
            principal = parts[0] if parts else ''
            secondary = parts[1] if len(parts) > 1 else ''
        else:
            principal, secondary = split_cols(r['text'])
        ev = [r['raw']]
        if not principal and not secondary:
            # text wrapped around the name line (row printed above and below the name)
            prev = raw_rows[i - 1] if i > 0 and raw_rows[i - 1]['name'] is None else None
            nxt = raw_rows[i + 1] if i + 1 < len(raw_rows) and raw_rows[i + 1]['name'] is None else None
            ps, ss = [], []
            for c in (prev, nxt):
                if c:
                    a, b = split_cols(c['text'])
                    ps.append(a)
                    ss.append(b)
            principal, secondary = ws(' '.join(ps)), ws(' '.join(ss))
            ev = ([prev['raw']] if prev else []) + ev + ([nxt['raw']] if nxt else [])
            if prev:
                raw_rows[i - 1]['used'] = True
            if nxt:
                raw_rows[i + 1]['used'] = True
        rows.append({'printed': r['name'], 'principal': principal or None, 'secondary': secondary or None,
                     'evidence': ' | '.join(ev), 'page': pidx + 1})
        i += 1
    # attach unused continuation lines to the preceding row
    for j, r in enumerate(raw_rows):
        if r['name'] is None and not r.get('used'):
            raise SystemExit(f'unattached continuation line in Alliant guide table: {r["raw"]}')
    # page 10 powder information
    info = pages[pidx + 1]
    info_par = ws(info[info.index('Smokeless sporting propellants'):info.index('By utilizing')])
    chart = {
        'publisher': 'Alliant Powder',
        'edition': '2023 Alliant Powder Reloader\'s Guide (AP399), "Smokeless Powders for Reloading" table',
        'chartId': 'alliant-2023-guide',
        'url': url,
        'orderedNames': [r['printed'] for r in rows],
        'count': len(rows),
        'evidence': intro + ' | first: ' + rows[0]['evidence'] + ' | last: ' + rows[-1]['evidence'],
        'sources': [src(url, 'manufacturer', pidx + 1)],
        'notes': 'Alliant-only list "in the order of decreasing burning rates" (fastest first). The intro sentence '
                 'says 37 powders; the table as printed lists ' + str(len(rows)) + ' names. Names kept as printed '
                 '(including registered/trademark signs).',
    }
    add_doc(url, local, "Alliant Powder 2023 Reloader's Guide (AP399)", '2023')
    return chart, rows, info_par, url, pidx + 2


def parse_alliant_products():
    prods = []
    for u in alliant_product_urls():
        local = local_for(u, 'alliant/product')
        if not os.path.exists(local):
            continue
        h = read(local)
        m = re.search(r'(?s)<div id="mainContent">(.*?)<div id="sideBar">', h)
        main = m.group(1)
        tm = re.search(r'<title>(.*?)</title>', h)
        title = tm.group(1) if tm else None
        h1 = ws(htmlmod.unescape(re.sub(r'<[^>]+>', '', re.search(r'(?s)<h1>(.*?)</h1>', main).group(1))))
        h2 = ws(htmlmod.unescape(re.sub(r'<[^>]+>', '', re.search(r'(?s)<h2>(.*?)</h2>', main).group(1))))
        h4m = re.search(r'(?s)<h4>(.*?)</h4>', main)
        h4 = ws(htmlmod.unescape(re.sub(r'<[^>]+>', '', h4m.group(1)))) if h4m else None
        disc = bool(re.search(r'<h3[^>]*>\s*Discontinued\s*</h3>', main))
        main_nc = re.sub(r'(?s)<!--.*?-->', '', main)
        info = re.search(r'(?s)<div class="mainInfo">(.*?)<div class="productSpecs">', main_nc)
        paras = [ws(htmlmod.unescape(re.sub(r'<[^>]+>', ' ', p))) for p in re.findall(r'(?s)<p>(.*?)</p>', info.group(1))] if info else []
        bullets = [ws(htmlmod.unescape(re.sub(r'<[^>]+>', ' ', li))) for li in re.findall(r'(?s)<li>(.*?)</li>', info.group(1))] if info else []
        specs_m = re.search(r'(?s)<div class="productSpecs">(.*)', main_nc)
        specs = specs_m.group(1) if specs_m else ''

        def spec(label):
            mm = re.search(r'(?s)<strong>\s*' + label + r':?\s*(?:&nbsp;)?\s*(?:\.)?\s*</strong>(.*?)<br', specs)
            if not mm:
                return None, None
            # handle "Principal Purpose:&nbsp;.</strong>223 ammunition" (dot inside strong)
            raw = re.search(r'(?s)<strong>\s*' + label + r'.*?(?=<br)', specs).group(0)
            val = ws(htmlmod.unescape(re.sub(r'<[^>]+>', ' ', mm.group(1)))).strip()
            if re.search(r'<strong>\s*' + label + r':&nbsp;\.</strong>', specs):
                val = '.' + val
            return (val or None), ws(htmlmod.unescape(re.sub(r'<[^>]+>', '', raw)))
        principal, ev_p = spec('Principal Purpose')
        secondary, ev_s = spec('Secondary Uses')
        rm = re.search(r'(?s)<strong>Remarks:</strong>\s*<br\s*/?>(.*?)<br', specs)
        remarks = ws(htmlmod.unescape(re.sub(r'<[^>]+>', ' ', rm.group(1)))) if rm else None
        sds = []
        for s in re.findall(r'href="([^"]*/downloads/sds/[^"]+\.pdf)"', main_nc):
            fn = s.split('/')[-1]
            if fn not in sds:
                sds.append(fn)
        name = strip_marks(h1)
        title = ws(htmlmod.unescape(title)) if title else 'Alliant Powder - ' + name
        prods.append({'url': u, 'local': local, 'title': title, 'h1': h1, 'name': name,
                      'category': h2, 'subtitle': h4, 'discontinued': disc, 'paras': paras, 'bullets': bullets,
                      'principal': principal, 'secondary': secondary, 'remarks': remarks,
                      'ev_principal': ev_p, 'ev_secondary': ev_s, 'sds': sds})
        add_doc(u, local, title, None)
    return prods


def parse_alliant_sds():
    out = {}
    for u in alliant_all_sds_urls():
        local = local_for(u, 'alliant/sds')
        if not os.path.exists(local):
            continue
        pages = pdfpages(local)
        full = '\f'.join(pages)
        d = {'url': u, 'local': local, 'file': u.split('/')[-1]}
        with open(local, 'rb') as fh:
            d['md5'] = hashlib.md5(fh.read()).hexdigest()
        dup = next((x for x in out.values() if x['md5'] == d['md5']), None)
        d['duplicateOf'] = dup['url'] if dup else None
        pm = re.search(r'Product Name:\s*(.+)', full) or re.search(r'Trade name:\s*(.+)', full)
        d['productName'] = ws(pm.group(1)) if pm else None
        d['productNameLine'] = ws(pm.group(0)) if pm else None
        rev = re.search(r'Revision Date:\s*(\S+)', full) or re.search(r'Printing date\s*(\S+)', full)
        d['date'] = rev.group(1) if rev else None
        # Section 3 nitroglycerin row (may wrap onto following line)
        ng = None
        for pi, p in enumerate(pages):
            mm = re.search(r'^\s*Nitroglycerin\s+\(CAS No\) 55-63-0\s+(.+?)\s{2,}', p, re.M)
            if mm:
                ng = {'raw': mm.group(1).strip(), 'line': ws(mm.group(0)), 'page': pi + 1}
                break
            # older (2013) format: "Nitroglycerin         4.0 – 40%       55-63-0     OSHA ..."
            mm = re.search(r'^\s*Nitroglycerin\s+(\d+(?:\.\d+)?\s*[–-]\s*\d+(?:\.\d+)?)\s*%\s+55-63-0.*$', p, re.M)
            if mm:
                ng = {'raw': mm.group(1).strip(), 'line': ws(mm.group(0)), 'page': pi + 1}
                break
        d['ng'] = ng
        ap = None
        for pi, p in enumerate(pages):
            mm = re.search(r'^\s*(Appearance\s*:\s*(.+))$', p, re.M)
            if mm:
                ap = {'text': ws(mm.group(2)), 'line': ws(mm.group(1)), 'page': pi + 1}
                break
            mm = re.search(r'Appearance:\s*\n\s*(Form:\s+(\S.*))$', p, re.M)
            if mm:
                ap = {'text': ws(mm.group(2)), 'line': 'Appearance: ' + ws(mm.group(1)), 'page': pi + 1}
                break
            # older two-column format; value may wrap onto the next line ("Small black/gray" / "flakes")
            mm = re.search(r'(Appearance:\s+(\S[^\n]*))\n(\s{40,}(\S[^\n]{0,30}))?\n', p)
            if mm:
                text = ws(mm.group(2) + ' ' + (mm.group(4) or ''))
                ap = {'text': text, 'line': ws(mm.group(1) + ' ' + (mm.group(4) or '')), 'page': pi + 1}
                break
        d['appearance'] = ap
        out[d['file']] = d
        add_doc(u, local, 'Alliant SDS: ' + (d['productName'] or d['file']) +
                (f' (byte-identical to {dup["url"]})' if dup else ''), d['date'])
    return out


def sds_listed_keys(product_name):
    """Normalized keys of the individual powders an SDS 'Product Name' line lists."""
    if not product_name:
        return []
    t = strip_marks(product_name)
    t = re.sub(r'\s*Smokeless Powders?\b', '', t)
    keys = []
    m = re.match(r'^Reloder\s+([\d, and]+)$', t.strip())
    if m:
        return [normkey('Reloder ' + n) for n in re.findall(r'\d+', m.group(1))]
    for tok in re.split(r'\s*[-–]\s+|\s+[-–]\s*|,\s*', t):
        tok = tok.strip()
        if not tok or re.search(r'\bSeries\b', tok):
            continue
        if '/' in tok and re.search(r'[A-Za-z]', tok):
            parts = tok.split('/')
            suffix = parts[-1].split(' ', 1)[1] if ' ' in parts[-1] else ''
            for x in parts:
                keys.append(normkey(x if (' ' in x or not suffix) else f'{x} {suffix}'))
        else:
            keys.append(normkey(tok))
    return keys


def ng_range(raw):
    """'4 - 10, 10 - 30, 30 - 40' -> (4, 40); '<0.1, 0.1 - 1, 1 - 5, 5 - 18' -> (0, 18)."""
    nums = [float(x) for x in re.findall(r'\d+(?:\.\d+)?', raw)]
    lo = 0.0 if raw.strip().startswith('<') else min(nums)
    hi = max(nums)
    f = lambda v: int(v) if v == int(v) else v
    return f(lo), f(hi)


def parse_brand_pages():
    """Featured-product one-liners on hodgdonpowderco.com brand pages + family statements."""
    feats = []
    fam = {}
    for key, brand in (('hodgdon', 'HODGDON'), ('imr', 'IMR'), ('winchester', 'WINCHESTER')):
        local = hodg_page_local(key)
        url = HODG_PAGES[key]
        lines = html_text(read(local))
        add_doc(url, local, f'Hodgdon Powder Company brand page: {key}', None)
        if 'Featured Products' in lines:
            i = lines.index('Featured Products') + 1
            while i + 2 < len(lines) and lines[i + 2] == 'Shop Now':
                t, d = lines[i], lines[i + 1]
                if re.search(r'powder', d, re.I) and t.upper().startswith(brand):
                    if not any(f['title'] == t for f in feats):
                        feats.append({'brand': brand, 'title': t, 'desc': d, 'url': url,
                                      'evidence': f'{t} | {d}'})
                i += 3
        full = ws(' '.join(lines))
        if key == 'winchester':
            m = re.search(r'Winchester® Staball® family ™ (This temperature-insensitive, double-base, BALL® Powder is stable in extremely hot or cold conditions[^.]*\.)', full)
            if m:
                fam['staball'] = {'evidence': m.group(0), 'url': url}
        if key == 'imr':
            m = re.search(r'[^.]*identified by the “Enduron” sub-branding, offer improved temperature stability[^.]*\.', full)
            if m:
                fam['enduron'] = {'evidence': ws(m.group(0)), 'url': url}
    return feats, fam


def parse_extreme_pdf():
    url = [u for u in hodg_links(read(hodg_page_local('reference-data')), r'temperature-sensitivity.*\.pdf$')][0]
    local = local_for(url, 'hodgdon/pdf')
    pages = pdfpages(local)
    blocks = []
    for pi in (1, 2):  # PDF pages 2-3: the per-powder descriptions
        cur = None
        for l in pages[pi].split('\n'):
            if re.match(r'^\s{4,8}(H\d|[A-Z]{4,}|H\d)', l) and len(l.strip()) < 30 and not re.search(r'[a-z]{3}', l.strip()[1:]):
                cur = {'heading': l.strip(), 'lines': [], 'page': pi + 1}
                blocks.append(cur)
            elif cur and re.match(r'^\s{20,}\S', l) and 'hodgdon.com' not in l and 'Go to' not in l:
                cur['lines'].append(l.strip())
    line_claim = re.search(r'Our exclusive line of extruded rifle powders – Hodgdon Extreme™ – was developed to give '
                           r'shooters consistent performance, load after load, in even the most extreme heat and cold\.',
                           ws(pages[0]))
    out = []
    for b in blocks:
        text = ws(' '.join(b['lines']))
        names = [strip_marks(x) for x in re.split(r'\s*&\s*', b['heading'])]
        out.append({'names': names, 'heading': b['heading'], 'text': text, 'page': b['page'], 'url': url,
                    'lineClaim': line_claim.group(0) if line_claim else None})
    add_doc(url, local, 'Hodgdon "Extreme Rifle Powders" web pages (printout of hodgdon.com/extreme.html and '
            '/smokeless/extreme/*.php, published on the reference-data page as "Extreme series powders test results '
            'for temperature sensitivity")', '2012-07-13 (printout date)')
    return out, url


def sds_title_class(title):
    """Map an SDS cover title to (field, value) pairs stated by it."""
    out = []
    if not title:
        return out
    if re.search(r'Spherical|BALL', title):
        out.append(('form', 'spherical'))
    if re.search(r'Extruded', title):
        out.append(('form', 'extruded'))
    if re.search(r'Double Base', title):
        out.append(('base', 'double'))
    if re.search(r'Single Base', title):
        out.append(('base', 'single'))
    return out


def parse_hodgdon_sds_covers():
    """OCR'd cover page of each Hodgdon-family SDS: title + list of product names covered."""
    out = []
    for u in hodg_sds_urls():
        local = local_for(u, 'hodgdon/sds')
        if not os.path.exists(local):
            continue
        txt = ocr_page(local, 1)
        lines = [ws(l) for l in txt.split('\n') if ws(l)]
        k = next(i for i, l in enumerate(lines) if l == 'SAFETY DATA SHEET')
        title = lines[k - 1]
        date = lines[k + 1] if re.match(r'^(January|February|March|April|May|June|July|August|September|'
                                         r'October|November|December) \d{4}$', lines[k + 1]) else None
        # names: lines after "... distributed by ..." (or after the date line) up to "1.4C EX Approval..."
        a = next((i for i, l in enumerate(lines) if re.search(r'distributed by', l)), k + 1)
        j = a + 1
        while j < len(lines) and re.match(r'^(IMR Legendary Powders|Hodgdon Powder Company\.?)$', lines[j]):
            j += 1
        names = []
        for l in lines[j:]:
            if re.search(r'1\.4C EX Approval', l):
                break
            status = 'discontinued' if re.search(r'\(discontinued product\)|\[DISCONTINUED\]', l, re.I) else None
            ex = re.search(r'\(\s*(EX-\s*\d{10}|NO 1\.4C)\s*\)', l)
            nm = re.sub(r'\(\s*(?:EX-\s*\d+|NO 1\.4C|discontinued product)\s*\)|\[DISCONTINUED\]', ' ', l, flags=re.I)
            nm = re.sub(r'\([^)]*[a-z]{3,}[^)]*\)', ' ', nm)  # e.g. "(up to 5 pound bottles)"
            bm = re.match(r'^\[([A-Z]{2,5})\]\s*(.*)$', nm)  # "[WST] Super-Target" -> "Super-Target (WST)"
            if bm:
                nm = bm.group(2) + ' (' + bm.group(1) + ')'
            nm = re.sub(r'[®™©°|_\[\]]', ' ', nm)
            nm = ws(nm)
            nm = re.sub(r'^\.\s*', '', nm)
            nm = re.sub(r'\s+[A-Za-z0-9]$', '', nm)  # stray single-character OCR fragment at line end
            nm = ws(nm)
            if not nm or not re.match(r"^[A-Za-z0-9][A-Za-z0-9 '\-().]{1,40}$", nm):
                continue
            names.append({'name': nm, 'line': l, 'status': status, 'exApproval': ws(ex.group(1)) if ex else None})
        out.append({'url': u, 'local': local, 'file': u.split('/')[-1], 'title': title, 'date': date,
                    'names': names, 'cover': ' | '.join(lines)})
        add_doc(u, local, 'Hodgdon Powder Co. SDS (scanned; cover page OCR): ' + title, date)
    return out


# ---------------------------------------------------------------- application keywords
def app_categories(text):
    if not text:
        return []
    t = text.lower()
    cats = []
    if re.search(r'rifle|varmint|bench ?rest|\b223\b|\b308\b|lapua|caliber|silhouette|45-70|hornet|\bar\b|'
                 r'ar-style|\.338|30-06|7mm|magnum cartridges|match', t):
        cats.append('rifle')
    if re.search(r'handgun|pistol|revolver|9mm|45 acp|\.40 s&w|10mm', t):
        cats.append('handgun')
    if re.search(r'shotshell|gauge|\bga\b|\bga\.|410|skeet|trap|clay|sporting', t):
        cats.append('shotshell')
    if re.search(r'muzzleload', t):
        cats.append('muzzleloader')
    return cats


TEMP_RE = re.compile(r'temperat|hot/cold|hot or cold|thermal stability|any weather|environmental stability', re.I)


def temp_sentences(texts):
    out = []
    for t in texts:
        for s in re.split(r'(?<=[.!])\s+(?=[A-Z])', t):
            if TEMP_RE.search(re.sub(r'(?i)(flame|ambient) temperature', '', s)) and s not in out:
                out.append(s.strip())
    return out


# ---------------------------------------------------------------- build
def new_record(brand, name, manufacturer):
    return {
        'id': kebab(f'{brand} {name}'),
        'manufacturer': manufacturer,
        'brand': brand,
        'name': name,
        'displayName': f'{brand} {name}',
        'aliases': [],
        'form': None,
        'base': None,
        'nitroglycerinPct': None,
        'nitroglycerinPctRange': None,
        'applications': [],
        'principalUse': None,
        'secondaryUse': None,
        'temperatureStableClaim': None,
        'temperatureClaims': [],
        'bulkDensityGcc': None,
        'heatOfExplosionJg': None,
        'grainDimensions': None,
        'status': None,
        'burnRateRanks': [],
        'madeIn': None,
        'sources': [],
        'evidence': None,
        'fieldEvidence': {},
        'conflicts': [],
        'notes': [],
    }


def add_source(rec, s):
    if not any(x['url'] == s['url'] and x['page'] == s['page'] for x in rec['sources']):
        rec['sources'].append(s)


def add_fe(rec, field, evidence, url, page=None):
    rec['fieldEvidence'].setdefault(field, [])
    item = {'evidence': ws(evidence), 'url': url, 'page': page}
    if item not in rec['fieldEvidence'][field]:
        rec['fieldEvidence'][field].append(item)


def set_field(rec, field, value, evidence, url, page=None):
    """Set a field; if a different value is already present keep the first and record a conflict.
    temperatureStableClaim is free text: the first claim is kept and every claim goes to temperatureClaims."""
    if field == 'temperatureStableClaim':
        if rec[field] is None:
            rec[field] = value
        tc = rec.setdefault('temperatureClaims', [])
        if not any(c['text'] == value for c in tc):
            tc.append({'text': value, 'source': url, 'page': page})
        add_fe(rec, field, evidence, url, page)
        return
    cur = rec[field]
    if cur is None or cur == [] or cur == value:
        rec[field] = value
    else:
        c = next((c for c in rec['conflicts'] if c['field'] == field), None)
        if not c:
            first_src = rec['fieldEvidence'][field][0]['url'] if rec['fieldEvidence'].get(field) else None
            c = {'field': field, 'values': [{'value': cur, 'source': first_src}]}
            rec['conflicts'].append(c)
        if not any(v['value'] == value and v['source'] == url for v in c['values']):
            c['values'].append({'value': value, 'source': url})
    add_fe(rec, field, evidence, url, page)


def add_apps(rec, cats, evidence, url, page=None):
    new = [c for c in cats if c not in rec['applications']]
    if cats:
        rec['applications'] = sorted(set(rec['applications']) | set(cats))
        add_fe(rec, 'applications', evidence, url, page)


def build():
    records = {}
    keymap = {}

    def key_for(brand, name):
        n = strip_marks(name)
        if brand and n.upper().startswith(brand.upper() + ' '):
            n = n[len(brand) + 1:]
        return normkey(f'{brand} {n}')

    def get(brand, name, manufacturer, create=True):
        k = key_for(brand, name)
        if k in keymap:
            return records[keymap[k]]
        if not create:
            return None
        n = strip_marks(name)
        if n.upper().startswith(brand.upper() + ' '):
            n = n[len(brand) + 1:]
        rec = new_record(brand, n, manufacturer)
        while rec['id'] in records:
            rec['id'] += '-x'
        records[rec['id']] = rec
        keymap[k] = rec['id']
        return rec

    def alias(rec, name):
        k = key_for(rec['brand'], name)
        keymap.setdefault(k, rec['id'])
        nm = strip_marks(name)
        if nm.upper().startswith(rec['brand'].upper() + ' '):
            nm = nm[len(rec['brand']) + 1:]
        if nm != rec['name'] and nm not in rec['aliases']:
            rec['aliases'].append(nm)

    BRANDCASE = {'HODGDON': 'Hodgdon', 'IMR': 'IMR', 'WINCHESTER': 'Winchester', 'ALLIANT': 'Alliant'}
    MFR = {'Hodgdon': 'Hodgdon Powder Company', 'IMR': 'Hodgdon Powder Company',
           'Winchester': 'Hodgdon Powder Company', 'Alliant': 'Alliant Powder'}

    # 1. Hodgdon 2026 chart -> Hodgdon/IMR/Winchester records (Alliant names matched later)
    hchart, hentries, hurl = parse_hodgdon_chart()
    alliant_chart_entries = []
    for e in hentries:
        if e['brand'] in ('HODGDON', 'IMR', 'WINCHESTER'):
            brand = BRANDCASE[e['brand']]
            parts = [p.strip() for p in e['rest'].split(' & ')] if ' & ' in e['rest'] else [e['rest']]
            for p in parts:
                rec = get(brand, p, MFR[brand])
                rec['burnRateRanks'].append({'chart': 'hodgdon-2026', 'position': e['pos'], 'of': hchart['count'],
                                             'printedAs': e['printed']})
                add_source(rec, src(hurl, 'manufacturer', 1))
                add_fe(rec, 'burnRateRanks', f"{e['pos']} {e['printed']}", hurl, 1)
                if rec['status'] is None:
                    rec['status'] = 'current'
                    add_fe(rec, 'status', f"RELATIVE BURN RATES FROM FASTEST TO SLOWEST (rev. Aug'26) | {e['pos']} {e['printed']}", hurl, 1)
                if len(parts) > 1:
                    rec['notes'].append(f'Shares chart position {e["pos"]} with the other name in "{e["printed"]}".')
        elif e['brand'] == 'ALLIANT':
            alliant_chart_entries.append((e, hchart, hurl, 1))

    # 1b. Hodgdon Annual Manual: burn-rate chart (earlier edition), Powder Usage matrix, powder descriptions
    amchart, amentries, amurl, ampage = parse_am_chart()
    for e in amentries:
        if e['brand'] in ('HODGDON', 'IMR', 'WINCHESTER'):
            brand = BRANDCASE[e['brand']]
            parts = [p.strip() for p in e['rest'].split(' & ')] if ' & ' in e['rest'] else [e['rest']]
            for p in parts:
                rec = get(brand, p, MFR[brand], create=False)
                if rec is None:
                    rec = get(brand, p, MFR[brand])
                    rec['notes'].append(f'Listed on the {amchart["edition"]} burn-rate chart but not on the 2026 chart.')
                rec['burnRateRanks'].append({'chart': amchart['chartId'], 'position': e['pos'], 'of': amchart['count'],
                                             'printedAs': e['printed']})
                add_source(rec, src(amurl, 'manufacturer', ampage))
                add_fe(rec, 'burnRateRanks', f"{e['pos']} {e['printed']}", amurl, ampage)
                alias(rec, p)
        elif e['brand'] == 'ALLIANT':
            alliant_chart_entries.append((e, amchart, amurl, ampage))
    usage_rows, _, _ = parse_am_usage()
    SECT = {'SHOTGUN': 'shotshell', 'PISTOL': 'handgun', 'RIFLE': 'rifle'}
    for r in usage_rows:
        if not r['brand']:
            continue
        rec = get(r['brand'], r['name'], MFR[r['brand']], create=False)
        if rec is None:
            rec = get(r['brand'], r['name'], MFR[r['brand']])
            rec['notes'].append('Name from the Annual Manual "Powder Usage" table did not match any burn-rate chart '
                                'entry by normalized name.')
        alias(rec, r['name'])
        add_source(rec, src(amurl, 'manufacturer', r['page']))
        ev = f"Powder Usage | {r['header']} | ... | {r['line']}"
        add_apps(rec, [SECT[r['section']]], ev, amurl, r['page'])
        rec.setdefault('usage', {})[SECT[r['section']]] = r['uses']
        add_fe(rec, 'usage', ev, amurl, r['page'])
    paras, _ = parse_am_descriptions()
    for para in paras:
        brand = para['brand']
        body = re.sub(r'^»\s*', '', para['raw'])
        pk = key_for(brand, body[:80])
        best = None
        for k, rid in keymap.items():
            if records[rid]['brand'] != brand or not pk.startswith(k):
                continue
            if len(pk) > len(k) and pk[len(k)].isdigit():
                continue
            if best is None or len(k) > len(best):
                best = k
        if best is None:
            AM_UNMATCHED.append(para['raw'][:120])
            continue
        rec = records[keymap[best]]
        add_source(rec, src(amurl, 'manufacturer', para['page']))
        ev = f"{para['section']} | {para['raw']}"
        add_fe(rec, 'description', ev, amurl, para['page'])
        t = para['text']
        form = None
        if re.search(r'geometry of an extruded|extruded-shaped', t):
            form = 'extruded'
        elif re.search(r'\bspherical\b|\bBall powder\b', t):
            form = 'spherical'
        elif re.search(r'\bflake\b', t):
            form = 'flake'
        elif re.search(r'\bextruded\b', t, re.I):
            form = 'extruded'
        if form:
            set_field(rec, 'form', form, ev, amurl, para['page'])
        if re.search(r'\bdouble-base\b', t):
            set_field(rec, 'base', 'double', ev, amurl, para['page'])
        elif re.search(r'\bsingle-base\b', t):
            set_field(rec, 'base', 'single', ev, amurl, para['page'])
        ts = temp_sentences([t])
        if ts:
            set_field(rec, 'temperatureStableClaim', ' '.join(ts), ev, amurl, para['page'])
        # explicit "<...> pistol/rifle/shotshell/shotgun powder|propellant" wording in the description
        for mm in re.finditer(r'\b(pistol|handgun|rifle|shotshell|shotgun)\s+(?:powder|propellant)\b', t, re.I):
            cat = {'pistol': 'handgun', 'handgun': 'handgun', 'rifle': 'rifle', 'shotshell': 'shotshell',
                   'shotgun': 'shotshell'}[mm.group(1).lower()]
            add_apps(rec, [cat], ev, amurl, para['page'])

    # 2. Hodgdon brand pages: featured products + family claims
    feats, fam = parse_brand_pages()
    for f in feats:
        brand = BRANDCASE[f['brand']]
        rec = get(brand, f['title'], MFR[brand])
        if not rec['sources']:
            rec['notes'].append('Name as shown on the brand page did not match any 2026 burn-rate chart entry '
                                'by normalized name; kept as its own record.')
        add_source(rec, src(f['url'], 'manufacturer', None))
        alias(rec, f['title'])
        add_apps(rec, app_categories(f['desc']), f['evidence'], f['url'])
        if rec['status'] is None:
            rec['status'] = 'current'
            add_fe(rec, 'status', 'Featured Products | ' + f['evidence'], f['url'])
        if re.search(r'\bball powder\b', f['desc'], re.I):
            set_field(rec, 'form', 'spherical', f['evidence'], f['url'])
    for rec in list(records.values()):
        if rec['brand'] == 'Winchester' and 'STABALL' in rec['name'].upper() and 'staball' in fam:
            fa = fam['staball']
            add_source(rec, src(fa['url'], 'manufacturer', None))
            set_field(rec, 'form', 'spherical', fa['evidence'], fa['url'])
            set_field(rec, 'base', 'double', fa['evidence'], fa['url'])
            set_field(rec, 'temperatureStableClaim',
                      'This temperature-insensitive, double-base, BALL® Powder is stable in extremely hot or cold conditions',
                      fa['evidence'], fa['url'])
            rec['notes'].append('The Winchester brand-page statement about the "Staball family" (temperature-'
                                'insensitive, double-base, BALL powder) was applied to every Winchester powder whose '
                                'name contains "StaBALL".')

    # 3. Hodgdon SDS covers (OCR) -- processed after the Annual Manual so manual wording wins on conflicts
    covers = parse_hodgdon_sds_covers()
    for c in covers:
        fn = c['file'].lower()
        brand = 'IMR' if 'imr' in fn else ('Winchester' if 'winchester' in fn else 'Hodgdon')
        for n in c['names']:
            nm = re.sub(r'^Winchester\s+', '', n['name'], flags=re.I)
            # "Super-Target (WST)" -> candidates "Super-Target (WST)", "Super-Target", "WST"
            cands = [nm]
            pm = re.match(r'^(.*?)\s*\(([A-Z]{2,5})\)$', nm)
            if pm:
                cands += [pm.group(1), pm.group(2)]
            existing = next((get(brand, x, MFR[brand], create=False) for x in cands
                             if get(brand, x, MFR[brand], create=False)), None)
            rec = existing or get(brand, cands[-1] if pm else nm, MFR[brand])
            if not existing:
                rec['notes'].append('Name read by OCR from an SDS cover page and not matched to any 2026 burn-rate '
                                    'chart entry by normalized name.')
            for x in cands:
                alias(rec, x)
            add_source(rec, src(c['url'], 'manufacturer', 1))
            ev = f"[OCR] {c['title']} | SAFETY DATA SHEET | {c['date'] or ''} | ... | {n['line']}"
            add_fe(rec, 'sdsCover', ev, c['url'], 1)
            for fld, val in sds_title_class(c['title']):
                set_field(rec, fld, val, ev, c['url'], 1)
            if n['status'] == 'discontinued':
                rec['status'] = 'discontinued'
                rec['fieldEvidence']['status'] = []
                add_fe(rec, 'status', ev, c['url'], 1)
            if 'Enduron' in c['title'] and 'enduron' in fam:
                fa = fam['enduron']
                add_source(rec, src(fa['url'], 'manufacturer', None))
                set_field(rec, 'temperatureStableClaim', 'offer improved temperature stability',
                          fa['evidence'] + ' || ' + ev, fa['url'])
                rec['notes'].append('Listed on the "Double Base Powders - Enduron" SDS cover; temperature claim is '
                                    'the IMR brand-page statement about Enduron powders.')

    # 4. Hodgdon "Extreme" pages (2012 printout)
    ext, eurl = parse_extreme_pdf()
    for b in ext:
        for nm in b['names']:
            rec = get('Hodgdon', nm, MFR['Hodgdon'], create=False)
            if rec is None:
                rec = get('Hodgdon', nm, MFR['Hodgdon'])
                rec['notes'].append('Only found on the 2012 Extreme-series printout; not on the 2026 burn-rate chart.')
            add_source(rec, src(eurl, 'manufacturer', b['page']))
            alias(rec, nm)
            ev = f"{b['heading']} | {b['text']}"
            if re.search(r'Extreme Extruded|extruded', b['text']):
                set_field(rec, 'form', 'extruded', ev, eurl, b['page'])
            add_apps(rec, ['rifle'], 'EXTREME RIFLE POWDERS | ' + b['heading'], eurl, b['page'])
            ts = temp_sentences([b['text']])
            if ts:
                set_field(rec, 'temperatureStableClaim', ' '.join(ts), ev, eurl, b['page'])
            elif b['lineClaim'] and rec['temperatureStableClaim'] is None:
                set_field(rec, 'temperatureStableClaim', b['lineClaim'], b['lineClaim'] + ' || ' + ev, eurl, 1)
                rec['notes'].append('temperatureStableClaim is the Hodgdon Extreme line-level statement (2012 '
                                    'printout, page 1); the per-powder paragraph has no temperature wording.')

    # 5. Alliant product pages
    prods = parse_alliant_products()
    sdsd = parse_alliant_sds()
    for p in prods:
        nm = p['name']
        nm_core = re.sub(r'\s*\(.*\)\s*$', '', nm)  # "Power Pro 2000-MR (Medium Rifle)" -> "Power Pro 2000-MR"
        rec = get('Alliant', nm_core, MFR['Alliant'])
        if nm_core != nm:
            alias(rec, nm)
        add_source(rec, src(p['url'], 'manufacturer', None))
        page_ev = ' | '.join(x for x in [p['h1'], p['category'], p['subtitle']] if x)
        add_fe(rec, 'productPage', page_ev, p['url'])
        if p['discontinued']:
            rec['status'] = 'discontinued'
            rec['fieldEvidence']['status'] = []
            add_fe(rec, 'status', 'Discontinued | ' + p['h1'], p['url'])
        elif rec['status'] is None:
            rec['status'] = 'current'
            add_fe(rec, 'status', 'Product page on www.alliantpowder.com: ' + page_ev, p['url'])
        cat_apps = app_categories(p['category'])
        add_apps(rec, cat_apps, p['category'], p['url'])
        if p['principal']:
            if rec['principalUse'] is None:
                rec['principalUse'] = p['principal']
            add_fe(rec, 'principalUse', p['ev_principal'], p['url'])
            add_apps(rec, app_categories(p['principal']), p['ev_principal'], p['url'])
        if p['secondary']:
            if rec['secondaryUse'] is None:
                rec['secondaryUse'] = p['secondary']
            add_fe(rec, 'secondaryUse', p['ev_secondary'], p['url'])
            add_apps(rec, app_categories(p['secondary']), p['ev_secondary'], p['url'])
        alltext = [p['subtitle'] or ''] + p['paras'] + p['bullets'] + ([p['remarks']] if p['remarks'] else [])
        # form / base stated on the page
        sub = p['subtitle'] or ''
        if re.search(r'\bspherical\b', sub, re.I):
            set_field(rec, 'form', 'spherical', sub, p['url'])
        for t in p['paras'] + p['bullets']:
            if re.search(r"\bflake powders?\b", t, re.I):
                s = next(s for s in re.split(r'(?<=[.!])\s+', t) if re.search(r'flake powder', s, re.I))
                set_field(rec, 'form', 'flake', s, p['url'])
        if re.search(r'double[- ]based?\b', sub, re.I):
            set_field(rec, 'base', 'double', sub, p['url'])
            rec['baseBasis'] = 'stated'
        ts = temp_sentences(alltext)
        if ts:
            set_field(rec, 'temperatureStableClaim', ' | '.join(ts), ' | '.join(ts), p['url'])
        for b in p['bullets']:
            mm = re.match(r'^(?:Proudly )?Made in (?:the )?(.+?)(?: for Alliant Powder| to Alliant Powder specifications)?\.?$', b)
            if mm and rec['madeIn'] is None:
                rec['madeIn'] = mm.group(1).strip()
                add_fe(rec, 'madeIn', b, p['url'])
            if re.search(r'Manufactured in the USA', b) and rec['madeIn'] is None:
                rec['madeIn'] = 'USA'
                add_fe(rec, 'madeIn', b, p['url'])
        # SDS for this product: the one(s) the page links + any whose Product Name lists this powder
        sds_files = list(p['sds'])
        for x in sdsd.values():
            if normkey(nm_core) in sds_listed_keys(x['productName']) and x['file'] not in sds_files:
                sds_files.append(x['file'])
        seen_md5 = rec.setdefault('_seen_md5', set())
        for fn in sds_files:
            d = sdsd.get(fn)
            if not d:
                # link target not in the SDS listing (e.g. Sport Pistol) -> find SDS whose product name lists it
                d = next((x for x in sdsd.values() if x['productName'] and
                          normkey(nm_core) in [normkey(y) for y in re.split(r'\s+-\s+|\s+–\s+|/|,', x['productName'])]),
                         None)
                if d:
                    rec['notes'].append(f'Product page links SDS file "{fn}", which is not in the SDS listing; used '
                                        f'"{d["file"]}" whose product name lists this powder.')
                else:
                    rec['notes'].append(f'Product page links SDS file "{fn}", not found in the SDS listing.')
                    continue
            if d.get('_used_by') is None:
                d['_used_by'] = []
            if rec['id'] in d['_used_by'] or d['md5'] in seen_md5:
                continue
            seen_md5.add(d['md5'])
            d['_used_by'].append(rec['id'])
            add_source(rec, src(d['url'], 'manufacturer', d['ng']['page'] if d['ng'] else None))
            add_fe(rec, 'sds', d['productNameLine'], d['url'], 1)
            if d['ng']:
                lo, hi = ng_range(d['ng']['raw'])
                val = {'min': lo, 'max': hi, 'raw': d['ng']['raw'],
                       'note': 'SDS Section 3 lists these % (w/w) bands for the whole product family covered by the SDS'}
                if rec['nitroglycerinPctRange'] is None:
                    rec['nitroglycerinPctRange'] = val
                add_fe(rec, 'nitroglycerinPctRange', d['ng']['line'], d['url'], d['ng']['page'])
            if d['appearance']:
                a = d['appearance']['text']
                form = 'flake' if re.search(r'\bflakes?\b', a, re.I) else (
                    'extruded' if re.search(r'perforated grain', a, re.I) else None)
                if form:
                    set_field(rec, 'form', form, d['appearance']['line'], d['url'], d['appearance']['page'])
                else:
                    add_fe(rec, 'sdsAppearance', d['appearance']['line'], d['url'], d['appearance']['page'])
        rec.setdefault('_alliant_page', []).append(p)

    # 6. Alliant 2023 guide: burn order + uses + NG statements
    achart, arows, info_par, gurl, info_page = parse_alliant_guide()
    for i, r in enumerate(arows):
        rec = get('Alliant', r['printed'], MFR['Alliant'], create=False)
        if rec is None:
            rec = get('Alliant', r['printed'], MFR['Alliant'])
            rec['notes'].append('Listed in the 2023 Reloader\'s Guide powder table; no product page found on the Alliant site.')
        alias(rec, r['printed'])
        add_source(rec, src(gurl, 'manufacturer', r['page']))
        rec['burnRateRanks'].append({'chart': 'alliant-2023-guide', 'position': i + 1, 'of': len(arows),
                                     'printedAs': r['printed']})
        add_fe(rec, 'burnRateRanks', r['evidence'], gurl, r['page'])
        rec['guideUse'] = {'principal': r['principal'], 'secondary': r['secondary']}
        add_fe(rec, 'guideUse', r['evidence'], gurl, r['page'])
        add_apps(rec, app_categories(' '.join(x for x in (r['principal'], r['secondary']) if x)), r['evidence'], gurl, r['page'])
    # powder information paragraph (p. 10): explicit NG % for two powders
    # two phrasings on p. 10: '"near" single-base American Select (2% nitroglycerin)' and
    # 'high nitroglycerin (40%) double-base Bullseye'
    ng_stmts = [(m.group(1), m.group(2), m.group(3), m.group(0)) for m in re.finditer(
        r'(“near” single-base|double-base) ([A-Z][A-Za-z ]+?) \((\d+)% nitroglycerin\)', info_par)]
    ng_stmts += [('double-base', m.group(2), m.group(1), m.group(0)) for m in re.finditer(
        r'nitroglycerin \((\d+)%\) double-base ([A-Z][A-Za-z]+)', info_par)]
    for kind, pname, pct, whole in ng_stmts:
        rec = get('Alliant', pname, MFR['Alliant'], create=False)
        if rec is None:
            continue
        sent = next(s for s in re.split(r'(?<=\.)\s+', info_par) if whole in s)
        add_source(rec, src(gurl, 'manufacturer', info_page))
        set_field(rec, 'nitroglycerinPct', int(pct), sent, gurl, info_page)
        if kind == 'double-base':
            set_field(rec, 'base', 'double', sent, gurl, info_page)
            rec['baseBasis'] = 'stated'
        else:
            rec['notes'].append('Alliant calls this powder "near" single-base; base left null.')
    # NG % vs SDS family bands -> conflict when outside
    for rec in records.values():
        if rec['nitroglycerinPct'] is not None and rec['nitroglycerinPctRange']:
            r = rec['nitroglycerinPctRange']
            if not (r['min'] <= rec['nitroglycerinPct'] <= r['max']):
                sds_url = rec['fieldEvidence']['nitroglycerinPctRange'][0]['url']
                rec['conflicts'].append({'field': 'nitroglycerinPct', 'values': [
                    {'value': rec['nitroglycerinPct'], 'source': rec['fieldEvidence']['nitroglycerinPct'][0]['url']},
                    {'value': f"{r['raw']} (SDS family bands, min {r['min']})", 'source': sds_url}]})
    # base from SDS composition for Alliant: NG listed with lowest band >= 4 % -> nitroglycerin present
    # => double-base by Alliant's own definition (guide p. 10). Recorded with baseBasis='sds-composition'.
    for rec in records.values():
        if rec['brand'] != 'Alliant' or rec['base'] is not None:
            continue
        r = rec['nitroglycerinPctRange']
        if r and r['min'] >= 4 and not any('single-base' in n for n in rec['notes']):
            defin = next(s for s in re.split(r'(?<=\.)\s+', info_par) if 'double-base from a combination' in s)
            set_field(rec, 'base', 'double', rec['fieldEvidence']['nitroglycerinPctRange'][0]['evidence'] + ' || ' + defin,
                      rec['fieldEvidence']['nitroglycerinPctRange'][0]['url'])
            rec['baseBasis'] = 'sds-composition'
    # Alliant names on the Hodgdon charts (third-party listing for Alliant)
    for e, ch, curl, cpage in alliant_chart_entries:
        rec = get('Alliant', e['rest'], MFR['Alliant'], create=False)
        if rec is None:
            rec = get('Alliant', e['rest'], MFR['Alliant'])
            rec['notes'].append('Only source is the Hodgdon burn-rate chart(s) (third-party listing for Alliant); '
                                'no Alliant product page or guide entry found.')
        rec['burnRateRanks'].append({'chart': ch['chartId'], 'position': e['pos'], 'of': ch['count'],
                                     'printedAs': e['printed']})
        add_source(rec, src(curl, 'third-party', cpage))
        add_fe(rec, 'burnRateRanks', f"{e['pos']} {e['printed']}", curl, cpage)
        alias(rec, e['rest'])

    # names that differ only by one inserted letter (e.g. "7828SC" vs "7828SSC") are NOT merged; flag them
    recs = list(records.values())
    for a in recs:
        for b in recs:
            if a is b or a['brand'] != b['brand']:
                continue
            ka, kb = normkey(a['name']), normkey(b['name'])
            if len(kb) == len(ka) + 1 and len(ka) >= 5:
                for i in range(len(kb)):
                    if kb[:i] + kb[i + 1:] == ka and kb[i].isalpha():
                        a['notes'].append(f'Similar name "{b["displayName"]}" (id {b["id"]}) exists as a separate '
                                          f'record; the sources print the names differently and they were not merged.')
                        b['notes'].append(f'Similar name "{a["displayName"]}" (id {a["id"]}) exists as a separate '
                                          f'record; the sources print the names differently and they were not merged.')
                        break

    # finalize
    out = []
    for rec in records.values():
        rec.pop('_alliant_page', None)
        rec.pop('_seen_md5', None)
        evs = []
        for fld, items in rec['fieldEvidence'].items():
            for it in items:
                if it['evidence'] not in evs:
                    evs.append(it['evidence'])
        rec['evidence'] = ' || '.join(evs)
        rec['notes'] = ' '.join(dict.fromkeys(rec['notes'])) or None
        if not rec['conflicts']:
            rec['conflicts'] = []
        out.append(rec)
    out.sort(key=lambda r: (r['brand'], r['id']))
    return out, [hchart, amchart, achart], covers, sdsd


# ---------------------------------------------------------------- self-check
def self_check(data):
    pw = data['powders']
    print(f'powders: {len(pw)}  charts: {len(data["charts"])}')
    by_brand = {}
    for r in pw:
        by_brand[r['brand']] = by_brand.get(r['brand'], 0) + 1
    print('by brand:', by_brand)
    errors = []
    ids = [r['id'] for r in pw]
    if len(ids) != len(set(ids)):
        errors.append('duplicate ids')
    for r in pw:
        fe = r['fieldEvidence']
        if not r['sources'] or not r['evidence']:
            errors.append(f'{r["id"]}: missing sources/evidence')
        for rk in r['burnRateRanks']:
            if not any(re.search(r'(^|\s)' + str(rk['position']) + r'\s', it['evidence'] + ' ') or
                       rk['printedAs'] in it['evidence'] for it in fe.get('burnRateRanks', [])):
                errors.append(f'{r["id"]}: burn rank {rk} not in evidence')
        if r['nitroglycerinPct'] is not None:
            if not any(f"({r['nitroglycerinPct']}% nitroglycerin)" in it['evidence'] or
                       f"nitroglycerin ({r['nitroglycerinPct']}%)" in it['evidence'] for it in fe['nitroglycerinPct']):
                errors.append(f'{r["id"]}: NG% not in evidence')
        if r['nitroglycerinPctRange']:
            ng = r['nitroglycerinPctRange']
            ev = ' '.join(it['evidence'] for it in fe['nitroglycerinPctRange'])
            if ng['raw'] not in ev:
                errors.append(f'{r["id"]}: NG range raw not in evidence')
            nums = [float(x) for x in re.findall(r'\d+(?:\.\d+)?', ng['raw'])]
            if float(ng['max']) != max(nums) or not (float(ng['min']) == min(nums) or
                                                      (ng['min'] == 0 and ng['raw'].startswith('<'))):
                errors.append(f'{r["id"]}: NG bounds {ng["min"]}-{ng["max"]} not matching raw {ng["raw"]}')
        kw = {'spherical': r'spherical|ball', 'extruded': r'extruded|perforated grain', 'flake': r'flake'}
        if r['form']:
            if not any(re.search(kw[r['form']], dehyphen(it['evidence']), re.I) for it in fe['form']):
                errors.append(f'{r["id"]}: form keyword not in evidence')
        if r['base']:
            if not any(re.search(r['base'] + r'[- ]based?|nitroglycerin', dehyphen(it['evidence']), re.I) for it in fe['base']):
                errors.append(f'{r["id"]}: base keyword not in evidence')
        for fld in ('bulkDensityGcc', 'heatOfExplosionJg', 'grainDimensions'):
            if r[fld] is not None:
                errors.append(f'{r["id"]}: unexpected {fld}')
    for c in data['charts']:
        if len(c['orderedNames']) != c['count'] or len(set(c['orderedNames'])) != c['count']:
            errors.append(f'chart {c["publisher"]}: count/duplicate mismatch')
    random.seed(7)
    for r in random.sample(pw, min(5, len(pw))):
        print('-' * 80)
        print(json.dumps({k: r[k] for k in ('id', 'form', 'base', 'nitroglycerinPct', 'nitroglycerinPctRange',
                                             'applications', 'temperatureStableClaim', 'status', 'burnRateRanks')},
                         ensure_ascii=False))
        print('EVIDENCE:', r['evidence'][:900])
    print('-' * 80)
    if errors:
        print('SELF-CHECK ERRORS:')
        for e in errors:
            print('  ', e)
    else:
        print('self-check OK')
    return errors


def main():
    if '--download' in sys.argv:
        download()
    powders, charts, covers, sdsd = build()
    notes = (
        'Hodgdon-family product pages are on shop.hodgdon.com, which is blocked from this sandbox. Hodgdon/IMR/'
        'Winchester records come from: (1) the 2026 relative burn-rate chart (names, order; status=current); '
        '(2) the latest Hodgdon Annual Manual PDF published free on hodgdonpowderco.com/reloading-manuals-library '
        '(AM25 = 2025 Annual Manual): its earlier-edition burn-rate chart, its "Powder Usage" matrix (applications = '
        'the SHOTGUN/PISTOL/RIFLE sections a powder is listed in -> shotshell/handgun/rifle; usage = the column '
        'headings ticked for PISTOL/RIFLE), and its per-powder descriptions (form from the words spherical/Ball powder/'
        'flake/extruded, base from "double-base"/"single-base", temperature claims); (3) brand-page featured-product '
        'one-liners, the Winchester "Staball family" and IMR "Enduron" statements; (4) the OCR\'d COVER PAGE of each '
        'scanned Hodgdon SDS (title such as "Spherical Powders"/"Extruded Rifle Powders"/"Double Base Powders"/'
        '"Single Base Powders"/"BALL Powder Propellant", the product names listed, [DISCONTINUED] marks); evidence '
        'from OCR is prefixed "[OCR]"; numeric composition in the scanned SDS was NOT extracted (OCR digits '
        'unreliable; tables keyed by internal codes); (5) the 2012 Hodgdon Extreme-series web printout. When sources '
        'disagree the first value is kept (order: Annual Manual > brand pages > SDS covers > 2012 printout for the '
        'Hodgdon family; product page > SDS for Alliant) and all values are listed in conflicts. Alliant records '
        'come from www.alliantpowder.com product pages, Alliant SDS PDFs (Section 3 nitroglycerin bands, Section 9 '
        'appearance; byte-identical duplicates de-duplicated) and the 2023 Reloader\'s Guide (burn order and uses). '
        'nitroglycerinPct is set only where a single figure is stated (Alliant guide: Bullseye 40 %, American Select '
        '2 %). nitroglycerinPctRange holds SDS family bands (not product-specific). baseBasis="sds-composition" '
        'means base was inferred from an Alliant SDS listing nitroglycerin with lowest band >= 4 % together with '
        'Alliant\'s own definition of double-base; "stated" means a page says it; Hodgdon-family base values are '
        'stated by an SDS cover title or the Annual Manual text. temperatureStableClaim is maker text (sentences '
        'containing temperature wording; end-of-line hyphenation removed), not a boolean, and claims differ in '
        'strength. Alliant applications are keyword categories from the product page category/principal/secondary '
        'use and guide uses (raw text in principalUse/secondaryUse/guideUse). bulkDensityGcc, heatOfExplosionJg and '
        'grainDimensions are null everywhere: none of these documents publish them. burnRateRanks are chart '
        'positions (ordinal), not quantitative burn rates; the Hodgdon and Alliant charts order some powders '
        'differently. usage holds, per application, the Annual Manual matrix column headings ticked (PISTOL: TARGET/'
        'LIGHT DUTY/MEDIUM DUTY/MAGNUM; RIFLE: TARGET/SILHOUETTE/LIGHT/MEDIUM/MAGNUM/50 CAL); usage.shotshell is null '
        'because the SHOTGUN sub-columns (gauge/load class) were not parsed. temperatureClaims lists every claim with '
        'its source. Page numbers are PDF page indices (1-based), not printed folios. fieldEvidence maps each '
        'populated field to the verbatim, whitespace-collapsed lines it came from; "evidence" joins them with " || ".'
    )
    data = {
        'meta': {'documents': DOCS, 'notes': notes, 'retrieved': RETRIEVED,
                 'unmatchedManualParagraphs': AM_UNMATCHED,
                 'blockedHosts': ['shop.hodgdon.com']},
        'powders': powders,
        'charts': charts,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f'wrote {OUT}')
    errs = self_check(data)
    sys.exit(1 if errs else 0)


if __name__ == '__main__':
    main()
