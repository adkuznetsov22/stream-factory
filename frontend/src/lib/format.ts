export const formatNumber = (n?: number | null): string => {
  if (n === null || n === undefined) return "—";
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("ru-RU").format(n);
};

export const formatDateTime = (iso?: string | null): string => {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  })
    .format(date)
    .replace(".", "");
};
