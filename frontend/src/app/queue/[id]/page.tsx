"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { artifactLabel, formatDurationMs, statusBadgeVariant, statusLabel } from "@/lib/uiText";

const API_BASE = "";

type UiFileItem = { title: string; url: string | null; available: boolean; kind?: string | null; file?: string | null };
type UiResultBlock = { title: string; url: string | null; available: boolean };
type UiStep = {
  index: number;
  id: string;
  title: string;
  description?: string | null;
  status: string;
  status_label: string;
  duration_sec?: number | null;
  error_message?: string | null;
  outputs?: UiFileItem[] | null;
};
type UiPipeline = {
  summary: { total: number; done: number; skipped: number; error: number; duration_sec?: number | null };
  steps: UiStep[];
};
type UiTask = {
  id: number;
  status: string;
  status_label: string;
  project_id: number;
  project_name?: string | null;
  platform: string;
  platform_label?: string | null;
  preset_id?: number | null;
  preset_name?: string | null;
  external_id?: string | null;
  permalink?: string | null;
  caption_text?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};
type UiActions = { can_process: boolean; can_process_v2: boolean; can_retry_publish: boolean; can_mark_done: boolean; can_mark_error: boolean };
type PublishInfo = {
  published_url?: string | null;
  published_external_id?: string | null;
  published_at?: string | null;
  publish_error?: string | null;
  last_metrics_json?: Record<string, number> | null;
  last_metrics_at?: string | null;
};
type CandidateInfo = {
  id: number;
  title?: string | null;
  author?: string | null;
  platform: string;
  url?: string | null;
  origin: string;
  virality_score?: number | null;
  virality_factors?: Record<string, number> | null;
  views?: number | null;
  likes?: number | null;
  comments?: number | null;
  shares?: number | null;
  brief_id?: number | null;
  meta?: Record<string, unknown> | null;
};
type StepResultItem = {
  id: number;
  step_index: number;
  tool_id: string;
  step_name?: string | null;
  status: string;
  started_at?: string | null;
  completed_at?: string | null;
  duration_ms?: number | null;
  output_data?: Record<string, unknown> | null;
  output_files?: string[] | null;
  error_message?: string | null;
  logs?: string | null;
  moderation_status: string;
  retry_count: number;
  version: number;
};
type MetricSnapshot = {
  id: number; task_id: number; platform: string;
  views: number; likes: number; comments: number; shares?: number | null;
  snapshot_at: string; hours_since_publish?: number | null;
};
type UiResponse = {
  task: UiTask;
  result: { preview: UiResultBlock; final: UiResultBlock; ready: UiResultBlock; raw: UiResultBlock; thumb: UiResultBlock };
  pipeline: UiPipeline;
  files: { video: UiFileItem[]; preview: UiFileItem[]; subtitles: UiFileItem[]; technical: UiFileItem[] };
  actions: UiActions;
  publish: PublishInfo;
  candidate?: CandidateInfo | null;
  step_results: StepResultItem[];
};

const FILTERED_PATTERNS = [
  "[swscaler",
  "deprecated pixel format",
  "frame=",
  "Past duration",
  "[h264",
  "[aac",
  "Last message repeated",
  "speed=",
  "bitrate=",
];

