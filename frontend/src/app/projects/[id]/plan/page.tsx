"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL || "";

type Slot = {
  at: string;
  task_id: number;
  candidate_id: number | null;
  score: number;
  effective_score: number;
  priority: number;
  reason: string;
};

type SkippedItem = { task_id: number; reason: string };

type DestPlan = {
  destination_id: number;
  social_account_id: number;
  platform: string;
  already_published_today: number;
  daily_limit: number;
  total_slots: number;
  slots: Slot[];
  skipped: SkippedItem[];
};

type Plan = {
  project_id: number;
  timezone: string;
  date: string;
  day: string;
  windows: string[][];
  min_gap_minutes: number;
  destinations: DestPlan[];
  error?: string;
};

type ApplyResult = {
  ok: { task_id: number; priority: number; enqueued?: boolean; celery_task_id?: string }[];
  failed: { task_id: number; reason: string }[];
  plan_summary?: { date: string; timezone: string; destinations: number };
};

type Toast = { message: string; type: "success" | "error" } | null;

const PLATFORM_COLORS: Record<string, string> = {
  tiktok: "#ff0050", youtube: "#ff0000", vk: "#0077ff", instagram: "#e4405f",
  TikTok: "#ff0050", YouTube: "#ff0000", VK: "#0077ff", Instagram: "#e4405f",
};

function fmtTime(iso: string): string {
  try { return new Date(iso).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }); } catch { return iso; }
}

