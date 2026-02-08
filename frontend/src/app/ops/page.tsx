"use client";

import { useEffect, useState, useCallback } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type HealthData = {
  counts: Record<string, number>;
  stuck: { processing: number; publishing: number };
  scheduler_enabled: boolean;
  watchdog_enabled: boolean;
  last_decisions: { action: string; at: string | null }[];
};

type WatchdogReport = {
  stuck_count: number;
  stuck_processing: number;
  stuck_publishing: number;
  items: {
    task_id: number;
    project_id: number;
    old_status: string;
    age_minutes: number;
    action: string;
    error_message: string;
  }[];
  dry_run: boolean;
  run_at: string;
  settings: {
    stuck_processing_minutes: number;
    stuck_publishing_minutes: number;
    auto_requeue: boolean;
  };
};

export default function OpsPage() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [report, setReport] = useState<WatchdogReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [wdLoading, setWdLoading] = useState(false);

  const loadHealth = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/ops/health`);
      if (res.ok) setHealth(await res.json());
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { loadHealth(); }, [loadHealth]);

  const runWatchdog = async (dryRun: boolean) => {
    setWdLoading(true);
    try {
      const res = await fetch(`${API}/api/ops/watchdog?dry_run=${dryRun}`, { method: "POST" });
      if (res.ok) {
        setReport(await res.json());
        loadHealth();
      }
    } catch { /* ignore */ }
    setWdLoading(false);
  };

  const STATUS_COLORS: Record<string, string> = {
    queued: "#3b82f6",
    processing: "#f59e0b",
    ready: "#22c55e",
    done: "#22c55e",
    publishing: "#8b5cf6",
    published: "#10b981",
    error: "#ef4444",
    cancelled: "#6b7280",
  };

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "32px 16px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>Operations</h1>
        <button
          onClick={loadHealth}
          disabled={loading}
          style={{
            padding: "6px 16px", borderRadius: 8, fontSize: 12, fontWeight: 500, cursor: "pointer",
            background: "#dbeafe", color: "#2563eb", border: "1px solid #93c5fd",
          }}
        >
          {loading ? "Loading..." : "↻ Refresh"}
        </button>
      </div>

      {/* Health */}
      {health && (
        <>
          {/* Status indicators */}
          <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
            <div style={{
              padding: "6px 12px", borderRadius: 8, fontSize: 12, fontWeight: 600,
              background: health.scheduler_enabled ? "#dcfce7" : "#fee2e2",
              color: health.scheduler_enabled ? "#166534" : "#991b1b",
            }}>
              Scheduler: {health.scheduler_enabled ? "ON" : "OFF"}
            </div>
            <div style={{
              padding: "6px 12px", borderRadius: 8, fontSize: 12, fontWeight: 600,
              background: health.watchdog_enabled ? "#dcfce7" : "#fee2e2",
              color: health.watchdog_enabled ? "#166534" : "#991b1b",
            }}>
              Watchdog: {health.watchdog_enabled ? "ON" : "OFF"}
            </div>
            {(health.stuck.processing > 0 || health.stuck.publishing > 0) && (
              <div style={{
                padding: "6px 12px", borderRadius: 8, fontSize: 12, fontWeight: 600,
                background: "#fee2e2", color: "#991b1b",
              }}>
                ⚠ Stuck: {health.stuck.processing} processing, {health.stuck.publishing} publishing
              </div>
            )}
          </div>

          {/* Task counts */}
          <div style={{
            marginBottom: 24, padding: 16, background: "var(--bg-muted)", borderRadius: 10,
            border: "1px solid var(--border)",
          }}>
            <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 12 }}>Task Counts</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
              {Object.entries(health.counts).sort((a, b) => b[1] - a[1]).map(([status, count]) => (
                <div key={status} style={{
                  padding: "8px 16px", borderRadius: 8, fontSize: 13, fontWeight: 600,
                  background: (STATUS_COLORS[status] || "#6b7280") + "18",
                  color: STATUS_COLORS[status] || "#6b7280",
                  border: `1px solid ${(STATUS_COLORS[status] || "#6b7280")}40`,
                  minWidth: 80, textAlign: "center",
                }}>
                  <div style={{ fontSize: 20, fontWeight: 700 }}>{count}</div>
                  <div style={{ fontSize: 11 }}>{status}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Last decisions */}
          {health.last_decisions.length > 0 && (
            <div style={{
              marginBottom: 24, padding: 16, background: "var(--bg-muted)", borderRadius: 10,
              border: "1px solid var(--border)",
            }}>
              <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8 }}>Recent Decisions</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {health.last_decisions.map((d, i) => (
                  <div key={i} style={{ display: "flex", gap: 12, fontSize: 12, alignItems: "center" }}>
                    <span style={{
                      padding: "2px 8px", borderRadius: 4, fontSize: 10, fontWeight: 600,
                      background: d.action.includes("watchdog") ? "#fee2e2" : "#dbeafe",
                      color: d.action.includes("watchdog") ? "#991b1b" : "#1e40af",
                    }}>
                      {d.action}
                    </span>
                    <span style={{ color: "var(--fg-subtle)" }}>
                      {d.at ? new Date(d.at).toLocaleString("ru") : "—"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Watchdog */}
      <div style={{
        padding: 16, background: "var(--bg-muted)", borderRadius: 10,
        border: "1px solid var(--border)", marginBottom: 24,
      }}>
        <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 12 }}>Watchdog</div>
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <button
            onClick={() => runWatchdog(true)}
            disabled={wdLoading}
            style={{
              padding: "6px 16px", borderRadius: 8, fontSize: 12, fontWeight: 500, cursor: "pointer",
              background: wdLoading ? "var(--bg-subtle)" : "#dbeafe",
              color: wdLoading ? "var(--fg-subtle)" : "#2563eb",
              border: "1px solid #93c5fd",
            }}
          >
            {wdLoading ? "Running..." : "Dry Run"}
          </button>
          <button
            onClick={() => runWatchdog(false)}
            disabled={wdLoading}
            style={{
              padding: "6px 16px", borderRadius: 8, fontSize: 12, fontWeight: 500, cursor: "pointer",
              background: wdLoading ? "var(--bg-subtle)" : "#fee2e2",
              color: wdLoading ? "var(--fg-subtle)" : "#991b1b",
              border: "1px solid #fca5a5",
            }}
          >
            Run Watchdog
          </button>
        </div>

        {report && (
          <div style={{ padding: 12, background: "var(--bg-subtle)", borderRadius: 8, border: "1px solid var(--border)" }}>
            <div style={{ display: "flex", gap: 16, marginBottom: 8, fontSize: 12, alignItems: "center" }}>
              {report.dry_run && (
                <span style={{ background: "#dbeafe", color: "#2563eb", padding: "2px 8px", borderRadius: 10, fontSize: 10, fontWeight: 600 }}>DRY RUN</span>
              )}
              <span>Found: <strong>{report.stuck_count}</strong> stuck</span>
              <span style={{ color: "#f59e0b" }}>Processing: <strong>{report.stuck_processing}</strong></span>
              <span style={{ color: "#8b5cf6" }}>Publishing: <strong>{report.stuck_publishing}</strong></span>
              <span style={{ color: "var(--fg-subtle)", fontSize: 10 }}>
                thresholds: processing &gt; {report.settings.stuck_processing_minutes}m, publishing &gt; {report.settings.stuck_publishing_minutes}m
              </span>
            </div>
            {report.items.length > 0 ? (
              <div style={{ fontSize: 11 }}>
                {report.items.map(item => (
                  <div key={item.task_id} style={{ display: "flex", gap: 8, padding: "3px 0", alignItems: "center" }}>
                    <span style={{ color: "#ef4444", fontWeight: 600 }}>Task #{item.task_id}</span>
                    <span style={{ color: "var(--fg-subtle)" }}>{item.old_status}</span>
                    <span style={{ color: "var(--fg-subtle)" }}>{item.age_minutes}m stuck</span>
                    <span style={{
                      padding: "1px 6px", borderRadius: 4, fontSize: 10, fontWeight: 600,
                      background: item.action.includes("would") ? "#fef3c7" : "#fee2e2",
                      color: item.action.includes("would") ? "#92400e" : "#991b1b",
                    }}>
                      {item.action}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: 12, color: "#22c55e" }}>✓ No stuck tasks found</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
