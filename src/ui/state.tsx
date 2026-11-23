// App-wide state: user data, merged database, shared load builder, preferences.

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { loadUserData, mergedDb, saveUserData, type UserData } from '../data/db';
import type { Database } from '../data/schema';
import type { LoadInputs } from '../engine/adapter';
import { defaultShotStartPsi, DEFAULT_POWDER_TEMP_F, DEFAULT_PRESSURE_MARGIN_PCT } from '../engine/defaults';
import type { UnitSystem } from './format';

export type PressureStandard = 'SAAMI' | 'CIP' | 'custom';

export interface BuilderState {
  cartridgeId: string | null;
  /** Key of the selected capacity option (see capacityOptions) or 'measured'. */
  brassKey: string | null;
  /** Brand id of the selected brass, when known. */
  brassBrandId: string | null;
  /** Where the capacity value in inputs came from (shown to the user). */
  capacityBasis: string;
  bulletId: string | null;
  powderId: string | null;
  inputs: LoadInputs;
  standard: PressureStandard;
  customLimitPsi: number;
  marginPct: number;
}

export type ThemePref = 'auto' | 'light' | 'dark';
export interface Prefs {
  units: UnitSystem;
  theme: ThemePref;
  acknowledged: boolean;
}

export const EMPTY_INPUTS: LoadInputs = {
  boreDiameterIn: NaN,
  grooveDiameterIn: NaN,
  caseLengthIn: NaN,
  caseCapacityGrH2O: NaN,
  barrelLengthIn: NaN,
  bulletWeightGr: NaN,
  bulletDiameterIn: NaN,
  bulletLengthIn: NaN,
  boatTailLengthIn: 0,
  bulletBaseDiameterIn: 0,
  coalIn: NaN,
  chargeGr: NaN,
  powderTempF: DEFAULT_POWDER_TEMP_F,
  shotStartPsi: defaultShotStartPsi(),
};

export const EMPTY_BUILDER: BuilderState = {
  cartridgeId: null,
  brassKey: null,
  brassBrandId: null,
  capacityBasis: '',
  bulletId: null,
  powderId: null,
  inputs: EMPTY_INPUTS,
  standard: 'SAAMI',
  customLimitPsi: NaN,
  marginPct: DEFAULT_PRESSURE_MARGIN_PCT,
};

const BUILDER_KEY = 'orka.builder.v1';
const PREFS_KEY = 'orka.prefs.v1';

function readJson<T>(key: string): T | null {
  try {
    const s = globalThis.localStorage?.getItem(key);
    return s ? (JSON.parse(s) as T) : null;
  } catch {
    return null;
  }
}
function writeJson(key: string, v: unknown) {
  try {
    globalThis.localStorage?.setItem(key, JSON.stringify(v));
  } catch {
    /* storage unavailable: state just won't persist */
  }
}

/** JSON turns NaN into null; restore NaN for numeric inputs. */
export function reviveInputs(raw: Partial<Record<keyof LoadInputs, number | null>> | undefined): LoadInputs {
  const out = { ...EMPTY_INPUTS };
  if (!raw) return out;
  for (const k of Object.keys(EMPTY_INPUTS) as (keyof LoadInputs)[]) {
    const v = raw[k];
    if (typeof v === 'number' && Number.isFinite(v)) out[k] = v;
    else if (v === null) out[k] = EMPTY_INPUTS[k] === 0 ? 0 : NaN;
  }
  return out;
}

function loadBuilder(): BuilderState {
  const raw = readJson<Partial<BuilderState>>(BUILDER_KEY);
  if (!raw) return EMPTY_BUILDER;
  return {
    ...EMPTY_BUILDER,
    ...raw,
    inputs: reviveInputs(raw.inputs as never),
    customLimitPsi: typeof raw.customLimitPsi === 'number' ? raw.customLimitPsi : NaN,
    marginPct: typeof raw.marginPct === 'number' ? raw.marginPct : DEFAULT_PRESSURE_MARGIN_PCT,
  };
}

function loadPrefs(): Prefs {
  const raw = readJson<Partial<Prefs>>(PREFS_KEY);
  return { units: 'imperial', theme: 'auto', acknowledged: false, ...(raw ?? {}) };
}

export type TabId = 'predict' | 'ladder' | 'search' | 'calibrate' | 'database' | 'loads' | 'validation' | 'method';

interface AppCtx {
  db: Database;
  user: UserData;
  updateUser: (fn: (u: UserData) => UserData) => void;
  builder: BuilderState;
  setBuilder: (fn: (b: BuilderState) => BuilderState) => void;
  patchInputs: (p: Partial<LoadInputs>) => void;
  prefs: Prefs;
  setPrefs: (p: Partial<Prefs>) => void;
  tab: TabId;
  setTab: (t: TabId) => void;
  storageOk: boolean;
}

const Ctx = createContext<AppCtx | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserData>(() => loadUserData());
  const [builder, setBuilderState] = useState<BuilderState>(() => loadBuilder());
  const [prefs, setPrefsState] = useState<Prefs>(() => loadPrefs());
  const [tab, setTab] = useState<TabId>('predict');
  const [storageOk, setStorageOk] = useState(true);

  const db = useMemo(() => mergedDb(user), [user]);

  const updateUser = useCallback((fn: (u: UserData) => UserData) => {
    setUser((u) => {
      const next = fn(u);
      const ok = saveUserData(next);
      setStorageOk(ok);
      return next;
    });
  }, []);

  const setBuilder = useCallback((fn: (b: BuilderState) => BuilderState) => {
    setBuilderState((b) => {
      const next = fn(b);
      writeJson(BUILDER_KEY, next);
      return next;
    });
  }, []);

  const patchInputs = useCallback(
    (p: Partial<LoadInputs>) => setBuilder((b) => ({ ...b, inputs: { ...b.inputs, ...p } })),
    [setBuilder],
  );

  const setPrefs = useCallback((p: Partial<Prefs>) => {
    setPrefsState((cur) => {
      const next = { ...cur, ...p };
      writeJson(PREFS_KEY, next);
      return next;
    });
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    if (prefs.theme === 'auto') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', prefs.theme);
  }, [prefs.theme]);

  const value: AppCtx = { db, user, updateUser, builder, setBuilder, patchInputs, prefs, setPrefs, tab, setTab, storageOk };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error('useApp outside AppProvider');
  return c;
}
