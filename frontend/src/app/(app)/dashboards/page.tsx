"use client";

import { LayoutDashboard, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, Card, Empty, ErrorText, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Dashboard } from "@/lib/types";

export default function DashboardsPage() {
  const { can, org } = useAuth();
  const router = useRouter();
  const [dashboards, setDashboards] = useState<Dashboard[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Dashboard[]>("/dashboards").then(setDashboards).catch((e) => setError(e.message));
  }, [org?.id]);

  async function create() {
    const name = prompt("Dashboard name", "New dashboard");
    if (!name) return;
    try {
      const d = await api<Dashboard>("/dashboards", { method: "POST", json: { name } });
      router.push(`/dashboards/${d.id}`);
    } catch (e) { setError((e as Error).message); }
  }

  return (
    <>
      <PageHeader title="Dashboards" actions={can("admin") && <Button onClick={create}><Plus size={15} /> New dashboard</Button>} />
      <ErrorText error={error} />
      {dashboards?.length === 0 && <Empty title="No dashboards yet">Create one, or pin a chart from Ask AI.</Empty>}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {dashboards?.map((d) => (
          <Link key={d.id} href={`/dashboards/${d.id}`}>
            <Card className="flex items-center gap-3 transition hover:border-brand-500">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-50 text-brand-600 dark:bg-brand-700/20"><LayoutDashboard size={18} /></div>
              <div>
                <p className="font-semibold">{d.name}</p>
                <p className="text-xs text-slate-500">{d.widgets.length} widgets</p>
              </div>
            </Card>
          </Link>
        ))}
      </div>
    </>
  );
}
