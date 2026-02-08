"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";

type Candidate = {
  id: number;
  project_id: number;
  platform: string;
  platform_video_id: string;
  url: string | null;
  author: string | null;
  title: string | null;
  caption: string | null;
  thumbnail_url: string | null;
  published_at: string | null;
  views: number | null;
  likes: number | null;
  comments: number | null;
  shares: number | null;
  subscribers: number | null;
  virality_score: number | null;
  origin: string;
  brief_id: number | null;
  meta: Record<string, unknown> | null;
  status: string;
  manual_rating: number | null;
  notes: string | null;
  linked_publish_task_id: number | null;
};

type Destination = {
  id: number;
  platform: string;
  social_account_id: number;
  is_active: boolean;
  priority: number;
};

type Toast = { message: string; type: "success" | "error" } | null;

const PLATFORM_COLORS: Record<string, string> = {
  TikTok: "#ff0050",
  YouTube: "#ff0000",
  VK: "#0077ff",
  Instagram: "#e4405f",
};

const PLATFORM_ICONS: Record<string, string> = {
  TikTok: "♪",
  YouTube: "▶",
  VK: "В",
  Instagram: "📷",
};

function fmt(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

function fmtDate(d: string | null): string {
  if (!d) return "—";
  return new Date(d).toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" });
}

function scoreColor(score: number | null): string {
  if (score == null) return "var(--fg-subtle)";
  if (score >= 70) return "#22c55e";
  if (score >= 40) return "#eab308";
  if (score >= 20) return "#f97316";
  return "#ef4444";
}

function statusBadge(status: string): { bg: string; fg: string } {
  switch (status) {
    case "NEW": return { bg: "var(--bg-hover)", fg: "var(--fg)" };
    case "APPROVED": return { bg: "#22c55e20", fg: "#22c55e" };
    case "REJECTED": return { bg: "#ef444420", fg: "#ef4444" };
    case "USED": return { bg: "#6366f120", fg: "#6366f1" };
    default: return { bg: "var(--bg-hover)", fg: "var(--fg-subtle)" };
  }
}

export default function ProjectFeedPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const projectId = Number(params?.id);

  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [toast, setToast] = useState<Toast>(null);
  const [actionLoading, setActionLoading] = useState<number | null>(null);
  const [destinations, setDestinations] = useState<Destination[]>([]);

  // Approve modal
  const [approveTarget, setApproveTarget] = useState<Candidate | null>(null);
  const [selectedDestId, setSelectedDestId] = useState<number | null>(null);

  // Filters
  const [platform, setPlatform] = useState("");
  const [minScore, setMinScore] = useState("");
  const [includeUsed, setIncludeUsed] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");
  const [originFilter, setOriginFilter] = useState(searchParams?.get("origin") || "");

  // Rating modal
  const [ratingTarget, setRatingTarget] = useState<Candidate | null>(null);
  const [ratingValue, setRatingValue] = useState(3);
  const [ratingNotes, setRatingNotes] = useState("");

  const showToast = (message: string, type: "success" | "error" = "success") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const loadFeed = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    const params = new URLSearchParams();
    if (platform) params.set("platform", platform);
    if (minScore) params.set("min_score", minScore);
    if (includeUsed) params.set("include_used", "true");
    if (statusFilter) params.set("status", statusFilter);
    if (originFilter) params.set("origin", originFilter);
    params.set("limit", "100");

    try {
      const res = await fetch(`/api/projects/${projectId}/feed?${params}`);
      if (res.ok) setCandidates(await res.json());
      else showToast("Ошибка загрузки фида", "error");
    } catch {
      showToast("Сетевая ошибка", "error");
    } finally {
      setLoading(false);
    }
  }, [projectId, platform, minScore, includeUsed, statusFilter, originFilter]);

  useEffect(() => { loadFeed(); }, [loadFeed]);

  // Загрузка destinations проекта
  useEffect(() => {
    if (!projectId) return;
    fetch(`/api/projects/${projectId}/destinations`)
      .then(r => r.ok ? r.json() : [])
      .then(setDestinations)
      .catch(() => {});
  }, [projectId]);

  const syncSources = async () => {
    setSyncing(true);
    try {
      const res = await fetch(`/api/projects/${projectId}/sync-sources`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        showToast(`Синхронизировано: +${data.total_added} новых, ${data.total_updated} обновлено`);
        loadFeed();
      } else {
        const err = await res.json().catch(() => ({ detail: "Ошибка синхронизации" }));
        showToast(err.detail || "Ошибка синхронизации", "error");
      }
    } catch {
      showToast("Сетевая ошибка", "error");
    } finally {
      setSyncing(false);
    }
  };

  const openApproveModal = (c: Candidate) => {
    const activeDests = destinations.filter(d => d.is_active);
    if (activeDests.length <= 1) {
      // Один или ноль — сразу approve без модалки
      doApprove(c, activeDests[0]?.id ?? null);
    } else {
      setApproveTarget(c);
      setSelectedDestId(activeDests[0]?.id ?? null);
    }
  };

  const doApprove = async (c: Candidate, destId: number | null) => {
    setApproveTarget(null);
    setActionLoading(c.id);
    try {
      const res = await fetch(`/api/projects/${projectId}/feed/${c.id}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ destination_id: destId }),
      });
      if (res.ok) {
        const data = await res.json();
        const platInfo = data.destination_platform ? ` → ${data.destination_platform}` : "";
        showToast(`Одобрено${platInfo} → задача #${data.task_id}`);
        loadFeed();
        setTimeout(() => router.push(`/queue/${data.task_id}`), 800);
      } else {
        const err = await res.json().catch(() => ({ detail: "Ошибка" }));
        showToast(err.detail || "Ошибка одобрения", "error");
      }
    } catch {
      showToast("Сетевая ошибка", "error");
    } finally {
      setActionLoading(null);
    }
  };

  const reject = async (c: Candidate) => {
    setActionLoading(c.id);
    try {
      const res = await fetch(`/api/projects/${projectId}/feed/${c.id}/reject`, { method: "POST" });
      if (res.ok) {
        showToast("Отклонено");
        loadFeed();
      } else {
        const err = await res.json().catch(() => ({ detail: "Ошибка" }));
        showToast(err.detail || "Ошибка отклонения", "error");
      }
    } catch {
      showToast("Сетевая ошибка", "error");
    } finally {
      setActionLoading(null);
    }
  };

  const submitRating = async () => {
    if (!ratingTarget) return;
    setActionLoading(ratingTarget.id);
    try {
      const res = await fetch(`/api/projects/${projectId}/feed/${ratingTarget.id}/rate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ manual_rating: ratingValue, notes: ratingNotes || null }),
      });
      if (res.ok) {
        showToast(`Оценка ${ratingValue}/5 сохранена`);
        setRatingTarget(null);
        loadFeed();
      } else {
        const err = await res.json().catch(() => ({ detail: "Ошибка" }));
        showToast(err.detail || "Ошибка оценки", "error");
      }
    } catch {
      showToast("Сетевая ошибка", "error");
    } finally {
      setActionLoading(null);
    }
  };

  const openRating = (c: Candidate) => {
    setRatingTarget(c);
    setRatingValue(c.manual_rating || 3);
    setRatingNotes(c.notes || "");
  };

  if (!projectId) return <div className="empty">Некорректный ID</div>;

  const counts = {
    total: candidates.length,
    new: candidates.filter(c => c.status === "NEW").length,
    approved: candidates.filter(c => c.status === "APPROVED").length,
    rejected: candidates.filter(c => c.status === "REJECTED").length,
  };

  return (
    <div className="page">
      {/* Header */}
      <div className="page-header">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button
              onClick={() => router.push("/projects")}
              style={{ width: 32, height: 32, borderRadius: "var(--radius)", background: "var(--bg-muted)", fontSize: 16, display: "flex", alignItems: "center", justifyContent: "center" }}
            >
              ←
            </button>
            <div>
              <h1 className="page-title">Feed проекта #{projectId}</h1>
              <p style={{ color: "var(--fg-subtle)", marginTop: 4, fontSize: 13 }}>
                {counts.total} кандидатов • {counts.new} новых • {counts.approved} одобрено • {counts.rejected} отклонено
              </p>
            </div>
          </div>
        </div>
        <button
          className="btn btn-primary"
          onClick={syncSources}
          disabled={syncing}
          style={{ opacity: syncing ? 0.6 : 1 }}
        >
          {syncing ? "⟳ Синхронизация..." : "⟳ Sync Sources"}
        </button>
      </div>

      {/* Filters */}
      <div style={{
        display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap", alignItems: "center",
        padding: "12px 16px", background: "var(--bg-subtle)", borderRadius: "var(--radius-lg)",
        border: "1px solid var(--border)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <label style={{ fontSize: 12, color: "var(--fg-subtle)", whiteSpace: "nowrap" }}>Платформа</label>
          <select value={platform} onChange={e => setPlatform(e.target.value)} style={{ fontSize: 13, padding: "6px 10px" }}>
            <option value="">Все</option>
            <option value="TikTok">TikTok</option>
            <option value="YouTube">YouTube</option>
            <option value="VK">VK</option>
            <option value="Instagram">Instagram</option>
          </select>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <label style={{ fontSize: 12, color: "var(--fg-subtle)", whiteSpace: "nowrap" }}>Мин. score</label>
          <input
            type="number" value={minScore} onChange={e => setMinScore(e.target.value)}
            placeholder="0" min={0} max={100} step={5}
            style={{ width: 70, fontSize: 13, padding: "6px 10px" }}
          />
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <label style={{ fontSize: 12, color: "var(--fg-subtle)", whiteSpace: "nowrap" }}>Статус</label>
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ fontSize: 13, padding: "6px 10px" }}>
            <option value="">Все</option>
            <option value="NEW">Новые</option>
            <option value="APPROVED">Одобренные</option>
            <option value="REJECTED">Отклонённые</option>
            <option value="USED">Использованные</option>
          </select>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <label style={{ fontSize: 12, color: "var(--fg-subtle)", whiteSpace: "nowrap" }}>Источник</label>
          <select value={originFilter} onChange={e => setOriginFilter(e.target.value)} style={{ fontSize: 13, padding: "6px 10px" }}>
            <option value="">Все</option>
            <option value="REPURPOSE">Repurpose</option>
            <option value="GENERATE">Generate</option>
          </select>
        </div>

        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, cursor: "pointer" }}>
          <input type="checkbox" checked={includeUsed} onChange={e => setIncludeUsed(e.target.checked)} />
          <span style={{ color: "var(--fg-subtle)" }}>Показать использованные</span>
        </label>
      </div>

      {/* Feed Grid */}
      {loading ? (
        <div style={{ padding: 60, textAlign: "center", color: "var(--fg-subtle)" }}>Загрузка...</div>
      ) : candidates.length === 0 ? (
        <div style={{ padding: 60, textAlign: "center", color: "var(--fg-subtle)" }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>📭</div>
          <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 8 }}>Фид пуст</div>
          <div style={{ fontSize: 13 }}>Нажмите «Sync Sources» для загрузки кандидатов из источников проекта</div>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340, 1fr))", gap: 16 }}>
          {candidates.map(c => {
            const platColor = PLATFORM_COLORS[c.platform] || "#888";
            const platIcon = PLATFORM_ICONS[c.platform] || "?";
            const badge = statusBadge(c.status);
            const isLoading = actionLoading === c.id;

            return (
              <div
                key={c.id}
                style={{
                  background: "var(--bg-subtle)",
                  borderRadius: "var(--radius-lg)",
                  border: "1px solid var(--border)",
                  overflow: "hidden",
                  opacity: c.status === "REJECTED" ? 0.6 : 1,
                  transition: "opacity 0.2s",
                }}
              >
                {/* Thumbnail */}
                <div style={{ position: "relative", height: 180, background: "var(--bg-muted)", overflow: "hidden" }}>
                  {c.thumbnail_url ? (
                    <img
                      src={c.thumbnail_url}
                      alt=""
                      style={{ width: "100%", height: "100%", objectFit: "cover" }}
                      onError={e => { (e.target as HTMLImageElement).style.display = "none"; }}
                    />
                  ) : (
                    <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 48, color: "var(--fg-subtle)" }}>
                      🎬
                    </div>
                  )}
                  {/* Platform badge */}
                  <div style={{
                    position: "absolute", top: 8, left: 8,
                    display: "flex", gap: 4,
                  }}>
                    <div style={{
                      padding: "4px 8px", borderRadius: 6, fontSize: 11, fontWeight: 600,
                      background: platColor, color: "#fff",
                    }}>
                      {platIcon} {c.platform}
                    </div>
                    {c.origin === "GENERATE" && (
                      <div style={{
                        padding: "4px 8px", borderRadius: 6, fontSize: 11, fontWeight: 600,
                        background: "#8b5cf6", color: "#fff",
                      }}>
                        ⚡ GEN
                      </div>
                    )}
                  </div>
                  {/* Virality score */}
                  <div style={{
                    position: "absolute", top: 8, right: 8,
                    padding: "4px 10px", borderRadius: 6, fontSize: 13, fontWeight: 700,
                    background: "rgba(0,0,0,0.7)", color: scoreColor(c.virality_score),
                  }}>
                    {c.virality_score != null ? c.virality_score.toFixed(1) : "—"}
                  </div>
                  {/* Status badge */}
                  <div style={{
                    position: "absolute", bottom: 8, left: 8,
                    padding: "3px 8px", borderRadius: 4, fontSize: 10, fontWeight: 600,
                    background: badge.bg, color: badge.fg, backdropFilter: "blur(4px)",
                  }}>
                    {c.status}
                  </div>
                  {/* Rating */}
                  {c.manual_rating && (
                    <div style={{
                      position: "absolute", bottom: 8, right: 8,
                      padding: "3px 8px", borderRadius: 4, fontSize: 12, fontWeight: 600,
                      background: "rgba(0,0,0,0.7)", color: "#eab308",
                    }}>
                      {"★".repeat(c.manual_rating)}{"☆".repeat(5 - c.manual_rating)}
                    </div>
                  )}
                </div>

                {/* Content */}
                <div style={{ padding: "12px 16px" }}>
                  <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {c.title || c.caption || c.platform_video_id}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--fg-subtle)", marginBottom: 10 }}>
                    {c.author && <span style={{ marginRight: 8 }}>@{c.author}</span>}
                    <span>{fmtDate(c.published_at)}</span>
                  </div>

                  {/* Metrics row or GENERATE meta */}
                  {c.origin === "GENERATE" && c.meta ? (
                    <div style={{ fontSize: 12, color: "var(--fg-subtle)", marginBottom: 12 }}>
                      {typeof c.meta.hook === "string" && (
                        <div style={{ marginBottom: 4, fontStyle: "italic" }}>
                          &quot;{(c.meta.hook as string).slice(0, 80)}...&quot;
                        </div>
                      )}
                      {Array.isArray(c.meta.keywords) && (
                        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                          {(c.meta.keywords as string[]).slice(0, 5).map((kw, i) => (
                            <span key={i} style={{ padding: "1px 6px", borderRadius: 4, background: "var(--bg-hover)", fontSize: 11 }}>#{kw}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div style={{ display: "flex", gap: 12, fontSize: 12, color: "var(--fg-subtle)", marginBottom: 12 }}>
                      <span title="Просмотры">👁 {fmt(c.views)}</span>
                      <span title="Лайки">❤ {fmt(c.likes)}</span>
                      <span title="Комментарии">💬 {fmt(c.comments)}</span>
                      {c.shares != null && <span title="Репосты">↗ {fmt(c.shares)}</span>}
                    </div>
                  )}

                  {/* Actions */}
                  <div style={{ display: "flex", gap: 6 }}>
                    {c.status === "NEW" && (
                      <>
                        <button
                          onClick={() => openApproveModal(c)}
                          disabled={isLoading}
                          style={{
                            flex: 1, padding: "8px 0", borderRadius: 6, fontSize: 12, fontWeight: 600,
                            background: "#22c55e20", color: "#22c55e", opacity: isLoading ? 0.5 : 1,
                          }}
                        >
                          ✓ Approve
                        </button>
                        <button
                          onClick={() => reject(c)}
                          disabled={isLoading}
                          style={{
                            flex: 1, padding: "8px 0", borderRadius: 6, fontSize: 12, fontWeight: 600,
                            background: "#ef444420", color: "#ef4444", opacity: isLoading ? 0.5 : 1,
                          }}
                        >
                          ✕ Reject
                        </button>
                      </>
                    )}
                    {c.status === "APPROVED" && c.linked_publish_task_id && (
                      <button
                        onClick={() => router.push(`/queue/${c.linked_publish_task_id}`)}
                        style={{
                          flex: 1, padding: "8px 0", borderRadius: 6, fontSize: 12, fontWeight: 600,
                          background: "#6366f120", color: "#6366f1",
                        }}
                      >
                        → Задача #{c.linked_publish_task_id}
                      </button>
                    )}
                    {c.status === "REJECTED" && (
                      <button
                        onClick={() => openApproveModal(c)}
                        disabled={isLoading}
                        style={{
                          flex: 1, padding: "8px 0", borderRadius: 6, fontSize: 12, fontWeight: 500,
                          background: "var(--bg-hover)", color: "var(--fg-subtle)", opacity: isLoading ? 0.5 : 1,
                        }}
                      >
                        Вернуть
                      </button>
                    )}
                    <button
                      onClick={() => openRating(c)}
                      style={{
                        width: 36, padding: "8px 0", borderRadius: 6, fontSize: 14,
                        background: "var(--bg-hover)", color: "#eab308",
                      }}
                      title="Оценить"
                    >
                      ★
                    </button>
                    {c.url && (
                      <a
                        href={c.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          width: 36, padding: "8px 0", borderRadius: 6, fontSize: 13,
                          background: "var(--bg-hover)", color: "var(--fg-subtle)",
                          display: "flex", alignItems: "center", justifyContent: "center", textDecoration: "none",
                        }}
                        title="Открыть оригинал"
                      >
                        ↗
                      </a>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Approve Destination Modal */}
      {approveTarget && (
        <div
          onClick={() => setApproveTarget(null)}
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}
        >
          <div onClick={e => e.stopPropagation()} style={{
            background: "var(--bg-subtle)", borderRadius: "var(--radius-lg)",
            border: "1px solid var(--border)", width: "100%", maxWidth: 420, padding: 24,
          }}>
            <div style={{ fontWeight: 600, fontSize: 16, marginBottom: 4 }}>
              Выберите назначение
            </div>
            <div style={{ fontSize: 13, color: "var(--fg-subtle)", marginBottom: 16 }}>
              {approveTarget.title || approveTarget.platform_video_id}
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 20 }}>
              {destinations.filter(d => d.is_active).map(d => (
                <label
                  key={d.id}
                  style={{
                    display: "flex", alignItems: "center", gap: 10, padding: "10px 14px",
                    background: selectedDestId === d.id ? "#3b82f615" : "var(--bg-muted)",
                    border: selectedDestId === d.id ? "1px solid #3b82f6" : "1px solid var(--border)",
                    borderRadius: 8, cursor: "pointer", transition: "all 0.15s",
                  }}
                >
                  <input
                    type="radio"
                    name="dest"
                    checked={selectedDestId === d.id}
                    onChange={() => setSelectedDestId(d.id)}
                  />
                  <span style={{
                    padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 600,
                    background: PLATFORM_COLORS[d.platform] || "#666", color: "#fff",
                  }}>
                    {PLATFORM_ICONS[d.platform] || "•"} {d.platform}
                  </span>
                  <span style={{ fontSize: 13 }}>Аккаунт #{d.social_account_id}</span>
                  {d.priority > 0 && (
                    <span style={{ fontSize: 11, color: "var(--fg-subtle)", marginLeft: "auto" }}>
                      приоритет {d.priority}
                    </span>
                  )}
                </label>
              ))}
            </div>

            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button
                onClick={() => setApproveTarget(null)}
                style={{ padding: "10px 20px", background: "var(--bg-muted)", borderRadius: 6, color: "var(--fg-muted)", fontSize: 13 }}
              >
                Отмена
              </button>
              <button
                onClick={() => approveTarget && doApprove(approveTarget, selectedDestId)}
                disabled={!selectedDestId}
                style={{
                  padding: "10px 20px", background: "#22c55e", borderRadius: 6,
                  color: "#fff", fontWeight: 600, fontSize: 13,
                  opacity: selectedDestId ? 1 : 0.5,
                }}
              >
                ✓ Approve
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Rating Modal */}
      {ratingTarget && (
        <div
          onClick={() => setRatingTarget(null)}
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}
        >
          <div onClick={e => e.stopPropagation()} style={{
            background: "var(--bg-subtle)", borderRadius: "var(--radius-lg)",
            border: "1px solid var(--border)", width: "100%", maxWidth: 400, padding: 24,
          }}>
            <div style={{ fontWeight: 600, fontSize: 16, marginBottom: 16 }}>
              Оценка: {ratingTarget.title || ratingTarget.platform_video_id}
            </div>

            {/* Stars */}
            <div style={{ display: "flex", gap: 8, marginBottom: 16, justifyContent: "center" }}>
              {[1, 2, 3, 4, 5].map(n => (
                <button
                  key={n}
                  onClick={() => setRatingValue(n)}
                  style={{
                    width: 44, height: 44, borderRadius: 8, fontSize: 22,
                    background: n <= ratingValue ? "#eab30830" : "var(--bg-muted)",
                    color: n <= ratingValue ? "#eab308" : "var(--fg-subtle)",
                    transition: "all 0.1s",
                  }}
                >
                  {n <= ratingValue ? "★" : "☆"}
                </button>
              ))}
            </div>

            {/* Notes */}
            <textarea
              value={ratingNotes}
              onChange={e => setRatingNotes(e.target.value)}
              placeholder="Заметки (опционально)..."
              rows={3}
              style={{
                width: "100%", marginBottom: 16, padding: 10, borderRadius: 6,
                background: "var(--bg-muted)", border: "1px solid var(--border)",
                color: "var(--fg)", fontSize: 13, resize: "vertical",
              }}
            />

            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button
                onClick={() => setRatingTarget(null)}
                style={{ padding: "10px 20px", background: "var(--bg-muted)", borderRadius: 6, color: "var(--fg-muted)", fontSize: 13 }}
              >
                Отмена
              </button>
              <button
                onClick={submitRating}
                disabled={actionLoading === ratingTarget.id}
                style={{
                  padding: "10px 20px", background: "var(--primary)", borderRadius: 6,
                  color: "#fff", fontWeight: 500, fontSize: 13,
                  opacity: actionLoading === ratingTarget.id ? 0.6 : 1,
                }}
              >
                Сохранить
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