export default function TaskDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const taskId = Number(params?.id);

  const [data, setData] = useState<UiResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [metrics, setMetrics] = useState<MetricSnapshot[]>([]);
  const [expandedStepResult, setExpandedStepResult] = useState<number | null>(null);

  const [logTail, setLogTail] = useState<string>("");
  const [tailSize, setTailSize] = useState<number>(200);
  const [hideFfmpeg, setHideFfmpeg] = useState<boolean>(true);
  const [searchLog, setSearchLog] = useState<string>("");
  const [onlyErrors, setOnlyErrors] = useState<boolean>(false);
  const [showTechnical, setShowTechnical] = useState<boolean>(false);

  const fetchData = async () => {
    if (!taskId) return;
    setLoading(true);
    setError(null);
    setErrorStatus(null);
    try {
      const res = await fetch(`${API_BASE}/api/publish-tasks/${taskId}/ui`);
      if (!res.ok) {
        setErrorStatus(res.status);
        const text = await res.text();
        throw new Error(res.status === 404 ? "Задача не найдена" : `Ошибка ${res.status}: ${text || "Неизвестно"}`);
      }
      const json: UiResponse = await res.json();
      setData(json);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка загрузки");
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  const loadLog = async (tail: number) => {
    if (!taskId) return;
    try {
      const res = await fetch(`${API_BASE}/api/publish-tasks/${taskId}/log?tail=${tail}`);
      if (res.ok) {
        const json = await res.json();
        setLogTail(json.tail || "");
      } else {
        setLogTail("");
      }
    } catch {
      setLogTail("");
    }
  };

  const loadMetrics = async () => {
    if (!taskId) return;
    try {
      const res = await fetch(`${API_BASE}/api/publish-tasks/${taskId}/metrics`);
      if (res.ok) setMetrics(await res.json());
    } catch { /* ignore */ }
  };

  useEffect(() => {
    fetchData();
    loadLog(tailSize);
    loadMetrics();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId]);

  useEffect(() => {
    loadLog(tailSize);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tailSize]);

  const parsedLogLines = useMemo(() => {
    const lines = (logTail || "").split("\n");
    const filteredFfmpeg = hideFfmpeg
      ? lines.filter((line) => !FILTERED_PATTERNS.some((p) => line.trim().startsWith(p) || line.includes(p)))
      : lines;
    const query = searchLog.trim().toLowerCase();
    let res = query ? filteredFfmpeg.filter((line) => line.toLowerCase().includes(query)) : filteredFfmpeg;
    if (onlyErrors) {
      res = res.filter((line) => {
        const lower = line.toLowerCase();
        return lower.includes("error") || lower.includes("failed") || lower.includes("exception");
      });
    }
    return res;
  }, [logTail, hideFfmpeg, searchLog, onlyErrors]);

  const parsedLog = parsedLogLines.join("\n");

  const statusPalette: Record<string, { bg: string; fg: string }> = {
    neutral: { bg: "#e2e8f0", fg: "#0f172a" },
    primary: { bg: "#dbeafe", fg: "#1d4ed8" },
    warning: { bg: "#fef3c7", fg: "#92400e" },
    success: { bg: "#dcfce7", fg: "#166534" },
    destructive: { bg: "#fee2e2", fg: "#991b1b" },
  };

  const renderStatusChip = (status: string, label?: string) => {
    const variant = statusBadgeVariant(status);
    const map = statusPalette[variant] || statusPalette.neutral;
    return (
      <span
        style={{
          background: map.bg,
          color: map.fg,
          padding: "4px 10px",
          borderRadius: 999,
          fontSize: 12,
          fontWeight: 600,
        }}
      >
        {label || statusLabel(status)}
      </span>
    );
  };

  const renderFileButtons = (item: UiFileItem) => {
    if (!item.url || !item.available) return <span style={{ color: "#94a3b8" }}>Недоступно</span>;
    return (
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <a style={{ padding: "6px 14px", borderRadius: 6, border: "1px solid var(--border-primary)", background: "transparent", color: "var(--text-primary)", fontSize: 13, textDecoration: "none" }} href={item.url} target="_blank" rel="noreferrer">
          Открыть
        </a>
        <a style={{ padding: "6px 14px", borderRadius: 6, border: "1px solid var(--border-primary)", background: "transparent", color: "var(--text-primary)", fontSize: 13, textDecoration: "none" }} href={item.url} target="_blank" rel="noreferrer" download>
          Скачать
        </a>
        <button
          style={{ padding: "6px 14px", borderRadius: 6, border: "1px solid var(--border-primary)", background: "transparent", color: "var(--text-primary)", fontSize: 13, cursor: "pointer" }}
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(item.url || "");
            } catch {
              // ignore
            }
          }}
        >
          Копировать ссылку
        </button>
      </div>
    );
  };

  const renderResultCard = (title: string, item: UiResultBlock, placeholder: string) => {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>{title}</div>
        <div
          style={{
            border: "1px solid #e2e8f0",
            borderRadius: 12,
            padding: 8,
            background: "#f8fafc",
            aspectRatio: "9 / 16",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            maxHeight: 420,
          }}
        >
          {item && item.url ? (
            item.title.toLowerCase().includes("миниатюра") ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={item.url} alt={item.title} style={{ width: "100%", height: "100%", objectFit: "contain", borderRadius: 10 }} />
            ) : (
              <video controls style={{ width: "100%", height: "100%", objectFit: "contain", borderRadius: 10, maxHeight: 400 }} src={item.url} />
            )
          ) : (
            <div style={{ padding: 12, color: "#64748b" }}>{placeholder}</div>
          )}
        </div>
      </div>
    );
  };

  const renderStepOutputs = (outputs?: UiFileItem[] | null) => {
    if (!outputs || !outputs.length) return <span style={{ color: "#94a3b8" }}>Нет выходных файлов</span>;
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {outputs.map((o, idx) => (
          <div key={idx} style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontWeight: 600 }}>{o.title}</span>
            {o.url ? (
              <>
                <a style={{ padding: "6px 14px", borderRadius: 6, border: "1px solid var(--border-primary)", background: "transparent", color: "var(--text-primary)", fontSize: 13, textDecoration: "none" }} href={o.url} target="_blank" rel="noreferrer">
                  Открыть
                </a>
                <a style={{ padding: "6px 14px", borderRadius: 6, border: "1px solid var(--border-primary)", background: "transparent", color: "var(--text-primary)", fontSize: 13, textDecoration: "none" }} href={o.url} target="_blank" rel="noreferrer" download>
                  Скачать
                </a>
              </>
            ) : (
              <span style={{ color: "#94a3b8" }}>Нет ссылки</span>
            )}
          </div>
        ))}
      </div>
    );
  };

  const statusBanner = () => {
    if (!data) return null;
    const hasFinal = data.result.final?.available;
    const hasReady = data.result.ready?.available;
    if (data.task.status === "error") return <div style={{ color: "#991b1b" }}>Ошибка обработки ❌</div>;
    if (hasFinal) return <div style={{ color: "#166534" }}>Итог сформирован ✅</div>;
    if (hasReady) return <div style={{ color: "#92400e" }}>Сформирован черновик (без итога) 🟡</div>;
    return <div style={{ color: "#991b1b" }}>Видео не собрано ❌</div>;
  };

  const handleProcess = async () => {
    if (!taskId) return;
    setActionError(null);
    const res = await fetch(`${API_BASE}/api/publish-tasks/${taskId}/process`, { method: "POST" });
    if (!res.ok) {
      setActionError("Не удалось запустить обработку");
      return;
    }
    await fetchData();
    await loadLog(tailSize);
  };

  const handleProcessV2 = async () => {
    if (!taskId) return;
    setActionError(null);
    const res = await fetch(`${API_BASE}/api/publish-tasks/${taskId}/process-v2`, { method: "POST" });
    if (!res.ok) {
      setActionError("Не удалось запустить Process v2");
      return;
    }
    await fetchData();
    await loadLog(tailSize);
  };

  const handleEnqueue = async () => {
    if (!taskId) return;
    setActionError(null);
    const res = await fetch(`${API_BASE}/api/publish-tasks/${taskId}/enqueue`, { method: "POST" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Ошибка" }));
      setActionError(typeof err.detail === "string" ? err.detail : "Не удалось отправить в очередь");
      return;
    }
    await fetchData();
  };

  const handlePause = async () => {
    if (!taskId) return;
    setActionError(null);
    const res = await fetch(`${API_BASE}/api/publish-tasks/${taskId}/pause`, { method: "POST" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Ошибка" }));
      setActionError(typeof err.detail === "string" ? err.detail : "Не удалось поставить на паузу");
      return;
    }
    await fetchData();
  };

  const handleResume = async () => {
    if (!taskId) return;
    setActionError(null);
    const res = await fetch(`${API_BASE}/api/publish-tasks/${taskId}/resume`, { method: "POST" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Ошибка" }));
      setActionError(typeof err.detail === "string" ? err.detail : "Не удалось возобновить");
      return;
    }
    await fetchData();
  };

  const handleCancel = async () => {
    if (!taskId) return;
    if (!confirm("Отменить задачу? Это действие нельзя отменить.")) return;
    setActionError(null);
    const res = await fetch(`${API_BASE}/api/publish-tasks/${taskId}/cancel`, { method: "POST" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Ошибка" }));
      setActionError(typeof err.detail === "string" ? err.detail : "Не удалось отменить");
      return;
    }
    await fetchData();
  };

  const [readyChecks, setReadyChecks] = useState<{check:string;ok:boolean;detail:string}[] | null>(null);

  const handleMarkReadyForPublish = async () => {
    if (!taskId) return;
    setActionError(null);
    setReadyChecks(null);
    const res = await fetch(`${API_BASE}/api/publish-tasks/${taskId}/mark-ready-for-publish`, { method: "POST" });
    if (res.ok) {
      const j = await res.json();
      setReadyChecks(j.checks || null);
      await fetchData();
    } else {
      const err = await res.json().catch(() => ({ detail: "Ошибка" }));
      if (err.detail?.checks) {
        setReadyChecks(err.detail.checks);
        setActionError("Задача не готова к публикации — см. чек-лист ниже");
      } else {
        setActionError(typeof err.detail === "string" ? err.detail : "Не удалось перевести в ready_for_publish");
      }
    }
  };

  const handleRetryPublish = async (force = false) => {
    if (!taskId) return;
    setActionError(null);
    const qs = force ? "?force=true" : "";
    const res = await fetch(`${API_BASE}/api/publish-tasks/${taskId}/retry-publish${qs}`, { method: "POST" });
    if (res.status === 409) {
      // Already published — ask user to confirm force
      if (confirm("Задача уже опубликована. Переопубликовать принудительно (force)?")) {
        return handleRetryPublish(true);
      }
      return;
    }
    if (!res.ok) {
      const text = await res.text();
      setActionError(`Retry publish: ${text}`);
      return;
    }
    await fetchData();
    await loadMetrics();
  };

  const handleStatusUpdate = async (status: string, reason?: string) => {
    if (!taskId) return;
    setActionError(null);
    const res = await fetch(`${API_BASE}/api/publish-tasks/${taskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, error_text: reason ?? null }),
    });
    if (!res.ok) {
      setActionError("Не удалось обновить статус");
      return;
    }
    await fetchData();
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-primary)", padding: "24px" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 1200, margin: "0 auto" }}>
        <div style={{ background: "var(--bg-secondary)", borderRadius: 12, border: "1px solid var(--border-primary)", padding: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>
                Задача #{taskId}
              </h1>
              {data && renderStatusChip(data.task.status, data.task.status_label)}
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button style={{ padding: "8px 16px", borderRadius: 8, border: "1px solid var(--border-primary)", background: "transparent", color: "var(--text-primary)", cursor: "pointer" }} onClick={() => router.push("/queue")}>
                Назад
              </button>
              <button style={{ padding: "8px 16px", borderRadius: 8, border: "none", background: "#f59e0b", color: "#fff", fontWeight: 600, cursor: "pointer" }} onClick={handleEnqueue} disabled={!(data?.actions?.can_process_v2 ?? true)}>
                ⚡ Enqueue
              </button>
              <button style={{ padding: "8px 16px", borderRadius: 8, border: "none", background: "var(--accent)", color: "#fff", fontWeight: 600, cursor: "pointer" }} onClick={handleProcess} disabled={!(data?.actions?.can_process ?? true)}>
                Обработать
              </button>
              <button style={{ padding: "8px 16px", borderRadius: 8, border: "none", background: "#7c3aed", color: "#fff", fontWeight: 600, cursor: "pointer" }} onClick={handleProcessV2} disabled={!(data?.actions?.can_process_v2 ?? true)}>
                Process v2
              </button>
              <button
                style={{ padding: "8px 16px", borderRadius: 8, border: "none", background: "#0ea5e9", color: "#fff", fontWeight: 600, cursor: "pointer", opacity: data?.actions?.can_retry_publish ? 1 : 0.4 }}
                onClick={() => handleRetryPublish()}
                disabled={!(data?.actions?.can_retry_publish ?? false)}
              >
                Retry Publish
              </button>
              <button
                style={{ padding: "8px 16px", borderRadius: 8, border: "none", background: "#d1fae5", color: "#065f46", cursor: "pointer" }}
                onClick={() => handleStatusUpdate("done")}
                disabled={!(data?.actions?.can_mark_done ?? true)}
              >
                Готово
              </button>
              <button
                style={{ padding: "8px 16px", borderRadius: 8, border: "none", background: "#fee2e2", color: "#991b1b", cursor: "pointer" }}
                onClick={() => handleStatusUpdate("error", "Ошибка оператора")}
                disabled={!(data?.actions?.can_mark_error ?? true)}
              >
                Ошибка
              </button>
              {/* Task control: Pause / Resume / Cancel */}
              {data && data.task.status !== "published" && data.task.status !== "canceled" && data.task.status !== "paused" && (
                <button
                  style={{ padding: "8px 16px", borderRadius: 8, border: "none", background: "#fef3c7", color: "#92400e", fontWeight: 600, cursor: "pointer" }}
                  onClick={handlePause}
                >
                  ⏸ Пауза
                </button>
              )}
              {data && data.task.status === "paused" && (
                <button
                  style={{ padding: "8px 16px", borderRadius: 8, border: "none", background: "#dbeafe", color: "#1e40af", fontWeight: 600, cursor: "pointer" }}
                  onClick={handleResume}
                >
                  ▶ Возобновить
                </button>
              )}
              {data && data.task.status !== "published" && data.task.status !== "canceled" && (
                <button
                  style={{ padding: "8px 16px", borderRadius: 8, border: "none", background: "#991b1b", color: "#fff", fontWeight: 600, cursor: "pointer" }}
                  onClick={handleCancel}
                >
                  ✕ Отмена
                </button>
              )}
              {data && (data.task.status === "done" || data.task.status === "ready_for_review") && (
                <button
                  style={{ padding: "8px 16px", borderRadius: 8, border: "none", background: "#0ea5e9", color: "#fff", fontWeight: 600, cursor: "pointer" }}
                  onClick={handleMarkReadyForPublish}
                >
                  🚀 Ready for Publish
                </button>
              )}
            </div>
          </div>
          {actionError && <div style={{ color: "var(--error)", marginTop: 8 }}>{actionError}</div>}
          {/* Чек-лист готовности к публикации */}
          {readyChecks && (
            <div style={{ marginTop: 8, padding: "10px 14px", background: "#f8fafc", borderRadius: 8, border: "1px solid #e2e8f0" }}>
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>Чек-лист публикации:</div>
              {readyChecks.map((c, i) => (
                <div key={i} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, padding: "3px 0" }}>
                  <span style={{ fontSize: 14 }}>{c.ok ? "✅" : "❌"}</span>
                  <span style={{ fontWeight: 600, minWidth: 120 }}>{c.check}</span>
                  <span style={{ color: c.ok ? "#166534" : "#991b1b" }}>{c.detail}</span>
                </div>
              ))}
            </div>
          )}
          {data && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 8, color: "#475569", fontSize: 14 }}>
              <div>
                Проект #{data.task.project_id} · Платформа: {data.task.platform_label || data.task.platform} · Получатель: acct{" "}
                {data.task.project_id} · Preset: {data.task.preset_name || data.task.preset_id || "—"}
              </div>
              <div>External ID: {data.task.external_id}</div>
              {data.task.permalink && (
                <div>
                  Оригинал:{" "}
                  <a style={{ color: "var(--accent)", textDecoration: "underline" }} href={data.task.permalink} target="_blank" rel="noreferrer">
                    открыть
                  </a>
                </div>
              )}
              {data.task.status === "error" && data.task.status_label && <div style={{ color: "var(--error)" }}>{data.task.status_label}</div>}
              {(data as any).celery_task_id && (
                <div style={{ fontSize: 12, color: "#94a3b8" }}>
                  Celery ID: <code style={{ background: "#f1f5f9", padding: "1px 6px", borderRadius: 4, fontSize: 11 }}>{(data as any).celery_task_id}</code>
                </div>
              )}
            </div>
          )}
          {loading && <div style={{ color: "var(--text-tertiary)", marginTop: 8 }}>Загрузка...</div>}
          {error && (
            <div style={{ color: "var(--error)", marginTop: 8 }}>
              {error}
              {errorStatus && errorStatus !== 404 ? ` (status ${errorStatus})` : ""}
            </div>
          )}
          {!loading && !data && (
            <div style={{ marginTop: 8 }}>
              <div style={{ color: "var(--text-tertiary)", textAlign: "center", padding: 20 }}>Задача не найдена</div>
              <button style={{ marginTop: 8, padding: "8px 16px", borderRadius: 8, border: "1px solid var(--border-primary)", background: "transparent", color: "var(--text-primary)", cursor: "pointer" }} onClick={() => router.push("/queue")}>
                Назад к очереди
              </button>
            </div>
          )}
        </div>

        {data && (
          <>
            {/* Результат */}
            <div style={{ background: "var(--bg-secondary)", borderRadius: 12, border: "1px solid var(--border-primary)", padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
              {statusBanner()}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
                  gap: 16,
                }}
              >
                {renderResultCard("Превью", data.result.preview, "Нет превью")}
                {renderResultCard(data.result.final.available ? "Итог" : data.result.ready.available ? "Готовое" : "Видео", data.result.final.available ? data.result.final : data.result.ready.available ? data.result.ready : data.result.raw, "Нет видео")}
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {data.result.final.available && data.result.final.url && (
                  <>
                    <a style={{ padding: "10px 20px", borderRadius: 8, border: "none", background: "var(--accent)", color: "#fff", fontWeight: 600, textDecoration: "none" }} href={data.result.final.url} target="_blank" rel="noreferrer">
                      Открыть итог
                    </a>
                    <a style={{ padding: "8px 16px", borderRadius: 8, border: "1px solid var(--border-primary)", background: "transparent", color: "var(--text-primary)", textDecoration: "none" }} href={data.result.final.url} target="_blank" rel="noreferrer" download>
                      Скачать итог
                    </a>
                  </>
                )}
                {!data.result.final.available && data.result.ready.available && data.result.ready.url && (
                  <>
                    <a style={{ padding: "10px 20px", borderRadius: 8, border: "none", background: "var(--accent)", color: "#fff", fontWeight: 600, textDecoration: "none" }} href={data.result.ready.url} target="_blank" rel="noreferrer">
                      Открыть черновик
                    </a>
                    <a style={{ padding: "8px 16px", borderRadius: 8, border: "1px solid var(--border-primary)", background: "transparent", color: "var(--text-primary)", textDecoration: "none" }} href={data.result.ready.url} target="_blank" rel="noreferrer" download>
                      Скачать черновик
                    </a>
                  </>
                )}
                {data.result.raw.available && data.result.raw.url && (
                  <a style={{ padding: "8px 16px", borderRadius: 8, border: "1px solid var(--border-primary)", background: "transparent", color: "var(--text-primary)", textDecoration: "none" }} href={data.result.raw.url} target="_blank" rel="noreferrer" download>
                    Скачать исходник
                  </a>
                )}
              </div>
            </div>

            {/* Publish Info + Candidate */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              {/* Publish Status */}
              <div style={{ background: "var(--bg-secondary)", borderRadius: 12, border: "1px solid var(--border-primary)", padding: 16 }}>
                <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Публикация</div>
                {data.publish.published_url ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ background: "#dcfce7", color: "#166534", padding: "2px 10px", borderRadius: 20, fontSize: 12, fontWeight: 600 }}>Опубликовано</span>
                      {data.publish.published_at && (
                        <span style={{ fontSize: 12, color: "#64748b" }}>{new Date(data.publish.published_at).toLocaleString("ru")}</span>
                      )}
                    </div>
                    <a href={data.publish.published_url} target="_blank" rel="noreferrer" style={{ color: "#2563eb", fontSize: 13, textDecoration: "underline", wordBreak: "break-all" }}>
                      {data.publish.published_url}
                    </a>
                    {data.publish.published_external_id && (
                      <div style={{ fontSize: 12, color: "#64748b" }}>External ID: {data.publish.published_external_id}</div>
                    )}
                    {data.publish.last_metrics_json && (
                      <div style={{ display: "flex", gap: 12, marginTop: 4, fontSize: 12 }}>
                        {Object.entries(data.publish.last_metrics_json).map(([k, v]) => (
                          <span key={k}><strong>{k}:</strong> {typeof v === "number" ? v.toLocaleString() : String(v)}</span>
                        ))}
                      </div>
                    )}
                  </div>
                ) : data.publish.publish_error ? (
                  <div>
                    <span style={{ background: "#fee2e2", color: "#991b1b", padding: "2px 10px", borderRadius: 20, fontSize: 12, fontWeight: 600 }}>Ошибка</span>
                    <div style={{ marginTop: 6, fontSize: 13, color: "#991b1b", background: "#fee2e2", padding: 8, borderRadius: 8 }}>
                      {data.publish.publish_error}
                    </div>
                  </div>
                ) : (
                  <div style={{ color: "#94a3b8", fontSize: 13 }}>Не опубликовано</div>
                )}
              </div>

              {/* Candidate Info */}
              <div style={{ background: "var(--bg-secondary)", borderRadius: 12, border: "1px solid var(--border-primary)", padding: 16 }}>
                <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Кандидат</div>
                {data.candidate ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 13 }}>
                    <div style={{ fontWeight: 600 }}>{data.candidate.title || `#${data.candidate.id}`}</div>
                    <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                      <span style={{ padding: "2px 8px", borderRadius: 10, background: "#dbeafe", color: "#1d4ed8", fontSize: 11, fontWeight: 600 }}>{data.candidate.platform}</span>
                      <span style={{ padding: "2px 8px", borderRadius: 10, background: "#f3e8ff", color: "#7c3aed", fontSize: 11, fontWeight: 600 }}>{data.candidate.origin}</span>
                      {data.candidate.virality_score != null && (
                        <span style={{ padding: "2px 8px", borderRadius: 10, background: "#fef3c7", color: "#92400e", fontSize: 11, fontWeight: 600 }}>
                          Score: {data.candidate.virality_score.toFixed(1)}
                        </span>
                      )}
                    </div>
                    {data.candidate.author && <div style={{ color: "#64748b" }}>Автор: {data.candidate.author}</div>}
                    {data.candidate.url && (
                      <a href={data.candidate.url} target="_blank" rel="noreferrer" style={{ color: "#2563eb", fontSize: 12, textDecoration: "underline" }}>
                        Оригинал
                      </a>
                    )}
                    <div style={{ display: "flex", gap: 12, color: "#64748b", fontSize: 12 }}>
                      {data.candidate.views != null && <span>Views: {data.candidate.views.toLocaleString()}</span>}
                      {data.candidate.likes != null && <span>Likes: {data.candidate.likes.toLocaleString()}</span>}
                      {data.candidate.comments != null && <span>Comments: {data.candidate.comments.toLocaleString()}</span>}
                    </div>
                    {data.candidate.virality_factors && (
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 4 }}>
                        {Object.entries(data.candidate.virality_factors).filter(([k]) => ["velocity", "engagement", "recency", "sub_ratio"].includes(k)).map(([k, v]) => (
                          <div key={k} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11 }}>
                            <span style={{ color: "#64748b" }}>{k}:</span>
                            <div style={{ width: 40, height: 4, background: "#e2e8f0", borderRadius: 2 }}>
                              <div style={{ width: `${Math.min(100, (v as number))}%`, height: "100%", background: (v as number) > 50 ? "#22c55e" : "#eab308", borderRadius: 2 }} />
                            </div>
                            <span style={{ fontWeight: 600 }}>{(v as number).toFixed(0)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <div style={{ color: "#94a3b8", fontSize: 13 }}>Нет связанного кандидата</div>
                )}
              </div>
            </div>

            {/* Metrics */}
            {metrics.length > 0 && (
              <div style={{ background: "var(--bg-secondary)", borderRadius: 12, border: "1px solid var(--border-primary)", padding: 16 }}>
                <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Метрики ({metrics.length} снимков)</div>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                    <thead>
                      <tr style={{ borderBottom: "2px solid #e2e8f0", textAlign: "left" }}>
                        <th style={{ padding: "6px 8px", fontWeight: 600 }}>Время</th>
                        <th style={{ padding: "6px 8px", fontWeight: 600, textAlign: "right" }}>Часы</th>
                        <th style={{ padding: "6px 8px", fontWeight: 600, textAlign: "right" }}>Views</th>
                        <th style={{ padding: "6px 8px", fontWeight: 600, textAlign: "right" }}>Likes</th>
                        <th style={{ padding: "6px 8px", fontWeight: 600, textAlign: "right" }}>Comments</th>
                        <th style={{ padding: "6px 8px", fontWeight: 600, textAlign: "right" }}>Shares</th>
                      </tr>
                    </thead>
                    <tbody>
                      {metrics.map((m, i) => {
                        const prev = i > 0 ? metrics[i - 1] : null;
                        const delta = prev ? m.views - prev.views : 0;
                        return (
                          <tr key={m.id} style={{ borderBottom: "1px solid #f1f5f9" }}>
                            <td style={{ padding: "6px 8px", color: "#64748b" }}>{new Date(m.snapshot_at).toLocaleString("ru", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</td>
                            <td style={{ padding: "6px 8px", textAlign: "right", color: "#64748b" }}>{m.hours_since_publish != null ? `${m.hours_since_publish.toFixed(0)}h` : "—"}</td>
                            <td style={{ padding: "6px 8px", textAlign: "right", fontWeight: 600 }}>
                              {m.views.toLocaleString()}
                              {delta > 0 && <span style={{ color: "#22c55e", fontSize: 11, marginLeft: 4 }}>+{delta.toLocaleString()}</span>}
                            </td>
                            <td style={{ padding: "6px 8px", textAlign: "right" }}>{m.likes.toLocaleString()}</td>
                            <td style={{ padding: "6px 8px", textAlign: "right" }}>{m.comments.toLocaleString()}</td>
                            <td style={{ padding: "6px 8px", textAlign: "right" }}>{m.shares != null ? m.shares.toLocaleString() : "—"}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Step Results (DB-based, collapsible) */}
            {data.step_results && data.step_results.length > 0 && (
              <div style={{ background: "var(--bg-secondary)", borderRadius: 12, border: "1px solid var(--border-primary)", padding: 16 }}>
                <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Step Results (DB)</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {data.step_results.map((sr) => {
                    const isOpen = expandedStepResult === sr.id;
                    const color = sr.status === "completed" || sr.status === "ok" ? "#16a34a" : sr.status === "error" ? "#dc2626" : sr.status === "running" ? "#2563eb" : "#94a3b8";
                    return (
                      <div key={sr.id} style={{ border: "1px solid #e2e8f0", borderRadius: 8 }}>
                        <div
                          onClick={() => setExpandedStepResult(isOpen ? null : sr.id)}
                          style={{ padding: "8px 12px", cursor: "pointer", display: "grid", gridTemplateColumns: "32px 120px 1fr 80px 60px", alignItems: "center", gap: 8, fontSize: 13 }}
                        >
                          <span style={{ color: "#94a3b8" }}>{sr.step_index}</span>
                          <span style={{ color, fontWeight: 600 }}>{sr.status}</span>
                          <span style={{ fontWeight: 500 }}>{sr.step_name || sr.tool_id}</span>
                          <span style={{ color: "#64748b", textAlign: "right" }}>{sr.duration_ms != null ? `${(sr.duration_ms / 1000).toFixed(1)}s` : "—"}</span>
                          <span style={{ color: "#94a3b8", textAlign: "right" }}>{isOpen ? "▲" : "▼"}</span>
                        </div>
                        {isOpen && (
                          <div style={{ padding: "0 12px 12px", display: "flex", flexDirection: "column", gap: 6, fontSize: 12 }}>
                            {sr.error_message && (
                              <div style={{ background: "#fee2e2", color: "#991b1b", padding: 8, borderRadius: 6 }}>{sr.error_message}</div>
                            )}
                            {sr.output_data && Object.keys(sr.output_data).length > 0 && (
                              <div>
                                <div style={{ fontWeight: 600, marginBottom: 4 }}>Output Data:</div>
                                <pre style={{ background: "#f1f5f9", padding: 8, borderRadius: 6, overflow: "auto", maxHeight: 200, fontSize: 11 }}>
                                  {JSON.stringify(sr.output_data, null, 2)}
                                </pre>
                              </div>
                            )}
                            {sr.logs && (
                              <div>
                                <div style={{ fontWeight: 600, marginBottom: 4 }}>Logs:</div>
                                <pre style={{ background: "#0f172a", color: "#e2e8f0", padding: 8, borderRadius: 6, overflow: "auto", maxHeight: 200, fontSize: 11, whiteSpace: "pre-wrap" }}>
                                  {sr.logs}
                                </pre>
                              </div>
                            )}
                            <div style={{ display: "flex", gap: 12, color: "#64748b" }}>
                              <span>v{sr.version}</span>
                              {sr.retry_count > 0 && <span>Retries: {sr.retry_count}</span>}
                              <span>Moderation: {sr.moderation_status}</span>
                              {sr.started_at && <span>Start: {new Date(sr.started_at).toLocaleTimeString("ru")}</span>}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Шаги (pipeline) */}
            <div style={{ background: "var(--bg-secondary)", borderRadius: 12, border: "1px solid var(--border-primary)", padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ display: "flex", gap: 12, fontSize: 14, color: "#475569", flexWrap: "wrap" }}>
                <span>Всего: {data.pipeline.summary.total}</span>
                <span style={{ color: "#16a34a" }}>Выполнено: {data.pipeline.summary.done}</span>
                <span style={{ color: "#94a3b8" }}>Пропущено: {data.pipeline.summary.skipped}</span>
                <span style={{ color: "#dc2626" }}>Ошибок: {data.pipeline.summary.error}</span>
                <span style={{ color: "#0f172a" }}>
                  Время:{" "}
                  {data.pipeline.summary.duration_sec && data.pipeline.summary.duration_sec > 0
                    ? `${data.pipeline.summary.duration_sec.toFixed(1)} с`
                    : "—"}
                </span>
              </div>
              {data.pipeline.steps && data.pipeline.steps.length ? (
                data.pipeline.steps.map((s) => {
                  const color =
                    s.status === "ok" ? "#16a34a" : s.status === "error" ? "#dc2626" : s.status === "processing" ? "#2563eb" : "#94a3b8";
                  return (
                    <div key={s.id} style={{ border: "1px solid #e2e8f0", borderRadius: 10 }}>
                      <div
                        style={{
                          width: "100%",
                          textAlign: "left",
                          padding: "10px 12px",
                          display: "grid",
                          gridTemplateColumns: "120px 1fr 120px",
                          gap: 8,
                          alignItems: "center",
                        }}
                      >
                        <span style={{ color, fontWeight: 600 }}>{s.status_label}</span>
                        <div>
                          <div style={{ fontWeight: 700 }}>{s.title}</div>
                          <div style={{ color: "#94a3b8", fontSize: 12 }}>Инструмент: {s.id}</div>
                          {s.description && <div style={{ color: "#64748b", fontSize: 12 }}>{s.description}</div>}
                        </div>
                        <span style={{ color: "#0f172a" }}>{s.duration_sec ? `${s.duration_sec.toFixed(1)} с` : "—"}</span>
                      </div>
                      <div style={{ padding: "0 12px 12px 12px", display: "flex", flexDirection: "column", gap: 8 }}>
                        {s.outputs && s.outputs.length > 0 && (
                          <div>
                            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", marginBottom: 4 }}>
                              Файлы
                            </div>
                            {renderStepOutputs(s.outputs)}
                          </div>
                        )}
                        {s.error_message && (
                          <div style={{ background: "#fee2e2", color: "#991b1b", padding: 8, borderRadius: 8 }}>Причина: {s.error_message}</div>
                        )}
                        {s.status === "skipped" && !s.error_message && (
                          <div style={{ color: "#94a3b8" }}>Шаг пропущен или выключен</div>
                        )}
                      </div>
                    </div>
                  );
                })
              ) : (
                <div style={{ color: "var(--text-tertiary)", textAlign: "center", padding: 20 }}>Данных о шагах нет</div>
              )}
            </div>

            {/* Файлы */}
            <div style={{ background: "var(--bg-secondary)", borderRadius: 12, border: "1px solid var(--border-primary)", padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ fontSize: 16, fontWeight: 600, color: "var(--text-primary)" }}>Файлы задачи</div>
              {["video", "preview", "subtitles", "technical"].map((key) => {
                const list = (data.files as Record<string, UiFileItem[]>)[key] || [];
                const visible = list.filter((i) => i.available || i.url);
                if (!visible.length) return null;
                const titleMap: Record<string, string> = {
                  video: "Главное",
                  preview: "Превью и миниатюры",
                  subtitles: "Субтитры",
                  technical: "Техническое",
                };
                return (
                  <div key={key} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>{titleMap[key] || key}</div>
                    {visible.map((item, idx) => (
                      <div
                        key={`${key}-${idx}`}
                        style={{
                          display: "grid",
                          gridTemplateColumns: "1fr auto",
                          alignItems: "center",
                          padding: "6px 0",
                          borderBottom: "1px solid #e2e8f0",
                          gap: 8,
                        }}
                      >
                        <div>
                          <div style={{ fontWeight: 700 }}>{item.title || artifactLabel(item.file || "")}</div>
                          {item.file && <div style={{ color: "#94a3b8", fontSize: 12 }}>файл: {item.file}</div>}
                        </div>
                        {renderFileButtons(item)}
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>

            {/* Техническое (логи) */}
            <div style={{ background: "var(--bg-secondary)", borderRadius: 12, border: "1px solid var(--border-primary)", padding: 16, display: "flex", flexDirection: "column", gap: 8 }}>
              <button
                style={{ padding: "8px 16px", borderRadius: 8, border: "1px solid var(--border-primary)", background: "transparent", color: "var(--text-primary)", cursor: "pointer", width: "fit-content" }}
                onClick={() => setShowTechnical((prev) => !prev)}
              >
                {showTechnical ? "Скрыть техническое" : "Показать техническое"}
              </button>
              {showTechnical && (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                    <label style={{ display: "flex", gap: 6, alignItems: "center", color: "var(--text-secondary)" }}>
                      Хвост:
                      <select value={tailSize} onChange={(e) => setTailSize(Number(e.target.value))} style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid var(--border-primary)", background: "var(--bg-tertiary)", color: "var(--text-primary)" }}>
                        {[200, 500, 2000].map((v) => (
                          <option key={v} value={v}>
                            {v}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label style={{ display: "flex", gap: 6, alignItems: "center", color: "var(--text-secondary)" }}>
                      <input type="checkbox" checked={hideFfmpeg} onChange={(e) => setHideFfmpeg(e.target.checked)} /> Скрыть шум ffmpeg
                    </label>
                    <label style={{ display: "flex", gap: 6, alignItems: "center", color: "var(--text-secondary)" }}>
                      Поиск:
                      <input
                        style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid var(--border-primary)", background: "var(--bg-tertiary)", color: "var(--text-primary)", width: 180 }}
                        value={searchLog}
                        onChange={(e) => setSearchLog(e.target.value)}
                        placeholder="строка или слово"
                      />
                    </label>
                    <label style={{ display: "flex", gap: 6, alignItems: "center", color: "var(--text-secondary)" }}>
                      <input type="checkbox" checked={onlyErrors} onChange={(e) => setOnlyErrors(e.target.checked)} /> Только ошибки
                    </label>
                    <button style={{ padding: "8px 16px", borderRadius: 8, border: "1px solid var(--border-primary)", background: "transparent", color: "var(--text-primary)", cursor: "pointer" }} onClick={() => loadLog(tailSize)}>
                      Обновить
                    </button>
                    <button
                      style={{ padding: "8px 16px", borderRadius: 8, border: "1px solid var(--border-primary)", background: "transparent", color: "var(--text-primary)", cursor: "pointer" }}
                      onClick={async () => {
                        try {
                          await navigator.clipboard.writeText(parsedLog || "");
                        } catch {
                          // ignore
                        }
                      }}
                    >
                      Копировать лог
                    </button>
                  </div>
                  <div
                    style={{
                      background: "#0f172a",
                      color: "#e2e8f0",
                      padding: 12,
                      borderRadius: 10,
                      fontSize: 12,
                      maxHeight: 420,
                      overflow: "auto",
                      fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
                    }}
                  >
                    {parsedLogLines.length ? (
                      parsedLogLines.map((line, idx) => {
                        const lower = line.toLowerCase();
                        const isErr = ["error", "failed", "exception"].some((w) => lower.includes(w));
                        const isWarn = ["warning", "deprecated"].some((w) => lower.includes(w));
                        return (
                          <div
                            key={idx}
                            style={{
                              color: isErr ? "#fecdd3" : isWarn ? "#fef3c7" : "#e2e8f0",
                              whiteSpace: "pre-wrap",
                              wordBreak: "break-word",
                            }}
                          >
                            {line}
                          </div>
                        );
                      })
                    ) : (
                      <div>Лог пуст</div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
