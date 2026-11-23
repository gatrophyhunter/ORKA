#!/usr/bin/env python3
"""Extract the smokeless-powder catalog for the Hodgdon family (Hodgdon, IMR, Winchester) and Alliant,
plus the publishers' relative burn-rate charts.

Sources (public, fetched with plain curl and its default user agent):
  * hodgdonpowderco.com (robots.txt: Crawl-delay 10, no Disallow) -> we sleep >= 10 s between requests.
      - /reference-data/  -> 2026 Smokeless Relative Burn Rate Chart (PDF)
      - /safety-data-sheets/ -> Hodgdon / IMR / Winchester SDS PDFs (composition, physical form)
      - brand pages /hodgdon/ /imr/ /winchester/ (brand-level claims)
    Product pages live on shop.hodgdon.com, which is NOT reachable from this sandbox (proxy 403).
  * www.alliantpowder.com (robots.txt: no rules) -> we sleep >= 2 s between requests.
      - /products/{rifle,shotshell,handgun,muzzleloader}.aspx and every linked /products/powder/*.aspx page
      - /resources/sds.aspx -> SDS PDFs
      - /resources/catalog.aspx -> 2023 Reloaders Guide PDF (burn-rate chart)

Usage:
  python3 -I powders-hodgdon-alliant.py --download   # fetch any missing source documents
  python3 -I powders-hodgdon-alliant.py              # parse cached documents and write JSON

Everything is parsed with code from HTML and `pdftotext -layout` output; nothing is typed in.
"""
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
        subprocess.run(['pdftotext', '-layout', local, txt], check=True)
    with open(txt, encoding='utf-8', errors='replace') as f:
        return f.read()


def read(local):
    with open(local, encoding='utf-8', errors='replace') as f:
        return f.read()


def ws(s):
    return re.sub(r'\s+', ' ', s).strip()


# ---------------------------------------------------------------- document lists
HODG_PAGES = {
    'reference-data': f'{HODG}/reference-data/',
    'safety-data-sheets': f'{HODG}/safety-data-sheets/',
    'hodgdon': f'{HODG}/hodgdon/',
    'imr': f'{HODG}/imr/',
    'winchester': f'{HODG}/winchester/',
}


def hodg_page_local(key):
    return os.path.join(SRC, 'hodgdon', f'page-{key}.html')


# SDS PDFs from https://hodgdonpowderco.com/safety-data-sheets/ that cover Hodgdon / IMR / Winchester smokeless powders.
HODG_SDS_MATCH = re.compile(r'(hodgdon|imr|winchester|clays|trail-boss|bm2|extruded-rifle|spherical|700x|oem-st)', re.I)
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


def download():
    for k, u in HODG_PAGES.items():
        fetch(u, hodg_page_local(k))
    ref = read(hodg_page_local('reference-data'))
    for u in hodg_links(ref, r'Burn-Rate-Chart.*\.pdf$|temperature-sensitivity.*\.pdf$'):
        fetch(u, local_for(u, 'hodgdon/pdf'))
    sds = read(hodg_page_local('safety-data-sheets'))
    for u in hodg_links(sds, r'\.pdf$'):
        name = u.split('/')[-1]
        if HODG_SDS_MATCH.search(name) and not HODG_SDS_EXCLUDE.search(name):
            fetch(u, local_for(u, 'hodgdon/sds'))
    for c in ALLIANT_CATS:
        fetch(f'{ALL}/products/{c}.aspx', alliant_cat_local(c))
    for k, u in ALLIANT_RES.items():
        fetch(u, alliant_res_local(k))
    for u in alliant_product_urls():
        fetch(u, local_for(u, 'alliant/product'))
    for u in alliant_pdf_urls('sds', r'/sds/'):
        fetch(u, local_for(u, 'alliant/sds'))
    for u in alliant_pdf_urls('catalog', r'catalog/'):
        fetch(u, local_for(u, 'alliant/pdf'))


if __name__ == '__main__' and '--download' in sys.argv:
    download()
