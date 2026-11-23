// Shared UI building blocks.

import { useEffect, useId, useMemo, useRef, useState, type ReactNode, type KeyboardEvent } from 'react';
import type { ModelStatus } from '../data/schema';
import { decimalsOf, fromDisplay, toDisplay, unitOf, type InputQty } from './format';
import { useApp } from './state';

export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

const STATUS_TEXT: Record<ModelStatus, string> = {
  calibrated: 'calibrated',
  'user-calibrated': 'my calibration',
  estimated: 'estimate',
  none: 'no model',
};

const STATUS_TITLE: Record<ModelStatus, string> = {
  calibrated: 'Burn model fitted to published pressure-tested load data.',
  'user-calibrated': 'Burn model from your own calibration or manually entered parameters.',
  estimated: 'Interpolated from a burn-rate chart — not for load development.',
  none: 'No burn model: calibrate this powder or enter parameters before predicting.',
};

export function StatusChip({ status }: { status: ModelStatus }) {
  return (
    <span className={`chip ${status}`} title={STATUS_TITLE[status]}>
      {status === 'estimated' ? '⚠ ' : ''}
      {STATUS_TEXT[status]}
    </span>
  );
}

/** Fit quality of a calibrated model: RMS pressure error of the fit (and held-out error when measured). */
export function FitGrade({ model }: { model?: { status: string; calibration?: { grade?: string; rmsPressurePct?: number | null; heldOutPressurePct?: number | null } } | null }) {
  const c = model?.calibration;
  if (!model || (model.status !== 'calibrated' && model.status !== 'user-calibrated') || !c || typeof c.rmsPressurePct !== 'number') return null;
  const grade = c.grade ?? (c.rmsPressurePct <= 10 ? 'good' : c.rmsPressurePct <= 20 ? 'fair' : 'poor');
  const title = `Fit to published pressure data: RMS error ${c.rmsPressurePct.toFixed(1)} %${typeof c.heldOutPressurePct === 'number' ? `; median error on held-out cartridges ${c.heldOutPressurePct.toFixed(1)} %` : ''}.`;
  return (
    <span className={`chip fit-${grade}`} title={title} data-testid="fit-grade">
      fit ±{c.rmsPressurePct.toFixed(0)} % · {grade}
    </span>
  );
}

export function EstimateWarning({ status }: { status: ModelStatus }) {
  if (status !== 'estimated') return null;
  return (
    <div className="alert warn" role="note">
      <strong>Estimate:</strong> this powder's model is interpolated from a burn-rate chart — not for load development. Treat every number as a rough guess.
    </div>
  );
}

/** Unit-aware number input. `value` is in the stored (imperial) unit; the user types in the display unit. */
export function NumberField(props: {
  label: string;
  qty: InputQty;
  value: number;
  onChange: (v: number) => void;
  hint?: ReactNode;
  error?: string | null;
  step?: number;
  digits?: number;
  unitOverride?: string;
  testId?: string;
  required?: boolean;
}) {
  const { prefs } = useApp();
  const sys = prefs.units;
  const id = useId();
  const digits = props.digits ?? decimalsOf(props.qty, sys);
  const shown = Number.isFinite(props.value) ? +toDisplay(props.qty, sys, props.value).toFixed(digits) : NaN;
  const [text, setText] = useState(Number.isFinite(shown) ? String(shown) : '');
  const [focused, setFocused] = useState(false);
  useEffect(() => {
    if (!focused) setText(Number.isFinite(shown) ? String(shown) : '');
  }, [shown, focused]);
  const unit = props.unitOverride ?? unitOf(props.qty, sys);
  const invalid = !!props.error || (props.required && !Number.isFinite(props.value));
  return (
    <div className="field">
      <label htmlFor={id}>{props.label}</label>
      <div className={`input-wrap${invalid ? ' invalid' : ''}`}>
        <input
          id={id}
          type="text"
          inputMode="decimal"
          autoComplete="off"
          data-testid={props.testId}
          value={text}
          aria-invalid={invalid || undefined}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onChange={(e) => {
            const t = e.target.value;
            setText(t);
            const n = Number(t.replace(',', '.'));
            if (t.trim() === '') props.onChange(NaN);
            else if (Number.isFinite(n)) props.onChange(fromDisplay(props.qty, sys, n));
          }}
        />
        {unit && <span className="unit">{unit}</span>}
      </div>
      {props.error && <span className="error">{props.error}</span>}
      {props.hint && <span className="hint">{props.hint}</span>}
    </div>
  );
}

