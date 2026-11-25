// Lazily loaded table of the makers' published loads (for the safety cross-check). Kept out of the main bundle.

import { useCallback, useEffect, useState } from 'react';
import type { ValidationLoad } from '../data/schema';

export interface Compact {
  c: string; p: string; w: number; bm: string; bt: string; t: string; ch: number; v: number;
  pr: number | null; pu: 'psi' | 'CUP' | 'bar' | null; b: number | null; oal: number | null;
  cs: string | null; pm: string | null; u: string | null; pg: number | string | null; cp: boolean | null;
  cn?: string | null;
}

export interface Packed {
  v: 1;
  s: string[];
  r: (number | null)[][];
}

const loaders = import.meta.glob('../data/published-loads.json', { import: 'default' }) as Record<string, () => Promise<Packed | Compact[]>>;

function unpack(p: Packed | Compact[]): Compact[] {
  if (Array.isArray(p)) return p;
  // A malformed file counts as a failed load, not as "no published data".
  if (!p || !Array.isArray(p.r) || !Array.isArray(p.s)) throw new Error('published loads: unexpected format');
  const S = (i: number | null) => (i === null || i < 0 ? null : p.s[i] ?? null);
  return p.r.map((x) => ({
    c: S(x[0]) as string, p: S(x[1]) as string, w: x[2] as number, bm: S(x[3]) ?? '', bt: S(x[4]) ?? '', t: S(x[5]) ?? 'other',
    ch: x[6] as number, v: x[7] as number, pr: x[8], pu: S(x[9]) as Compact['pu'], b: x[10], oal: x[11], cs: S(x[12]), pm: S(x[13]),
    u: S(x[14]), pg: x[15], cp: x[16] === -1 ? null : x[16] === 1, cn: x.length > 17 ? S(x[17]) : null,
  }));
}

function expand(r: Compact): ValidationLoad {
  return {
    cartridge: r.cn ?? r.c, cartridgeId: r.c, bulletMfr: r.bm ?? '', bulletModel: r.bt ?? '', bulletWeightGr: r.w,
    caseBrand: r.cs, primer: r.pm, coalIn: r.oal ?? NaN, barrelLengthIn: r.b ?? NaN, powder: r.p, powderId: r.p,
    chargeGr: r.ch, velocityFps: r.v, pressure: r.pr, pressureUnit: r.pu, loadType: r.t, compressed: r.cp,
    sources: r.u ? [{ url: r.u, type: 'manufacturer', page: r.pg }] : [],
  };
}

export interface PublishedStore {
  /** Loads the table; resolves to [] on failure (check failed()). Only a successful load is cached, so a failure can be retried. */
  load(): Promise<ValidationLoad[]>;
  cached(): ValidationLoad[] | null;
  /** True when the last load attempt failed (network error, stale chunk after a redeploy, missing or malformed file). */
  failed(): boolean;
}

export function createPublishedStore(fetchData: (() => Promise<Packed | Compact[]>) | undefined): PublishedStore {
  let cache: ValidationLoad[] | null = null;
  let failed = false;
  let pending: Promise<ValidationLoad[]> | null = null;
  return {
    cached: () => cache,
    failed: () => failed,
    load() {
      if (cache) return Promise.resolve(cache);
      if (pending) return pending;
      pending = (fetchData ? fetchData() : Promise.reject(new Error('published loads: file not in this build')))
        .then((data) => {
          const rows = unpack(data).map(expand);
          cache = rows;
          failed = false;
          return rows;
        })
        .catch(() => {
          failed = true;
          return [] as ValidationLoad[];
        })
        .finally(() => {
          pending = null;
        });
      return pending;
    },
  };
}

const store = createPublishedStore(Object.values(loaders)[0]);

/** True when the published-load table could not be loaded. */
export const publishedLoadFailed = () => store.failed();
export const loadPublished = () => store.load();

/** Published loads (null while loading; [] with failed = true when loading failed) and a retry for a failed load. */
export function usePublished(): { rows: ValidationLoad[] | null; failed: boolean; retry: () => void } {
  const [state, setState] = useState<{ rows: ValidationLoad[] | null; failed: boolean }>(() => ({ rows: store.cached(), failed: false }));
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    if (!store.cached()) store.load().then((r) => live && setState({ rows: r, failed: store.failed() }));
    return () => {
      live = false;
    };
  }, [attempt]);
  const retry = useCallback(() => {
    setState({ rows: null, failed: false });
    setAttempt((a) => a + 1);
  }, []);
  return { ...state, retry };
}

export function usePublishedLoads(): ValidationLoad[] | null {
  return usePublished().rows;
}
