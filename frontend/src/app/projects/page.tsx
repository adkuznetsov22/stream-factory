"use client";

import { useEffect, useState } from "react";

type Policy = {
  require_voice_change?: boolean;
  require_caption_rewrite?: boolean;
  require_visual_transform?: boolean;
  require_hook_rewrite?: boolean;
};

type FeedSettings = {
  auto_approve_enabled?: boolean;
  daily_limit_per_destination?: number;
  cooldown_hours_per_source?: number;
  min_score_override?: number | null;
  origin_filter?: string;
};

type AutoApproveReport = {
  threshold: number;
  approved_count: number;
  skipped_count: number;
  approved: { candidate_id: number; task_id: number | null; score: number; title?: string; destination_platform?: string; dry_run?: boolean }[];
  skipped: { candidate_id: number; score: number; reason: string }[];
  daily_limits?: Record<string, { platform: string; used: number; limit: number }>;
  run_at?: string;
  error?: string;
  dry_run?: boolean;
};

type PublishSettings = {
  publish_enabled?: boolean;
  timezone?: string;
  windows?: Record<string, string[][]>;
  min_gap_minutes_per_destination?: number;
  daily_limit_per_destination?: number;
  jitter_minutes?: number;
};

type Project = {
  id: number;
  name: string;
  theme_type?: string | null;
  status: string;
  mode: string;
  preset_id?: number | null;
  export_profile_id?: number | null;
  policy?: Policy | null;
  feed_settings?: FeedSettings | null;
  meta?: Record<string, unknown> | null;
};

type Source = { id: number; platform: string; social_account_id: number };
type Destination = { id: number; platform: string; social_account_id: number; priority: number };
type Account = { id: number; platform: string; label: string };
type Preset = { id: number; name: string };
type ExportProfileItem = { id: number; name: string; target_platform: string; max_duration_sec: number; width: number; height: number; fps: number; codec: string };

