"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ToolParamsForm, ToolIcon } from "@/components/pipeline";
import { useTools } from "@/lib/useTools";
import type { ToolCategory } from "@/lib/toolDefinitions";

type Preset = { id: number; name: string; description?: string | null; is_active: boolean };
type Step = { id: number; preset_id: number; tool_id: string; name: string; enabled: boolean; order_index: number; params?: Record<string, unknown>; requires_moderation?: boolean };
type Toast = { message: string; type: "success" | "error" } | null;

export default function PresetDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const presetId = Number(params?.id);
  const { toolsList, toolsByCategory, getTool, categoryLabels, loading: toolsLoading } = useTools();
  const [preset, setPreset] = useState<Preset | null>(null);
  const [steps, setSteps] = useState<Step[]>([]);
  const [loading, setLoading] = useState(true);
  const [editStep, setEditStep] = useState<number | null>(null);
  const [paramsText, setParamsText] = useState("");
  const [toast, setToast] = useState<Toast>(null);
  const [moving, setMoving] = useState<number | null>(null);

  const showToast = (message: string, type: "success" | "error" = "success") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  useEffect(() => { loadAll(); }, [presetId]);

  const loadAll = async () => {
    if (!presetId) return;
    try {
      const [pRes, sRes] = await Promise.all([
        fetch(`/api/presets/${presetId}`),
        fetch(`/api/presets/${presetId}/steps`),
      ]);
      if (pRes.ok) setPreset(await pRes.json());
      if (sRes.ok) setSteps(await sRes.json());
    } finally { setLoading(false); }
  };

  const sortedSteps = useMemo(() => [...steps].sort((a, b) => a.order_index - b.order_index), [steps]);

  const addStep = async (toolId: string) => {
    const maxOrder = steps.reduce((acc, s) => Math.max(acc, s.order_index), 0);
    const res = await fetch(`/api/presets/${presetId}/steps`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool_id: toolId, order_index: maxOrder + 10, enabled: true }),
    });
    if (!res.ok) {
      showToast("Ошибка добавления шага", "error");
      return;
    }
    loadAll();
  };

  const updateStep = async (stepId: number, data: Partial<Step>) => {
    await fetch(`/api/preset-steps/${stepId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    loadAll();
  };

  const deleteStep = async (stepId: number) => {
    await fetch(`/api/preset-steps/${stepId}`, { method: "DELETE" });
    loadAll();
  };

  const moveStep = async (stepId: number, direction: "up" | "down") => {
    setMoving(stepId);
    try {
      const res = await fetch(`/api/preset-steps/${stepId}/move`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ direction }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Ошибка перемещения" }));
        showToast(err.detail || "Ошибка перемещения", "error");
        return;
      }
      const updatedSteps = await res.json();
      setSteps(updatedSteps);
    } catch {
      showToast("Сетевая ошибка", "error");
    } finally {
      setMoving(null);
    }
  };

  const saveParams = async () => {
    if (!editStep) return;
    try {
      await updateStep(editStep, { params: JSON.parse(paramsText) });
      setEditStep(null);
    } catch { /* invalid json */ }
  };

  if (!presetId) return <div className="empty">Некорректный ID</div>;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <button onClick={() => router.push("/presets")} className="btn btn-ghost" style={{ marginBottom: 8 }}>← Назад</button>
          <h1 className="page-title">{preset?.name || `Пресет #${presetId}`}</h1>
          {preset && <p style={{ color: "var(--fg-subtle)", marginTop: 4, fontSize: 13 }}>{preset.description || "Без описания"}</p>}
        </div>
        {preset && (
          <span className={`badge ${preset.is_active ? "badge-success" : ""}`}>
            {preset.is_active ? "Активен" : "Неактивен"}
          </span>
        )}
      </div>

      {loading ? (
        <div style={{ padding: 60, textAlign: "center", color: "var(--fg-subtle)" }}>Загрузка...</div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 300px", gap: 24 }}>
          {/* Pipeline */}
          <div style={{ background: "var(--bg-subtle)", borderRadius: "var(--radius-lg)", border: "1px solid var(--border)" }}>
            <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)", fontWeight: 600 }}>
              Pipeline ({sortedSteps.length} шагов)
            </div>
            <div style={{ padding: 16 }}>
              {sortedSteps.length === 0 ? (
                <div style={{ padding: 40, textAlign: "center", color: "var(--fg-subtle)" }}>Добавьте инструменты из панели справа</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {sortedSteps.map((s, idx) => {
                    const t = getTool(s.tool_id);
                    return (
                      <div key={s.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px", background: "var(--bg-muted)", borderRadius: "var(--radius)", opacity: s.enabled ? 1 : 0.5 }}>
                        <div style={{ width: 24, height: 24, borderRadius: 6, background: t ? `${t.color}20` : "var(--bg-hover)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 600, color: "var(--fg-subtle)" }}>
                          {idx + 1}
                        </div>
                        <div style={{ width: 32, height: 32, borderRadius: "var(--radius)", background: t ? `${t.color}20` : "var(--bg-hover)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                          <ToolIcon icon={t?.icon || "HelpCircle"} size={16} color={t?.color} />
                        </div>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontWeight: 500 }}>{t?.name || s.tool_id}</div>
                          <div style={{ fontSize: 11, color: "var(--fg-subtle)" }}>
                            {s.params ? Object.keys(s.params).length + " params" : "Defaults"}
                            {s.requires_moderation && <span style={{ marginLeft: 6, color: "#eab308" }}>• Модерация</span>}
                          </div>
                        </div>
                        <div style={{ display: "flex", gap: 4 }}>
                          <button onClick={() => updateStep(s.id, { enabled: !s.enabled })} style={{ width: 28, height: 28, borderRadius: "var(--radius)", background: "var(--bg-hover)", fontSize: 12 }} title={s.enabled ? "Отключить" : "Включить"}>
                            {s.enabled ? "✓" : "○"}
                          </button>
                          <button onClick={() => updateStep(s.id, { requires_moderation: !s.requires_moderation })} style={{ width: 28, height: 28, borderRadius: "var(--radius)", background: s.requires_moderation ? "#eab30830" : "var(--bg-hover)", color: s.requires_moderation ? "#eab308" : "var(--fg-subtle)", fontSize: 12 }} title={s.requires_moderation ? "Модерация вкл" : "Модерация выкл"}>
                            👁
                          </button>
                          <button onClick={() => { setEditStep(s.id); setParamsText(JSON.stringify(s.params || {}, null, 2)); }} style={{ width: 28, height: 28, borderRadius: "var(--radius)", background: "var(--bg-hover)", fontSize: 12 }} title="Настроить">⚙</button>
                          {idx > 0 && <button onClick={() => moveStep(s.id, "up")} disabled={moving === s.id} style={{ width: 28, height: 28, borderRadius: "var(--radius)", background: "var(--bg-hover)", fontSize: 10, opacity: moving === s.id ? 0.5 : 1 }}>↑</button>}
                          {idx < sortedSteps.length - 1 && <button onClick={() => moveStep(s.id, "down")} disabled={moving === s.id} style={{ width: 28, height: 28, borderRadius: "var(--radius)", background: "var(--bg-hover)", fontSize: 10, opacity: moving === s.id ? 0.5 : 1 }}>↓</button>}
                          <button onClick={() => deleteStep(s.id)} style={{ width: 28, height: 28, borderRadius: "var(--radius)", background: "#ef444420", color: "#ef4444", fontSize: 12 }}>×</button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Tool Picker */}
          <div style={{ background: "var(--bg-subtle)", borderRadius: "var(--radius-lg)", border: "1px solid var(--border)", height: "fit-content" }}>
            <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)", fontWeight: 600 }}>Инструменты</div>
            <div style={{ padding: 16 }}>
              {(["input", "analysis", "video", "audio", "text", "output"] as ToolCategory[]).map((cat) => {
                const tools = toolsByCategory[cat];
                if (!tools?.length) return null;
                return (
                  <div key={cat} style={{ marginBottom: 16 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: "var(--fg-subtle)", textTransform: "uppercase", marginBottom: 8 }}>{categoryLabels[cat]}</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      {tools.map((tool) => (
                        <button
                          key={tool.id}
                          onClick={() => addStep(tool.id)}
                          style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", background: "var(--bg-muted)", borderRadius: "var(--radius)", textAlign: "left", transition: "background 0.1s" }}
                          onMouseEnter={(e) => e.currentTarget.style.background = "var(--bg-hover)"}
                          onMouseLeave={(e) => e.currentTarget.style.background = "var(--bg-muted)"}
                        >
                          <ToolIcon icon={tool.icon} size={14} color={tool.color} />
                          <span style={{ fontSize: 13 }}>{tool.name}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {editStep && (() => {
        const step = steps.find((s) => s.id === editStep);
        const tool = step ? getTool(step.tool_id) : null;
        return (
          <div onClick={() => setEditStep(null)} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}>
            <div onClick={(e) => e.stopPropagation()} style={{ background: "var(--bg-subtle)", borderRadius: "var(--radius-lg)", border: "1px solid var(--border)", width: "100%", maxWidth: 480 }}>
              <div style={{ padding: 20, borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  {tool && <ToolIcon icon={tool.icon} size={18} color={tool.color} />}
                  <span style={{ fontWeight: 600 }}>{tool?.name || step?.tool_id}</span>
                </div>
                <button onClick={() => setEditStep(null)} style={{ width: 28, height: 28, borderRadius: "var(--radius)", background: "var(--bg-muted)", fontSize: 18 }}>×</button>
              </div>
              <div style={{ padding: 20 }}>
                <ToolParamsForm
                  toolId={step?.tool_id || ""}
                  params={(() => { try { return JSON.parse(paramsText) || {}; } catch { return {}; } })()}
                  onChange={(p) => setParamsText(JSON.stringify(p, null, 2))}
                  paramSchema={tool?.paramSchema}
                />
              </div>
              <div style={{ padding: 20, borderTop: "1px solid var(--border)", display: "flex", justifyContent: "flex-end", gap: 8 }}>
                <button onClick={() => setEditStep(null)} style={{ padding: "10px 20px", background: "var(--bg-muted)", borderRadius: "var(--radius)", color: "var(--fg-muted)" }}>Отмена</button>
                <button onClick={saveParams} style={{ padding: "10px 20px", background: "var(--primary)", borderRadius: "var(--radius)", color: "#fff", fontWeight: 500 }}>Сохранить</button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* Toast notification */}
      {toast && (
        <div style={{
          position: "fixed",
          bottom: 24,
          right: 24,
          padding: "12px 20px",
          borderRadius: "var(--radius)",
          background: toast.type === "error" ? "#ef4444" : "#22c55e",
          color: "#fff",
          fontWeight: 500,
          fontSize: 14,
          boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
          zIndex: 200,
          animation: "fadeIn 0.2s ease"
        }}>
          {toast.message}
        </div>
      )}
    </div>
  );
}
