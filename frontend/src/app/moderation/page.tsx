"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type QueueItem = {
  task_id: number;
  step_index: number;
  tool_id: string;
  step_name: string | null;
  project_id: number;
  project_name: string | null;
  moderation_status: string;
};

type Stats = { pending: number; approved: number; rejected: number; total: number };

const STATUS_CLASS: Record<string, string> = {
  pending: "badge-warning", approved: "badge-success", rejected: "badge-error",
};

const STATUS_LABEL: Record<string, string> = {
  pending: "Ожидает", approved: "Одобрено", rejected: "Отклонено",
};

export default function ModerationPage() {
  const router = useRouter();
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");

  useEffect(() => { load(); }, [filter]);

  const load = async () => {
    setLoading(true);
    const params = filter ? `?status=${filter}` : "";
    const [qRes, sRes] = await Promise.all([fetch(`/api/moderation/queue${params}`), fetch(`/api/moderation/stats`)]);
    if (qRes.ok) { const d = await qRes.json(); setQueue(d.items || []); }
    if (sRes.ok) setStats(await sRes.json());
    setLoading(false);
  };

  const action = async (taskId: number, stepIndex: number, act: "approve" | "reject") => {
    const body = act === "reject" ? { comment: prompt("Причина:") || "Отклонено" } : {};
    await fetch(`/api/moderation/tasks/${taskId}/steps/${stepIndex}/${act}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    load();
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Модерация</h1>
          <p style={{ color: "var(--fg-subtle)", marginTop: 4, fontSize: 13 }}>{queue.length} в очереди</p>
        </div>
        <button className="btn btn-ghost" onClick={load}>↻ Обновить</button>
      </div>

      {stats && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 24 }}>
          {[
            { key: "", label: "Всего", val: stats.total, cls: "" },
            { key: "pending", label: "Ожидает", val: stats.pending, cls: "badge-warning" },
            { key: "approved", label: "Одобрено", val: stats.approved, cls: "badge-success" },
            { key: "rejected", label: "Отклонено", val: stats.rejected, cls: "badge-error" },
          ].map(s => (
            <button
              key={s.key}
              className={`card ${filter === s.key ? "active" : ""}`}
              onClick={() => setFilter(filter === s.key ? "" : s.key)}
              style={{ padding: 16, textAlign: "left", border: filter === s.key ? "1px solid var(--primary)" : undefined }}
            >
              <div style={{ fontSize: 24, fontWeight: 600 }}>{s.val}</div>
              <div style={{ fontSize: 12, color: "var(--fg-subtle)", marginTop: 4 }}>{s.label}</div>
            </button>
          ))}
        </div>
      )}

      <div className="card">
        {loading ? (
          <div className="empty">Загрузка...</div>
        ) : queue.length === 0 ? (
          <div className="empty">
            <div style={{ fontSize: 32, marginBottom: 8 }}>✓</div>
            Очередь пуста
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Task</th>
                <th>Шаг</th>
                <th>Проект</th>
                <th>Статус</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {queue.map(item => (
                <tr key={`${item.task_id}-${item.step_index}`}>
                  <td style={{ fontWeight: 500 }}>#{item.task_id}</td>
                  <td>{item.step_name || item.tool_id}</td>
                  <td style={{ color: "var(--fg-subtle)" }}>{item.project_name || `#${item.project_id}`}</td>
                  <td><span className={`badge ${STATUS_CLASS[item.moderation_status] || ""}`}>{STATUS_LABEL[item.moderation_status] || item.moderation_status}</span></td>
                  <td>
                    <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
                      {item.moderation_status === "pending" && (
                        <>
                          <button className="btn badge-success" style={{ padding: "4px 8px" }} onClick={() => action(item.task_id, item.step_index, "approve")}>✓</button>
                          <button className="btn badge-error" style={{ padding: "4px 8px" }} onClick={() => action(item.task_id, item.step_index, "reject")}>×</button>
                        </>
                      )}
                      <button className="btn btn-ghost" onClick={() => router.push(`/moderation/${item.task_id}`)}>Открыть</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
