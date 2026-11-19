"use client";

import { Check, CreditCard, Trash2, UserPlus } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { Badge, Button, Card, ErrorText, Input, Label, PageHeader, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Member, PlanInfo, Role } from "@/lib/types";

const PLAN_ORDER = ["free", "pro", "enterprise"] as const;
const FEATURE_LABELS: Record<string, string> = {
  csv_upload: "CSV upload", api_connectors: "API polling", webhooks: "Webhooks", pdf_export: "PDF export",
  anomaly_detection: "Anomaly detection", scheduled_reports: "Scheduled reports",
};

export default function SettingsPage() {
  return <Suspense><Settings /></Suspense>;
}

function Settings() {
  const { org, can, refresh, user } = useAuth();
  const params = useSearchParams();
  const [members, setMembers] = useState<Member[]>([]);
  const [plan, setPlan] = useState<PlanInfo | null>(null);
  const [plans, setPlans] = useState<Record<string, PlanInfo["limits"]>>({});
  const [invite, setInvite] = useState({ email: "", role: "viewer" as Role, password: "" });
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setMembers(await api<Member[]>("/orgs/members"));
      setPlan(await api<PlanInfo>("/billing"));
      setPlans(await api("/billing/plans"));
    } catch (e) { setError((e as Error).message); }
  }, []);
  useEffect(() => { load(); }, [load, org?.id]);
  useEffect(() => { if (params.get("billing") === "success") refresh(); }, [params, refresh]);

  async function act(fn: () => Promise<unknown>) {
    setError(null);
    try { await fn(); await load(); } catch (e) { setError((e as Error).message); }
  }

  async function choosePlan(p: string) {
    if (plan?.stripe_enabled && p !== "free") {
      await act(async () => { window.location.href = (await api<{ url: string }>("/billing/checkout", { method: "POST", json: { plan: p } })).url; });
    } else if (plan?.stripe_enabled) {
      await act(async () => { window.location.href = (await api<{ url: string }>("/billing/portal", { method: "POST" })).url; });
    } else {
      await act(() => api("/billing/dev/set-plan", { method: "POST", json: { plan: p } }));
      await refresh();
    }
  }

  return (
    <>
      <PageHeader title="Settings" subtitle={org?.name} />
      <ErrorText error={error} />
      {params.get("billing") === "success" && <p className="mb-4 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">Payment complete — your plan will update in a moment.</p>}

      <section className="mb-10">
        <h2 className="mb-1 text-lg font-semibold">Plan & billing</h2>
        {plan && (
          <p className="mb-4 text-sm text-slate-500">
            Using {plan.usage.datasets} datasets · {plan.usage.members} members · {plan.usage.dashboards} dashboards · {plan.usage.ai_queries_today} AI questions today
            {!plan.stripe_enabled && " · Stripe not configured: plan buttons switch instantly (dev mode)."}
          </p>
        )}
        <div className="grid gap-3 md:grid-cols-3">
          {PLAN_ORDER.map((p) => {
            const l = plans[p];
            if (!l) return null;
            const current = plan?.plan === p;
            return (
              <Card key={p} className={current ? "border-brand-500 ring-2 ring-brand-500/20" : ""}>
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold capitalize">{p}</h3>
                  {current && <Badge tone="blue">Current</Badge>}
                </div>
                <p className="my-2 text-2xl font-semibold">${l.price_usd}<span className="text-sm font-normal text-slate-500">/mo</span></p>
                <ul className="mb-4 space-y-1 text-sm">
                  <li>{l.datasets ?? "Unlimited"} datasets</li>
                  <li>{l.ai_queries_per_day ?? "Unlimited"} AI questions / day</li>
                  <li>{l.members ?? "Unlimited"} members</li>
                  {l.features.map((f) => <li key={f} className="flex items-center gap-1.5"><Check size={13} className="text-emerald-600" />{FEATURE_LABELS[f] ?? f}</li>)}
                </ul>
                {can("owner") && !current && (
                  <Button variant={p === "free" ? "secondary" : "primary"} className="w-full" onClick={() => choosePlan(p)}>
                    <CreditCard size={14} /> {p === "free" ? "Downgrade" : `Upgrade to ${p}`}
                  </Button>
                )}
              </Card>
            );
          })}
        </div>
        {can("owner") && plan?.stripe_enabled && plan.plan !== "free" && (
          <Button variant="ghost" className="mt-3" onClick={() => choosePlan("free")}>Manage subscription in Stripe</Button>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Members</h2>
        <Card className="divide-y divide-slate-100 p-0 dark:divide-slate-800">
          {members.map((m) => (
            <div key={m.user_id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{m.full_name || m.email}{m.user_id === user?.id && " (you)"}</p>
                <p className="text-xs text-slate-500">{m.email}</p>
              </div>
              {can("owner") ? (
                <Select className="w-32" value={m.role} onChange={(e) => act(() => api(`/orgs/members/${m.user_id}`, { method: "PATCH", json: { role: e.target.value } }))}>
                  <option value="viewer">viewer</option><option value="admin">admin</option><option value="owner">owner</option>
                </Select>
              ) : <Badge>{m.role}</Badge>}
              {can("admin") && m.user_id !== user?.id && (
                <button aria-label={`Remove ${m.email}`} className="text-slate-400 hover:text-red-600" onClick={() => act(() => api(`/orgs/members/${m.user_id}`, { method: "DELETE" }))}><Trash2 size={15} /></button>
              )}
            </div>
          ))}
        </Card>

        {can("admin") && (
          <form className="mt-4 grid gap-2 sm:grid-cols-[1fr_140px_1fr_auto] sm:items-end" onSubmit={(e) => {
            e.preventDefault();
            act(() => api("/orgs/members", { method: "POST", json: { ...invite, password: invite.password || null } }))
              .then(() => setInvite({ email: "", role: "viewer", password: "" }));
          }}>
            <Label text="Email"><Input type="email" required value={invite.email} onChange={(e) => setInvite({ ...invite, email: e.target.value })} /></Label>
            <Label text="Role">
              <Select value={invite.role} onChange={(e) => setInvite({ ...invite, role: e.target.value as Role })}>
                <option value="viewer">viewer</option><option value="admin">admin</option>{can("owner") && <option value="owner">owner</option>}
              </Select>
            </Label>
            <Label text="Temp password (new users)"><Input type="password" minLength={8} value={invite.password} onChange={(e) => setInvite({ ...invite, password: e.target.value })} /></Label>
            <Button><UserPlus size={15} /> Add</Button>
          </form>
        )}
      </section>
    </>
  );
}
