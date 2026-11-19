"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, ErrorText, Input, Label } from "@/components/ui";
import { AuthShell } from "@/components/AuthShell";
import { useAuth } from "@/lib/auth";

export default function SignupPage() {
  const { signup } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState({ full_name: "", email: "", password: "", org_name: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await signup(form); router.replace("/datasets"); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <AuthShell title="Create your workspace" footer={<>Already have an account? <Link className="text-brand-600 hover:underline" href="/login">Sign in</Link></>}>
      <form onSubmit={submit} className="space-y-3">
        <Label text="Your name"><Input value={form.full_name} onChange={set("full_name")} /></Label>
        <Label text="Organisation name"><Input required minLength={2} value={form.org_name} onChange={set("org_name")} /></Label>
        <Label text="Work email"><Input type="email" required value={form.email} onChange={set("email")} /></Label>
        <Label text="Password (8+ characters)"><Input type="password" required minLength={8} value={form.password} onChange={set("password")} /></Label>
        <ErrorText error={error} />
        <Button className="w-full" disabled={busy}>{busy ? "Creating…" : "Create account"}</Button>
      </form>
    </AuthShell>
  );
}
