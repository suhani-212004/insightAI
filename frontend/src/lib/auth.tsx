"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, session } from "./api";
import type { AuthResponse, Org, User } from "./types";

interface AuthState {
  user: User | null;
  orgs: Org[];
  org: Org | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (data: { email: string; password: string; full_name: string; org_name: string }) => Promise<void>;
  logout: () => void;
  switchOrg: (id: number) => void;
  refresh: () => Promise<void>;
  can: (role: "admin" | "owner") => boolean;
}

const AuthContext = createContext<AuthState | null>(null);
const RANK = { viewer: 0, admin: 1, owner: 2 } as const;

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [orgId, setOrgId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  const apply = useCallback((data: AuthResponse) => {
    session.setToken(data.access_token);
    setUser(data.user);
    setOrgs(data.orgs);
    const saved = Number(session.orgId());
    const chosen = data.orgs.find((o) => o.id === saved) ?? data.orgs[0] ?? null;
    session.setOrgId(chosen?.id ?? null);
    setOrgId(chosen?.id ?? null);
  }, []);

  const refresh = useCallback(async () => {
    if (!session.token()) { setLoading(false); return; }
    try { apply(await api<AuthResponse>("/auth/me")); }
    catch { session.setToken(null); setUser(null); }
    finally { setLoading(false); }
  }, [apply]);

  useEffect(() => { refresh(); }, [refresh]);

  const value = useMemo<AuthState>(() => {
    const org = orgs.find((o) => o.id === orgId) ?? null;
    return {
      user, orgs, org, loading, refresh,
      login: async (email, password) => apply(await api<AuthResponse>("/auth/login", { method: "POST", json: { email, password } })),
      signup: async (data) => apply(await api<AuthResponse>("/auth/signup", { method: "POST", json: data })),
      logout: () => { session.setToken(null); session.setOrgId(null); setUser(null); setOrgs([]); },
      switchOrg: (id) => { session.setOrgId(id); setOrgId(id); },
      can: (role) => !!org && RANK[org.role] >= RANK[role],
    };
  }, [user, orgs, orgId, loading, refresh, apply]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
