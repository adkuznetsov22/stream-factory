"use client";

import { useEffect, useState } from "react";

type Platform = "YouTube" | "TikTok" | "VK" | "Instagram";

type Account = {
  id: number;
  platform: Platform;
  label: string;
  login: string;
  handle: string;
  url: string;
  subscribers?: number | null;
  views_total?: number | null;
  views_7d?: number | null;
  videos_total?: number | null;
  posts_total?: number | null;
  sync_status?: string | null;
  sync_error?: string | null;
  avatar_url?: string | null;
  last_synced_at?: string | null;
};

const fmt = (n?: number | null) => n == null ? "—" : n >= 1e6 ? `${(n/1e6).toFixed(1)}M` : n >= 1e3 ? `${(n/1e3).toFixed(1)}K` : String(n);

const PLATFORM_DOT: Record<Platform, string> = {
  YouTube: "#ff0000",
  TikTok: "#00f2ea",
  VK: "#0077ff",
  Instagram: "#e4405f",
};

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Platform | "all">("all");
  const [search, setSearch] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({ platform: "YouTube" as Platform, login: "", label: "" });
  const [syncing, setSyncing] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    const res = await fetch("/api/accounts");
    if (res.ok) setAccounts(await res.json());
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const filtered = accounts.filter(a => {
    if (filter !== "all" && a.platform !== filter) return false;
    if (search && !a.label.toLowerCase().includes(search.toLowerCase()) && !a.handle?.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const syncAccount = async (id: number, platform: Platform) => {
    setSyncing(id);
    const paths: Record<Platform, string> = {
      YouTube: `/api/accounts/${id}/youtube/sync`,
      TikTok: `/api/accounts/${id}/tiktok/sync`,
      VK: `/api/accounts/${id}/vk/sync`,
      Instagram: `/api/accounts/${id}/instagram/sync`,
    };
    await fetch(paths[platform], { method: "POST" });
    setSyncing(null);
    load();
  };

  const createAccount = async () => {
    const handle = form.login.replace(/^@/, "");
    const urls: Record<Platform, string> = {
      YouTube: `https://youtube.com/@${handle}`,
      TikTok: `https://tiktok.com/@${handle}`,
      VK: `https://vk.com/${handle}`,
      Instagram: `https://instagram.com/${handle}`,
    };
    await fetch("/api/accounts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ platform: form.platform, label: form.label || handle, login: handle, url: urls[form.platform] }),
    });
    setShowModal(false);
    setForm({ platform: "YouTube", login: "", label: "" });
    load();
  };

  const deleteAccount = async (id: number) => {
    if (!confirm("Удалить?")) return;
    await fetch(`/api/accounts/${id}`, { method: "DELETE" });
    load();
  };

  return (
    <div className="page">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">Аккаунты</h1>
          <p style={{ color: "var(--fg-subtle)", marginTop: 4, fontSize: 13 }}>{accounts.length} всего</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowModal(true)}>+ Добавить</button>
      </div>

      {/* Filters */}
      <div className="filters">
        <div className="filter-tabs">
          {(["all", "YouTube", "TikTok", "VK", "Instagram"] as const).map(p => (
            <button key={p} className={`filter-tab ${filter === p ? "active" : ""}`} onClick={() => setFilter(p)}>
              {p === "all" ? "Все" : p}
            </button>
          ))}
        </div>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Поиск..."
          style={{ width: 200 }}
        />
      </div>

      {/* Table */}
      <div className="card">
        {loading ? (
          <div className="empty">Загрузка...</div>
        ) : filtered.length === 0 ? (
          <div className="empty">Нет аккаунтов</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Аккаунт</th>
                <th>Платформа</th>
                <th style={{ textAlign: "right" }}>Подписчики</th>
                <th style={{ textAlign: "right" }}>Просмотры</th>
                <th style={{ textAlign: "right" }}>Видео</th>
                <th>Статус</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(acc => (
                <tr key={acc.id}>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <div style={{
                        width: 36, height: 36, borderRadius: 8,
                        background: acc.avatar_url ? `url(${acc.avatar_url}) center/cover` : "var(--bg-muted)",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontSize: 12, fontWeight: 600, color: "var(--fg-subtle)",
                      }}>
                        {!acc.avatar_url && acc.label.slice(0, 2).toUpperCase()}
                      </div>
                      <div>
                        <div style={{ fontWeight: 500 }}>{acc.label}</div>
                        <div style={{ fontSize: 12, color: "var(--fg-subtle)" }}>{acc.handle}</div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ width: 8, height: 8, borderRadius: 4, background: PLATFORM_DOT[acc.platform] }} />
                      {acc.platform}
                    </div>
                  </td>
                  <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{fmt(acc.subscribers)}</td>
                  <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{fmt(acc.views_total || acc.views_7d)}</td>
                  <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{fmt(acc.videos_total || acc.posts_total)}</td>
                  <td>
                    <span className={`badge ${acc.sync_status === "ok" ? "badge-success" : acc.sync_status === "error" ? "badge-error" : ""}`}>
                      {acc.sync_status === "ok" ? "OK" : acc.sync_status === "error" ? "Ошибка" : "—"}
                    </span>
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
                      <button
                        className="btn btn-ghost"
                        onClick={() => syncAccount(acc.id, acc.platform)}
                        disabled={syncing === acc.id}
                        title="Синхронизировать"
                      >
                        {syncing === acc.id ? "..." : "↻"}
                      </button>
                      <a href={acc.url} target="_blank" rel="noreferrer" className="btn btn-ghost" title="Открыть">↗</a>
                      <button className="btn btn-ghost" onClick={() => deleteAccount(acc.id)} title="Удалить">×</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <span style={{ fontWeight: 500 }}>Добавить аккаунт</span>
              <button className="btn btn-ghost" onClick={() => setShowModal(false)}>×</button>
            </div>
            <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div>
                <label style={{ display: "block", marginBottom: 6, fontSize: 12, color: "var(--fg-subtle)" }}>Платформа</label>
                <div style={{ display: "flex", gap: 6 }}>
                  {(["YouTube", "TikTok", "VK", "Instagram"] as Platform[]).map(p => (
                    <button
                      key={p}
                      className={`btn ${form.platform === p ? "btn-primary" : "btn-outline"}`}
                      style={{ flex: 1 }}
                      onClick={() => setForm(f => ({ ...f, platform: p }))}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label style={{ display: "block", marginBottom: 6, fontSize: 12, color: "var(--fg-subtle)" }}>Handle / Username</label>
                <input
                  value={form.login}
                  onChange={e => setForm(f => ({ ...f, login: e.target.value }))}
                  placeholder="@username"
                  style={{ width: "100%" }}
                />
              </div>
              <div>
                <label style={{ display: "block", marginBottom: 6, fontSize: 12, color: "var(--fg-subtle)" }}>Название (опционально)</label>
                <input
                  value={form.label}
                  onChange={e => setForm(f => ({ ...f, label: e.target.value }))}
                  placeholder="Мой канал"
                  style={{ width: "100%" }}
                />
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={() => setShowModal(false)}>Отмена</button>
              <button className="btn btn-primary" onClick={createAccount}>Добавить</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
