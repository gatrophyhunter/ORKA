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
    re.compile(r'\b1\s*(?:[:/-]|-?in-?|\s+in\s+)\s*(\d{1,2}(?:\.\d+)?)\s*(?:"|”|″|\'\'|-?\s*inch(?:es)?|in\.)?\s*(?:or (?:faster|quicker))?\s*(?:barrel\s+)?twist', re.I),
    re.compile(r'twist[^.]{0,40}?\b1\s*(?:[:/-]|-?in-?|\s+in\s+)\s*(\d{1,2}(?:\.\d+)?)', re.I),
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
