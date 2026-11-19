"use client";

import { Copy, Play, Plug, Trash2, Upload } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Badge, Button, Card, Empty, ErrorText, Input, Label, Modal, PageHeader, Select } from "@/components/ui";
import { API_URL, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Connector, Dataset } from "@/lib/types";

export default function DatasetsPage() {
  const { can, org } = useAuth();
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [showConnector, setShowConnector] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setDatasets(await api<Dataset[]>("/datasets"));
      if (can("admin")) setConnectors(await api<Connector[]>("/connectors"));
    } catch (e) { setError((e as Error).message); }
  }, [can]);

  useEffect(() => { load(); }, [load, org?.id]);

  // Live refresh when a connector / webhook pushes new rows (SSE).
  useEffect(() => {
    const on = (e: Event) => {
      const t = (e as CustomEvent).detail?.type as string;
      if (t?.startsWith("dataset.") || t === "ingest.completed") load();
    };
    window.addEventListener("insight:event", on);
    return () => window.removeEventListener("insight:event", on);
  }, [load]);

  async function upload(file: File) {
    setUploading(true); setError(null);
    const body = new FormData();
    body.append("file", file);
    body.append("name", file.name.replace(/\.csv$/i, ""));
    try { await api("/datasets/upload", { method: "POST", body }); await load(); }
    catch (e) { setError((e as Error).message); }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = ""; }
  }

  async function remove(d: Dataset) {
    if (!confirm(`Delete ${d.name}? Widgets that use it will stop working.`)) return;
    await api(`/datasets/${d.id}`, { method: "DELETE" });
    load();
  }

  return (
    <>
      <PageHeader
        title="Data"
        subtitle="Upload CSVs or connect an API / webhook. Each dataset becomes a table you can chart and ask questions about."
        actions={can("admin") && <>
          <input ref={fileRef} type="file" accept=".csv" hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          <Button variant="secondary" onClick={() => setShowConnector(true)}><Plug size={15} /> Add connector</Button>
          <Button onClick={() => fileRef.current?.click()} disabled={uploading}><Upload size={15} /> {uploading ? "Uploading…" : "Upload CSV"}</Button>
        </>}
      />
      <ErrorText error={error} />

      {datasets.length === 0 ? (
        <Empty title="No datasets yet">{can("admin") ? "Upload a CSV to get started." : "Ask an admin to add data."}</Empty>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {datasets.map((d) => (
            <Card key={d.id} className="flex flex-col gap-2">
              <div className="flex items-start justify-between gap-2">
                <Link href={`/datasets/${d.id}`} className="font-semibold hover:text-brand-600">{d.name}</Link>
                <Badge tone={d.source_type === "csv" ? "slate" : "green"}>{d.source_type}</Badge>
              </div>
              <p className="font-mono text-xs text-slate-500">{d.table_name}</p>
              <p className="text-sm">{d.row_count.toLocaleString()} rows · {d.columns.length} columns</p>
              <p className="line-clamp-2 text-xs text-slate-500">{d.columns.map((c) => `${c.name} (${c.type})`).join(", ") || "Waiting for first data…"}</p>
              {can("admin") && (
                <button onClick={() => remove(d)} className="mt-auto self-end text-slate-400 hover:text-red-600" aria-label={`Delete ${d.name}`}><Trash2 size={15} /></button>
              )}
            </Card>
          ))}
        </div>
      )}

      {can("admin") && connectors.length > 0 && (
        <section className="mt-10">
          <h2 className="mb-3 text-lg font-semibold">Connectors</h2>
          <div className="space-y-2">
            {connectors.map((c) => <ConnectorRow key={c.id} c={c} onChange={load} />)}
          </div>
        </section>
      )}

      <ConnectorModal open={showConnector} onClose={() => setShowConnector(false)} onCreated={load} />
    </>
  );
}

function ConnectorRow({ c, onChange }: { c: Connector; onChange: () => void }) {
  const url = c.webhook_url ? `${API_URL}${c.webhook_url}` : String(c.config.url ?? "");
  return (
    <Card className="flex flex-wrap items-center gap-3 py-3 text-sm">
      <Badge tone="green">{c.type === "webhook" ? "Webhook" : "API polling"}</Badge>
      <code className="min-w-0 flex-1 truncate text-xs">{url}</code>
      {c.last_status && <span className="text-xs text-slate-500">{c.last_status}</span>}
      {c.type === "webhook" && <Button size="sm" variant="ghost" onClick={() => navigator.clipboard.writeText(url)}><Copy size={13} /> Copy URL</Button>}
      {c.type === "api_poll" && <Button size="sm" variant="ghost" onClick={async () => { await api(`/connectors/${c.id}/run`, { method: "POST" }); onChange(); }}><Play size={13} /> Run now</Button>}
      <Button size="sm" variant="ghost" onClick={async () => { await api(`/connectors/${c.id}`, { method: "DELETE" }); onChange(); }}><Trash2 size={13} /></Button>
    </Card>
  );
}

function ConnectorModal({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: () => void }) {
  const [form, setForm] = useState({ dataset_name: "", type: "webhook", url: "", interval_minutes: 60, json_path: "" });
  const [error, setError] = useState<string | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault(); setError(null);
    try {
      await api("/connectors", { method: "POST", json: { ...form, url: form.url || null, json_path: form.json_path || null } });
      onCreated(); onClose();
    } catch (err) { setError((err as Error).message); }
  }

  return (
    <Modal open={open} onClose={onClose} title="Add a data connector">
      <form onSubmit={create} className="space-y-3">
        <Label text="Dataset name"><Input required value={form.dataset_name} onChange={(e) => setForm({ ...form, dataset_name: e.target.value })} /></Label>
        <Label text="Type">
          <Select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
            <option value="webhook">Webhook receiver — external systems POST JSON rows to us</option>
            <option value="api_poll">REST API polling — we GET a JSON URL on a schedule</option>
          </Select>
        </Label>
        {form.type === "api_poll" && <>
          <Label text="URL (returns JSON)"><Input required type="url" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} placeholder="https://api.example.com/orders" /></Label>
          <div className="grid grid-cols-2 gap-2">
            <Label text="Every N minutes"><Input type="number" min={1} value={form.interval_minutes} onChange={(e) => setForm({ ...form, interval_minutes: Number(e.target.value) })} /></Label>
            <Label text="JSON path to rows (optional)"><Input value={form.json_path} onChange={(e) => setForm({ ...form, json_path: e.target.value })} placeholder="data.items" /></Label>
          </div>
        </>}
        <ErrorText error={error} />
        <Button>Create connector</Button>
      </form>
    </Modal>
  );
}
