"use client";

// Print-friendly dashboard used by the backend's Playwright PDF export.
// The backend passes a short-lived token + org id in the URL. Once every widget
// has loaded, <body data-ready="true"> tells Playwright it can save the PDF.
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { WidgetCard } from "@/components/WidgetCard";
import { api, setSessionOverride } from "@/lib/api";
import type { Dashboard } from "@/lib/types";

export default function PrintPage() {
  return <Suspense><PrintDashboard /></Suspense>;
}

function PrintDashboard() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const loaded = useRef(0);

  useEffect(() => {
    document.body.style.background = "white";
    const token = params.get("token");
    const org = params.get("org");
    if (token && org) setSessionOverride(token, org);
    api<Dashboard>(`/dashboards/${id}`).then((d) => {
      setDash(d);
      if (d.widgets.length === 0) document.body.dataset.ready = "true";
    }).catch((e) => { setError(e.message); document.body.dataset.ready = "true"; });
  }, [id, params]);

  const onLoaded = useCallback(() => {
    loaded.current += 1;
    // give Recharts a moment to finish its first paint
    if (dash && loaded.current >= dash.widgets.length) setTimeout(() => { document.body.dataset.ready = "true"; }, 800);
  }, [dash]);

  if (error) return <p className="p-8">{error}</p>;
  if (!dash) return null;

  const ordered = [...dash.widgets].sort((a, b) => {
    const la = dash.layout.find((l) => l.i === String(a.id));
    const lb = dash.layout.find((l) => l.i === String(b.id));
    return (la?.y ?? 0) - (lb?.y ?? 0) || (la?.x ?? 0) - (lb?.x ?? 0);
  });

  return (
    <main className="bg-white p-6 text-slate-900">
      <header className="mb-4 flex items-end justify-between border-b border-slate-200 pb-3">
        <h1 className="text-2xl font-semibold">{dash.name}</h1>
        <p className="text-sm text-slate-500">Generated {new Date().toLocaleString()}</p>
      </header>
      <div className="grid grid-cols-2 gap-4">
        {ordered.map((w) => (
          <div key={w.id} className="h-[290px] break-inside-avoid">
            <WidgetCard widget={w} onLoaded={onLoaded} animate={false} />
          </div>
        ))}
      </div>
    </main>
  );
}
