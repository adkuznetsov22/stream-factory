"use client";

import { useEffect, useState, useCallback } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type HealthData = {
  counts: Record<string, number>;
  stuck: { processing: number; publishing: number };
  scheduler_enabled: boolean;
  watchdog_enabled: boolean;
  celery_enabled?: boolean;
  last_decisions: { action: string; at: string | null }[];
};

type WatchdogReport = {
  stuck_count: number;
  stuck_processing: number;
  stuck_publishing: number;
  items: { task_id: number; project_id: number; old_status: string; age_minutes: number; action: string; error_message: string }[];
  dry_run: boolean;
  run_at: string;
  settings: { stuck_processing_minutes: number; stuck_publishing_minutes: number; auto_requeue: boolean };
};

type OpsTask = {
  id: number; status: string; project_id: number; platform: string;
  destination_social_account_id: number;
  candidate_id: number | null; virality_score: number | null;
  priority: number;
  created_at: string | null; updated_at: string | null;
  pause_requested_at: string | null; paused_at: string | null;
  cancel_requested_at: string | null; canceled_at: string | null;
  celery_task_id: string | null;
};

type BulkResult = { ok: number[]; failed: { id: number; reason: string }[] };

const STATUS_COLORS: Record<string, string> = {
  queued: "#3b82f6", processing: "#f59e0b", ready_for_review: "#a855f7",
  done: "#22c55e", publishing: "#8b5cf6", published: "#10b981",
  error: "#ef4444", canceled: "#6b7280", paused: "#eab308",
};

const STATUSES = ["", "queued", "processing", "ready_for_review", "done", "publishing", "published", "error", "canceled", "paused"];

const chip = (bg: string, fg: string, text: string) => (
  <span style={{ padding: "2px 8px", borderRadius: 10, fontSize: 10, fontWeight: 600, background: bg, color: fg, whiteSpace: "nowrap" }}>{text}</span>
);

