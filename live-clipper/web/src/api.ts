import { useEffect, useRef, useState } from "react";

export class ApiError extends Error {}
type Listener = () => void;
const unauthorized = new Set<Listener>();
export const onUnauthorized = (fn: Listener) => { unauthorized.add(fn); return () => unauthorized.delete(fn); };

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const r = await fetch(path, {
    method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"),
    headers: { "Content-Type": "application/json" },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (r.status === 401 && path !== "/api/login") unauthorized.forEach((f) => f());
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? data));
  return data as T;
}

export function useApi<T>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);
  const reload = async () => {
    if (!path) return;
    const n = ++seq.current;
    setLoading(true);
    try { const d = await api<T>(path); if (n === seq.current) { setData(d); setError(null); } }
    catch (e) { if (n === seq.current) setError((e as Error).message); }
    finally { if (n === seq.current) setLoading(false); }
  };
  useEffect(() => { reload(); }, [path, ...deps]);
  return { data, setData, error, loading, reload };
}

export type Plan = { state: string; reason: string; at: number | null; today: number; queued: number };
export type TargetStatus = Plan & { id: number; name: string; kind: Kind; enabled: number; mode: string; daily_limit: number; check_ok: number | null };
export type Kind = "telegram" | "vk" | "youtube";
export type LiveChannel = {
  login: string; name: string; title: string; game: string; avatar: string | null; viewers: number; list: string;
  since: number; buffered_s: number; recording: boolean; warming: boolean; score: number; chat_z: number; audio_z: number;
  threshold: number; chat_per_min: number; history: [number, number][]; moments: [number, number][]; preview_at: number;
};
export type Status = {
  ts: number; channels: LiveChannel[]; trigger_score: number; queue: number; rendering: number[]; publish_paused: boolean;
  day: { clips: number; published: number; errors: number; duplicates: number; posts: number }; pending_review: number;
  targets: TargetStatus[]; disk: { free_gb: number; total_gb: number; data_gb: number; hours_left: number | null };
  alerts: boolean; auto_discover: boolean; whitelist: string[];
};
export type Publication = {
  id: number; clip_id: number; target_id: number; status: string; url: string | null; error: string | null;
  created_at: number; done_at: number | null; views: number | null; remote: unknown;
};
export type Clip = {
  id: number; login: string; score: number; title: string | null; status: string; created_at: number; manual: number;
  error: string | null; duplicate_of: number | null; version: number; updated_at: number | null;
  meta: { overlay?: string; title?: string; description?: string } | null;
  timings: Record<string, number> | null; reasons: Record<string, any> | null;
  edit: { trim_start: number; trim_end: number; overlay?: string; subtitles?: boolean; layout?: string; facecam?: number[] | null } | null;
  src_duration: number | null; has_file: boolean; has_source: boolean; has_source_preview: boolean;
  publications: Publication[]; streamer: { name: string; avatar: string | null };
  subs?: { start: number; end: number; text: string }[]; transcript?: string; stream_title?: string;
  posts?: Record<number, { title: string; caption: string }>;
};

export function useStatus() {
  const [status, setStatus] = useState<Status | null>(null);
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    let es: EventSource | null = null, stop = false, timer: number | undefined;
    const open = () => {
      es = new EventSource("/api/events");
      es.onmessage = (e) => { setStatus(JSON.parse(e.data)); setConnected(true); };
      es.onerror = () => {
        setConnected(false); es?.close();
        if (!stop) timer = window.setTimeout(() => api("/api/status").then(() => open()).catch(() => (timer = window.setTimeout(open, 5000))), 2000);
      };
    };
    open();
    return () => { stop = true; es?.close(); clearTimeout(timer); };
  }, []);
  return { status, connected };
}

export const KIND_LABEL: Record<Kind, string> = { telegram: "Telegram", vk: "VK", youtube: "YouTube" };

export function ago(ts: number | null | undefined) {
  if (!ts) return "—";
  const s = Math.round(Date.now() / 1000 - ts);
  if (s < 0) return "через " + dur(-s);
  if (s < 45) return "только что";
  return dur(s) + " назад";
}
export function dur(s: number) {
  s = Math.round(s);
  if (s < 60) return `${s} с`;
  if (s < 3600) return `${Math.round(s / 60)} мин`;
  if (s < 86400) return `${Math.floor(s / 3600)} ч ${Math.round((s % 3600) / 60)} мин`;
  return `${Math.round(s / 86400)} д`;
}
export const clock = (ts: number) => new Date(ts * 1000).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" });
export const num = (n: number | null | undefined) => (n == null ? "—" : n.toLocaleString("ru"));
