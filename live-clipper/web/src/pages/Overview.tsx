import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2, Circle, Clapperboard, HardDrive, Radio, Send, Timer } from "lucide-react";
import { KIND_LABEL, ago, clock, num, useApi } from "../api";
import { useLive } from "../main";
import { Badge, Card, CardHeader, PageHeader, Sparkline, Stat, type Tone } from "../ui";

const STATE_TONE: Record<string, Tone> = { ready: "ok", publishing: "info", off: "muted", paused: "warn", quiet: "muted", limit: "warn", interval: "muted", waiting: "muted", manual: "info" };

export default function Overview() {
  const s = useLive();
  const health = useApi<any>("/api/health");
  if (!s) return null;
  const steps = [
    { done: s.targets.length > 0, text: "Добавить площадку (Telegram, VK или YouTube)", to: "/targets" },
    { done: s.targets.some((t) => t.check_ok === 1), text: "Пройти проверку прав на публикацию", to: "/targets" },
    { done: s.targets.some((t) => t.enabled), text: "Включить площадку и выбрать режим: авто или на одобрении", to: "/targets" },
    { done: s.whitelist.length > 0, text: "Собрать белый список стримеров и выставить вебку", to: "/streamers" },
    { done: s.alerts, text: "Привязать алерты в личку Telegram", to: "/health" },
  ];
  const setupLeft = steps.filter((x) => !x.done).length;
  const lat = health.data?.latency;
  return <>
    <PageHeader title="Обзор" hint="Что происходит прямо сейчас и что требует внимания." />
    {setupLeft > 0 && <Card className="mb-5 border-accent/30">
      <CardHeader title={`Настройка: осталось ${setupLeft} из ${steps.length}`} hint="Без этих шагов сервис режет клипы, но не публикует их." />
      <div className="divide-y divide-line">{steps.map((x) => <Link key={x.text} to={x.to} className="flex items-center gap-3 px-4 py-2.5 text-sm hover:bg-panel2">
        {x.done ? <CheckCircle2 className="size-4 text-ok" /> : <Circle className="size-4 text-muted" />}<span className={x.done ? "text-muted line-through" : ""}>{x.text}</span></Link>)}</div>
    </Card>}
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
      <Stat icon={<Radio className="size-3.5" />} label="Пишется стримов" value={s.channels.length} sub={s.auto_discover ? "авто-поиск включён" : "только белый список"} />
      <Stat icon={<Clapperboard className="size-3.5" />} label="Клипов за 24 ч" value={num(s.day.clips)} sub={`${s.day.duplicates} дублей отсеяно`} />
      <Stat icon={<Clapperboard className="size-3.5" />} label="Ждут решения" value={s.pending_review} tone={s.pending_review ? "warn" : undefined} sub="за 24 ч" />
      <Stat icon={<Send className="size-3.5" />} label="Постов за 24 ч" value={s.day.posts} tone="ok" />
      <Stat icon={<Timer className="size-3.5" />} label="Момент → клип" value={lat?.render_p50 != null ? `${lat.render_p50} с` : "—"} sub={lat?.post_p50 != null ? `→ пост ${lat.post_p50} с (медиана)` : "медиана за 24 ч"} />
      <Stat icon={<HardDrive className="size-3.5" />} label="Свободно на диске" value={`${s.disk.free_gb} ГБ`} tone={s.disk.free_gb < 15 ? "err" : undefined}
        sub={s.disk.hours_left ? `хватит на ~${s.disk.hours_left} ч` : `данные ${s.disk.data_gb} ГБ`} />
    </div>
    <div className="mt-5 grid gap-5 xl:grid-cols-[1fr_420px]">
      <Card>
        <CardHeader title="В эфире" right={<Link to="/live" className="text-xs text-accent">все стримы →</Link>} />
        {s.channels.length === 0 ? <div className="p-6 text-sm text-muted">Никто из списка сейчас не стримит. Проверьте стримеров или порог зрителей в авто-поиске.</div> :
          <div className="divide-y divide-line">{s.channels.map((c) => <div key={c.login} className="flex items-center gap-3 px-4 py-2.5">
            {c.avatar ? <img src={c.avatar} className="size-8 rounded-full" /> : <div className="size-8 rounded-full bg-panel2" />}
            <div className="w-40 min-w-0"><div className="truncate font-medium">{c.name}</div><div className="text-xs text-muted">{num(c.viewers)} зрителей</div></div>
            <Sparkline className="flex-1" height={32} points={c.history} threshold={c.threshold} moments={c.moments} />
            <div className="w-16 text-right tabular-nums"><div className={c.score >= c.threshold ? "font-semibold text-ok" : ""}>{c.score.toFixed(1)}</div><div className="text-[11px] text-muted">порог {c.threshold}</div></div>
          </div>)}</div>}
      </Card>
      <div className="space-y-5">
        <Card>
          <CardHeader title="Площадки" right={<Link to="/targets" className="text-xs text-accent">настроить →</Link>} />
          {s.targets.length === 0 ? <div className="p-4 text-sm text-muted">Площадок нет.</div> :
            <div className="divide-y divide-line">{s.targets.map((t) => <div key={t.id} className="px-4 py-2.5">
              <div className="flex items-center gap-2"><span className="font-medium">{t.name}</span><Badge>{KIND_LABEL[t.kind]}</Badge><span className="flex-1" />
                <Badge tone={STATE_TONE[t.state] ?? "muted"}>{t.reason}</Badge></div>
              <div className="mt-1 text-xs text-muted">сегодня {t.today} / {t.daily_limit}{t.queued ? ` · в очереди ${t.queued}` : ""}{t.at && t.at > s.ts + 30 ? ` · следующий пост в ${clock(t.at)}` : ""}</div>
            </div>)}</div>}
        </Card>
        <Card>
          <CardHeader title="Требует внимания" right={<Link to="/health" className="text-xs text-accent">здоровье →</Link>} />
          {(health.data?.errors ?? []).length === 0 ? <div className="flex items-center gap-2 p-4 text-sm text-muted"><CheckCircle2 className="size-4 text-ok" />Ошибок за сутки нет</div> :
            <div className="divide-y divide-line">{health.data.errors.slice(0, 6).map((e: any, i: number) => <div key={i} className="flex gap-2 px-4 py-2.5 text-sm">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-err" /><div className="min-w-0"><div>{e.kind}: {e.place} <span className="text-muted">×{e.n} · {ago(e.last)}</span></div>
                <div className="truncate text-xs text-muted" title={e.error}>{e.error}</div></div></div>)}</div>}
        </Card>
      </div>
    </div>
  </>;
}
