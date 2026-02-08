"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";

type Brief = {
  id: number;
  project_id: number;
  title: string;
  topic: string | null;
  description: string | null;
  target_platform: string | null;
  style: string | null;
  tone: string | null;
  language: string;
  target_duration_sec: number | null;
  reference_urls: string[] | null;
  llm_prompt_template: string | null;
  status: string;
  created_at: string | null;
  updated_at: string | null;
};

type Toast = { message: string; type: "success" | "error" } | null;

const STATUS_OPTIONS = ["draft", "active", "completed", "archived"];
const PLATFORM_OPTIONS = ["", "TikTok", "YouTube", "VK", "Instagram"];
const STYLE_OPTIONS = ["", "educational", "entertaining", "review", "tutorial", "story", "news"];
const TONE_OPTIONS = ["", "casual", "formal", "humorous", "serious", "inspirational"];

function fmtDate(d: string | null): string {
  if (!d) return "—";
  return new Date(d).toLocaleDateString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function statusBadge(s: string): { bg: string; fg: string } {
  switch (s) {
    case "draft": return { bg: "var(--bg-hover)", fg: "var(--fg-subtle)" };
    case "active": return { bg: "#22c55e20", fg: "#22c55e" };
    case "completed": return { bg: "#6366f120", fg: "#6366f1" };
    case "archived": return { bg: "#78716c20", fg: "#78716c" };
    default: return { bg: "var(--bg-hover)", fg: "var(--fg-subtle)" };
  }
}

const emptyForm = {
  title: "",
  topic: "",
  description: "",
  target_platform: "",
  style: "",
  tone: "",
  language: "ru",
  target_duration_sec: "",
  reference_urls: "",
  llm_prompt_template: "",
};

export default function ProjectBriefsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const projectId = Number(params?.id);

  const [briefs, setBriefs] = useState<Brief[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<Toast>(null);

  // Create / Edit
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);

  const showToast = (message: string, type: "success" | "error" = "success") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const loadBriefs = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/projects/${projectId}/briefs`);
      if (res.ok) setBriefs(await res.json());
    } catch { /* ignore */ }
    setLoading(false);
  }, [projectId]);

  useEffect(() => { loadBriefs(); }, [loadBriefs]);

  const openCreate = () => {
    setEditId(null);
    setForm(emptyForm);
    setShowForm(true);
  };

  const openEdit = (b: Brief) => {
    setEditId(b.id);
    setForm({
      title: b.title,
      topic: b.topic || "",
      description: b.description || "",
      target_platform: b.target_platform || "",
      style: b.style || "",
      tone: b.tone || "",
      language: b.language || "ru",
      target_duration_sec: b.target_duration_sec ? String(b.target_duration_sec) : "",
      reference_urls: Array.isArray(b.reference_urls) ? b.reference_urls.join("\n") : "",
      llm_prompt_template: b.llm_prompt_template || "",
    });
    setShowForm(true);
  };

  const save = async () => {
    if (!form.title.trim()) { showToast("Введите название", "error"); return; }
    setSaving(true);
    const body: Record<string, unknown> = {
      title: form.title,
      topic: form.topic || null,
      description: form.description || null,
      target_platform: form.target_platform || null,
      style: form.style || null,
      tone: form.tone || null,
      language: form.language || "ru",
      target_duration_sec: form.target_duration_sec ? Number(form.target_duration_sec) : null,
      reference_urls: form.reference_urls.trim() ? form.reference_urls.split("\n").map(s => s.trim()).filter(Boolean) : null,
      llm_prompt_template: form.llm_prompt_template || null,
    };

    try {
      const url = editId ? `/api/briefs/${editId}` : `/api/projects/${projectId}/briefs`;
      const method = editId ? "PATCH" : "POST";
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        showToast(editId ? "Бриф обновлён" : "Бриф создан");
        setShowForm(false);
        loadBriefs();
      } else {
        const err = await res.json().catch(() => ({ detail: "Ошибка" }));
        showToast(err.detail || "Ошибка сохранения", "error");
      }
    } catch {
      showToast("Сетевая ошибка", "error");
    }
    setSaving(false);
  };

  const updateStatus = async (id: number, status: string) => {
    const res = await fetch(`/api/briefs/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (res.ok) { showToast(`Статус → ${status}`); loadBriefs(); }
  };

  const deleteBrief = async (id: number) => {
    if (!confirm("Удалить бриф?")) return;
    const res = await fetch(`/api/briefs/${id}`, { method: "DELETE" });
    if (res.ok) { showToast("Бриф удалён"); loadBriefs(); }
  };

  const set = (k: string, v: string) => setForm(prev => ({ ...prev, [k]: v }));

  if (!projectId) return <div className="empty">Некорректный ID</div>;

  const inputStyle: React.CSSProperties = {
    width: "100%", padding: "8px 12px", borderRadius: 6,
    background: "var(--bg-muted)", border: "1px solid var(--border)",
    color: "var(--fg)", fontSize: 13,
  };
  const labelStyle: React.CSSProperties = {
    display: "block", marginBottom: 4, fontSize: 12, color: "var(--fg-subtle)", fontWeight: 500,
  };

  return (
    <div className="page">
      {/* Header */}
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button
            onClick={() => router.push("/projects")}
            style={{ width: 32, height: 32, borderRadius: "var(--radius)", background: "var(--bg-muted)", fontSize: 16, display: "flex", alignItems: "center", justifyContent: "center" }}
          >←</button>
          <div>
            <h1 className="page-title">Брифы проекта #{projectId}</h1>
            <p style={{ color: "var(--fg-subtle)", marginTop: 4, fontSize: 13 }}>{briefs.length} брифов</p>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={() => router.push(`/projects/${projectId}/feed`)}
            style={{ padding: "8px 16px", background: "var(--bg-muted)", borderRadius: 6, fontSize: 13, color: "var(--fg-subtle)" }}
          >📋 Feed</button>
          <button className="btn btn-primary" onClick={openCreate}>+ Новый бриф</button>
        </div>
      </div>

      {/* Briefs List */}
      {loading ? (
        <div style={{ padding: 60, textAlign: "center", color: "var(--fg-subtle)" }}>Загрузка...</div>
      ) : briefs.length === 0 && !showForm ? (
        <div style={{ padding: 60, textAlign: "center", color: "var(--fg-subtle)" }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>📝</div>
          <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 8 }}>Нет брифов</div>
          <div style={{ fontSize: 13 }}>Создайте бриф для генерации контента</div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {briefs.map(b => {
            const badge = statusBadge(b.status);
            return (
              <div key={b.id} style={{
                background: "var(--bg-subtle)", borderRadius: "var(--radius-lg)",
                border: "1px solid var(--border)", padding: 20,
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                      <span style={{ fontWeight: 600, fontSize: 15 }}>{b.title}</span>
                      <span style={{ padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 600, background: badge.bg, color: badge.fg }}>{b.status}</span>
                    </div>
                    {b.topic && <div style={{ fontSize: 13, color: "var(--fg-subtle)", marginBottom: 4 }}>Тема: {b.topic}</div>}
                    {b.description && <div style={{ fontSize: 13, color: "var(--fg-subtle)", marginBottom: 4 }}>{b.description}</div>}
                    <div style={{ display: "flex", gap: 12, fontSize: 12, color: "var(--fg-subtle)", flexWrap: "wrap" }}>
                      {b.target_platform && <span>📱 {b.target_platform}</span>}
                      {b.style && <span>🎨 {b.style}</span>}
                      {b.tone && <span>🎭 {b.tone}</span>}
                      {b.target_duration_sec && <span>⏱ {b.target_duration_sec}с</span>}
                      {b.language && <span>🌐 {b.language}</span>}
                      <span>📅 {fmtDate(b.created_at)}</span>
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 6, marginLeft: 12, flexShrink: 0 }}>
                    <button onClick={() => openEdit(b)} style={{ padding: "6px 12px", background: "var(--bg-hover)", borderRadius: 6, fontSize: 12 }}>✏ Ред.</button>
                    <select
                      value={b.status}
                      onChange={e => updateStatus(b.id, e.target.value)}
                      style={{ padding: "6px 8px", borderRadius: 6, fontSize: 12, background: "var(--bg-hover)", color: "var(--fg)", border: "none" }}
                    >
                      {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                    <button onClick={() => deleteBrief(b.id)} style={{ padding: "6px 12px", background: "#ef444420", color: "#ef4444", borderRadius: 6, fontSize: 12 }}>✕</button>
                  </div>
                </div>

                {/* Extra details */}
                {(b.reference_urls || b.llm_prompt_template) && (
                  <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12, marginTop: 8 }}>
                    {b.reference_urls && Array.isArray(b.reference_urls) && b.reference_urls.length > 0 && (
                      <div style={{ marginBottom: 8 }}>
                        <span style={{ fontSize: 12, color: "var(--fg-subtle)", fontWeight: 500 }}>Ссылки: </span>
                        {b.reference_urls.map((u, i) => (
                          <a key={i} href={String(u)} target="_blank" rel="noopener noreferrer" style={{ fontSize: 12, color: "var(--primary)", marginRight: 8 }}>
                            {String(u).slice(0, 50)}...
                          </a>
                        ))}
                      </div>
                    )}
                    {b.llm_prompt_template && (
                      <div>
                        <span style={{ fontSize: 12, color: "var(--fg-subtle)", fontWeight: 500 }}>Промпт: </span>
                        <span style={{ fontSize: 12, color: "var(--fg-subtle)" }}>{b.llm_prompt_template.slice(0, 120)}...</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Create / Edit Modal */}
      {showForm && (
        <div onClick={() => setShowForm(false)} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}>
          <div onClick={e => e.stopPropagation()} style={{
            background: "var(--bg-subtle)", borderRadius: "var(--radius-lg)",
            border: "1px solid var(--border)", width: "100%", maxWidth: 560,
            maxHeight: "90vh", overflow: "auto",
          }}>
            <div style={{ padding: 20, borderBottom: "1px solid var(--border)", fontWeight: 600, fontSize: 16 }}>
              {editId ? "Редактировать бриф" : "Новый бриф"}
            </div>
            <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 14 }}>
              <div>
                <label style={labelStyle}>Название *</label>
                <input value={form.title} onChange={e => set("title", e.target.value)} style={inputStyle} placeholder="Название брифа..." />
              </div>
              <div>
                <label style={labelStyle}>Тема</label>
                <input value={form.topic} onChange={e => set("topic", e.target.value)} style={inputStyle} placeholder="Основная тема контента..." />
              </div>
              <div>
                <label style={labelStyle}>Описание</label>
                <textarea value={form.description} onChange={e => set("description", e.target.value)} rows={2} style={{ ...inputStyle, resize: "vertical" }} placeholder="Детальное описание..." />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <label style={labelStyle}>Платформа</label>
                  <select value={form.target_platform} onChange={e => set("target_platform", e.target.value)} style={inputStyle}>
                    {PLATFORM_OPTIONS.map(p => <option key={p} value={p}>{p || "Не указана"}</option>)}
                  </select>
                </div>
                <div>
                  <label style={labelStyle}>Стиль</label>
                  <select value={form.style} onChange={e => set("style", e.target.value)} style={inputStyle}>
                    {STYLE_OPTIONS.map(s => <option key={s} value={s}>{s || "Не указан"}</option>)}
                  </select>
                </div>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
                <div>
                  <label style={labelStyle}>Тон</label>
                  <select value={form.tone} onChange={e => set("tone", e.target.value)} style={inputStyle}>
                    {TONE_OPTIONS.map(t => <option key={t} value={t}>{t || "Не указан"}</option>)}
                  </select>
                </div>
                <div>
                  <label style={labelStyle}>Язык</label>
                  <input value={form.language} onChange={e => set("language", e.target.value)} style={inputStyle} placeholder="ru" />
                </div>
                <div>
                  <label style={labelStyle}>Длительность (сек)</label>
                  <input type="number" value={form.target_duration_sec} onChange={e => set("target_duration_sec", e.target.value)} style={inputStyle} placeholder="60" min={5} max={600} />
                </div>
              </div>
              <div>
                <label style={labelStyle}>Ссылки-референсы (по одной на строку)</label>
                <textarea value={form.reference_urls} onChange={e => set("reference_urls", e.target.value)} rows={3} style={{ ...inputStyle, resize: "vertical" }} placeholder="https://youtube.com/watch?v=...&#10;https://tiktok.com/..." />
              </div>
              <div>
                <label style={labelStyle}>LLM промпт-шаблон</label>
                <textarea value={form.llm_prompt_template} onChange={e => set("llm_prompt_template", e.target.value)} rows={4} style={{ ...inputStyle, resize: "vertical", fontFamily: "monospace", fontSize: 12 }} placeholder="Ты — контент-мейкер. Создай сценарий для {target_platform} видео на тему {topic}..." />
              </div>
            </div>
            <div style={{ padding: 20, borderTop: "1px solid var(--border)", display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <button onClick={() => setShowForm(false)} style={{ padding: "10px 20px", background: "var(--bg-muted)", borderRadius: 6, color: "var(--fg-muted)", fontSize: 13 }}>Отмена</button>
              <button onClick={save} disabled={saving} style={{ padding: "10px 20px", background: "var(--primary)", borderRadius: 6, color: "#fff", fontWeight: 500, fontSize: 13, opacity: saving ? 0.6 : 1 }}>
                {saving ? "Сохранение..." : editId ? "Сохранить" : "Создать"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div style={{
          position: "fixed", bottom: 24, right: 24,
          padding: "12px 20px", borderRadius: "var(--radius)",
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
