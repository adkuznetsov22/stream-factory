"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type DashboardStats = {
  tasks: { total: number; by_status: Record<string, number>; completion_rate: number; per_day: { date: string; count: number }[] };
  projects: { total: number; active: number };
  accounts: { total: number };
};

type ProjectStats = { id: number; name: string; status: string; task_count: number; done_count: number; error_count: number; success_rate: number };
type Activity = { task_id: number; project_name: string; status: string; timestamp: string };

export default function DashboardPage() {
  const router = useRouter();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [projects, setProjects] = useState<ProjectStats[]>([]);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(7);

  const load = async () => {
    setLoading(true);
    const [sRes, pRes, aRes] = await Promise.all([
      fetch(`/api/dashboard/stats?days=${days}`),
      fetch(`/api/dashboard/projects?days=${days}`),
      fetch(`/api/dashboard/activity?limit=10`),
    ]);
    if (sRes.ok) setStats(await sRes.json());
    if (pRes.ok) setProjects(await pRes.json());
    if (aRes.ok) setActivity(await aRes.json());
    setLoading(false);
  };

  useEffect(() => { load(); }, [days]);

  const fmtDate = (d: string) => new Date(d).toLocaleDateString("ru", { day: "numeric", month: "short" });
  const fmtTime = (d: string) => {
    const mins = Math.floor((Date.now() - new Date(d).getTime()) / 60000);
    if (mins < 60) return `${mins}м`;
    if (mins < 1440) return `${Math.floor(mins / 60)}ч`;
    return fmtDate(d);
  };

  const maxDay = stats?.tasks.per_day.reduce((m, d) => Math.max(m, d.count), 0) || 1;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Статистика</h1>
          <p style={{ color: "var(--fg-subtle)", marginTop: 4, fontSize: 13 }}>За {days} дней</p>
        </div>
        <div className="filter-tabs">
          {[7, 14, 30].map(d => (
            <button key={d} className={`filter-tab ${days === d ? "active" : ""}`} onClick={() => setDays(d)}>{d}д</button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="empty">Загрузка...</div>
      ) : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 24 }}>
            {[
              { label: "Всего задач", val: stats?.tasks.total || 0 },
              { label: "Завершено", val: `${stats?.tasks.completion_rate || 0}%`, color: "var(--success)" },
              { label: "Проектов", val: stats?.projects.active || 0 },
              { label: "Аккаунтов", val: stats?.accounts.total || 0 },
            ].map((s, i) => (
              <div key={i} className="card" style={{ padding: 16 }}>
                <div style={{ fontSize: 12, color: "var(--fg-subtle)", marginBottom: 4 }}>{s.label}</div>
                <div style={{ fontSize: 24, fontWeight: 600, color: s.color }}>{s.val}</div>
              </div>
            ))}
          </div>

          {/* Chart + Activity */}
          <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16, marginBottom: 24 }}>
            {/* Chart */}
            <div style={{ background: "var(--bg-subtle)", borderRadius: "var(--radius-lg)", border: "1px solid var(--border)", padding: 20 }}>
              <div style={{ fontWeight: 600, marginBottom: 16 }}>Задачи по дням</div>
              <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 120 }}>
                {stats?.tasks.per_day.map((d, i) => (
                  <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center" }}>
                    <div
                      style={{
                        width: "100%",
                        height: `${(d.count / maxDay) * 100}px`,
                        background: "var(--accent)",
                        borderRadius: "4px 4px 0 0",
                        minHeight: d.count > 0 ? 4 : 0,
                      }}
                    />
                    <div style={{ fontSize: 10, color: "var(--fg-subtle)", marginTop: 4 }}>{fmtDate(d.date)}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Activity Feed */}
            <div style={{ background: "var(--bg-subtle)", borderRadius: "var(--radius-lg)", border: "1px solid var(--border)", padding: 20 }}>
              <div style={{ fontWeight: 600, marginBottom: 16 }}>Активность</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 180, overflow: "auto" }}>
                {activity.length === 0 ? (
                  <div style={{ color: "var(--fg-subtle)", fontSize: 13 }}>Нет активности</div>
                ) : activity.map((a, i) => (
                  <div
                    key={i}
                    onClick={() => router.push(`/moderation/${a.task_id}`)}
                    style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", padding: 8, borderRadius: 6, background: "var(--bg-muted)" }}
                  >
                    <div style={{ width: 8, height: 8, borderRadius: "50%", background: a.status === "done" ? "var(--success)" : a.status === "error" ? "var(--error)" : "var(--fg-subtle)" }} />
                    <div style={{ flex: 1, fontSize: 12 }}>
                      <span style={{ fontWeight: 500 }}>#{a.task_id}</span>
                      <span style={{ color: "var(--fg-subtle)" }}> • {a.project_name}</span>
                    </div>
                    <div style={{ fontSize: 11, color: "var(--fg-subtle)" }}>{fmtTime(a.timestamp)}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Status breakdown */}
          <div style={{ background: "var(--bg-subtle)", borderRadius: "var(--radius-lg)", border: "1px solid var(--border)", padding: 20, marginBottom: 24 }}>
            <div style={{ fontWeight: 600, marginBottom: 16 }}>Статусы задач</div>
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
              {Object.entries(stats?.tasks.by_status || {}).map(([status, count]) => (
                <div key={status} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <div style={{ width: 12, height: 12, borderRadius: 3, background: status === "done" ? "var(--success)" : status === "error" ? "var(--error)" : "var(--fg-subtle)" }} />
                  <span style={{ fontSize: 13 }}>{status}: <strong>{count}</strong></span>
                </div>
              ))}
            </div>
          </div>

          {/* Projects Table */}
          <div style={{ background: "var(--bg-subtle)", borderRadius: "var(--radius-lg)", border: "1px solid var(--border)" }}>
            <div style={{ padding: 20, borderBottom: "1px solid var(--border)", fontWeight: 600 }}>
              Проекты ({projects.length})
            </div>
            <div style={{ padding: 12 }}>
              {projects.length === 0 ? (
                <div style={{ padding: 20, textAlign: "center", color: "var(--fg-subtle)" }}>Нет проектов</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {projects.map(p => (
                    <div
                      key={p.id}
                      onClick={() => router.push(`/projects`)}
                      style={{
                        display: "grid",
                        gridTemplateColumns: "2fr 1fr 1fr 1fr 100px",
                        alignItems: "center",
                        padding: "12px 16px",
                        borderRadius: "var(--radius)",
                        cursor: "pointer",
                        background: "var(--bg-muted)",
                      }}
                    >
                      <div>
                        <div style={{ fontWeight: 500 }}>{p.name}</div>
                        <div style={{ fontSize: 11, color: "var(--fg-subtle)" }}>{p.status}</div>
                      </div>
                      <div style={{ textAlign: "center" }}>
                        <div style={{ fontWeight: 600 }}>{p.task_count}</div>
                        <div style={{ fontSize: 11, color: "var(--fg-subtle)" }}>задач</div>
                      </div>
                      <div style={{ textAlign: "center" }}>
                        <div style={{ fontWeight: 600, color: "#22c55e" }}>{p.done_count}</div>
                        <div style={{ fontSize: 11, color: "var(--fg-subtle)" }}>готово</div>
                      </div>
                      <div style={{ textAlign: "center" }}>
                        <div style={{ fontWeight: 600, color: "#ef4444" }}>{p.error_count}</div>
                        <div style={{ fontSize: 11, color: "var(--fg-subtle)" }}>ошибок</div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div style={{
                          padding: "4px 10px",
                          borderRadius: 20,
                          background: p.success_rate > 80 ? "#22c55e20" : p.success_rate > 50 ? "#eab30820" : "#ef444420",
                          color: p.success_rate > 80 ? "#22c55e" : p.success_rate > 50 ? "#eab308" : "#ef4444",
                          fontSize: 12,
                          fontWeight: 600,
                          display: "inline-block",
                        }}>
                          {p.success_rate}%
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
