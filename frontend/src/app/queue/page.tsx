"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type Task = {
  id: number;
  project_id: number;
  platform: string;
  status: string;
  error_message?: string | null;
  created_at?: string | null;
  caption_text?: string | null;
  artifacts?: { thumbnail_path?: string | null } | null;
};

type Project = { id: number; name: string };

const STATUS_LABELS: Record<string, string> = {
  queued: "Очередь", processing: "Обработка", ready_for_review: "Проверка", done: "Готово", ready_for_publish: "К публикации", error: "Ошибка", published: "Опубликовано",
};

const STATUS_CLASS: Record<string, string> = {
  queued: "", processing: "badge-info", ready_for_review: "badge-warning", done: "badge-success", ready_for_publish: "badge-warning", error: "badge-error", published: "badge-info",
};

export default function QueuePage() {
  const router = useRouter();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [projectId, setProjectId] = useState("");
  const [processing, setProcessing] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    const params = new URLSearchParams();
    if (filter !== "all") params.set("status", filter);
    if (projectId) params.set("project_id", projectId);
    const [tRes, pRes] = await Promise.all([fetch(`/api/publish-tasks?${params}`), fetch("/api/projects")]);
    if (tRes.ok) { const d = await tRes.json(); setTasks(Array.isArray(d) ? d : d.items || []); }
    if (pRes.ok) setProjects(await pRes.json());
    setLoading(false);
  };

  useEffect(() => { load(); }, [filter, projectId]);

  const process = async (id: number) => { setProcessing(id); await fetch(`/api/publish-tasks/${id}/process-v2`, { method: "POST" }); setProcessing(null); load(); };
  const approve = async (id: number) => { await fetch(`/api/publish-tasks/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: "done" }) }); load(); };
  const del = async (id: number) => { if (!confirm("Удалить?")) return; await fetch(`/api/publish-tasks/${id}`, { method: "DELETE" }); load(); };
  const getProj = (id: number) => projects.find(p => p.id === id);
  const fmtDate = (d?: string | null) => d ? new Date(d).toLocaleDateString("ru") : "—";

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Очередь</h1>
          <p style={{ color: "var(--fg-subtle)", marginTop: 4, fontSize: 13 }}>{tasks.length} задач</p>
        </div>
        <button className="btn btn-ghost" onClick={load}>↻ Обновить</button>
      </div>

      <div className="filters">
        <div className="filter-tabs">
          {["all", "queued", "processing", "ready_for_review", "done", "ready_for_publish", "error"].map(s => (
            <button key={s} className={`filter-tab ${filter === s ? "active" : ""}`} onClick={() => setFilter(s)}>
              {s === "all" ? "Все" : STATUS_LABELS[s]}
            </button>
          ))}
        </div>
        <select value={projectId} onChange={e => setProjectId(e.target.value)} style={{ minWidth: 160 }}>
          <option value="">Все проекты</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      <div className="card">
        {loading ? (
          <div className="empty">Загрузка...</div>
        ) : tasks.length === 0 ? (
          <div className="empty">Нет задач</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Проект</th>
                <th>Платформа</th>
                <th>Статус</th>
                <th>Дата</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {tasks.map(t => (
                <tr key={t.id} style={{ cursor: "pointer" }} onClick={() => router.push(`/queue/${t.id}`)}>
                  <td style={{ fontWeight: 500 }}>#{t.id}</td>
                  <td>{getProj(t.project_id)?.name || `#${t.project_id}`}</td>
                  <td>{t.platform}</td>
                  <td><span className={`badge ${STATUS_CLASS[t.status] || ""}`}>{STATUS_LABELS[t.status] || t.status}</span></td>
                  <td style={{ color: "var(--fg-subtle)" }}>{fmtDate(t.created_at)}</td>
                  <td>
                    <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }} onClick={e => e.stopPropagation()}>
                      {t.status === "queued" && (
                        <button className="btn btn-primary" style={{ padding: "4px 8px", fontSize: 11 }} onClick={() => process(t.id)} disabled={processing === t.id}>
                          {processing === t.id ? "..." : "▶"}
                        </button>
                      )}
                      {t.status === "ready_for_review" && (
                        <button className="btn badge-success" style={{ padding: "4px 8px", fontSize: 11 }} onClick={() => approve(t.id)}>✓</button>
                      )}
                      <button className="btn btn-ghost" onClick={() => del(t.id)}>×</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {tasks.some(t => t.error_message) && (
        <div style={{ marginTop: 24 }}>
          <h3 style={{ fontSize: 14, fontWeight: 500, marginBottom: 12, color: "var(--error)" }}>Ошибки</h3>
          {tasks.filter(t => t.error_message).map(t => (
            <div key={t.id} style={{ padding: 12, background: "rgba(239,68,68,0.1)", borderRadius: 6, marginBottom: 8, fontSize: 13 }}>
              <strong>#{t.id}:</strong> {t.error_message}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
