"use client";

import clsx from "clsx";
import { Code2, Download, MessageSquarePlus, Pin, Send, Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { ChartRenderer } from "@/components/charts/ChartRenderer";
import { Button, ErrorText, Modal, Select, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toCSV } from "@/lib/chartData";
import type { ChatMessage, ChatSession, Dashboard } from "@/lib/types";

const SUGGESTIONS = [
  "What was total revenue each month?",
  "Which region sells the most electronics?",
  "Compare revenue by category as a share",
  "Now only show 2026",
];

export default function ChatPage() {
  const { org } = useAuth();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pinning, setPinning] = useState<ChatMessage | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const loadSessions = useCallback(() => api<ChatSession[]>("/ai/sessions").then(setSessions).catch(() => {}), []);
  useEffect(() => { loadSessions(); setSessionId(null); setMessages([]); }, [loadSessions, org?.id]);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);

  async function open(id: number) {
    setSessionId(id);
    setMessages(await api<ChatMessage[]>(`/ai/sessions/${id}`));
  }

  async function ask(q: string) {
    if (!q.trim() || busy) return;
    setBusy(true); setError(null); setQuestion("");
    const optimistic: ChatMessage = { id: -Date.now(), role: "user", content: q, sql: null, chart: null, rows: null, created_at: "" };
    setMessages((m) => [...m, optimistic]);
    try {
      const res = await api<{ session_id: number; message: ChatMessage }>("/ai/ask", { method: "POST", json: { question: q, session_id: sessionId } });
      setMessages((m) => [...m, res.message]);
      if (!sessionId) { setSessionId(res.session_id); loadSessions(); }
    } catch (e) {
      setError((e as Error).message);
      setMessages((m) => m.filter((x) => x.id !== optimistic.id));
      setQuestion(q);
    } finally { setBusy(false); }
  }

  return (
    <div className="grid h-[calc(100vh-4rem)] gap-4 lg:grid-cols-[220px_1fr]">
      <aside className="hidden flex-col gap-1 overflow-y-auto lg:flex">
        <Button variant="secondary" className="mb-2" onClick={() => { setSessionId(null); setMessages([]); }}><MessageSquarePlus size={15} /> New chat</Button>
        {sessions.map((s) => (
          <button key={s.id} onClick={() => open(s.id)} className={clsx(
            "truncate rounded-lg px-3 py-2 text-left text-sm",
            s.id === sessionId ? "bg-brand-50 text-brand-700 dark:bg-brand-700/20 dark:text-brand-100" : "hover:bg-slate-100 dark:hover:bg-slate-800",
          )}>{s.title}</button>
        ))}
      </aside>

      <section className="flex min-h-0 flex-col">
        <div className="flex-1 space-y-4 overflow-y-auto pb-4">
          {messages.length === 0 && (
            <div className="mx-auto mt-16 max-w-lg text-center">
              <Sparkles className="mx-auto mb-3 text-brand-600" />
              <h1 className="text-xl font-semibold">Ask your data anything</h1>
              <p className="mt-1 text-sm text-slate-500">Plain English in, SQL + chart out. Follow-up questions remember the conversation.</p>
              <div className="mt-6 flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.slice(0, 3).map((s) => <Button key={s} size="sm" variant="secondary" onClick={() => ask(s)}>{s}</Button>)}
              </div>
            </div>
          )}
          {messages.map((m) => m.role === "user"
            ? <div key={m.id} className="ml-auto max-w-xl rounded-2xl bg-brand-600 px-4 py-2 text-sm text-white">{m.content}</div>
            : <AnswerCard key={m.id} m={m} onPin={() => setPinning(m)} />)}
          {busy && <div className="flex items-center gap-2 text-sm text-slate-500"><Spinner /> Writing SQL and running it…</div>}
          <div ref={bottom} />
        </div>
        <ErrorText error={error} />
        <form onSubmit={(e) => { e.preventDefault(); ask(question); }} className="mt-2 flex gap-2">
          <input className="field" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="e.g. Top 5 categories by revenue last quarter" disabled={busy} />
          <Button disabled={busy || !question.trim()} aria-label="Send"><Send size={15} /></Button>
        </form>
      </section>

      <PinModal message={pinning} onClose={() => setPinning(null)} />
    </div>
  );
}

function AnswerCard({ m, onPin }: { m: ChatMessage; onPin: () => void }) {
  const [showSql, setShowSql] = useState(false);
  const { can } = useAuth();
  const columns = m.rows?.length ? Object.keys(m.rows[0]) : [];

  function downloadCsv() {
    const blob = new Blob([toCSV(columns, m.rows ?? [])], { type: "text/csv" });
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: "result.csv" });
    a.click();
  }

  return (
    <div className="max-w-4xl rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <p className="text-sm">{m.content}</p>
      {m.rows && m.chart && (
        <div className="mt-3 h-72"><ChartRenderer spec={m.chart} columns={columns} rows={m.rows} /></div>
      )}
      {m.sql && (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" variant="ghost" onClick={() => setShowSql(!showSql)}><Code2 size={13} /> {showSql ? "Hide" : "Show"} SQL</Button>
          {m.rows && <Button size="sm" variant="ghost" onClick={downloadCsv}><Download size={13} /> CSV</Button>}
          {m.rows && can("admin") && <Button size="sm" variant="ghost" onClick={onPin}><Pin size={13} /> Pin to dashboard</Button>}
        </div>
      )}
      {showSql && <pre className="mt-2 overflow-x-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-100">{m.sql}</pre>}
    </div>
  );
}

function PinModal({ message, onClose }: { message: ChatMessage | null; onClose: () => void }) {
  const [dashboards, setDashboards] = useState<Dashboard[]>([]);
  const [target, setTarget] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!message) return;
    setDone(false); setError(null); setTitle(message.content.slice(0, 60));
    api<Dashboard[]>("/dashboards").then((d) => { setDashboards(d); setTarget(d[0] ? String(d[0].id) : ""); });
  }, [message]);

  async function pin() {
    if (!message?.sql || !message.chart) return;
    try {
      await api(`/dashboards/${target}/widgets`, { method: "POST", json: { title, sql: message.sql, chart: message.chart } });
      setDone(true);
    } catch (e) { setError((e as Error).message); }
  }

  return (
    <Modal open={!!message} onClose={onClose} title="Pin to dashboard">
      {done ? <p className="text-sm">Pinned. <a className="text-brand-600 hover:underline" href={`/dashboards/${target}`}>Open dashboard →</a></p> : (
        <div className="space-y-3">
          <input className="field" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Widget title" />
          {dashboards.length === 0 ? <p className="text-sm text-slate-500">Create a dashboard first.</p> : (
            <Select value={target} onChange={(e) => setTarget(e.target.value)}>
              {dashboards.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </Select>
          )}
          <ErrorText error={error} />
          <Button onClick={pin} disabled={!target}>Pin</Button>
        </div>
      )}
    </Modal>
  );
}
