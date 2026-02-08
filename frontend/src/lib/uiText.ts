export const STATUS_LABELS: Record<string, string> = {
  queued: "В очереди",
  processing: "В обработке",
  ready_for_review: "На проверке",
  done: "Готово",
  completed: "Готово",
  error: "Ошибка",
};

export type BadgeVariant = "neutral" | "primary" | "warning" | "success" | "destructive";

export const statusLabel = (value?: string | null): string => {
  if (!value) return "Неизвестно";
  return STATUS_LABELS[value] ?? "Неизвестно";
};

export const statusBadgeVariant = (value?: string | null): BadgeVariant => {
  switch (value) {
    case "queued":
      return "neutral";
    case "processing":
      return "primary";
    case "ready_for_review":
      return "warning";
    case "done":
    case "completed":
      return "success";
    case "error":
      return "destructive";
    default:
      return "neutral";
  }
};

export const stepStatusLabel = (value?: string | null): string => {
  switch (value) {
    case "ok":
      return "Выполнено";
    case "skipped":
      return "Пропущено";
    case "processing":
      return "В обработке";
    case "error":
      return "Ошибка";
    default:
      return "—";
  }
};

const TOOL_LABELS: Record<string, string> = {
  T04_CROP_RESIZE: "Обрезка/Resize",
  T14_BURN_CAPTIONS: "Вшить субтитры",
  T02_PROBE_MEDIA: "Проверка медиа",
  T07_EXTRACT_AUDIO: "Извлечение аудио",
};

export const toolLabel = (toolId?: string | null, fallback?: string | null): string => {
  if (!toolId) return fallback || "Без названия";
  if (TOOL_LABELS[toolId]) return TOOL_LABELS[toolId];
  const text = fallback || toolId;
  return text.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
};

export const toFileUrl = (pathOrNull?: string | null): string | null => {
  if (!pathOrNull) return null;
  if (pathOrNull.startsWith("/files/")) return pathOrNull;
  if (pathOrNull.startsWith("/data/tasks/")) {
    const [, , , taskId, filename] = pathOrNull.split("/");
    if (taskId && filename) {
      return `/files/tasks/${taskId}/${filename}`;
    }
  }
  return pathOrNull;
};

export const formatDurationMs = (ms?: number | null): string => {
  if (!ms && ms !== 0) return "—";
  const seconds = ms / 1000;
  return seconds >= 1 ? `${seconds.toFixed(1)} с` : `${ms} мс`;
};

const ARTIFACT_LABELS: Record<string, string> = {
  "final.mp4": "Итоговое видео",
  "ready.mp4": "Готовое видео (до субтитров)",
  "raw.mp4": "Исходник",
  "preview.mp4": "Превью",
  "thumb.jpg": "Миниатюра",
  "captions.srt": "Субтитры (SRT)",
  "probe.json": "Метаданные (JSON)",
  "process.log": "Лог обработки",
};

export const artifactLabel = (filename?: string | null): string => {
  if (!filename) return "Файл";
  if (ARTIFACT_LABELS[filename]) return ARTIFACT_LABELS[filename];
  return filename;
};

export const dataPathToFileUrl = (pathOrNull?: string | null): string | null => {
  return toFileUrl(pathOrNull);
};
