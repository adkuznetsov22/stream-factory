import { useEffect, useState } from "react";
import { AlertTriangle, BellRing, CheckCircle2 } from "lucide-react";
import { ago, api, clock, dur, useApi } from "../api";
import { Badge, Button, Card, CardHeader, Input, PageHeader, Segmented, Stat, useAction } from "../ui";

export default function Health() {
  const h = useApi<any>("/api/health");
  const [level, setLevel] = useState("INFO"); const [q, setQ] = useState("");
  const log = useApi<any[]>(`/api/log?level=${level}&q=${encodeURIComponent(q)}`);
  const { busy, run } = useAction(); const [link, setLink] = useState<any>(null);
  useEffect(() => { const t = setInterval(() => { h.reload(); log.reload(); }, 5000); return () => clearInterval(t); }, [level, q]);
  const d = h.data; if (!d) return null; const l = d.latency;
  return <>
    <PageHeader title="Здоровье" hint="Скорость конвейера, состояние записи, ошибки и алерты." />
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
      <Stat label="Момент → готовый клип" value={l.render_p50 != null ? `${l.render_p50} с` : "—"} sub={l.render_p90 != null ? `90% быстрее ${l.render_p90} с · ${l.count} клипов` : "за 24 ч"} />
      <Stat label="Момент → пост" value={l.post_p50 != null ? `${l.post_p50} с` : "—"} sub={l.post_p90 != null ? `90% быстрее ${l.post_p90} с` : "постов не было"} />
      <Stat label="Очередь рендера" value={d.render_queue} tone={d.render_queue > 5 ? "warn" : undefined} />
      <Stat label="Свободно" value={`${d.disk.free_gb} ГБ`} sub={d.disk.hours_left ? `хватит на ~${d.disk.hours_left} ч` : `из ${d.disk.total_gb} ГБ`} tone={d.disk.free_gb < 15 ? "err" : undefined} />
      <Stat label="Данные сервиса" value={`${d.disk.data_gb} ГБ`} sub="клипы, исходники, буфер" />
    </div>
    <div className="mt-5 grid gap-5 xl:grid-cols-2">
      <Card><CardHeader title="Запись стримов" />
        <div className="divide-y divide-line">{d.recorders.length === 0 ? <div className="p-4 text-sm text-muted">Ничего не пишется.</div> : d.recorders.map((r: any) =>
          <div key={r.login} className="flex items-center gap-3 px-4 py-2.5 text-sm"><span className="w-36 font-medium">{r.login}</span>
            <Badge tone={r.segment_age != null && r.segment_age < 15 ? "ok" : "err"}>{r.segment_age != null ? `видео ${r.segment_age} с назад` : "нет видео"}</Badge>
            <Badge tone={r.chat ? "ok" : "err"}>{r.chat ? "чат подключён" : "чат отключён"}</Badge>
            <span className="flex-1 text-right text-xs text-muted">переподключений {Math.max(r.runs - 1, 0)} · пишется {dur(Date.now() / 1000 - r.since)}</span></div>)}</div></Card>
      <Card><CardHeader title="Алерты в Telegram" hint="Бот пишет в личку: сбой публикации, остановка записи, ошибка рендера, мало места." />
        <div className="space-y-3 p-4 text-sm">
          {d.alerts_chat_id ? <div className="flex items-center gap-2"><CheckCircle2 className="size-4 text-ok" />Привязано к чату {d.alerts_chat_id}
            <Button size="sm" loading={busy === "ta"} onClick={() => run("ta", () => api("/api/alerts/test", { body: {} }), "Тестовый алерт отправлен")}>Отправить тест</Button></div>
            : <div className="text-muted">Не привязано.</div>}
          <Button icon={<BellRing className="size-4" />} loading={busy === "link"} onClick={() => run("link", () => api("/api/alerts/link", { body: {} })).then((x) => x && setLink(x))}>{d.alerts_chat_id ? "Привязать другой чат" : "Привязать мой Telegram"}</Button>
          {link && <div className="rounded-lg bg-bg p-3">Откройте <a className="text-accent" href={link.url} target="_blank">{link.url}</a> и нажмите «Start». Привязка произойдёт сама в течение 10 минут.</div>}
        </div></Card>
    </div>
    <Card className="mt-5"><CardHeader title="Ошибки за 24 часа" />
      {d.errors.length === 0 ? <div className="flex items-center gap-2 p-4 text-sm text-muted"><CheckCircle2 className="size-4 text-ok" />Ошибок нет</div> :
        <div className="divide-y divide-line">{d.errors.map((e: any, i: number) => <div key={i} className="flex gap-3 px-4 py-2.5 text-sm"><AlertTriangle className="mt-0.5 size-4 shrink-0 text-err" />
          <div className="min-w-0 flex-1"><div>{e.kind} · {e.place} <span className="text-muted">×{e.n} · последняя {ago(e.last)}</span></div><div className="text-xs break-words text-muted">{e.error}</div></div></div>)}</div>}</Card>
    <Card className="mt-5"><CardHeader title="Журнал" right={<div className="flex gap-2"><Input className="h-8 w-56 text-xs" placeholder="поиск" value={q} onChange={(e) => setQ(e.target.value)} />
      <Segmented value={level} onChange={setLevel} options={[{ value: "INFO", label: "всё" }, { value: "WARNING", label: "предупреждения" }, { value: "ERROR", label: "ошибки" }]} /></div>} />
      <div className="max-h-[480px] overflow-y-auto font-mono text-xs">{(log.data ?? []).map((r, i) => <div key={i} className="flex gap-3 border-b border-line/50 px-4 py-1.5">
        <span className="shrink-0 text-muted">{clock(r.ts)}</span><span className={r.level === "ERROR" ? "text-err" : r.level === "WARNING" ? "text-warn" : ""}>{r.msg}</span></div>)}</div></Card>
  </>;
}
