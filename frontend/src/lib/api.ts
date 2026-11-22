// Small fetch wrapper: adds the JWT and the current org id to every request.
export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const TOKEN_KEY = "insight.token";
const ORG_KEY = "insight.org";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function read(key: string): string | null {
  try { return typeof window === "undefined" ? null : window.localStorage.getItem(key); } catch { return null; }
}
function write(key: string, value: string | null) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch { /* storage unavailable */ }
}

// The print page passes its token/org in the URL instead of localStorage.
let override: { token: string; org: string } | null = null;
export function setSessionOverride(token: string, org: string) { override = { token, org }; }

export const session = {
  token: () => override?.token ?? read(TOKEN_KEY),
  orgId: () => override?.org ?? read(ORG_KEY),
  setToken: (t: string | null) => write(TOKEN_KEY, t),
  setOrgId: (id: number | string | null) => write(ORG_KEY, id === null ? null : String(id)),
};

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = session.token();
  const org = session.orgId();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (org) headers.set("X-Org-Id", org);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  const res = await fetch(`${API_URL}/api/v1${path}`, { ...init, headers, body });
  if (!res.ok) {
    // Token expired or revoked: drop it and send the user back to the login page,
    // otherwise every page just shows "Invalid or expired token" forever.
    // (Skipped for the print page, which uses its own short-lived token.)
    if (res.status === 401 && !override && !path.startsWith("/auth/login") && typeof window !== "undefined") {
      session.setToken(null);
      if (window.location.pathname !== "/login") window.location.assign("/login");
    }
    let message = res.statusText;
    try {
      const data = await res.json();
      message = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? data);
    } catch { /* not JSON */ }
    throw new ApiError(res.status, message);
  }
  if (res.status === 204) return undefined as T;
  const type = res.headers.get("content-type") || "";
  return (type.includes("application/json") ? res.json() : res.blob()) as Promise<T>;
}

/** Save a Blob as a file. Revoking right after click() can cancel the download in some browsers. */
export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// EventSource can't send headers, so the stream is the one endpoint that takes ?token=.
export function streamUrl(): string {
  const p = new URLSearchParams({ token: session.token() || "", org_id: session.orgId() || "" });
  return `${API_URL}/api/v1/stream?${p}`;
}
