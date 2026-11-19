import type { ChartSpec, Row } from "./types";

export const PALETTE = ["#3b6cf6", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#06b6d4", "#ec4899", "#84cc16"];

export function formatNumber(v: unknown): string {
  if (typeof v !== "number") return v === null || v === undefined ? "" : String(v);
  const abs = Math.abs(v);
  if (abs >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (abs >= 1e4) return `${(v / 1e3).toFixed(1)}K`;
  return Number.isInteger(v) ? v.toLocaleString() : v.toFixed(2);
}

/** Shorten ISO timestamps ("2026-01-01T00:00:00") to dates for axis labels. */
export function formatLabel(v: unknown): string {
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}T00:00:00/.test(v)) return v.slice(0, 10);
  return v === null || v === undefined ? "" : String(v);
}

/** Pick sensible x / y columns when a spec doesn't name valid ones. */
export function resolveAxes(spec: ChartSpec, columns: string[], rows: Row[]): { x: string; y: string[] } {
  const numeric = columns.filter((c) => rows.some((r) => typeof r[c] === "number"));
  const x = spec.x && columns.includes(spec.x) ? spec.x : columns.find((c) => !numeric.includes(c)) ?? columns[0];
  const y = (spec.y || []).filter((c) => columns.includes(c));
  return { x, y: y.length ? y : numeric.filter((c) => c !== x).slice(0, 3) };
}

export interface HeatmapData { xs: string[]; ys: string[]; cells: Map<string, number>; min: number; max: number }

export function toHeatmap(rows: Row[], x: string, y: string, value: string): HeatmapData {
  const xs: string[] = [];
  const ys: string[] = [];
  const cells = new Map<string, number>();
  let min = Infinity;
  let max = -Infinity;
  for (const r of rows) {
    const xv = formatLabel(r[x]);
    const yv = formatLabel(r[y]);
    const v = Number(r[value]);
    if (!xs.includes(xv)) xs.push(xv);
    if (!ys.includes(yv)) ys.push(yv);
    if (Number.isFinite(v)) {
      cells.set(`${xv}\u0000${yv}`, v);
      min = Math.min(min, v);
      max = Math.max(max, v);
    }
  }
  return { xs, ys, cells, min: Number.isFinite(min) ? min : 0, max: Number.isFinite(max) ? max : 0 };
}

/** 0..1 -> light-to-dark blue. */
export function heatColor(t: number): string {
  const clamped = Math.max(0, Math.min(1, t));
  const light = 95 - clamped * 55;
  return `hsl(222, 85%, ${light}%)`;
}

export function toFunnel(rows: Row[], x: string, y: string) {
  return rows.map((r, i) => ({
    name: formatLabel(r[x]),
    value: Number(r[y]) || 0,
    fill: PALETTE[i % PALETTE.length],
  }));
}

export function toCSV(columns: string[], rows: Row[]): string {
  const esc = (v: unknown) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [columns.join(","), ...rows.map((r) => columns.map((c) => esc(r[c])).join(","))].join("\n");
}