/** Plain number input with a fixed unit label (no unit-system conversion). */
export function PlainNumber(props: { label: string; value: number; onChange: (v: number) => void; unit?: string; hint?: ReactNode; testId?: string; min?: number; max?: number }) {
  const id = useId();
  const clean = (v: number) => (Number.isFinite(v) ? String(+v.toPrecision(12)) : '');
  const [text, setText] = useState(clean(props.value));
  const [focused, setFocused] = useState(false);
  useEffect(() => {
    if (!focused) setText(clean(props.value));
  }, [props.value, focused]);
  return (
    <div className="field">
      <label htmlFor={id}>{props.label}</label>
      <div className="input-wrap">
        <input
          id={id}
          type="text"
          inputMode="decimal"
          data-testid={props.testId}
          value={text}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onChange={(e) => {
            setText(e.target.value);
            const n = Number(e.target.value.replace(',', '.'));
            if (e.target.value.trim() === '') props.onChange(NaN);
            else if (Number.isFinite(n)) props.onChange(n);
          }}
        />
        {props.unit && <span className="unit">{props.unit}</span>}
      </div>
      {props.hint && <span className="hint">{props.hint}</span>}
    </div>
  );
}

export function TextField(props: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; testId?: string; hint?: ReactNode }) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{props.label}</label>
      <input id={id} type="text" value={props.value} placeholder={props.placeholder} data-testid={props.testId} onChange={(e) => props.onChange(e.target.value)} />
      {props.hint && <span className="hint">{props.hint}</span>}
    </div>
  );
}

export function SelectField<T extends string>(props: { label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; testId?: string; hint?: ReactNode }) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{props.label}</label>
      <select id={id} value={props.value} data-testid={props.testId} onChange={(e) => props.onChange(e.target.value as T)}>
        {props.options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {props.hint && <span className="hint">{props.hint}</span>}
    </div>
  );
}

export interface PickerItem {
  id: string;
  label: string;
  sub?: string;
  right?: ReactNode;
  /** Extra text that search should match. */
  keywords?: string;
}

