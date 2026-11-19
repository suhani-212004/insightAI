export type Role = "owner" | "admin" | "viewer";
export type ChartType = "line" | "bar" | "pie" | "scatter" | "heatmap" | "funnel" | "table";

export interface User { id: number; email: string; full_name: string }
export interface Org { id: number; name: string; slug: string; plan: string; role: Role }
export interface AuthResponse { access_token: string; user: User; orgs: Org[] }

export interface Column { name: string; type: string }
export interface Dataset {
  id: number; name: string; table_name: string; source_type: string;
  columns: Column[]; row_count: number; created_at: string; updated_at: string;
}

export interface ChartSpec { type: ChartType; x?: string | null; y: string[]; value?: string | null }
export type Row = Record<string, string | number | boolean | null>;
export interface QueryResult { columns: string[]; rows: Row[]; truncated: boolean }

export interface Widget { id: number; title: string; sql: string; chart: ChartSpec }
export interface LayoutItem { i: string; x: number; y: number; w: number; h: number }
export interface Dashboard { id: number; name: string; layout: LayoutItem[]; widgets: Widget[] }

export interface ChatMessage {
  id: number; role: "user" | "assistant"; content: string;
  sql: string | null; chart: ChartSpec | null; rows: Row[] | null; created_at: string;
}
export interface ChatSession { id: number; title: string; created_at: string }

export interface Anomaly {
  id: number; dataset_id: number; column: string; row_index: number;
  value: number; score: number; method: string; detected_at: string;
}

export interface Connector {
  id: number; dataset_id: number; type: "api_poll" | "webhook"; config: Record<string, unknown>;
  enabled: boolean; last_run_at: string | null; last_status: string | null; webhook_url: string | null;
}

export interface Member { user_id: number; email: string; full_name: string; role: Role }

export interface PlanInfo {
  plan: string;
  limits: { price_usd: number; datasets: number | null; members: number | null;
    ai_queries_per_day: number | null; dashboards: number | null; features: string[] };
  usage: Record<string, number>;
  stripe_enabled: boolean;
}
