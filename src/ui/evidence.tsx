// Verbatim source evidence for shipped records, kept in a separate lazily loaded file so the main bundle stays small.

import { useEffect, useState } from 'react';

type EvidenceMap = Record<string, Record<string, string>>;
const loaders = import.meta.glob('../data/db-evidence.json', { import: 'default' }) as Record<string, () => Promise<EvidenceMap>>;
let cache: EvidenceMap | null = null;
let pending: Promise<EvidenceMap> | null = null;

function load(): Promise<EvidenceMap> {
  if (cache) return Promise.resolve(cache);
  if (!pending) {
    const fn = Object.values(loaders)[0];
    pending = (fn ? fn() : Promise.resolve({} as EvidenceMap)).then((m) => (cache = m ?? {})).catch(() => (cache = {}));
  }
  return pending;
}

/** key = "<collection>:<id>" (brass cases use their index). */
export function Evidence({ k }: { k: string }) {
  const [text, setText] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    let live = true;
    const [col, ...rest] = k.split(':');
    const id = rest.join(':');
    load().then((m) => live && setText(m[col]?.[id] ?? null));
    return () => {
      live = false;
    };
  }, [k]);
  if (text === undefined) return <p className="small muted">Loading source evidence…</p>;
  if (text === null) return null;
  return (
    <div data-testid="db-evidence">
      <h4 style={{ marginTop: 12 }}>Notes and evidence (verbatim lines from the source)</h4>
      <pre className="small" style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{text}</pre>
    </div>
  );
}
