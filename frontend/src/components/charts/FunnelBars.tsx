import { PALETTE, formatNumber, toFunnel } from "@/lib/chartData";
import type { Row } from "@/lib/types";

/** Centered bars, one per stage, with conversion % from the previous stage. */
export function FunnelBars({ rows, x, y }: { rows: Row[]; x: string; y: string }) {
  const stages = toFunnel(rows, x, y);
  const top = Math.max(...stages.map((s) => s.value), 1);
  return (
    <div className="flex h-full flex-col justify-center gap-2 px-2" data-testid="chart-funnel">
      {stages.map((s, i) => {
        const prev = i > 0 ? stages[i - 1].value : null;
        const pct = prev ? (s.value / prev) * 100 : null;
        return (
          <div key={s.name} className="grid grid-cols-[90px_1fr_64px] items-center gap-2 text-xs">
            <span className="truncate text-right font-medium text-slate-600 dark:text-slate-300" title={s.name}>{s.name}</span>
            <div className="flex justify-center">
              <div
                className="flex h-7 min-w-[2.5rem] items-center justify-center rounded-md font-semibold text-white"
                style={{ width: `${Math.max((s.value / top) * 100, 4)}%`, background: PALETTE[i % PALETTE.length] }}
              >
                {formatNumber(s.value)}
              </div>
            </div>
            <span className="tabular-nums text-slate-500">{pct === null ? "" : `${pct.toFixed(1)}%`}</span>
          </div>
        );
      })}
    </div>
  );
}
