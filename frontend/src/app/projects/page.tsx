"use client";

import { useEffect, useState } from "react";

type Policy = {
  require_voice_change?: boolean;
  require_caption_rewrite?: boolean;
  require_visual_transform?: boolean;
  require_hook_rewrite?: boolean;
};

type Project = {
  id: number;
  name: string;
  theme_type?: string | null;
  status: string;
  mode: string;
  preset_id?: number | null;
  policy?: Policy | null;
};

type Source = { id: number; platform: string; social_account_id: number };
type Destination = { id: number; platform: string; social_account_id: number; priority: number };
type Account = { id: number; platform: string; label: string };
type Preset = { id: number; name: string };

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [destinations, setDestinations] = useState<Destination[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: "", mode: "MANUAL", preset_id: "" });

  const load = async () => {
    setLoading(true);
    const [pRes, aRes, prRes] = await Promise.all([
      fetch("/api/projects"),
      fetch("/api/accounts"),
      fetch("/api/presets"),
    ]);
    if (pRes.ok) setProjects(await pRes.json());
    if (aRes.ok) setAccounts(await aRes.json());
    if (prRes.ok) setPresets(await prRes.json());
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const loadDetails = async (id: number) => {
    const [sRes, dRes] = await Promise.all([
      fetch(`/api/projects/${id}/sources`),
      fetch(`/api/projects/${id}/destinations`),
    ]);
    if (sRes.ok) setSources(await sRes.json());
    if (dRes.ok) setDestinations(await dRes.json());
  };

  const toggleExpand = (id: number) => {
    if (expanded === id) { setExpanded(null); }
    else { setExpanded(id); loadDetails(id); }
  };

  const createProject = async () => {
    await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: form.name, mode: form.mode, preset_id: form.preset_id ? Number(form.preset_id) : null }),
    });
    setShowCreate(false);
    setForm({ name: "", mode: "MANUAL", preset_id: "" });
    load();
  };

  const updateProject = async (id: number, data: Partial<Project>) => {
    await fetch(`/api/projects/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
    load();
  };

  const runNow = async (id: number) => {
    await fetch(`/api/projects/${id}/run-now`, { method: "POST" });
  };

  const deleteProject = async (id: number) => {
    if (!confirm("Удалить?")) return;
    await fetch(`/api/projects/${id}`, { method: "DELETE" });
    setExpanded(null);
    load();
  };

  const addSource = async (pid: number, aid: number, plat: string) => {
    await fetch(`/api/projects/${pid}/sources`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ social_account_id: aid, platform: plat }) });
    loadDetails(pid);
  };

  const addDest = async (pid: number, aid: number, plat: string) => {
    await fetch(`/api/projects/${pid}/destinations`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ social_account_id: aid, platform: plat, priority: 0 }) });
    loadDetails(pid);
  };

  const rmSource = async (pid: number, sid: number) => { await fetch(`/api/projects/${pid}/sources/${sid}`, { method: "DELETE" }); loadDetails(pid); };
  const rmDest = async (pid: number, did: number) => { await fetch(`/api/projects/${pid}/destinations/${did}`, { method: "DELETE" }); loadDetails(pid); };
  const getAcc = (id: number) => accounts.find(a => a.id === id);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Проекты</h1>
          <p style={{ color: "var(--fg-subtle)", marginTop: 4, fontSize: 13 }}>{projects.length} всего</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>+ Создать</button>
      </div>

      {/* Projects List */}
      {loading ? (
        <div style={{ padding: 60, textAlign: "center", color: "var(--fg-subtle)" }}>Загрузка...</div>
      ) : projects.length === 0 ? (
        <div style={{ padding: 60, textAlign: "center", color: "var(--fg-subtle)" }}>Нет проектов</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {projects.map(p => {
            const statusClass = p.status === "active" ? "badge-success" : p.status === "paused" ? "badge-warning" : "";
            const isExpanded = expanded === p.id;
            const preset = presets.find(pr => pr.id === p.preset_id);

            return (
              <div
                key={p.id}
                style={{
                  background: "var(--bg-subtle)",
                  borderRadius: "var(--radius-lg)",
                  border: "1px solid var(--border)",
                  overflow: "hidden",
                }}
              >
                {/* Project Header */}
                <div
                  style={{ padding: 20, display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer" }}
                  onClick={() => toggleExpand(p.id)}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                    <div style={{ width: 40, height: 40, borderRadius: 10, background: "var(--bg-hover)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18 }}>
                      📁
                    </div>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 16 }}>{p.name}</div>
                      <div style={{ fontSize: 13, color: "var(--fg-subtle)", marginTop: 2 }}>
                        {preset?.name || "Без пресета"} • {p.mode === "AUTO" ? "Авто" : "Ручной"}
                        {p.theme_type && ` • ${p.theme_type}`}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span className={`badge ${statusClass}`}>{p.status}</span>
                    <span style={{ color: "var(--fg-subtle)", fontSize: 18 }}>{isExpanded ? "▲" : "▼"}</span>
                  </div>
                </div>

                {/* Expanded Details */}
                {isExpanded && (
                  <div style={{ borderTop: "1px solid var(--border)", padding: 20 }}>
                    {/* Actions */}
                    <div style={{ display: "flex", gap: 8, marginBottom: 24 }}>
                      <button
                        onClick={() => window.location.href = `/projects/${p.id}/feed`}
                        style={{ padding: "8px 16px", background: "#3b82f620", color: "#3b82f6", borderRadius: 6, fontSize: 13, fontWeight: 500 }}
                      >
                        📋 Feed
                      </button>
                      <button
                        onClick={() => window.location.href = `/projects/${p.id}/briefs`}
                        style={{ padding: "8px 16px", background: "#8b5cf620", color: "#8b5cf6", borderRadius: 6, fontSize: 13, fontWeight: 500 }}
                      >
                        📝 Briefs
                      </button>
                      <button
                        onClick={() => runNow(p.id)}
                        style={{ padding: "8px 16px", background: "var(--accent)", color: "#fff", borderRadius: 6, fontSize: 13, fontWeight: 500 }}
                      >
                        ▶ Запустить
                      </button>
                      {p.status === "paused" ? (
                        <button
                          onClick={() => updateProject(p.id, { status: "active" })}
                          style={{ padding: "8px 16px", background: "var(--bg-muted)", borderRadius: 6, fontSize: 13, color: "var(--fg-muted)" }}
                        >
                          Возобновить
                        </button>
                      ) : p.status === "active" ? (
                        <button
                          onClick={() => updateProject(p.id, { status: "paused" })}
                          style={{ padding: "8px 16px", background: "var(--bg-muted)", borderRadius: 6, fontSize: 13, color: "var(--fg-muted)" }}
                        >
                          ⏸ Пауза
                        </button>
                      ) : (
                        <button
                          onClick={() => updateProject(p.id, { status: "active" })}
                          style={{ padding: "8px 16px", background: "#22c55e20", borderRadius: 6, fontSize: 13, color: "#22c55e" }}
                        >
                          Активировать
                        </button>
                      )}
                      <button
                        onClick={() => deleteProject(p.id)}
                        style={{ padding: "8px 16px", background: "#ef444420", borderRadius: 6, fontSize: 13, color: "#ef4444", marginLeft: "auto" }}
                      >
                        Удалить
                      </button>
                    </div>

                    {/* Settings */}
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 24 }}>
                      <div>
                        <label style={{ display: "block", marginBottom: 6, fontSize: 12, color: "var(--fg-subtle)" }}>Пресет</label>
                        <select
                          value={p.preset_id || ""}
                          onChange={e => updateProject(p.id, { preset_id: e.target.value ? Number(e.target.value) : null })}
                          style={{ width: "100%" }}
                        >
                          <option value="">Не выбран</option>
                          {presets.map(pr => <option key={pr.id} value={pr.id}>{pr.name}</option>)}
                        </select>
                      </div>
                      <div>
                        <label style={{ display: "block", marginBottom: 6, fontSize: 12, color: "var(--fg-subtle)" }}>Режим</label>
                        <select
                          value={p.mode}
                          onChange={e => updateProject(p.id, { mode: e.target.value })}
                          style={{ width: "100%" }}
                        >
                          <option value="MANUAL">Ручной</option>
                          <option value="AUTO">Автоматический</option>
                        </select>
                      </div>
                    </div>

                    {/* Policy */}
                    <div style={{ marginBottom: 24 }}>
                      <span style={{ fontWeight: 600, fontSize: 14, display: "block", marginBottom: 12 }}>Политика обработки</span>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                        {([
                          ["require_voice_change", "Замена голоса"],
                          ["require_caption_rewrite", "Перезапись субтитров"],
                          ["require_visual_transform", "Визуальная трансформация"],
                          ["require_hook_rewrite", "Переписывание хука"],
                        ] as const).map(([key, label]) => (
                          <label key={key} style={{
                            display: "flex", alignItems: "center", gap: 8, padding: "8px 12px",
                            background: "var(--bg-muted)", borderRadius: 8, cursor: "pointer", fontSize: 13,
                          }}>
                            <input
                              type="checkbox"
                              checked={!!(p.policy as Policy)?.[key as keyof Policy]}
                              onChange={e => {
                                const newPolicy = { ...(p.policy || {}), [key]: e.target.checked };
                                updateProject(p.id, { policy: newPolicy } as Partial<Project>);
                              }}
                            />
                            <span>{label}</span>
                          </label>
                        ))}
                      </div>
                    </div>

                    {/* Sources */}
                    <div style={{ marginBottom: 24 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                        <span style={{ fontWeight: 600, fontSize: 14 }}>Источники ({sources.length})</span>
                      </div>
                      {sources.length === 0 ? (
                        <div style={{ padding: 16, background: "var(--bg-muted)", borderRadius: 8, color: "var(--fg-subtle)", fontSize: 13 }}>
                          Нет источников
                        </div>
                      ) : (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                          {sources.map(s => {
                            const acc = getAcc(s.social_account_id);
                            return (
                              <div key={s.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", background: "var(--bg-muted)", borderRadius: 8 }}>
                                <span style={{ fontSize: 13 }}>{acc?.label || `#${s.social_account_id}`}</span>
                                <span style={{ fontSize: 11, color: "var(--fg-subtle)" }}>{s.platform}</span>
                                <button onClick={() => rmSource(p.id, s.id)} style={{ color: "var(--fg-subtle)", fontSize: 14 }}>×</button>
                              </div>
                            );
                          })}
                        </div>
                      )}
                      <select
                        onChange={e => {
                          if (!e.target.value) return;
                          const [aid, plat] = e.target.value.split("|");
                          addSource(p.id, Number(aid), plat);
                          e.target.value = "";
                        }}
                        style={{ marginTop: 8 }}
                      >
                        <option value="">+ Добавить источник</option>
                        {accounts.filter(a => !sources.some(s => s.social_account_id === a.id)).map(a => (
                          <option key={a.id} value={`${a.id}|${a.platform}`}>{a.label} ({a.platform})</option>
                        ))}
                      </select>
                    </div>

                    {/* Destinations */}
                    <div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                        <span style={{ fontWeight: 600, fontSize: 14 }}>Назначения ({destinations.length})</span>
                      </div>
                      {destinations.length === 0 ? (
                        <div style={{ padding: 16, background: "var(--bg-muted)", borderRadius: 8, color: "var(--fg-subtle)", fontSize: 13 }}>
                          Нет назначений
                        </div>
                      ) : (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                          {destinations.map(d => {
                            const acc = getAcc(d.social_account_id);
                            return (
                              <div key={d.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", background: "var(--bg-muted)", borderRadius: 8 }}>
                                <span style={{ fontSize: 13 }}>{acc?.label || `#${d.social_account_id}`}</span>
                                <span style={{ fontSize: 11, color: "var(--fg-subtle)" }}>{d.platform}</span>
                                <button onClick={() => rmDest(p.id, d.id)} style={{ color: "var(--fg-subtle)", fontSize: 14 }}>×</button>
                              </div>
                            );
                          })}
                        </div>
                      )}
                      <select
                        onChange={e => {
                          if (!e.target.value) return;
                          const [aid, plat] = e.target.value.split("|");
                          addDest(p.id, Number(aid), plat);
                          e.target.value = "";
                        }}
                        style={{ marginTop: 8 }}
                      >
                        <option value="">+ Добавить назначение</option>
                        {accounts.filter(a => !destinations.some(d => d.social_account_id === a.id)).map(a => (
                          <option key={a.id} value={`${a.id}|${a.platform}`}>{a.label} ({a.platform})</option>
                        ))}
                      </select>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Create Modal */}
      {showCreate && (
        <div
          onClick={() => setShowCreate(false)}
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}
        >
          <div onClick={e => e.stopPropagation()} style={{ background: "var(--bg-subtle)", borderRadius: "var(--radius-lg)", border: "1px solid var(--border)", width: "100%", maxWidth: 480 }}>
            <div style={{ padding: 20, borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontWeight: 600, fontSize: 16 }}>Создать проект</span>
              <button onClick={() => setShowCreate(false)} style={{ width: 28, height: 28, borderRadius: 6, background: "var(--bg-muted)", fontSize: 18 }}>×</button>
            </div>
            <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
              <div>
                <label style={{ display: "block", marginBottom: 6, fontSize: 13, color: "var(--fg-muted)" }}>Название *</label>
                <input
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="Мой проект"
                  style={{ width: "100%" }}
                />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <label style={{ display: "block", marginBottom: 6, fontSize: 13, color: "var(--fg-muted)" }}>Режим</label>
                  <select value={form.mode} onChange={e => setForm(f => ({ ...f, mode: e.target.value }))} style={{ width: "100%" }}>
                    <option value="MANUAL">Ручной</option>
                    <option value="AUTO">Автоматический</option>
                  </select>
                </div>
                <div>
                  <label style={{ display: "block", marginBottom: 6, fontSize: 13, color: "var(--fg-muted)" }}>Пресет</label>
                  <select value={form.preset_id} onChange={e => setForm(f => ({ ...f, preset_id: e.target.value }))} style={{ width: "100%" }}>
                    <option value="">Не выбран</option>
                    {presets.map(pr => <option key={pr.id} value={pr.id}>{pr.name}</option>)}
                  </select>
                </div>
              </div>
            </div>
            <div style={{ padding: 20, borderTop: "1px solid var(--border)", display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <button onClick={() => setShowCreate(false)} style={{ padding: "10px 20px", background: "var(--bg-muted)", borderRadius: 6, color: "var(--fg-muted)" }}>Отмена</button>
              <button
                onClick={createProject}
                disabled={!form.name.trim()}
                style={{ padding: "10px 20px", background: "var(--accent)", borderRadius: 6, color: "#fff", fontWeight: 500, opacity: form.name.trim() ? 1 : 0.5 }}
              >
                Создать
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
