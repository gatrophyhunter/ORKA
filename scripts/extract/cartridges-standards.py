#!/usr/bin/env python3
"""Extract cartridge specifications and maximum pressures from the standards bodies.

Sources (all public, fetched with plain curl, default user agent):
  * ANSI/SAAMI Z299.4 (centerfire rifle) and Z299.3 (centerfire pistol & revolver) PDFs,
    linked from https://saami.org/technical-information/ansi-saami-standards/
    (robots.txt: Crawl-delay 10 -> we sleep >= 10 s between saami.org requests).
  * C.I.P. public TDCC listing https://bobp.cip-bobp.org/en/tdcc_public (Tabs I-IV) and the
    per-cartridge EN TDCC sheets (PDF) linked from it (robots.txt has no active rules;
    we sleep 1.5 s between requests).

Usage:
  python3 -I cartridges-standards.py --download   # fetch any missing source documents
  python3 -I cartridges-standards.py              # parse cached documents and write JSON

Everything is parsed with code from `pdftotext -layout` output / HTML; nothing is typed in.
"""
import json
import os
import random
import re
import subprocess
import sys
import time

SRC = '/tmp/claude-0/-home-user-ORKA/29ce603d-ccc3-55ef-b8fe-c585397ac7c1/scratchpad/sources/cartridges-standards'
OUT = '/home/user/ORKA/research/raw2/cartridges-standards.json'
RETRIEVED = '2026-11-23'

SAAMI_PAGE = 'https://saami.org/technical-information/ansi-saami-standards/'
SAAMI_DOCS = {
    'Z299.4': {
        'url': 'https://saami.org/wp-content/uploads/2026/10/SAAMI-Z299.4-CFR-2025-Centerfire-Rifle-Approved-2-10-2025-2026-10-21.pdf',
        'local': 'Z299.4.pdf',
        'title': 'ANSI/SAAMI Z299.4-2025 Voluntary Industry Performance Standards for Pressure and Velocity of Centerfire Rifle Sporting Ammunition',
        'date': '2025-02-10 (approved; file revision dated 2026-10-21)',
        'kind': 'rifle',
    },
    'Z299.3': {
        'url': 'https://saami.org/wp-content/uploads/2025/05/SAAMI-Z299.3-2022-Centerfire-Pistol-Revolver-Approved-12-13-2022.pdf',
        'local': 'Z299.3.pdf',
        'title': 'ANSI/SAAMI Z299.3-2022 Voluntary Industry Performance Standards for Pressure and Velocity of Centerfire Pistol and Revolver Ammunition',
        'date': '2022-12-13 (approved)',
        'kind': 'handgun',
    },
}
CIP_BASE = 'https://bobp.cip-bobp.org'
CIP_TABS = {1: 'Tab I - Rimless cartridges', 2: 'Tab II - Rimmed cartridges',
            3: 'Tab III - Belted cartridges', 4: 'Tab IV - Pistol and revolver cartridges'}


def cip_tab_url(t):
    return f'{CIP_BASE}/en/tdcc_public?page=1&cartridge_type_id={t}'


def cip_tab_local(t):
    return os.path.join(SRC, 'cip', f'tab{t}.html')


def cip_pdf_local(path):
    # path like /uploads/tdcc/tab-i/308-win-en.pdf -> cip/pdf/tab-i_308-win-en.pdf
    rel = path.split('/uploads/tdcc/', 1)[1]
    return os.path.join(SRC, 'cip', 'pdf', rel.replace('/', '_'))


_last_fetch = {}


def fetch(url, local, delay):
    """Download url to local with plain curl (default UA) unless cached. Returns True if file present."""
    if os.path.exists(local) and os.path.getsize(local) > 0:
        return True
    host = url.split('/')[2]
    wait = _last_fetch.get(host, 0) + delay - time.time()
    if wait > 0:
        time.sleep(wait)
    os.makedirs(os.path.dirname(local), exist_ok=True)
    tmp = local + '.part'
    r = subprocess.run(['curl', '-sS', '-L', '-m', '300', '-o', tmp, '-w', '%{http_code}', url],
                       capture_output=True, text=True)
    _last_fetch[host] = time.time()
    code = r.stdout.strip()
    if r.returncode != 0 or code != '200':
        print(f'FETCH FAILED {url}: rc={r.returncode} http={code} {r.stderr.strip()[:200]}', file=sys.stderr)
        if os.path.exists(tmp):
            os.remove(tmp)
        return False
    os.replace(tmp, local)
    return True


def cip_rows_raw(t):
    h = open(cip_tab_local(t), encoding='utf-8').read()
    return re.findall(r'<tr id="cartridge-(\d+)"[^>]*>(.*?)</tr>', h, re.S)


def download_all():
    os.makedirs(SRC, exist_ok=True)
    for d in SAAMI_DOCS.values():
        fetch(d['url'], os.path.join(SRC, d['local']), 10.0)
    for t in CIP_TABS:
        fetch(cip_tab_url(t), cip_tab_local(t), 1.5)
    n = 0
    for t in CIP_TABS:
        for rid, r in cip_rows_raw(t):
            tds = re.findall(r'<td[^>]*>(.*?)</td>', r, re.S)
            links = dict((lang, u) for u, lang in re.findall(r'href="(/uploads/tdcc/[^"]+)"[^>]*>(\w\w)</a>', tds[4]))
            u = links.get('EN')
            if not u:
                continue
            ok = fetch(CIP_BASE + u, cip_pdf_local(u), 1.5)
            n += 1
            if n % 25 == 0:
                print(f'... {n} CIP sheets checked', flush=True)
    print('download done', flush=True)


if __name__ == '__main__' and '--download' in sys.argv:
    download_all()
    sys.exit(0)
