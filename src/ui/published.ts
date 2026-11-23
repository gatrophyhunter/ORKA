// Lazily loaded table of the makers' published loads (for the safety cross-check). Kept out of the main bundle.

import { useEffect, useState } from 'react';
import type { ValidationLoad } from '../data/schema';

interface Compact {
  c: string; p: string; w: number; bm: string; bt: string; t: string; ch: number; v: number;
  pr: number | null; pu: 'psi' | 'CUP' | 'bar' | null; b: number | null; oal: number | null;
  cs: string | null; pm: string | null; u: string | null; pg: number | string | null; cp: boolean | null;
}

const loaders = import.meta.glob('../data/published-loads.json', { import: 'default' }) as Record<string, () => Promise<Compact[]>>;
let cache: ValidationLoad[] | null = null;
let pending: Promise<ValidationLoad[]> | null = null;

function expand(r: Compact): ValidationLoad {
  return {
    cartridge: r.c, cartridgeId: r.c, bulletMfr: r.bm ?? '', bulletModel: r.bt ?? '', bulletWeightGr: r.w,
    caseBrand: r.cs, primer: r.pm, coalIn: r.oal ?? NaN, barrelLengthIn: r.b ?? NaN, powder: r.p, powderId: r.p,
    chargeGr: r.ch, velocityFps: r.v, pressure: r.pr, pressureUnit: r.pu, loadType: r.t, compressed: r.cp,
    sources: r.u ? [{ url: r.u, type: 'manufacturer', page: r.pg }] : [],
  };
}

export function loadPublished(): Promise<ValidationLoad[]> {
  if (cache) return Promise.resolve(cache);
  if (pending) return pending;
  const fn = Object.values(loaders)[0];
  pending = (fn ? fn() : Promise.resolve([] as Compact[]))
    .then((rows) => (cache = (rows ?? []).map(expand)))
    .catch(() => (cache = []));
  return pending;
}

export function usePublishedLoads(): ValidationLoad[] | null {
  const [rows, setRows] = useState<ValidationLoad[] | null>(cache);
  useEffect(() => {
    let live = true;
    if (!cache) loadPublished().then((r) => live && setRows(r));
    return () => {
      live = false;
    };
  }, []);
  return rows;
}
