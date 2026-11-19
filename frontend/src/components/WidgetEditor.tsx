"use client";

import { Play } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ChartSpec, ChartType, Dataset, QueryResult, Widget } from "@/lib/types";
import { ChartRenderer } from "./charts/ChartRenderer";
import { Button, ErrorText, Input, Label, Modal, Select } from "./ui";

const TYPES: ChartType[] = ["line", "bar", "pie", "scatter", "heatmap", "funnel", "table"];

interface Props {
  open: boolean;
  onClose: () => void;
  onSave: (w: { title: string; sql: string; chart: ChartSpec }) => Promise<void>;
  initial?: Widget | null;
}

/** Write SQL, preview the result, pick a chart type and axes, save as a widget. */
export function WidgetEditor({ open, onClose, onSave, initial }: Props) {
  const [title, setTitle] = useState("");
  const [sql, setSql] = useState("");
  const [chart, setChart] = useState<ChartSpec>({ type: "bar", x: null, y: [] });
  const [result, setResult] = useState<QueryResult | null>(null);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setTitle(initial?.title ?? "");
    setSql(initial?.sql ?? "");
    setChart(initial?.chart ?? { type: "bar", x: null, y: [] });
    setResult(null);
    setError(null);
    api<Dataset[]>("/datasets").then(setDatasets).catch(() => {});
  }, [open, initial]);

  async function run() {
    setBusy(true); setError(null);
    try {
      const r = await api<QueryResult>("/query", { method: "POST", json: { sql } });
      setResult(r);
      if (!chart.x || !r.columns.includes(chart.x)) {
        const numeric = r.columns.filter((c) => r.rows.some((row) => typeof row[c] === "number"));
        const x = r.columns.find((c) => !numeric.includes(c)) ?? r.columns[0];
        setChart((c) => ({ ...c, x, y: numeric.filter((n) => n !== x).slice(0, 1) }));
      }
    } catch (e) { setError((e as Error).message); setResult(null); }
    finally { setBusy(false); }
  }

  async function save() {
    setBusy(true); setError(null);
    try { await onSave({ title: title || "Untitled", sql, chart }); onClose(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  const cols = result?.columns ?? [];

  return (
    <Modal open={open} onClose={onClose} title={initial ? "Edit widget" : "Add widget"} wide>
      <div className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
        <div className="space-y-3">
          <Label text="Title"><Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Revenue by region" /></Label>
          <Label text="SQL (SELECT only — tables below)">
            <textarea
              value={sql}
              onChange={(e) => setSql(e.target.value)}
              rows={8}
              spellCheck={false}
              className="field font-mono text-xs"
              placeholder="SELECT region, sum(revenue) AS revenue FROM sales GROUP BY 1"
            />
          </Label>
          <div className="max-h-28 overflow-auto rounded-lg bg-slate-50 p-2 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            {datasets.length === 0 ? "No datasets yet." : datasets.map((d) => (
              <div key={d.id}><span className="font-mono font-semibold">{d.table_name}</span>: {d.columns.map((c) => c.name).join(", ")}</div>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Label text="Chart type">
              <Select value={chart.type} onChange={(e) => setChart({ ...chart, type: e.target.value as ChartType })}>
                {TYPES.map((t) => <option key={t}>{t}</option>)}
              </Select>
            </Label>
            <Label text={chart.type === "pie" || chart.type === "funnel" ? "Label column" : "X axis"}>
              <Select value={chart.x ?? ""} onChange={(e) => setChart({ ...chart, x: e.target.value })}>
                {cols.map((c) => <option key={c}>{c}</option>)}
              </Select>
            </Label>
            <Label text={chart.type === "heatmap" ? "Y axis (category)" : "Value column"}>
              <Select value={chart.y[0] ?? ""} onChange={(e) => setChart({ ...chart, y: [e.target.value] })}>
                {cols.map((c) => <option key={c}>{c}</option>)}
              </Select>
            </Label>
            {chart.type === "heatmap" && (
              <Label text="Colour value">
                <Select value={chart.value ?? ""} onChange={(e) => setChart({ ...chart, value: e.target.value })}>
                  {cols.map((c) => <option key={c}>{c}</option>)}
                </Select>
              </Label>
            )}
          </div>
          <ErrorText error={error} />
          <div className="flex gap-2">
            <Button variant="secondary" onClick={run} disabled={busy || !sql.trim()}><Play size={14} /> Run</Button>
            <Button onClick={save} disabled={busy || !result}>Save widget</Button>
          </div>
        </div>
        <div className="h-[380px] rounded-xl border border-slate-200 p-2 dark:border-slate-800">
          {result ? <ChartRenderer spec={chart} columns={result.columns} rows={result.rows} />
            : <p className="p-4 text-sm text-slate-500">Run the query to preview the chart.</p>}
        </div>
      </div>
    </Modal>
  );
}