/** Accessible searchable combobox for large lists. */
export function SearchPicker(props: {
  label: string;
  items: PickerItem[];
  value: string | null;
  onChange: (id: string | null) => void;
  placeholder?: string;
  emptyText?: string;
  testId?: string;
  limit?: number;
}) {
  const id = useId();
  const listId = `${id}-list`;
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const blurTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const selected = props.items.find((i) => i.id === props.value) ?? null;
  const limit = props.limit ?? 60;

  const filtered = useMemo(() => {
    const tokens = query.toLowerCase().split(/\s+/).filter(Boolean);
    if (!tokens.length) return props.items;
    return props.items.filter((it) => {
      const hay = `${it.label} ${it.sub ?? ''} ${it.keywords ?? ''}`.toLowerCase();
      return tokens.every((t) => hay.includes(t));
    });
  }, [props.items, query]);
  const shown = filtered.slice(0, limit);

  const choose = (it: PickerItem) => {
    props.onChange(it.id);
    setOpen(false);
    setQuery('');
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setOpen(true);
      setActive((a) => Math.min(a + 1, shown.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === 'Enter') {
      if (open && shown[active]) {
        e.preventDefault();
        choose(shown[active]);
      }
    } else if (e.key === 'Escape') {
      setOpen(false);
      setQuery('');
    }
  };

  return (
    <div className="field picker">
      <label htmlFor={id}>{props.label}</label>
      <input
        id={id}
        type="search"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && shown[active] ? `${id}-opt-${active}` : undefined}
        data-testid={props.testId}
        autoComplete="off"
        placeholder={selected ? selected.label : props.placeholder ?? 'Search…'}
        value={query}
        onFocus={() => {
          if (blurTimer.current) clearTimeout(blurTimer.current);
          setOpen(true);
          setActive(0);
        }}
        onBlur={() => {
          blurTimer.current = setTimeout(() => {
            setOpen(false);
            setQuery('');
          }, 150);
        }}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          setActive(0);
        }}
        onKeyDown={onKey}
      />
      {selected && (
        <div className="picker-selected">
          <span>
            Selected: <strong>{selected.label}</strong>
            {selected.sub ? <span className="muted"> · {selected.sub}</span> : null}
          </span>
          {selected.right}
          <button type="button" className="btn small" onClick={() => props.onChange(null)} aria-label={`Clear ${props.label}`}>
            clear
          </button>
        </div>
      )}
      {open && (
        <ul className="picker-list" id={listId} role="listbox">
          {shown.length === 0 && <li className="picker-more">{props.emptyText ?? 'No matches.'}</li>}
          {shown.map((it, i) => (
            <li
              key={it.id}
              id={`${id}-opt-${i}`}
              role="option"
              aria-selected={i === active}
              className="picker-item"
              onMouseDown={(e) => {
                e.preventDefault();
                choose(it);
              }}
              onMouseEnter={() => setActive(i)}
            >
              <span>
                <div>{it.label}</div>
                {it.sub && <div className="sub">{it.sub}</div>}
              </span>
              {it.right}
            </li>
          ))}
          {filtered.length > shown.length && (
            <li className="picker-more">
              Showing {shown.length} of {filtered.length} — keep typing to narrow.
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

export function Tile(props: { k: string; v: ReactNode; s?: ReactNode; state?: 'ok' | 'warn' | 'danger'; big?: boolean; testId?: string; children?: ReactNode }) {
  return (
    <div className={`tile${props.big ? ' big' : ''}${props.state ? ` state-${props.state}` : ''}`} data-testid={props.testId}>
      <div className="k">{props.k}</div>
      <div className="v">{props.v}</div>
      {props.s && <div className="s">{props.s}</div>}
      {props.children}
    </div>
  );
}

export interface Column<T> {
  key: string;
  label: string;
  render: (row: T) => ReactNode;
  sortValue?: (row: T) => number | string | null;
  num?: boolean;
}

/** Paginated, sortable table. Pagination keeps thousands of rows responsive. */
export function DataTable<T>(props: {
  rows: T[];
  columns: Column<T>[];
  rowKey: (r: T) => string;
  onRowClick?: (r: T) => void;
  selectedKey?: string | null;
  rowClass?: (r: T) => string;
  pageSize?: number;
  initialSort?: { key: string; dir: 1 | -1 };
  testId?: string;
  caption?: string;
}) {
  const pageSize = props.pageSize ?? 50;
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(props.initialSort ?? null);
  const sorted = useMemo(() => {
    if (!sort) return props.rows;
    const col = props.columns.find((c) => c.key === sort.key);
    if (!col?.sortValue) return props.rows;
    const sv = col.sortValue;
    return [...props.rows].sort((a, b) => {
      const x = sv(a);
      const y = sv(b);
      if (x === y) return 0;
      if (x === null || x === undefined || (typeof x === 'number' && !Number.isFinite(x))) return 1;
      if (y === null || y === undefined || (typeof y === 'number' && !Number.isFinite(y))) return -1;
      return (x < y ? -1 : 1) * sort.dir;
    });
  }, [props.rows, props.columns, sort]);
  const pages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const p = Math.min(page, pages - 1);
  const slice = sorted.slice(p * pageSize, (p + 1) * pageSize);
  useEffect(() => setPage(0), [props.rows.length]);
  return (
    <div>
      <div className="table-wrap">
        <table className="data" data-testid={props.testId}>
          {props.caption && <caption className="sr-only">{props.caption}</caption>}
          <thead>
            <tr>
              {props.columns.map((c) => {
                const active = sort?.key === c.key;
                return (
                  <th
                    key={c.key}
                    className={`${c.num ? 'num ' : ''}${c.sortValue ? 'sortable' : ''}`}
                    aria-sort={active ? (sort!.dir === 1 ? 'ascending' : 'descending') : undefined}
                    onClick={c.sortValue ? () => setSort((s) => (s?.key === c.key ? { key: c.key, dir: (s.dir * -1) as 1 | -1 } : { key: c.key, dir: 1 })) : undefined}
                    tabIndex={c.sortValue ? 0 : undefined}
                    onKeyDown={
                      c.sortValue
                        ? (e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              setSort((s) => (s?.key === c.key ? { key: c.key, dir: (s.dir * -1) as 1 | -1 } : { key: c.key, dir: 1 }));
                            }
                          }
                        : undefined
                    }
                  >
                    {c.label}
                    {active ? (sort!.dir === 1 ? ' ▲' : ' ▼') : ''}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {slice.map((r) => {
              const k = props.rowKey(r);
              const cls = [props.onRowClick ? 'clickable' : '', props.selectedKey === k ? 'selected' : '', props.rowClass?.(r) ?? ''].join(' ').trim();
              return (
                <tr
                  key={k}
                  className={cls}
                  onClick={props.onRowClick ? () => props.onRowClick!(r) : undefined}
                  tabIndex={props.onRowClick ? 0 : undefined}
                  onKeyDown={props.onRowClick ? (e) => (e.key === 'Enter' ? props.onRowClick!(r) : undefined) : undefined}
                >
                  {props.columns.map((c) => (
                    <td key={c.key} className={c.num ? 'num' : undefined}>
                      {c.render(r)}
                    </td>
                  ))}
                </tr>
              );
            })}
            {slice.length === 0 && (
              <tr>
                <td colSpan={props.columns.length} className="muted">
                  No rows.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <div className="pager">
          <span className="muted">
            {sorted.length.toLocaleString('en-US')} rows · page {p + 1} / {pages}
          </span>
          <button className="btn small" disabled={p === 0} onClick={() => setPage(0)}>
            «
          </button>
          <button className="btn small" disabled={p === 0} onClick={() => setPage(p - 1)}>
            ‹ Prev
          </button>
          <button className="btn small" disabled={p >= pages - 1} onClick={() => setPage(p + 1)}>
            Next ›
          </button>
          <button className="btn small" disabled={p >= pages - 1} onClick={() => setPage(pages - 1)}>
            »
          </button>
        </div>
      )}
    </div>
  );
}

export function Modal(props: { title: string; children: ReactNode; labelledBy?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, []);
  return (
    <div className="modal-backdrop">
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title" tabIndex={-1} ref={ref}>
        <h2 id="modal-title">{props.title}</h2>
        {props.children}
      </div>
    </div>
  );
}

export function ErrorList({ errors, title }: { errors: string[]; title?: string }) {
  if (!errors.length) return null;
  return (
    <div className="alert danger" role="alert" data-testid="input-errors">
      <strong>{title ?? 'Cannot run yet:'}</strong>
      <ul>
        {errors.map((e) => (
          <li key={e}>{e}</li>
        ))}
      </ul>
    </div>
  );
}

export function SourceLinks({ sources }: { sources: { url: string; type: string; fields?: string[] }[] }) {
  if (!sources?.length) return <span className="muted">No sources recorded.</span>;
  return (
    <ul style={{ margin: 0, paddingLeft: 18 }}>
      {sources.map((s, i) => (
        <li key={i}>
          {/^https?:\/\//.test(s.url) ? (
            <a href={s.url} target="_blank" rel="noopener noreferrer">
              {s.url}
            </a>
          ) : (
            <span>{s.url}</span>
          )}{' '}
          <span className="muted small">
            ({s.type}
            {s.fields?.length ? `: ${s.fields.join(', ')}` : ''})
          </span>
        </li>
      ))}
    </ul>
  );
}
