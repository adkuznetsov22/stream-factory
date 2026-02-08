"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ToolIcon, ToolParamsForm } from "@/components/pipeline";
import { getTool } from "@/lib/toolDefinitions";

type StepResult = {
  id: number;
  task_id: number;
  step_index: number;
  tool_id: string;
  step_name: string | null;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  input_params: Record<string, unknown> | null;
  output_data: Record<string, unknown> | null;
  output_files: string[] | null;
  error_message: string | null;
  logs: string | null;
  moderation_status: string;
  moderation_comment: string | null;
  moderated_by: string | null;
  moderated_at: string | null;
  can_retry: boolean;
  retry_count: number;
  version: number;
};

type Task = {
  id: number;
  project_id: number;
  platform: string;
  status: string;
  moderation_mode: string;
  pipeline_status: string;
  current_step_index: number;
  total_steps: number;
  preview_url: string | null;
  caption_text: string | null;
};

const STATUS_CONFIG: Record<string, { color: string; bg: string }> = {
  pending: { color: "var(--fg-subtle)", bg: "var(--bg-hover)" },
  running: { color: "#3b82f6", bg: "#3b82f615" },
  completed: { color: "#22c55e", bg: "#22c55e15" },
  failed: { color: "#ef4444", bg: "#ef444415" },
  skipped: { color: "var(--fg-subtle)", bg: "var(--bg-muted)" },
};

const MOD_CONFIG: Record<string, { color: string; label: string }> = {
  pending: { color: "#eab308", label: "Ожидает" },
  approved: { color: "#22c55e", label: "Одобрено" },
  rejected: { color: "#ef4444", label: "Отклонено" },
  auto_approved: { color: "#8b5cf6", label: "Авто" },
  needs_rework: { color: "#ec4899", label: "Доработка" },
};

