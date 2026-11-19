"use client";

import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart,
  Pie, PieChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis,
} from "recharts";
import { PALETTE, formatLabel, formatNumber, resolveAxes } from "@/lib/chartData";
import type { ChartSpec, Row } from "@/lib/types";
import { DataTable } from "./DataTable";
import { FunnelBars } from "./FunnelBars";
import { Heatmap } from "./Heatmap";

interface Props { spec: ChartSpec; columns: string[]; rows: Row[]; height?: number | string; animate?: boolean }

const axisProps = { tick: { fontSize: 11, fill: "currentColor" }, stroke: "currentColor", strokeOpacity: 0.25 };

/** Renders any of the 6 chart types (plus a table fallback) from a ChartSpec + rows. */
export function ChartRenderer({ spec, columns, rows, height = "100%", animate = true }: Props) {
  if (!rows.length) return <p className="p-4 text-sm text-slate-500">No rows returned.</p>;
  const { x, y } = resolveAxes(spec, columns, rows);
  const data = rows.map((r) => ({ ...r, [x]: formatLabel(r[x]) }));

  if (spec.type === "table" || (!y.length && spec.type !== "heatmap")) {
    return <DataTable columns={columns} rows={rows} />;
  }

  if (spec.type === "heatmap") {
    const yAxis = spec.y?.[0] && columns.includes(spec.y[0]) ? spec.y[0] : columns.find((c) => c !== x) ?? x;
    const value = spec.value && columns.includes(spec.value) ? spec.value : y[y.length - 1];
    return <Heatmap rows={rows} x={x} y={yAxis} value={value} />;
  }

  if (spec.type === "funnel") return <FunnelBars rows={rows} x={x} y={y[0]} />;

  return (
    <div className="h-full w-full text-slate-500" style={{ height }} data-testid={`chart-${spec.type}`}>
      <ResponsiveContainer width="100%" height="100%">
        {spec.type === "line" ? (
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.15} />
            <XAxis dataKey={x} {...axisProps} minTickGap={24} />
            <YAxis {...axisProps} tickFormatter={formatNumber} width={56} />
            <Tooltip formatter={formatNumber} />
            {y.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
            {y.map((k, i) => <Line isAnimationActive={animate} key={k} type="monotone" dataKey={k} stroke={PALETTE[i % PALETTE.length]} strokeWidth={2} dot={false} />)}
          </LineChart>
        ) : spec.type === "bar" ? (
          <BarChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.15} vertical={false} />
            <XAxis dataKey={x} {...axisProps} />
            <YAxis {...axisProps} tickFormatter={formatNumber} width={56} />
            <Tooltip formatter={formatNumber} cursor={{ fillOpacity: 0.08 }} />
            {y.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
            {y.map((k, i) => <Bar isAnimationActive={animate} key={k} dataKey={k} fill={PALETTE[i % PALETTE.length]} radius={[4, 4, 0, 0]} />)}
          </BarChart>
        ) : spec.type === "pie" ? (
          <PieChart>
            <Tooltip formatter={formatNumber} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Pie isAnimationActive={animate} data={data} dataKey={y[0]} nameKey={x} innerRadius="45%" outerRadius="80%" paddingAngle={2}>
              {data.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
            </Pie>
          </PieChart>
        ) : (
          <ScatterChart margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.15} />
            <XAxis dataKey={x} type="number" name={x} {...axisProps} tickFormatter={formatNumber} />
            <YAxis dataKey={y[0]} type="number" name={y[0]} {...axisProps} tickFormatter={formatNumber} width={56} />
            <Tooltip formatter={formatNumber} cursor={{ strokeDasharray: "3 3" }} />
            <Scatter isAnimationActive={animate} data={rows} fill={PALETTE[0]} fillOpacity={0.6} />
          </ScatterChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
