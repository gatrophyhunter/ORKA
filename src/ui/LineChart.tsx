// Minimal responsive SVG line chart (no chart library).

import { useEffect, useRef, useState } from 'react';

export interface Series {
  name: string;
  color: string;
  points: { x: number; y: number }[];
  dashed?: boolean;
}

export interface RefLine {
  y: number;
  label: string;
  color: string;
}

export function niceTicks(min: number, max: number, count = 5): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [];
  if (min === max) {
    const d = Math.abs(min) || 1;
    min -= d * 0.5;
    max += d * 0.5;
  }
  const span = max - min;
  const raw = span / Math.max(1, count);
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
  const start = Math.ceil(min / step - 1e-9) * step;
  const out: number[] = [];
  for (let v = start; v <= max + step * 1e-9; v += step) out.push(+v.toPrecision(12));
  return out;
}

function downsample(pts: { x: number; y: number }[], max = 500) {
  if (pts.length <= max) return pts;
  const k = Math.ceil(pts.length / max);
  const out = pts.filter((_, i) => i % k === 0);
  if (out[out.length - 1] !== pts[pts.length - 1]) out.push(pts[pts.length - 1]);
  return out;
}

export function LineChart(props: {
  title: string;
  series: Series[];
  xLabel: string;
  yLabel: string;
  refLines?: RefLine[];
  height?: number;
  xFmt?: (v: number) => string;
  yFmt?: (v: number) => string;
  yMin0?: boolean;
  testId?: string;
}) {
  // Measure the container so text stays at its nominal pixel size on narrow screens.
  const ref = useRef<HTMLElement | null>(null);
  const [cw, setCw] = useState(560);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w && Math.abs(w - cw) > 4) setCw(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [cw]);
  const W = Math.max(280, Math.round(cw));
  const H = props.height ?? (W < 420 ? 220 : 240);
  const m = { l: 58, r: 14, t: 10, b: 40 };
  const all = props.series.flatMap((s) => s.points).filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));
  if (!all.length) {
    return (
      <figure className="chart" style={{ margin: 0 }} ref={ref as never}>
        <div className="title">{props.title}</div>
        <div className="empty">No data</div>
      </figure>
    );
  }
  let xMin = Math.min(...all.map((p) => p.x));
  let xMax = Math.max(...all.map((p) => p.x));
  let yMin = props.yMin0 === false ? Math.min(...all.map((p) => p.y)) : Math.min(0, ...all.map((p) => p.y));
  let yMax = Math.max(...all.map((p) => p.y), ...(props.refLines ?? []).map((r) => r.y));
  if (xMin === xMax) xMax = xMin + 1;
  if (yMin === yMax) yMax = yMin + 1;
  yMax += (yMax - yMin) * 0.05;
  const xt = niceTicks(xMin, xMax, 5);
  const yt = niceTicks(yMin, yMax, 5);
  xMin = Math.min(xMin, xt[0] ?? xMin);
  yMin = Math.min(yMin, yt[0] ?? yMin);
  const sx = (x: number) => m.l + ((x - xMin) / (xMax - xMin)) * (W - m.l - m.r);
  const sy = (y: number) => H - m.b - ((y - yMin) / (yMax - yMin)) * (H - m.t - m.b);
  const xf = props.xFmt ?? ((v: number) => v.toLocaleString('en-US', { maximumFractionDigits: 3 }));
  const yf = props.yFmt ?? ((v: number) => v.toLocaleString('en-US', { maximumFractionDigits: 2 }));
  return (
    <figure className="chart" style={{ margin: 0 }} data-testid={props.testId} ref={ref as never}>
      <div className="title">{props.title}</div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${props.title}: ${props.yLabel} versus ${props.xLabel}`}>
        {yt.map((v) => (
          <g key={`y${v}`}>
            <line x1={m.l} x2={W - m.r} y1={sy(v)} y2={sy(v)} stroke="var(--chart-grid)" strokeWidth={1} />
            <text x={m.l - 6} y={sy(v) + 4} textAnchor="end" fontSize={11} fill="var(--text-muted)">
              {yf(v)}
            </text>
          </g>
        ))}
        {xt.map((v) => (
          <g key={`x${v}`}>
            <line x1={sx(v)} x2={sx(v)} y1={m.t} y2={H - m.b} stroke="var(--chart-grid)" strokeWidth={1} />
            <text x={sx(v)} y={H - m.b + 15} textAnchor="middle" fontSize={11} fill="var(--text-muted)">
              {xf(v)}
            </text>
          </g>
        ))}
        <line x1={m.l} x2={W - m.r} y1={H - m.b} y2={H - m.b} stroke="var(--border)" />
        <line x1={m.l} x2={m.l} y1={m.t} y2={H - m.b} stroke="var(--border)" />
        <text x={(m.l + W - m.r) / 2} y={H - 6} textAnchor="middle" fontSize={11.5} fill="var(--text-muted)">
          {props.xLabel}
        </text>
        <text x={12} y={(m.t + H - m.b) / 2} textAnchor="middle" fontSize={11.5} fill="var(--text-muted)" transform={`rotate(-90 12 ${(m.t + H - m.b) / 2})`}>
          {props.yLabel}
        </text>
        {(props.refLines ?? []).map((r) => (
          <g key={r.label}>
            <line x1={m.l} x2={W - m.r} y1={sy(r.y)} y2={sy(r.y)} stroke={r.color} strokeDasharray="6 4" strokeWidth={1.5} />
            <text x={W - m.r - 4} y={sy(r.y) - 4} textAnchor="end" fontSize={11} fill={r.color}>
              {r.label}
            </text>
          </g>
        ))}
        {props.series.map((s) => {
          const pts = downsample(s.points.filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y)));
          const d = pts.map((p, i) => `${i ? 'L' : 'M'}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join('');
          return <path key={s.name} d={d} fill="none" stroke={s.color} strokeWidth={2} strokeDasharray={s.dashed ? '5 4' : undefined} />;
        })}
      </svg>
      {props.series.length > 1 && (
        <figcaption className="legend">
          {props.series.map((s) => (
            <span key={s.name}>
              <i style={{ background: s.color }} />
              {s.name}
            </span>
          ))}
        </figcaption>
      )}
    </figure>
  );
}
