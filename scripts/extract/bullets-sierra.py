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


def download():
    if not os.path.exists(SITEMAP_LOCAL):
        fetch(SITEMAP_URL, SITEMAP_LOCAL)
    urls = product_urls()
    todo = [u for u in urls if not os.path.exists(local_of(u))]
    print(f'{len(urls)} bullet product URLs, {len(todo)} to fetch', flush=True)
    for i, u in enumerate(todo, 1):
        ok = fetch(u, local_of(u))
        print(f'[{i}/{len(todo)}] {"ok " if ok else "ERR"} {u}', flush=True)


if __name__ == '__main__' and '--download' in sys.argv:
    download()
    sys.exit(0)
