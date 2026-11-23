// Shareable load links: the builder state is encoded in the URL fragment (never sent to any server).

import { EMPTY_BUILDER, type BuilderState } from './state';

const PREFIX = '#load=';

function toB64Url(s: string): string {
  const bytes = new TextEncoder().encode(s);
  let bin = '';
  bytes.forEach((b) => (bin += String.fromCharCode(b)));
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
function fromB64Url(s: string): string {
  const b64 = s.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((s.length + 3) % 4);
  const bin = atob(b64);
  const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

export function encodeBuilder(b: BuilderState, dbVersion: string): string {
  const payload = { v: 1, db: dbVersion, b: JSON.parse(JSON.stringify(b, (_k, val) => (typeof val === 'number' && !Number.isFinite(val) ? null : val))) };
  return PREFIX + toB64Url(JSON.stringify(payload));
}

export interface DecodedShare {
  builder: BuilderState;
  dbVersion: string | null;
}

/** Parses a share fragment. Returns null when the fragment is absent or malformed. */
export function decodeBuilder(hash: string): DecodedShare | null {
  if (!hash.startsWith(PREFIX)) return null;
  try {
    const obj = JSON.parse(fromB64Url(hash.slice(PREFIX.length)));
    if (!obj || obj.v !== 1 || typeof obj.b !== 'object') return null;
    const b = obj.b;
    const inputs = { ...EMPTY_BUILDER.inputs };
    for (const k of Object.keys(inputs) as (keyof typeof inputs)[]) {
      const val = b.inputs?.[k];
      inputs[k] = typeof val === 'number' && Number.isFinite(val) ? val : (EMPTY_BUILDER.inputs[k] as number);
    }
    const str = (v: unknown) => (typeof v === 'string' ? v : null);
    const builder: BuilderState = {
      ...EMPTY_BUILDER,
      cartridgeId: str(b.cartridgeId),
      // A shared link cannot vouch for where its capacity came from: treat it as an entered value (review finding).
      brassKey: 'measured',
      brassBrandId: null,
      capacityBasis: 'from a shared link — verify against your own brass',
      bulletId: str(b.bulletId),
      powderId: str(b.powderId),
      inputs,
      standard: b.standard === 'CIP' || b.standard === 'custom' ? b.standard : 'SAAMI',
      customLimitPsi: typeof b.customLimitPsi === 'number' ? b.customLimitPsi : NaN,
      marginPct: typeof b.marginPct === 'number' ? b.marginPct : EMPTY_BUILDER.marginPct,
    };
    return { builder, dbVersion: typeof obj.db === 'string' ? obj.db : null };
  } catch {
    return null;
  }
}
