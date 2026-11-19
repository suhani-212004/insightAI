"use client";

import { ArrowLeft, Radar } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { DataTable } from "@/components/charts/DataTable";
import { Badge, Button, Card, ErrorText, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatNumber } from "@/lib/chartData";
import type { Anomaly, Dataset, Row } from "@/lib/types";

export default function DatasetDetail() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [preview, setPreview] = useState<{ columns: string[]; rows: Row[] } | null>(null);
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setDataset(await api<Dataset>(`/datasets/${id}`));
      setPreview(await api(`/datasets/${id}/preview?limit=100`));
      setAnomalies(await api<Anomaly[]>(`/datasets/${id}/anomalies`));
    } catch (e) { setError((e as Error).message); }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const flagged = useMemo(() => new Set(anomalies.map((a) => a.row_index)), [anomalies]);

  async function scan() {
    setError(null);
    try { setAnomalies(await api<Anomaly[]>(`/datasets/${id}/anomalies/scan`, { method: "POST" })); }
    catch (e) { setError((e as Error).message); }
  }

  if (!dataset) return <ErrorText error={error} />;

  return (
    <>
      <Link href="/datasets" className="mb-3 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"><ArrowLeft size={14} /> Data</Link>
      <PageHeader
        title={dataset.name}
        subtitle={`${dataset.row_count.toLocaleString()} rows · table ${dataset.table_name}`}
        actions={can("admin") && <Button variant="secondary" onClick={scan}><Radar size={15} /> Scan for anomalies</Button>}
      />
      <ErrorText error={error} />

      <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
        <Card className="h-[520px] p-0">{preview && <DataTable columns={preview.columns} rows={preview.rows} highlight={flagged} />}</Card>
        <div className="space-y-4">
          <Card>
            <h2 className="mb-2 text-sm font-semibold">Columns</h2>
            <ul className="space-y-1 text-sm">
              {dataset.columns.map((c) => <li key={c.name} className="flex justify-between"><span className="font-mono">{c.name}</span><Badge>{c.type}</Badge></li>)}
            </ul>
          </Card>
          <Card>
            <h2 className="mb-1 text-sm font-semibold">Anomalies</h2>
            <p className="mb-2 text-xs text-slate-500">Values more than 3 standard deviations (or 3×IQR) from normal.</p>
            {anomalies.length === 0 ? <p className="text-sm text-slate-500">None detected.</p> : (
              <ul className="max-h-72 space-y-1 overflow-auto text-sm">
                {anomalies.map((a) => (
                  <li key={a.id} className="flex items-center justify-between rounded bg-amber-50 px-2 py-1 dark:bg-amber-500/10">
                    <span><span className="font-mono">{a.column}</span> row {a.row_index}</span>
                    <span className="tabular-nums">{formatNumber(a.value)} <span className="text-xs text-slate-500">({a.method} {a.score})</span></span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
