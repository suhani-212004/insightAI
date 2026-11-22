"use client";

import { ArrowLeft, FileDown, Plus, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Responsive, WidthProvider, type Layout } from "react-grid-layout";
import { WidgetCard } from "@/components/WidgetCard";
import { WidgetEditor } from "@/components/WidgetEditor";
import { Button, Empty, ErrorText, PageHeader, Spinner } from "@/components/ui";
import { api, downloadBlob } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ChartSpec, Dashboard, Widget } from "@/lib/types";

const Grid = WidthProvider(Responsive);

export default function DashboardPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const editable = can("admin");
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Widget | null | undefined>(undefined); // undefined = closed
  const [refreshKey, setRefreshKey] = useState(0);
  const [exporting, setExporting] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout>>();

  const load = useCallback(async () => {
    try { setDash(await api<Dashboard>(`/dashboards/${id}`)); }
    catch (e) { setError((e as Error).message); }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  // New data arrived via SSE -> refresh every widget.
  useEffect(() => {
    const on = (e: Event) => {
      const t = (e as CustomEvent).detail?.type as string;
      if (t === "dataset.updated" || t === "ingest.completed") setRefreshKey((k) => k + 1);
    };
    window.addEventListener("insight:event", on);
    return () => window.removeEventListener("insight:event", on);
  }, []);

  const layout = useMemo(() => dash?.layout ?? [], [dash]);

  function onLayoutChange(next: Layout[]) {
    if (!editable || !dash) return;
    const clean = next.map(({ i, x, y, w, h }) => ({ i, x, y, w, h }));
    if (JSON.stringify(clean) === JSON.stringify(dash.layout)) return;
    setDash({ ...dash, layout: clean });
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      api(`/dashboards/${id}/layout`, { method: "PUT", json: { layout: clean } }).catch((e) => setError(e.message));
    }, 600);
  }

  async function saveWidget(w: { title: string; sql: string; chart: ChartSpec }) {
    if (editing) await api(`/widgets/${editing.id}`, { method: "PUT", json: w });
    else await api(`/dashboards/${id}/widgets`, { method: "POST", json: w });
    await load();
    setRefreshKey((k) => k + 1);
  }

  async function removeWidget(w: Widget) {
    if (!confirm(`Remove "${w.title}"?`)) return;
    try {
      await api(`/widgets/${w.id}`, { method: "DELETE" });
      load();
    } catch (e) { setError((e as Error).message); }
  }

  async function exportPdf() {
    setExporting(true); setError(null);
    try {
      const blob = await api<Blob>(`/dashboards/${id}/export`, { method: "POST" });
      downloadBlob(blob, `${dash?.name ?? "dashboard"}.pdf`);
    } catch (e) { setError((e as Error).message); }
    finally { setExporting(false); }
  }

  if (!dash) return error ? <ErrorText error={error} /> : <div className="flex justify-center p-10"><Spinner /></div>;

  return (
    <>
      <Link href="/dashboards" className="mb-3 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"><ArrowLeft size={14} /> Dashboards</Link>
      <PageHeader
        title={dash.name}
        subtitle={editable ? "Drag a widget's title bar to move it; drag the corner to resize." : undefined}
        actions={<>
          <Button variant="secondary" onClick={() => setRefreshKey((k) => k + 1)}><RefreshCw size={15} /> Refresh</Button>
          <Button variant="secondary" onClick={exportPdf} disabled={exporting}><FileDown size={15} /> {exporting ? "Rendering…" : "Export PDF"}</Button>
          {editable && <Button onClick={() => setEditing(null)}><Plus size={15} /> Add widget</Button>}
        </>}
      />
      <ErrorText error={error} />

      {dash.widgets.length === 0 ? (
        <Empty title="This dashboard is empty">{editable ? "Add a widget, or pin a chart from Ask AI." : "Nothing to show yet."}</Empty>
      ) : (
        <Grid
          className="-mx-2"
          layouts={{ lg: layout }}
          breakpoints={{ lg: 1024, sm: 0 }}
          cols={{ lg: 12, sm: 1 }}
          rowHeight={36}
          draggableHandle=".drag-handle"
          isDraggable={editable}
          isResizable={editable}
          onLayoutChange={(l) => onLayoutChange(l)}
        >
          {dash.widgets.map((w) => (
            <div key={String(w.id)}>
              <WidgetCard widget={w} refreshKey={refreshKey} editable={editable} onEdit={() => setEditing(w)} onDelete={() => removeWidget(w)} />
            </div>
          ))}
        </Grid>
      )}

      <WidgetEditor open={editing !== undefined} initial={editing ?? null} onClose={() => setEditing(undefined)} onSave={saveWidget} />
    </>
  );
}
