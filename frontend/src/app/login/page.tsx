"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, ErrorText, Input, Label } from "@/components/ui";
import { AuthShell } from "@/components/AuthShell";
import { useAuth } from "@/lib/auth";

const DEMO = [
  { email: "owner@acme.example.com", label: "Acme · Owner (Pro)" },
  { email: "viewer@acme.example.com", label: "Acme · Viewer" },
  { email: "owner@globex.example.com", label: "Globex · Owner (Free)" },
];

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e?: React.FormEvent, creds?: { email: string; password: string }) {
    e?.preventDefault();
    setBusy(true); setError(null);
    try {
      await login(creds?.email ?? email, creds?.password ?? password);
      router.replace("/dashboards");
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <AuthShell title="Sign in to InsightAI" footer={<>No account? <Link className="text-brand-600 hover:underline" href="/signup">Create one</Link></>}>
      <form onSubmit={submit} className="space-y-3">
        <Label text="Email"><Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></Label>
        <Label text="Password"><Input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></Label>
        <ErrorText error={error} />
        <Button className="w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</Button>
      </form>
      <div className="mt-6 border-t border-slate-200 pt-4 dark:border-slate-800">
        <p className="mb-2 text-xs font-medium text-slate-500">Demo accounts (password demo1234)</p>
        <div className="flex flex-wrap gap-2">
          {DEMO.map((d) => (
            <Button key={d.email} type="button" size="sm" variant="secondary" disabled={busy}
              onClick={() => submit(undefined, { email: d.email, password: "demo1234" })}>{d.label}</Button>
          ))}
        </div>
      </div>
    </AuthShell>
  );
}