export default function PlanPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const projectId = Number(params?.id);

  const [plan, setPlan] = useState<Plan | null>(null);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [toast, setToast] = useState<Toast>(null);
  const [applyResult, setApplyResult] = useState<ApplyResult | null>(null);

  // Controls
  const today = new Date().toISOString().slice(0, 10);
  const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
  const [dateChoice, setDateChoice] = useState<"today" | "tomorrow">("today");
  const [basePriority, setBasePriority] = useState(10);

  const selectedDate = dateChoice === "today" ? today : tomorrow;

  const showToast = (message: string, type: "success" | "error" = "success") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3500);
  };

  const loadPlan = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setPlan(null);
    setApplyResult(null);
    try {
      const res = await fetch(`${API}/api/projects/${projectId}/publish-plan?date=${selectedDate}`);
      if (res.ok) {
        const data = await res.json();
        if (data.error) { showToast(data.error, "error"); }
        else setPlan(data);
      } else showToast("Ошибка загрузки плана", "error");
    } catch { showToast("Сетевая ошибка", "error"); }
    setLoading(false);
  }, [projectId, selectedDate]);

  const applyPlan = async (enqueue: boolean) => {
    if (!projectId) return;
    setApplying(true);
    try {
      const res = await fetch(`${API}/api/projects/${projectId}/publish-plan/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date: selectedDate, base_priority: basePriority, enqueue }),
      });
      if (res.ok) {
        const data: ApplyResult = await res.json();
        setApplyResult(data);
        showToast(`Применено: ${data.ok.length} задач, ${data.failed.length} пропущено`);
      } else showToast("Ошибка применения", "error");
    } catch { showToast("Сетевая ошибка", "error"); }
    setApplying(false);
  };

  if (!projectId) return <div>Некорректный ID</div>;

  const totalSlots = plan?.destinations.reduce((s, d) => s + d.slots.length, 0) ?? 0;
  const totalSkipped = plan?.destinations.reduce((s, d) => s + d.skipped.length, 0) ?? 0;

  return (
    <div style={{ maxWidth: 1000, margin: "0 auto", padding: "32px 16px" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button onClick={() => router.push(`/projects`)} style={{ width: 32, height: 32, borderRadius: 8, background: "#f1f5f9", fontSize: 16, display: "flex", alignItems: "center", justifyContent: "center", border: "none", cursor: "pointer" }}>←</button>
          <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Publish Plan — проект #{projectId}</h1>
        </div>
      </div>

      {/* Controls */}
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 20, padding: "12px 16px", background: "#f8fafc", borderRadius: 10, border: "1px solid #e2e8f0", flexWrap: "wrap" }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: "#475569" }}>Дата:</span>
        <button onClick={() => setDateChoice("today")} style={{ padding: "5px 14px", borderRadius: 6, fontSize: 12, fontWeight: 600, border: "none", cursor: "pointer", background: dateChoice === "today" ? "#3b82f6" : "#e2e8f0", color: dateChoice === "today" ? "#fff" : "#475569" }}>Сегодня ({today})</button>
        <button onClick={() => setDateChoice("tomorrow")} style={{ padding: "5px 14px", borderRadius: 6, fontSize: 12, fontWeight: 600, border: "none", cursor: "pointer", background: dateChoice === "tomorrow" ? "#3b82f6" : "#e2e8f0", color: dateChoice === "tomorrow" ? "#fff" : "#475569" }}>Завтра ({tomorrow})</button>

        <span style={{ fontSize: 12, fontWeight: 600, color: "#475569", marginLeft: 12 }}>Base P:</span>
        <select value={basePriority} onChange={e => setBasePriority(Number(e.target.value))} style={{ padding: "4px 6px", borderRadius: 4, fontSize: 12, border: "1px solid #cbd5e1" }}>
          {Array.from({ length: 21 }, (_, i) => i - 10).reverse().map(v => <option key={v} value={v}>{v > 0 ? `+${v}` : v}</option>)}
        </select>

        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button onClick={loadPlan} disabled={loading} style={{ padding: "6px 18px", borderRadius: 8, fontSize: 12, fontWeight: 600, border: "none", cursor: "pointer", background: "#3b82f6", color: "#fff", opacity: loading ? 0.6 : 1 }}>
            {loading ? "..." : "Собрать план"}
          </button>
          {plan && (
            <>
              <button onClick={() => applyPlan(false)} disabled={applying} style={{ padding: "6px 18px", borderRadius: 8, fontSize: 12, fontWeight: 600, border: "none", cursor: "pointer", background: "#7c3aed", color: "#fff", opacity: applying ? 0.6 : 1 }}>
                {applying ? "..." : "Применить приоритеты"}
              </button>
              <button onClick={() => applyPlan(true)} disabled={applying} style={{ padding: "6px 18px", borderRadius: 8, fontSize: 12, fontWeight: 600, border: "none", cursor: "pointer", background: "#f59e0b", color: "#fff", opacity: applying ? 0.6 : 1 }}>
                {applying ? "..." : "Применить + Enqueue"}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Plan summary */}
      {plan && (
        <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
          <span style={{ padding: "4px 12px", borderRadius: 8, fontSize: 11, fontWeight: 600, background: "#dbeafe", color: "#1e40af" }}>TZ: {plan.timezone}</span>
          <span style={{ padding: "4px 12px", borderRadius: 8, fontSize: 11, fontWeight: 600, background: "#dbeafe", color: "#1e40af" }}>{plan.date} ({plan.day})</span>
          <span style={{ padding: "4px 12px", borderRadius: 8, fontSize: 11, fontWeight: 600, background: "#dcfce7", color: "#166534" }}>{totalSlots} слотов заполнено</span>
          {totalSkipped > 0 && <span style={{ padding: "4px 12px", borderRadius: 8, fontSize: 11, fontWeight: 600, background: "#fee2e2", color: "#991b1b" }}>{totalSkipped} пропущено</span>}
          {plan.windows.length > 0 && <span style={{ padding: "4px 12px", borderRadius: 8, fontSize: 11, fontWeight: 600, background: "#f1f5f9", color: "#64748b" }}>Окна: {plan.windows.map(w => w.join("–")).join(", ")}</span>}
          <span style={{ padding: "4px 12px", borderRadius: 8, fontSize: 11, fontWeight: 600, background: "#f1f5f9", color: "#64748b" }}>Gap: {plan.min_gap_minutes}m</span>
        </div>
      )}

      {/* Apply result */}
      {applyResult && (
        <div style={{ padding: 12, background: "#dcfce7", borderRadius: 8, marginBottom: 16, fontSize: 12 }}>
          <strong>Результат:</strong> {applyResult.ok.length} задач обновлено
          {applyResult.ok.some(o => o.enqueued) && `, ${applyResult.ok.filter(o => o.enqueued).length} enqueued`}
          {applyResult.failed.length > 0 && <span style={{ color: "#991b1b" }}>, {applyResult.failed.length} пропущено</span>}
          <div style={{ marginTop: 6, display: "flex", gap: 6, flexWrap: "wrap" }}>
            {applyResult.ok.map(o => (
              <span key={o.task_id} style={{ padding: "2px 8px", borderRadius: 4, fontSize: 10, background: "#22c55e20", color: "#166534" }}>
                #{o.task_id} P:{o.priority > 0 ? `+${o.priority}` : o.priority}{o.enqueued ? " ⚡" : ""}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Destination plans */}
      {plan?.destinations.map(dest => (
        <div key={dest.destination_id} style={{ marginBottom: 24, padding: 16, background: "#f8fafc", borderRadius: 10, border: "1px solid #e2e8f0" }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12 }}>
            <span style={{ padding: "4px 10px", borderRadius: 6, fontSize: 11, fontWeight: 600, background: PLATFORM_COLORS[dest.platform] || "#6b7280", color: "#fff" }}>{dest.platform}</span>
            <span style={{ fontSize: 13, fontWeight: 600 }}>Destination #{dest.destination_id}</span>
            <span style={{ fontSize: 11, color: "#64748b" }}>acct #{dest.social_account_id}</span>
            <span style={{ fontSize: 11, color: "#64748b" }}>• {dest.already_published_today}/{dest.daily_limit} published today</span>
            <span style={{ fontSize: 11, color: "#64748b" }}>• {dest.total_slots} slots</span>
          </div>

          {/* Slots table */}
          {dest.slots.length > 0 ? (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, marginBottom: 8 }}>
              <thead>
                <tr style={{ borderBottom: "2px solid #e2e8f0", textAlign: "left" }}>
                  <th style={{ padding: "6px 8px" }}>#</th>
                  <th style={{ padding: "6px 8px" }}>Время</th>
                  <th style={{ padding: "6px 8px" }}>Task</th>
                  <th style={{ padding: "6px 8px" }}>Candidate</th>
                  <th style={{ padding: "6px 8px" }}>Score</th>
                  <th style={{ padding: "6px 8px" }}>Eff. Score</th>
                  <th style={{ padding: "6px 8px" }}>P</th>
                </tr>
              </thead>
              <tbody>
                {dest.slots.map((slot, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid #f1f5f9" }}>
                    <td style={{ padding: "6px 8px", color: "#94a3b8" }}>{i + 1}</td>
                    <td style={{ padding: "6px 8px", fontWeight: 600 }}>{fmtTime(slot.at)}</td>
                    <td style={{ padding: "6px 8px" }}>
                      <a href={`/queue/${slot.task_id}`} style={{ color: "#2563eb", textDecoration: "none", fontWeight: 600 }}>#{slot.task_id}</a>
                    </td>
                    <td style={{ padding: "6px 8px", color: "#64748b" }}>{slot.candidate_id ? `#${slot.candidate_id}` : "—"}</td>
                    <td style={{ padding: "6px 8px" }}>
                      <span style={{ fontWeight: 600, color: slot.score >= 0.7 ? "#22c55e" : slot.score >= 0.4 ? "#eab308" : "#ef4444" }}>{slot.score.toFixed(2)}</span>
                    </td>
                    <td style={{ padding: "6px 8px", color: "#64748b" }}>{slot.effective_score.toFixed(2)}</td>
                    <td style={{ padding: "6px 8px", fontWeight: 600, color: basePriority - i > 0 ? "#059669" : "#dc2626" }}>
                      {basePriority - i > 0 ? `+${basePriority - i}` : basePriority - i}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div style={{ fontSize: 12, color: "#94a3b8", padding: "8px 0" }}>Нет доступных задач для слотов</div>
          )}

          {/* Skipped */}
          {dest.skipped.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "#94a3b8", marginBottom: 4 }}>Пропущено ({dest.skipped.length}):</div>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {dest.skipped.map((s, i) => (
                  <span key={i} style={{ padding: "2px 8px", borderRadius: 4, fontSize: 10, background: "#fee2e2", color: "#991b1b" }}>
                    #{s.task_id}: {s.reason}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      ))}

      {!plan && !loading && (
        <div style={{ padding: 60, textAlign: "center", color: "#94a3b8" }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>📋</div>
          <div style={{ fontSize: 14 }}>Нажмите «Собрать план» для генерации расписания публикаций</div>
        </div>
      )}

      {loading && (
        <div style={{ padding: 60, textAlign: "center", color: "#94a3b8" }}>Загрузка...</div>
      )}

      {/* Toast */}
      {toast && (
        <div style={{
          position: "fixed", bottom: 24, right: 24,
          padding: "12px 20px", borderRadius: 8,
          background: toast.type === "error" ? "#ef4444" : "#22c55e",
          color: "#fff", fontWeight: 500, fontSize: 14,
          boxShadow: "0 4px 12px rgba(0,0,0,0.3)", zIndex: 200,
        }}>
          {toast.message}
        </div>
      )}
    </div>
  );
}
