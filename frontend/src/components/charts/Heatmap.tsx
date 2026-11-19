"use client";

import { formatNumber, heatColor, toHeatmap } from "@/lib/chartData";
import type { Row } from "@/lib/types";

/** Recharts has no heatmap, so this is a small CSS-grid one. */
export function Heatmap({ rows, x, y, value }: { rows: Row[]; x: string; y: string; value: string }) {
  const { xs, ys, cells, min, max } = toHeatmap(rows, x, y, value);
  const span = max - min || 1;
  return (
    <div className="h-full overflow-auto p-1" data-testid="chart-heatmap">
      <div className="grid gap-0.5 text-xs" style={{ gridTemplateColumns: `minmax(70px, auto) repeat(${xs.length}, minmax(48px, 1fr))` }}>
        <div />
        {xs.map((xv) => <div key={xv} className="truncate px-1 pb-1 text-center font-medium text-slate-500" title={xv}>{xv}</div>)}
        {ys.map((yv) => (
          <div key={yv} className="contents">
            <div className="truncate pr-2 text-right font-medium leading-8 text-slate-500" title={yv}>{yv}</div>
            {xs.map((xv) => {
              const v = cells.get(`${xv}\u0000${yv}`);
              const t = v === undefined ? 0 : (v - min) / span;
              return (
                <div
                  key={xv}
                  title={`${yv} · ${xv}: ${v === undefined ? "—" : formatNumber(v)}`}
                  className="flex h-8 items-center justify-center rounded"
                  style={{ background: v === undefined ? "transparent" : heatColor(t), color: t > 0.55 ? "#fff" : "#1e293b" }}
                >
                  {v === undefined ? "" : formatNumber(v)}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
