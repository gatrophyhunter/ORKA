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

Swift (https://www.swiftbullets.com, Shopify storefront)
  * https://www.swiftbullets.com/robots.txt -> /products/ pages allowed, no
    Crawl-delay.  (Only public HTML product pages are used; no store APIs.)
  * https://www.swiftbullets.com/sitemap.xml -> sitemap_products_1.xml.
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

_last = {}


def fetch(url, dest, force=False):
    """Download url to dest with plain curl (default UA); >= DELAY s per host."""
    if os.path.exists(dest) and os.path.getsize(dest) > 0 and not force:
        return True
    host = re.match(r'https?://([^/]+)', url).group(1)
    wait = DELAY - (time.time() - _last.get(host, 0.0))
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
        if os.path.exists(tmp):
            os.remove(tmp)
        return False
    os.replace(tmp, dest)
    return True


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


def download():
    fetch(NOSLER + '/robots.txt', os.path.join(SRC, 'nosler-robots.txt'))
    fetch(SWIFT + '/robots.txt', os.path.join(SRC, 'swift-robots.txt'))
    fetch(NOSLER_SITEMAP, L_NOSLER_SITEMAP)
    fetch(NOSLER_CATREQ, L_NOSLER_CATREQ)
    fetch(NOSLER_CATALOG, L_NOSLER_CATALOG)
    if not os.path.exists(L_NOSLER_CATALOG_TXT):
        subprocess.run(['pdftotext', '-layout', L_NOSLER_CATALOG, L_NOSLER_CATALOG_TXT], check=True)
    fetch(SWIFT_SITEMAP, L_SWIFT_SITEMAP)
    sm = open(L_SWIFT_SITEMAP, encoding='utf-8').read()
    prod_sm = [htmlmod.unescape(u) for u in re.findall(r'<loc>([^<]+)</loc>', sm) if 'sitemap_products' in u]
    if prod_sm:
        fetch(prod_sm[0], L_SWIFT_SITEMAP_PRODUCTS)
    for loc, _t in swift_product_urls():
        fetch(loc, os.path.join(SWIFT_PAGES, slug_of(loc) + '.html'))
    urls = nosler_product_urls()
    for i, u in enumerate(urls):
        ok = fetch(u, os.path.join(NOSLER_PAGES, slug_of(u)))
        if i % 25 == 0:
            print('nosler %d/%d %s %s' % (i, len(urls), ok, u), flush=True)
    print('download done', flush=True)


if __name__ == '__main__' and '--download' in sys.argv:
    download()
    sys.exit(0)