function AutoApproveBlock({
  project, onUpdate, report, running, onRunNow,
}: {
  project: Project;
  onUpdate: (fs: FeedSettings) => void;
  report: AutoApproveReport | null;
  running: boolean;
  onRunNow: (dryRun: boolean) => void;
}) {
  const fs: FeedSettings = project.feed_settings || {};
  const enabled = fs.auto_approve_enabled ?? false;
  const dailyLimit = fs.daily_limit_per_destination ?? 3;
  const cooldown = fs.cooldown_hours_per_source ?? 12;
  const scoreOverride = fs.min_score_override ?? null;
  const originFilter = fs.origin_filter ?? "ALL";

  const set = (patch: Partial<FeedSettings>) => onUpdate({ ...fs, ...patch });

  return (
    <div style={{ marginBottom: 24 }}>
      <span style={{ fontWeight: 600, fontSize: 14, display: "block", marginBottom: 12 }}>Auto-Approve</span>
      <div style={{
        background: enabled ? "#22c55e08" : "var(--bg-muted)",
        border: `1px solid ${enabled ? "#22c55e40" : "var(--border)"}`,
        borderRadius: 10, padding: 16,
      }}>
        {/* Toggle */}
        <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", marginBottom: 12 }}>
          <input
            type="checkbox"
            checked={enabled}
            onChange={e => set({ auto_approve_enabled: e.target.checked })}
          />
          <span style={{ fontSize: 13, fontWeight: 500 }}>
            Автоматически одобрять кандидатов по порогу скоринга
          </span>
        </label>

        {enabled && (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 12, marginBottom: 12 }}>
              <div>
                <label style={{ display: "block", fontSize: 11, color: "var(--fg-subtle)", marginBottom: 4 }}>
                  Лимит / назначение / день
                </label>
                <input
                  type="number" min={1} max={50} value={dailyLimit}
                  onChange={e => set({ daily_limit_per_destination: Number(e.target.value) || 3 })}
                  style={{ width: "100%" }}
                />
              </div>
              <div>
                <label style={{ display: "block", fontSize: 11, color: "var(--fg-subtle)", marginBottom: 4 }}>
                  Cooldown источника (ч)
                </label>
                <input
                  type="number" min={0} max={168} value={cooldown}
                  onChange={e => set({ cooldown_hours_per_source: Number(e.target.value) || 12 })}
                  style={{ width: "100%" }}
                />
              </div>
              <div>
                <label style={{ display: "block", fontSize: 11, color: "var(--fg-subtle)", marginBottom: 4 }}>
                  Мин. score (override)
                </label>
                <input
                  type="number" min={0} max={100} step={0.01}
                  value={scoreOverride ?? ""}
                  placeholder="из калибровки"
                  onChange={e => set({ min_score_override: e.target.value ? Number(e.target.value) : null })}
                  style={{ width: "100%" }}
                />
              </div>
              <div>
                <label style={{ display: "block", fontSize: 11, color: "var(--fg-subtle)", marginBottom: 4 }}>
                  Тип кандидатов
                </label>
                <select
                  value={originFilter}
                  onChange={e => set({ origin_filter: e.target.value })}
                  style={{ width: "100%" }}
                >
                  <option value="ALL">Все</option>
                  <option value="REPURPOSE">Repurpose</option>
                  <option value="GENERATE">Generate</option>
                </select>
              </div>
            </div>

            {/* Run buttons */}
            <div style={{ display: "flex", gap: 8 }}>
              <button
                onClick={() => onRunNow(false)}
                disabled={running}
                style={{
                  padding: "6px 16px", borderRadius: 8, fontSize: 12, fontWeight: 500, cursor: "pointer",
                  background: running ? "var(--bg-muted)" : "#22c55e20",
                  color: running ? "var(--fg-subtle)" : "#22c55e",
                  border: "1px solid #22c55e40",
                }}
              >
                {running ? "Запуск..." : "▶ Запустить"}
              </button>
              <button
                onClick={() => onRunNow(true)}
                disabled={running}
                style={{
                  padding: "6px 16px", borderRadius: 8, fontSize: 12, fontWeight: 500, cursor: "pointer",
                  background: running ? "var(--bg-muted)" : "#dbeafe",
                  color: running ? "var(--fg-subtle)" : "#2563eb",
                  border: "1px solid #93c5fd",
                }}
              >
                Dry Run
              </button>
            </div>

            {/* Report */}
            {report && (
              <div style={{ marginTop: 12, padding: 12, background: "var(--bg-subtle)", borderRadius: 8, border: "1px solid var(--border)" }}>
                <div style={{ display: "flex", gap: 16, marginBottom: 8, fontSize: 12, alignItems: "center" }}>
                  {report.dry_run && (
                    <span style={{ background: "#dbeafe", color: "#2563eb", padding: "2px 8px", borderRadius: 10, fontSize: 10, fontWeight: 600 }}>DRY RUN</span>
                  )}
                  <span>Порог: <strong>{report.threshold?.toFixed(2)}</strong></span>
                  <span style={{ color: "#22c55e" }}>Одобрено: <strong>{report.approved_count}</strong></span>
                  <span style={{ color: "#ef4444" }}>Пропущено: <strong>{report.skipped_count}</strong></span>
                  {report.run_at && <span style={{ color: "var(--fg-subtle)" }}>{new Date(report.run_at).toLocaleTimeString("ru")}</span>}
                </div>
                {report.error && (
                  <div style={{ color: "#ef4444", fontSize: 12, marginBottom: 8 }}>{report.error}</div>
                )}
                {report.approved.length > 0 && (
                  <div style={{ fontSize: 11, marginBottom: 6 }}>
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>Одобрены:</div>
                    {report.approved.map(a => (
                      <div key={a.candidate_id} style={{ display: "flex", gap: 8, padding: "2px 0" }}>
                        <span style={{ color: "#22c55e" }}>✓</span>
                        <span>{a.title || `#${a.candidate_id}`}</span>
                        <span style={{ color: "var(--fg-subtle)" }}>score={a.score?.toFixed(2)}</span>
                        {a.destination_platform && <span style={{ color: "var(--fg-subtle)" }}>→ {a.destination_platform}</span>}
                      </div>
                    ))}
                  </div>
                )}
                {report.skipped.length > 0 && (
                  <div style={{ fontSize: 11 }}>
                    <div style={{ fontWeight: 600, marginBottom: 4, color: "var(--fg-subtle)" }}>Пропущены:</div>
                    {report.skipped.slice(0, 5).map(s => (
                      <div key={s.candidate_id} style={{ display: "flex", gap: 8, padding: "2px 0", color: "var(--fg-subtle)" }}>
                        <span>✕</span>
                        <span>#{s.candidate_id} (score={s.score?.toFixed(2)})</span>
                        <span style={{ fontSize: 10 }}>{s.reason}</span>
                      </div>
                    ))}
                    {report.skipped.length > 5 && (
                      <div style={{ color: "var(--fg-subtle)", fontSize: 10 }}>...и ещё {report.skipped.length - 5}</div>
                    )}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

type AutoPublishReport = {
  started_count: number;
  skipped_count: number;
  started: { project_id: number; task_id: number; destination_account_id?: number; score?: number; dry_run?: boolean; success?: boolean; published_url?: string; error?: string }[];
  skipped: { project_id?: number; task_id?: number; reason: string; count?: number }[];
  dry_run: boolean;
  run_at?: string;
};

function PublishScheduleBlock({
  project, onUpdate, report, running, onRunNow,
}: {
  project: Project;
  onUpdate: (meta: Record<string, unknown>) => void;
  report: AutoPublishReport | null;
  running: boolean;
  onRunNow: (dryRun: boolean) => void;
}) {
  const meta = (project.meta || {}) as Record<string, unknown>;
  const ps = (meta.publish_settings || {}) as PublishSettings;
  const enabled = ps.publish_enabled ?? false;
  const tz = ps.timezone ?? "Europe/Berlin";
  const minGap = ps.min_gap_minutes_per_destination ?? 90;
  const dailyLimit = ps.daily_limit_per_destination ?? 3;
  const jitter = ps.jitter_minutes ?? 0;
  const windows = ps.windows || {};
  const weekdayWindow = (windows.mon || [["10:00", "22:00"]])[0] || ["10:00", "22:00"];
  const weekendWindow = (windows.sat || [["12:00", "20:00"]])[0] || ["12:00", "20:00"];

  const set = (patch: Partial<PublishSettings>) => {
    const newPs = { ...ps, ...patch };
    onUpdate({ ...meta, publish_settings: newPs });
  };

  const setWindows = (weekday: string[], weekend: string[]) => {
    const w: Record<string, string[][]> = {};
    for (const d of ["mon", "tue", "wed", "thu", "fri"]) w[d] = [weekday];
    for (const d of ["sat", "sun"]) w[d] = [weekend];
    set({ windows: w });
  };

  return (
    <div style={{ marginBottom: 24 }}>
      <span style={{ fontWeight: 600, fontSize: 14, display: "block", marginBottom: 12 }}>Publish Schedule</span>
      <div style={{
        background: enabled ? "#3b82f608" : "var(--bg-muted)",
        border: `1px solid ${enabled ? "#3b82f640" : "var(--border)"}`,
        borderRadius: 10, padding: 16,
      }}>
        <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", marginBottom: 12 }}>
          <input type="checkbox" checked={enabled} onChange={e => set({ publish_enabled: e.target.checked })} />
          <span style={{ fontSize: 13, fontWeight: 500 }}>Автоматическая публикация по расписанию</span>
        </label>

        {enabled && (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr 1fr", gap: 12, marginBottom: 12 }}>
              <div>
                <label style={{ display: "block", fontSize: 11, color: "var(--fg-subtle)", marginBottom: 4 }}>Timezone</label>
                <select value={tz} onChange={e => set({ timezone: e.target.value })} style={{ width: "100%" }}>
                  {["UTC", "Europe/Moscow", "Europe/Berlin", "Europe/London", "America/New_York", "Asia/Tokyo"].map(t => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div>
                <label style={{ display: "block", fontSize: 11, color: "var(--fg-subtle)", marginBottom: 4 }}>Лимит / dest / день</label>
                <input type="number" min={1} max={50} value={dailyLimit}
                  onChange={e => set({ daily_limit_per_destination: Number(e.target.value) || 3 })}
                  style={{ width: "100%" }} />
              </div>
              <div>
                <label style={{ display: "block", fontSize: 11, color: "var(--fg-subtle)", marginBottom: 4 }}>Min gap (мин)</label>
                <input type="number" min={0} max={1440} value={minGap}
                  onChange={e => set({ min_gap_minutes_per_destination: Number(e.target.value) || 90 })}
                  style={{ width: "100%" }} />
              </div>
              <div>
                <label style={{ display: "block", fontSize: 11, color: "var(--fg-subtle)", marginBottom: 4 }}>Jitter (мин)</label>
                <input type="number" min={0} max={60} value={jitter}
                  onChange={e => set({ jitter_minutes: Number(e.target.value) || 0 })}
                  style={{ width: "100%" }} />
              </div>
            </div>

            {/* Windows */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
              <div>
                <label style={{ display: "block", fontSize: 11, color: "var(--fg-subtle)", marginBottom: 4 }}>Будни (пн-пт)</label>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <input type="time" value={weekdayWindow[0]} onChange={e => setWindows([e.target.value, weekdayWindow[1]], weekendWindow)} style={{ flex: 1 }} />
                  <span style={{ fontSize: 12 }}>—</span>
                  <input type="time" value={weekdayWindow[1]} onChange={e => setWindows([weekdayWindow[0], e.target.value], weekendWindow)} style={{ flex: 1 }} />
                </div>
              </div>
              <div>
                <label style={{ display: "block", fontSize: 11, color: "var(--fg-subtle)", marginBottom: 4 }}>Выходные (сб-вс)</label>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <input type="time" value={weekendWindow[0]} onChange={e => setWindows(weekdayWindow, [e.target.value, weekendWindow[1]])} style={{ flex: 1 }} />
                  <span style={{ fontSize: 12 }}>—</span>
                  <input type="time" value={weekendWindow[1]} onChange={e => setWindows(weekdayWindow, [weekendWindow[0], e.target.value])} style={{ flex: 1 }} />
                </div>
              </div>
            </div>

            {/* Run buttons */}
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={() => onRunNow(false)} disabled={running}
                style={{ padding: "6px 16px", borderRadius: 8, fontSize: 12, fontWeight: 500, cursor: "pointer",
                  background: running ? "var(--bg-muted)" : "#3b82f620", color: running ? "var(--fg-subtle)" : "#3b82f6", border: "1px solid #3b82f640" }}>
                {running ? "Публикация..." : "▶ Опубликовать"}
              </button>
              <button onClick={() => onRunNow(true)} disabled={running}
                style={{ padding: "6px 16px", borderRadius: 8, fontSize: 12, fontWeight: 500, cursor: "pointer",
                  background: running ? "var(--bg-muted)" : "#dbeafe", color: running ? "var(--fg-subtle)" : "#2563eb", border: "1px solid #93c5fd" }}>
                Dry Run
              </button>
            </div>

            {/* Report */}
            {report && (
              <div style={{ marginTop: 12, padding: 12, background: "var(--bg-subtle)", borderRadius: 8, border: "1px solid var(--border)" }}>
                <div style={{ display: "flex", gap: 16, marginBottom: 8, fontSize: 12, alignItems: "center" }}>
                  {report.dry_run && <span style={{ background: "#dbeafe", color: "#2563eb", padding: "2px 8px", borderRadius: 10, fontSize: 10, fontWeight: 600 }}>DRY RUN</span>}
                  <span style={{ color: "#22c55e" }}>Опубликовано: <strong>{report.started_count}</strong></span>
                  <span style={{ color: "#ef4444" }}>Пропущено: <strong>{report.skipped_count}</strong></span>
                  {report.run_at && <span style={{ color: "var(--fg-subtle)" }}>{new Date(report.run_at).toLocaleTimeString("ru")}</span>}
                </div>
                {report.started.length > 0 && (
                  <div style={{ fontSize: 11, marginBottom: 6 }}>
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>Запущены:</div>
                    {report.started.map(s => (
                      <div key={s.task_id} style={{ display: "flex", gap: 8, padding: "2px 0" }}>
                        <span style={{ color: "#22c55e" }}>✓</span>
                        <span>Task #{s.task_id}</span>
                        {s.published_url && <a href={s.published_url} target="_blank" rel="noreferrer" style={{ color: "#2563eb", fontSize: 10 }}>{s.published_url}</a>}
                        {s.error && <span style={{ color: "#ef4444", fontSize: 10 }}>{s.error}</span>}
                      </div>
                    ))}
                  </div>
                )}
                {report.skipped.length > 0 && (
                  <div style={{ fontSize: 11 }}>
                    <div style={{ fontWeight: 600, marginBottom: 4, color: "var(--fg-subtle)" }}>Пропущены:</div>
                    {report.skipped.slice(0, 5).map((s, i) => (
                      <div key={i} style={{ display: "flex", gap: 8, padding: "2px 0", color: "var(--fg-subtle)" }}>
                        <span>✕</span>
                        <span>{s.task_id ? `Task #${s.task_id}` : `${s.count || 1} задач`}</span>
                        <span style={{ fontSize: 10 }}>{s.reason}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [exportProfiles, setExportProfiles] = useState<ExportProfileItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [destinations, setDestinations] = useState<Destination[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: "", mode: "MANUAL", preset_id: "" });
  const [aaReport, setAaReport] = useState<AutoApproveReport | null>(null);
  const [aaRunning, setAaRunning] = useState(false);
  const [apReport, setApReport] = useState<AutoPublishReport | null>(null);
  const [apRunning, setApRunning] = useState(false);

  const load = async () => {
    setLoading(true);
    const [pRes, aRes, prRes, epRes] = await Promise.all([
      fetch("/api/projects"),
      fetch("/api/accounts"),
      fetch("/api/presets"),
      fetch("/api/export-profiles"),
    ]);
    if (pRes.ok) setProjects(await pRes.json());
    if (aRes.ok) setAccounts(await aRes.json());
    if (prRes.ok) setPresets(await prRes.json());
    if (epRes.ok) setExportProfiles(await epRes.json());
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

                    {/* Export Profile */}
                    <div style={{ marginBottom: 24 }}>
                      <span style={{ fontWeight: 600, fontSize: 14, display: "block", marginBottom: 12 }}>Профиль экспорта</span>
                      <select
                        value={p.export_profile_id || ""}
                        onChange={e => updateProject(p.id, { export_profile_id: e.target.value ? Number(e.target.value) : null })}
                        style={{ width: "100%", marginBottom: 8 }}
                      >
                        <option value="">Не выбран (параметры по умолчанию)</option>
                        {exportProfiles.map(ep => (
                          <option key={ep.id} value={ep.id}>
                            {ep.name} — {ep.target_platform} ({ep.width}×{ep.height}, {ep.fps}fps, {ep.max_duration_sec}с)
                          </option>
                        ))}
                      </select>
                      {p.export_profile_id && (() => {
                        const ep = exportProfiles.find(e => e.id === p.export_profile_id);
                        return ep ? (
                          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", fontSize: 11, color: "var(--fg-subtle)" }}>
                            <span style={{ padding: "2px 8px", background: "var(--bg-hover)", borderRadius: 4 }}>{ep.target_platform}</span>
                            <span style={{ padding: "2px 8px", background: "var(--bg-hover)", borderRadius: 4 }}>{ep.width}×{ep.height}</span>
                            <span style={{ padding: "2px 8px", background: "var(--bg-hover)", borderRadius: 4 }}>{ep.fps} fps</span>
                            <span style={{ padding: "2px 8px", background: "var(--bg-hover)", borderRadius: 4 }}>{ep.codec}</span>
                            <span style={{ padding: "2px 8px", background: "var(--bg-hover)", borderRadius: 4 }}>≤{ep.max_duration_sec}с</span>
                          </div>
                        ) : null;
                      })()}
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

                    {/* Auto-Approve */}
                    <AutoApproveBlock
                      project={p}
                      onUpdate={(fs) => updateProject(p.id, { feed_settings: fs } as any)}
                      report={expanded === p.id ? aaReport : null}
                      running={aaRunning}
                      onRunNow={async (dryRun: boolean) => {
                        setAaRunning(true);
                        setAaReport(null);
                        const qs = dryRun ? "?dry_run=true" : "";
                        const res = await fetch(`/api/projects/${p.id}/auto-approve${qs}`, { method: "POST" });
                        if (res.ok) setAaReport(await res.json());
                        setAaRunning(false);
                        if (!dryRun) load();
                      }}
                    />

                    {/* Publish Schedule */}
                    <PublishScheduleBlock
                      project={p}
                      onUpdate={(newMeta) => updateProject(p.id, { meta: newMeta } as any)}
                      report={expanded === p.id ? apReport : null}
                      running={apRunning}
                      onRunNow={async (dryRun: boolean) => {
                        setApRunning(true);
                        setApReport(null);
                        const qs = dryRun ? "?dry_run=true" : "";
                        const res = await fetch(`/api/scheduler/auto-publish${qs}`, { method: "POST" });
                        if (res.ok) setApReport(await res.json());
                        setApRunning(false);
                        if (!dryRun) load();
                      }}
                    />

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
