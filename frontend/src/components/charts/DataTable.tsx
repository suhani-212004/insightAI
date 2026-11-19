import { formatLabel } from "@/lib/chartData";
import type { Row } from "@/lib/types";

export function DataTable({ columns, rows, highlight }: { columns: string[]; rows: Row[]; highlight?: Set<number> }) {
  return (
    <div className="h-full overflow-auto">
      <table className="w-full text-left text-xs">
        <thead className="sticky top-0 bg-slate-50 dark:bg-slate-800">
          <tr>{columns.map((c) => <th key={c} className="whitespace-nowrap px-3 py-2 font-semibold">{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={highlight?.has(i) ? "bg-amber-50 dark:bg-amber-500/10" : "border-t border-slate-100 dark:border-slate-800"}>
              {columns.map((c) => <td key={c} className="whitespace-nowrap px-3 py-1.5 tabular-nums">{formatLabel(r[c])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
