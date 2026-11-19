"use client";

import clsx from "clsx";
import { Database, LayoutDashboard, LogOut, MessageSquareText, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Badge, Spinner } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { type AppEvent, useEvents } from "@/lib/useEvents";

const NAV = [
  { href: "/dashboards", label: "Dashboards", icon: LayoutDashboard },
  { href: "/chat", label: "Ask AI", icon: MessageSquareText },
  { href: "/datasets", label: "Data", icon: Database },
  { href: "/settings", label: "Settings", icon: Settings },
];

function describe(e: AppEvent): string | null {
  switch (e.type) {
    case "ingest.started": return `Uploading ${e.filename}…`;
    case "ingest.completed": return `${e.name} ready (${e.rows} rows)`;
    case "ingest.failed": return `Upload failed: ${e.error}`;
    case "dataset.updated": return `Dataset updated via ${e.source} (${e.rows} rows)`;
    case "anomalies.updated": return `${e.count} anomalies found`;
    case "billing.updated": return `Plan changed to ${e.plan}`;
    default: return null;
  }
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, org, orgs, loading, logout, switchOrg, refresh } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [toasts, setToasts] = useState<{ id: number; text: string }[]>([]);

  useEffect(() => { if (!loading && !user) router.replace("/login"); }, [loading, user, router]);

  useEvents(org?.id, (e) => {
    const text = describe(e);
    if (e.type === "billing.updated") refresh();
    window.dispatchEvent(new CustomEvent("insight:event", { detail: e }));  // pages can listen
    if (!text) return;
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000);
  });

  if (loading || !user || !org) return <div className="flex h-screen items-center justify-center"><Spinner /></div>;

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="no-print flex shrink-0 flex-col gap-4 border-b border-slate-200 bg-white p-3 md:h-screen md:w-60 md:border-b-0 md:border-r dark:border-slate-800 dark:bg-slate-900 md:sticky md:top-0">
        <div className="flex items-center gap-2 px-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 font-bold text-white">i</div>
          <span className="font-semibold">InsightAI</span>
        </div>
        <div className="px-1">
          <select aria-label="Organisation" className="field" value={org.id} onChange={(e) => { switchOrg(Number(e.target.value)); router.push("/dashboards"); }}>
            {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
          <div className="mt-2 flex gap-1.5 px-1">
            <Badge tone="blue">{org.plan}</Badge><Badge>{org.role}</Badge>
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto md:flex-col">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href} className={clsx(
              "flex items-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-sm",
              pathname.startsWith(href) ? "bg-brand-50 font-medium text-brand-700 dark:bg-brand-700/20 dark:text-brand-100" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
            )}><Icon size={16} />{label}</Link>
          ))}
        </nav>
        <div className="mt-auto hidden border-t border-slate-200 px-2 pt-3 text-sm md:block dark:border-slate-800">
          <p className="truncate font-medium">{user.full_name || user.email}</p>
          <p className="truncate text-xs text-slate-500">{user.email}</p>
          <button onClick={() => { logout(); router.replace("/login"); }} className="mt-2 flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-800 dark:hover:text-slate-200">
            <LogOut size={13} /> Sign out
          </button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:p-8">{children}</main>
      <div className="no-print fixed bottom-4 right-4 z-50 space-y-2">
        {toasts.map((t) => (
          <div key={t.id} className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white shadow-lg dark:bg-slate-100 dark:text-slate-900">{t.text}</div>
        ))}
      </div>
    </div>
  );
}
