// Name normalisation used to join records from different sources (cartridges, powders, brass).

const CART_TOKENS: Record<string, string> = {
  win: 'winchester',
  winchester: 'winchester',
  rem: 'remington',
  remington: 'remington',
  mag: 'magnum',
  magnum: 'magnum',
  wby: 'weatherby',
  weatherby: 'weatherby',
  spl: 'special',
  special: 'special',
  sprg: 'springfield',
  springfield: 'springfield',
  spfd: 'springfield',
  govt: 'government',
  government: 'government',
  gov: 'government',
  cm: 'creedmoor',
  creedmoor: 'creedmoor',
  creed: 'creedmoor',
  blk: 'blackout',
  blackout: 'blackout',
  aac: '',
  auto: 'auto',
  acp: 'auto',
  luger: 'luger',
  parabellum: 'luger',
  sw: 'sw',
  's&w': 'sw',
  um: 'ultramagnum',
  rum: 'remingtonultramagnum',
  wsm: 'wsm',
  prc: 'prc',
  nm: 'normamagnum',
  ai: 'ackleyimproved',
  ackley: 'ackley',
  improved: 'improved',
  sav: 'savage',
  savage: 'savage',
  nato: 'nato',
  mauser: 'mauser',
  swedish: 'swedish',
  swede: 'swedish',
  norma: 'norma',
  lapua: 'lapua',
  federal: 'federal',
  fed: 'federal',
  hornet: 'hornet',
  ruger: 'ruger',
  sig: 'sig',
  colt: 'colt',
  casull: 'casull',
  super: 'super',
  express: '',
  cartridge: '',
  the: '',
};

/** Canonical key for a cartridge name, e.g. ".308 Win" and "308 Winchester" -> "308-winchester". */
export function cartridgeKey(name: string): string {
  let s = name.toLowerCase().trim();
  s = s.replace(/s&w/g, ' sw ').replace(/×/g, 'x');
  s = s.replace(/(\d)\s*mm\b/g, '$1mm');
  s = s.replace(/^\./, '').replace(/\s\./g, ' ');
  s = s.replace(/[“”"']/g, '');
  const toks = s.split(/[\s,()/]+/).filter(Boolean);
  const out: string[] = [];
  for (let t of toks) {
    t = t.replace(/^\./, '');
    if (t in CART_TOKENS) {
      const v = CART_TOKENS[t];
      if (v) out.push(v);
    } else out.push(t.replace(/[^a-z0-9.+x-]/g, ''));
  }
  return out.filter(Boolean).join('-').replace(/-+/g, '-');
}

/** Canonical key for a powder within its manufacturer, e.g. "IMR 4064" / "IMR4064" -> "imr4064"; "Reloder 16" -> "reloder16". */
export function powderKey(name: string): string {
  let s = name.toLowerCase().trim();
  s = s.replace(/®|™/g, '');
  s = s.replace(/\bre-?loder\b/g, 'reloder').replace(/\brl[- ]?(\d)/g, 'reloder$1');
  s = s.replace(/[^a-z0-9.+]/g, '');
  return s;
}

export function slug(s: string): string {
  return s
    .toLowerCase()
    .replace(/®|™/g, '')
    .replace(/[^a-z0-9.]+/g, '-')
    .replace(/\./g, '')
    .replace(/^-+|-+$/g, '');
}

/** Manufacturer canonical name for joining (brand families map to the maker that publishes the data). */
export function makerKey(m: string): string {
  const s = m.toLowerCase();
  if (s.includes('hodgdon')) return 'hodgdon';
  if (s.includes('imr')) return 'imr';
  if (s.includes('winchester')) return 'winchester';
  if (s.includes('alliant')) return 'alliant';
  if (s.includes('vihta')) return 'vihtavuori';
  if (s.includes('norma')) return 'norma';
  if (s.includes('reload swiss') || s.includes('reload-swiss')) return 'reload-swiss';
  if (s.includes('shooters world') || s.includes("shooter's world")) return 'shooters-world';
  if (s.includes('accurate')) return 'accurate';
  if (s.includes('ramshot')) return 'ramshot';
  if (s.includes('adi')) return 'adi';
  return slug(m);
}
