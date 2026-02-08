"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type Preset = { id: number; name: string; description?: string | null; is_active: boolean };

export default function PresetsPage() {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  const load = async () => {
    setLoading(true);
    const res = await fetch("/api/presets");
    if (res.ok) setPresets(await res.json());
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!name.trim()) return;
    await fetch("/api/presets", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
    setName("");
    setShowCreate(false);
    load();
  };

  const del = async (id: number) => {
    if (!confirm("Удалить?")) return;
    await fetch(`/api/presets/${id}`, { method: "DELETE" });
    load();
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Пресеты</h1>
          <p style={{ color: "var(--fg-subtle)", marginTop: 4, fontSize: 13 }}>{presets.length} всего</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>+ Создать</button>
      </div>

      <div className="card">
        {loading ? (
          <div className="empty">Загрузка...</div>
        ) : presets.length === 0 ? (
          <div className="empty">Нет пресетов</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Название</th>
                <th>Описание</th>
                <th>Статус</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {presets.map(p => (
                <tr key={p.id}>
                  <td style={{ fontWeight: 500 }}>{p.name}</td>
                  <td style={{ color: "var(--fg-subtle)" }}>{p.description || "—"}</td>
                  <td><span className={`badge ${p.is_active ? "badge-success" : ""}`}>{p.is_active ? "Активен" : "Отключён"}</span></td>
                  <td>
                    <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
                      <Link href={`/presets/${p.id}`} className="btn btn-ghost">Открыть</Link>
                      <button className="btn btn-ghost" onClick={() => del(p.id)}>×</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showCreate && (
        <div className="modal-overlay" onClick={() => setShowCreate(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <span style={{ fontWeight: 500 }}>Создать пресет</span>
              <button className="btn btn-ghost" onClick={() => setShowCreate(false)}>×</button>
            </div>
            <div className="modal-body">
              <label style={{ display: "block", marginBottom: 6, fontSize: 12, color: "var(--fg-subtle)" }}>Название</label>
              <input value={name} onChange={e => setName(e.target.value)} placeholder="Новый пресет" style={{ width: "100%" }} />
            </div>
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={() => setShowCreate(false)}>Отмена</button>
              <button className="btn btn-primary" onClick={create}>Создать</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
