// Lazily loaded table of the makers' published loads (for the safety cross-check). Kept out of the main bundle.

import { useEffect, useState } from 'react';
import type { ValidationLoad } from '../data/schema';

interface Compact {
  c: string; p: string; w: number; bm: string; bt: string; t: string; ch: number; v: number;
  pr: number | null; pu: 'psi' | 'CUP' | 'bar' | null; b: number | null; oal: number | null;
  cs: string | null; pm: string | null; u: string | null; pg: number | string | null; cp: boolean | null;
  cn?: string | null;
}

interface Packed {
  v: 1;
  s: string[];
  r: (number | null)[][];
}

const loaders = import.meta.glob('../data/published-loads.json', { import: 'default' }) as Record<string, () => Promise<Packed | Compact[]>>;

function unpack(p: Packed | Compact[]): Compact[] {
  if (Array.isArray(p)) return p;
  if (!p || !Array.isArray(p.r)) return [];
  const S = (i: number | null) => (i === null || i < 0 ? null : p.s[i] ?? null);
  return p.r.map((x) => ({
    c: S(x[0]) as string, p: S(x[1]) as string, w: x[2] as number, bm: S(x[3]) ?? '', bt: S(x[4]) ?? '', t: S(x[5]) ?? 'other',
    ch: x[6] as number, v: x[7] as number, pr: x[8], pu: S(x[9]) as Compact['pu'], b: x[10], oal: x[11], cs: S(x[12]), pm: S(x[13]),
    u: S(x[14]), pg: x[15], cp: x[16] === -1 ? null : x[16] === 1, cn: x.length > 17 ? S(x[17]) : null,
  }));
}
let cache: ValidationLoad[] | null = null;
let pending: Promise<ValidationLoad[]> | null = null;

function expand(r: Compact): ValidationLoad {
  return {
    cartridge: r.cn ?? r.c, cartridgeId: r.c, bulletMfr: r.bm ?? '', bulletModel: r.bt ?? '', bulletWeightGr: r.w,
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
    .then((data) => (cache = unpack(data).map(expand)))
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
