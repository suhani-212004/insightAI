"use client";

import { Pencil, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { QueryResult, Widget } from "@/lib/types";
import { ChartRenderer } from "./charts/ChartRenderer";
import { Spinner } from "./ui";

interface Props {
  widget: Widget;
  refreshKey?: number;
  editable?: boolean;
  onEdit?: () => void;
  onDelete?: () => void;
  onLoaded?: () => void;
  animate?: boolean;
}

export function WidgetCard({ widget, refreshKey = 0, editable, onEdit, onDelete, onLoaded, animate = true }: Props) {
  const [data, setData] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api<QueryResult>(`/widgets/${widget.id}/data`));
      setError(null);
    } catch (e) { setError((e as Error).message); }
    finally { onLoaded?.(); }
  }, [widget.id, onLoaded]);

  useEffect(() => { load(); }, [load, refreshKey, widget.sql]);

  return (
    <div className="flex h-full flex-col rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <div className="drag-handle flex cursor-move items-center justify-between gap-2 border-b border-slate-100 px-3 py-2 dark:border-slate-800">
        <h3 className="truncate text-sm font-semibold">{widget.title}</h3>
        {editable && (
          <div className="flex gap-1" onMouseDown={(e) => e.stopPropagation()}>
            <button aria-label="Edit widget" onClick={onEdit} className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800"><Pencil size={14} /></button>
            <button aria-label="Delete widget" onClick={onDelete} className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10"><Trash2 size={14} /></button>
          </div>
        )}
      </div>
      <div className="min-h-0 flex-1 p-2">
        {error ? <p className="p-2 text-sm text-red-600">{error}</p>
          : !data ? <div className="flex h-full items-center justify-center"><Spinner /></div>
          : <ChartRenderer spec={widget.chart} columns={data.columns} rows={data.rows} animate={animate} />}
      </div>
    </div>
  );
}