export default function OpsPage() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [report, setReport] = useState<WatchdogReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [wdLoading, setWdLoading] = useState(false);

  // Task list
  const [tasks, setTasks] = useState<OpsTask[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkMsg, setBulkMsg] = useState<string | null>(null);
  const [bulkPriority, setBulkPriority] = useState(0);
  const [tasksLoading, setTasksLoading] = useState(false);

  const loadHealth = useCallback(async () => {
    setLoading(true);
    try { const r = await fetch(`${API}/api/ops/health`); if (r.ok) setHealth(await r.json()); } catch {}
    setLoading(false);
  }, []);

  const loadTasks = useCallback(async () => {
    setTasksLoading(true);
    const qs = statusFilter ? `?status=${statusFilter}&limit=200` : "?limit=200";
    try { const r = await fetch(`${API}/api/ops/tasks${qs}`); if (r.ok) { const j = await r.json(); setTasks(j.tasks || []); } } catch {}
    setTasksLoading(false);
  }, [statusFilter]);

  useEffect(() => { loadHealth(); loadTasks(); }, [loadHealth, loadTasks]);

  const runWatchdog = async (dryRun: boolean) => {
    setWdLoading(true);
    try { const r = await fetch(`${API}/api/ops/watchdog?dry_run=${dryRun}`, { method: "POST" }); if (r.ok) { setReport(await r.json()); loadHealth(); } } catch {}
    setWdLoading(false);
  };

  const toggleSelect = (id: number) => setSelected(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });
  const toggleAll = () => setSelected(prev => prev.size === tasks.length ? new Set() : new Set(tasks.map(t => t.id)));
  const selectedIds = Array.from(selected);

  const bulkAction = async (endpoint: string, body: object) => {
    setBulkMsg(null);
    try {
      const r = await fetch(`${API}/api/ops/tasks/${endpoint}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (r.ok) {
        const j: BulkResult & { priority?: number } = await r.json();
        setBulkMsg(`✓ ${j.ok.length} ok` + (j.failed.length ? `, ${j.failed.length} failed` : ""));
        setSelected(new Set());
        loadTasks(); loadHealth();
      } else { setBulkMsg("✕ Error: " + (await r.text())); }
    } catch (e) { setBulkMsg("✕ Network error"); }
  };

  const btnSm = (bg: string, fg: string, label: string, onClick: () => void, disabled = false) => (
    <button disabled={disabled} onClick={onClick} style={{ padding: "4px 12px", borderRadius: 6, fontSize: 11, fontWeight: 600, cursor: disabled ? "default" : "pointer", background: disabled ? "#e2e8f0" : bg, color: disabled ? "#94a3b8" : fg, border: "none", opacity: disabled ? 0.5 : 1 }}>{label}</button>
  );

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "32px 16px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>Operations</h1>
        <button onClick={() => { loadHealth(); loadTasks(); }} disabled={loading} style={{ padding: "6px 16px", borderRadius: 8, fontSize: 12, fontWeight: 500, cursor: "pointer", background: "#dbeafe", color: "#2563eb", border: "1px solid #93c5fd" }}>
          {loading ? "Loading..." : "↻ Refresh"}
        </button>
      </div>

      {/* Health indicators */}
      {health && (
        <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
          {chip(health.scheduler_enabled ? "#dcfce7" : "#fee2e2", health.scheduler_enabled ? "#166534" : "#991b1b", `Scheduler: ${health.scheduler_enabled ? "ON" : "OFF"}`)}
          {chip(health.watchdog_enabled ? "#dcfce7" : "#fee2e2", health.watchdog_enabled ? "#166534" : "#991b1b", `Watchdog: ${health.watchdog_enabled ? "ON" : "OFF"}`)}
          {health.celery_enabled !== undefined && chip(health.celery_enabled ? "#dcfce7" : "#fee2e2", health.celery_enabled ? "#166534" : "#991b1b", `Celery: ${health.celery_enabled ? "ON" : "OFF"}`)}
          {(health.stuck.processing > 0 || health.stuck.publishing > 0) && chip("#fee2e2", "#991b1b", `⚠ Stuck: ${health.stuck.processing}p / ${health.stuck.publishing}pub`)}
        </div>
      )}

      {/* Task counts */}
      {health && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 20 }}>
          {Object.entries(health.counts).sort((a, b) => b[1] - a[1]).map(([st, cnt]) => (
            <div key={st} onClick={() => { setStatusFilter(st); setSelected(new Set()); }} style={{ padding: "6px 14px", borderRadius: 8, fontSize: 12, fontWeight: 600, background: (STATUS_COLORS[st] || "#6b7280") + "18", color: STATUS_COLORS[st] || "#6b7280", border: `1px solid ${(STATUS_COLORS[st] || "#6b7280")}40`, cursor: "pointer", textAlign: "center", minWidth: 70 }}>
              <div style={{ fontSize: 18, fontWeight: 700 }}>{cnt}</div>
              <div style={{ fontSize: 10 }}>{st}</div>
            </div>
          ))}
        </div>
      )}

      {/* Watchdog */}
      <div style={{ padding: 12, background: "#f8fafc", borderRadius: 10, border: "1px solid #e2e8f0", marginBottom: 20 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontWeight: 600, fontSize: 13 }}>Watchdog</span>
          {btnSm("#dbeafe", "#2563eb", wdLoading ? "..." : "Dry Run", () => runWatchdog(true), wdLoading)}
          {btnSm("#fee2e2", "#991b1b", "Run", () => runWatchdog(false), wdLoading)}
          {report && <span style={{ fontSize: 11, color: "#64748b" }}>Found {report.stuck_count} stuck {report.dry_run ? "(dry)" : ""}</span>}
        </div>
      </div>

      {/* Task table */}
      <div style={{ padding: 16, background: "#f8fafc", borderRadius: 10, border: "1px solid #e2e8f0" }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12, flexWrap: "wrap" }}>
          <span style={{ fontWeight: 600, fontSize: 14 }}>Tasks</span>
          <select value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setSelected(new Set()); }} style={{ padding: "4px 8px", borderRadius: 6, fontSize: 12, border: "1px solid #cbd5e1" }}>
            {STATUSES.map(s => <option key={s} value={s}>{s || "all"}</option>)}
          </select>
          <span style={{ fontSize: 11, color: "#64748b" }}>{tasks.length} tasks</span>
          {tasksLoading && <span style={{ fontSize: 11, color: "#94a3b8" }}>loading...</span>}
        </div>

        {/* Bulk actions bar */}
        {selected.size > 0 && (
          <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 10, padding: "8px 12px", background: "#dbeafe", borderRadius: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: "#1e40af" }}>{selected.size} selected</span>
            {btnSm("#f59e0b", "#fff", "⚡ Enqueue", () => bulkAction("bulk-enqueue", { ids: selectedIds }))}
            {btnSm("#fef3c7", "#92400e", "⏸ Pause", () => bulkAction("bulk-pause", { ids: selectedIds }))}
            {btnSm("#dbeafe", "#1e40af", "▶ Resume", () => bulkAction("bulk-resume", { ids: selectedIds }))}
            {btnSm("#991b1b", "#fff", "✕ Cancel", () => bulkAction("bulk-cancel", { ids: selectedIds }))}
            <span style={{ fontSize: 11, color: "#475569" }}>P:</span>
            <select value={bulkPriority} onChange={e => setBulkPriority(Number(e.target.value))} style={{ padding: "2px 4px", borderRadius: 4, fontSize: 11, border: "1px solid #cbd5e1", width: 52 }}>
              {Array.from({ length: 21 }, (_, i) => i - 10).reverse().map(v => <option key={v} value={v}>{v > 0 ? `+${v}` : v}</option>)}
            </select>
            {btnSm("#7c3aed", "#fff", "Set P", () => bulkAction("bulk-set-priority", { ids: selectedIds, priority: bulkPriority }))}
            {bulkMsg && <span style={{ fontSize: 11, color: bulkMsg.startsWith("✓") ? "#166534" : "#991b1b" }}>{bulkMsg}</span>}
          </div>
        )}

        {/* Table */}
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: "2px solid #e2e8f0", textAlign: "left" }}>
                <th style={{ padding: "6px 4px", width: 28 }}><input type="checkbox" checked={selected.size === tasks.length && tasks.length > 0} onChange={toggleAll} /></th>
                <th style={{ padding: "6px 4px" }}>ID</th>
                <th style={{ padding: "6px 4px" }}>Status</th>
                <th style={{ padding: "6px 4px" }}>P</th>
                <th style={{ padding: "6px 4px" }}>Project</th>
                <th style={{ padding: "6px 4px" }}>Platform</th>
                <th style={{ padding: "6px 4px" }}>Score</th>
                <th style={{ padding: "6px 4px" }}>Updated</th>
                <th style={{ padding: "6px 4px" }}>Flags</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map(t => {
                const sc = STATUS_COLORS[t.status] || "#6b7280";
                return (
                  <tr key={t.id} style={{ borderBottom: "1px solid #f1f5f9", background: selected.has(t.id) ? "#eff6ff" : "transparent" }}>
                    <td style={{ padding: "5px 4px" }}><input type="checkbox" checked={selected.has(t.id)} onChange={() => toggleSelect(t.id)} /></td>
                    <td style={{ padding: "5px 4px", fontWeight: 600 }}>
                      <a href={`/queue/${t.id}`} style={{ color: "#2563eb", textDecoration: "none" }}>#{t.id}</a>
                    </td>
                    <td style={{ padding: "5px 4px" }}>
                      <span style={{ padding: "2px 8px", borderRadius: 10, fontSize: 10, fontWeight: 600, background: sc + "18", color: sc }}>{t.status}</span>
                    </td>
                    <td style={{ padding: "5px 4px", fontWeight: 600, color: t.priority > 0 ? "#059669" : t.priority < 0 ? "#dc2626" : "#94a3b8" }}>
                      {t.priority > 0 ? `+${t.priority}` : t.priority}
                    </td>
                    <td style={{ padding: "5px 4px" }}>{t.project_id}</td>
                    <td style={{ padding: "5px 4px" }}>{t.platform}</td>
                    <td style={{ padding: "5px 4px", color: "#64748b" }}>{t.virality_score != null ? t.virality_score.toFixed(2) : "—"}</td>
                    <td style={{ padding: "5px 4px", color: "#94a3b8", fontSize: 10 }}>{t.updated_at ? new Date(t.updated_at).toLocaleString("ru") : "—"}</td>
                    <td style={{ padding: "5px 4px", display: "flex", gap: 3, flexWrap: "wrap" }}>
                      {t.pause_requested_at && chip("#fef3c7", "#92400e", "pause_req")}
                      {t.paused_at && chip("#fef3c7", "#92400e", "paused")}
                      {t.cancel_requested_at && chip("#fee2e2", "#991b1b", "cancel_req")}
                      {t.canceled_at && chip("#fee2e2", "#991b1b", "canceled")}
                      {t.celery_task_id && chip("#f1f5f9", "#64748b", "celery")}
                    </td>
                  </tr>
                );
              })}
              {tasks.length === 0 && !tasksLoading && (
                <tr><td colSpan={9} style={{ padding: 20, textAlign: "center", color: "#94a3b8" }}>No tasks</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