export default function TaskModerationPage() {
  const params = useParams<{ taskId: string }>();
  const router = useRouter();
  const taskId = Number(params?.taskId);
  
  const [task, setTask] = useState<Task | null>(null);
  const [steps, setSteps] = useState<StepResult[]>([]);
  const [selectedStep, setSelectedStep] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [paramsText, setParamsText] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [editingField, setEditingField] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [qcChecklist, setQcChecklist] = useState<Record<string, boolean>>({
    video_quality: false,
    audio_sync: false,
    text_correct: false,
    no_artifacts: false,
    duration_ok: false,
  });

  useEffect(() => { loadData(); }, [taskId]);

  const loadData = async () => {
    if (!taskId) return;
    try {
      const [taskRes, stepsRes] = await Promise.all([
        fetch(`/api/publish-tasks/${taskId}`),
        fetch(`/api/moderation/tasks/${taskId}/steps`),
      ]);
      if (taskRes.ok) setTask(await taskRes.json());
      if (stepsRes.ok) {
        const data = await stepsRes.json();
        setSteps(data);
        if (data.length > 0 && selectedStep >= data.length) setSelectedStep(0);
      }
    } finally { setLoading(false); }
  };

  const currentStep = steps[selectedStep];
  const tool = currentStep ? getTool(currentStep.tool_id) : null;

  const handleAction = async (action: "approve" | "reject" | "retry") => {
    if (!currentStep) return;
    const body = action === "reject" 
      ? { comment: prompt("Причина:") || "Отклонено" }
      : action === "retry" 
        ? { new_params: paramsText ? JSON.parse(paramsText) : null }
        : {};
    await fetch(`/api/moderation/tasks/${taskId}/steps/${currentStep.step_index}/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    setShowModal(false);
    loadData();
  };

  const changeMode = async (mode: string) => {
    await fetch(`/api/moderation/tasks/${taskId}/moderation-mode`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ moderation_mode: mode }),
    });
    loadData();
  };

  if (!taskId) return <div style={{ padding: 40, textAlign: "center" }}>Некорректный ID</div>;

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: "32px 24px" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
        <div>
          <button onClick={() => router.push("/moderation")} style={{ color: "var(--fg-muted)", marginBottom: 8, fontSize: 13 }}>
            ← Назад
          </button>
          <h1 style={{ fontSize: 24, fontWeight: 600 }}>Задача #{taskId}</h1>
        </div>
        {task && (
          <div style={{ display: "flex", gap: 6 }}>
            {["auto", "manual", "step_by_step"].map((m) => (
              <button
                key={m}
                onClick={() => changeMode(m)}
                style={{
                  padding: "6px 12px",
                  borderRadius: "var(--radius)",
                  background: task.moderation_mode === m ? "var(--accent)" : "var(--bg-muted)",
                  color: task.moderation_mode === m ? "#fff" : "var(--fg-muted)",
                  fontSize: 12,
                }}
              >
                {m === "auto" ? "Авто" : m === "manual" ? "Ручной" : "По шагам"}
              </button>
            ))}
          </div>
        )}
      </div>

      {loading ? (
        <div style={{ padding: 60, textAlign: "center", color: "var(--fg-subtle)" }}>Загрузка...</div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: 24 }}>
          {/* Steps sidebar */}
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {steps.map((s, idx) => {
              const t = getTool(s.tool_id);
              const mod = MOD_CONFIG[s.moderation_status] || { color: "#666", label: s.moderation_status };
              const st = STATUS_CONFIG[s.status] || { color: "var(--fg-subtle)", bg: "var(--bg-hover)" };
              return (
                <button
                  key={s.id}
                  onClick={() => setSelectedStep(idx)}
                  style={{
                    padding: "10px 12px",
                    borderRadius: "var(--radius)",
                    background: selectedStep === idx ? "var(--bg-muted)" : "transparent",
                    border: selectedStep === idx ? "1px solid var(--border)" : "1px solid transparent",
                    textAlign: "left",
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                  }}
                >
                  <div style={{ width: 28, height: 28, borderRadius: 6, background: st.bg, display: "flex", alignItems: "center", justifyContent: "center" }}>
                    <ToolIcon icon={t?.icon || "HelpCircle"} size={14} color={st.color} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {s.step_name || t?.name || s.tool_id}
                    </div>
                    <div style={{ fontSize: 11, color: mod.color }}>{mod.label}</div>
                  </div>
                </button>
              );
            })}
            {steps.length === 0 && <div style={{ padding: 20, color: "var(--fg-subtle)", textAlign: "center" }}>Нет шагов</div>}
          </div>

          {/* Step detail */}
          {currentStep && (
            <div style={{ background: "var(--bg-subtle)", borderRadius: "var(--radius-lg)", border: "1px solid var(--border)" }}>
              {/* Header */}
              <div style={{ padding: 20, borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ width: 44, height: 44, borderRadius: "var(--radius)", background: tool ? `${tool.color}20` : "var(--bg-hover)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    <ToolIcon icon={tool?.icon || "HelpCircle"} size={20} color={tool?.color} />
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 16 }}>{currentStep.step_name || tool?.name || currentStep.tool_id}</div>
                    <div style={{ fontSize: 12, color: "var(--fg-subtle)" }}>
                      Шаг {currentStep.step_index + 1} · v{currentStep.version}
                      {currentStep.duration_ms && ` · ${(currentStep.duration_ms / 1000).toFixed(1)}s`}
                    </div>
                  </div>
                </div>
                <div style={{ padding: "6px 14px", borderRadius: 20, background: `${MOD_CONFIG[currentStep.moderation_status]?.color || "#666"}20`, color: MOD_CONFIG[currentStep.moderation_status]?.color || "#666", fontSize: 13, fontWeight: 500 }}>
                  {MOD_CONFIG[currentStep.moderation_status]?.label || currentStep.moderation_status}
                </div>
              </div>

              {/* Content */}
              <div style={{ padding: 20 }}>
                {/* Error */}
                {currentStep.error_message && (
                  <div style={{ marginBottom: 20, padding: 16, background: "#ef444415", border: "1px solid #ef4444", borderRadius: "var(--radius)", color: "#ef4444" }}>
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>Ошибка</div>
                    <pre style={{ fontSize: 12, whiteSpace: "pre-wrap", margin: 0 }}>{currentStep.error_message}</pre>
                  </div>
                )}

                {/* Editable Text Fields */}
                {currentStep.output_data && (() => {
                  const textFields = ["transcript_text", "translated_text", "caption_text", "description", "title"];
                  const editableEntries = Object.entries(currentStep.output_data).filter(([k]) => textFields.includes(k));
                  const otherEntries = Object.entries(currentStep.output_data).filter(([k]) => !textFields.includes(k));
                  
                  const saveEdit = async (field: string) => {
                    await fetch(`/api/moderation/tasks/${taskId}/steps/${currentStep.step_index}/edit`, {
                      method: "PATCH",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ [field]: editValue }),
                    });
                    setEditingField(null);
                    loadData();
                  };
                  
                  return (
                    <>
                      {editableEntries.length > 0 && (
                        <div style={{ marginBottom: 20 }}>
                          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--fg-subtle)", marginBottom: 12, textTransform: "uppercase" }}>Текстовые данные</div>
                          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                            {editableEntries.map(([key, value]) => (
                              <div key={key} style={{ background: "var(--bg-muted)", borderRadius: "var(--radius)", padding: 16 }}>
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                                  <span style={{ fontSize: 12, fontWeight: 600, color: "var(--fg-subtle)" }}>{key}</span>
                                  {editingField === key ? (
                                    <div style={{ display: "flex", gap: 4 }}>
                                      <button onClick={() => saveEdit(key)} style={{ padding: "4px 10px", background: "#22c55e", borderRadius: 4, color: "#fff", fontSize: 11 }}>Сохранить</button>
                                      <button onClick={() => setEditingField(null)} style={{ padding: "4px 10px", background: "var(--bg-hover)", borderRadius: 4, fontSize: 11 }}>Отмена</button>
                                    </div>
                                  ) : (
                                    <button
                                      onClick={() => { setEditingField(key); setEditValue(String(value || "")); }}
                                      style={{ padding: "4px 10px", background: "var(--bg-hover)", borderRadius: 4, fontSize: 11, color: "var(--fg-muted)" }}
                                    >
                                      ✏️ Редактировать
                                    </button>
                                  )}
                                </div>
                                {editingField === key ? (
                                  <textarea
                                    value={editValue}
                                    onChange={(e) => setEditValue(e.target.value)}
                                    style={{ width: "100%", minHeight: 120, padding: 12, borderRadius: "var(--radius)", background: "var(--bg-subtle)", border: "1px solid var(--border)", fontSize: 13, resize: "vertical" }}
                                  />
                                ) : (
                                  <div style={{ fontSize: 13, whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{String(value || "—")}</div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                      {otherEntries.length > 0 && (
                        <div style={{ marginBottom: 20 }}>
                          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--fg-subtle)", marginBottom: 8, textTransform: "uppercase" }}>Прочие данные</div>
                          <pre style={{ background: "var(--bg-muted)", padding: 16, borderRadius: "var(--radius)", fontSize: 12, overflow: "auto", maxHeight: 200, margin: 0 }}>
                            {JSON.stringify(Object.fromEntries(otherEntries), null, 2)}
                          </pre>
                        </div>
                      )}
                    </>
                  );
                })()}

                {/* Files */}
                {currentStep.output_files && currentStep.output_files.length > 0 && (
                  <div style={{ marginBottom: 20 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "var(--fg-subtle)", marginBottom: 8, textTransform: "uppercase" }}>Файлы</div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                      {currentStep.output_files.map((f, i) => (
                        <div key={i} style={{ padding: "6px 12px", background: "var(--bg-muted)", borderRadius: "var(--radius)", fontSize: 12 }}>
                          {f.split("/").pop()}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Logs */}
                {currentStep.logs && (
                  <details style={{ marginBottom: 20 }}>
                    <summary style={{ cursor: "pointer", fontSize: 12, color: "var(--fg-subtle)", marginBottom: 8 }}>Логи</summary>
                    <pre style={{ background: "var(--bg-muted)", padding: 16, borderRadius: "var(--radius)", fontSize: 11, overflow: "auto", maxHeight: 200, whiteSpace: "pre-wrap", margin: 0 }}>
                      {currentStep.logs}
                    </pre>
                  </details>
                )}

                {/* Comment */}
                {currentStep.moderation_comment && (
                  <div style={{ padding: 16, background: "var(--bg-muted)", borderRadius: "var(--radius)", borderLeft: `3px solid ${MOD_CONFIG[currentStep.moderation_status]?.color}`, marginBottom: 20 }}>
                    <div style={{ marginBottom: 4 }}>{currentStep.moderation_comment}</div>
                    {currentStep.moderated_by && <div style={{ fontSize: 11, color: "var(--fg-subtle)" }}>— {currentStep.moderated_by}</div>}
                  </div>
                )}

                {/* QC Checklist */}
                {currentStep.moderation_status === "pending" && (
                  <div style={{ marginBottom: 20, padding: 16, background: "var(--bg-muted)", borderRadius: "var(--radius)" }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "var(--fg-subtle)", marginBottom: 12, textTransform: "uppercase" }}>QC Чеклист</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      {[
                        { key: "video_quality", label: "Качество видео в норме" },
                        { key: "audio_sync", label: "Аудио синхронизировано" },
                        { key: "text_correct", label: "Текст/субтитры корректны" },
                        { key: "no_artifacts", label: "Нет артефактов/глитчей" },
                        { key: "duration_ok", label: "Длительность соответствует" },
                      ].map(item => (
                        <label key={item.key} style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
                          <input
                            type="checkbox"
                            checked={qcChecklist[item.key] || false}
                            onChange={e => setQcChecklist(prev => ({ ...prev, [item.key]: e.target.checked }))}
                            style={{ width: 18, height: 18, accentColor: "#22c55e" }}
                          />
                          <span style={{ fontSize: 13, color: qcChecklist[item.key] ? "var(--fg)" : "var(--fg-muted)" }}>{item.label}</span>
                        </label>
                      ))}
                    </div>
                    <div style={{ marginTop: 12, fontSize: 12, color: "var(--fg-subtle)" }}>
                      Проверено: {Object.values(qcChecklist).filter(Boolean).length} / 5
                    </div>
                  </div>
                )}
              </div>

              {/* Actions */}
              <div style={{ padding: 20, borderTop: "1px solid var(--border)", display: "flex", gap: 8 }}>
                {currentStep.moderation_status === "pending" && (
                  <>
                    <button onClick={() => handleAction("approve")} style={{ padding: "10px 20px", background: "#22c55e", borderRadius: "var(--radius)", color: "#fff", fontWeight: 500 }}>
                      Одобрить
                    </button>
                    <button onClick={() => handleAction("reject")} style={{ padding: "10px 20px", background: "#ef4444", borderRadius: "var(--radius)", color: "#fff", fontWeight: 500 }}>
                      Отклонить
                    </button>
                  </>
                )}
                {currentStep.can_retry && (
                  <button onClick={() => { setParamsText(JSON.stringify(currentStep.input_params || {}, null, 2)); setShowModal(true); }} style={{ padding: "10px 20px", background: "var(--accent)", borderRadius: "var(--radius)", color: "#fff", fontWeight: 500 }}>
                    Перезапустить
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Modal */}
      {showModal && currentStep && (
        <div onClick={() => setShowModal(false)} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: "var(--bg-subtle)", borderRadius: "var(--radius-lg)", border: "1px solid var(--border)", width: "100%", maxWidth: 480 }}>
            <div style={{ padding: 20, borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontWeight: 600 }}>Перезапуск: {tool?.name || currentStep.tool_id}</div>
              <button onClick={() => setShowModal(false)} style={{ width: 28, height: 28, borderRadius: "var(--radius)", background: "var(--bg-muted)", fontSize: 18 }}>×</button>
            </div>
            <div style={{ padding: 20 }}>
              <ToolParamsForm
                toolId={currentStep.tool_id}
                params={(() => { try { return JSON.parse(paramsText) || {}; } catch { return {}; } })()}
                onChange={(p) => setParamsText(JSON.stringify(p, null, 2))}
              />
            </div>
            <div style={{ padding: 20, borderTop: "1px solid var(--border)", display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <button onClick={() => setShowModal(false)} style={{ padding: "10px 20px", background: "var(--bg-muted)", borderRadius: "var(--radius)", color: "var(--fg-muted)" }}>Отмена</button>
              <button onClick={() => handleAction("retry")} style={{ padding: "10px 20px", background: "var(--accent)", borderRadius: "var(--radius)", color: "#fff", fontWeight: 500 }}>Перезапустить</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
