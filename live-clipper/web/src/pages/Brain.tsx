import { Link } from "react-router-dom";
import { Brain as BrainIcon, Eye, ShieldAlert, Sparkles } from "lucide-react";
import { ago, num, useApi } from "../api";
import { Badge, Card, CardHeader, Empty, PageHeader, Stat } from "../ui";

const SRC: Record<string, string> = { detector: "детектор", crowd: "зрители клипнули", model: "модель", manual: "вручную" };
const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}%`);

export default function Brain() {
  const { data: d } = useApi<any>("/api/brain");
  if (!d) return null;
  const t = d.total, m = d.model, lt = m.last_train;
  return <>
    <PageHeader title="Мозг" hint="Как сервис выбирает моменты и чему учится. Эталон — клипы, которые зрители сами нарезали на Twitch: если зрители клипнули момент и он набрал просмотры, значит он зашёл." />
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
      <Stat icon={<Eye className="size-3.5" />} label="Ловим популярные моменты" value={pct(t.recall)} sub={`${t.caught} из ${t.popular} клипов зрителей с 300+ просмотрами`} tone={t.recall != null && t.recall < 0.5 ? "warn" : "ok"} />
      <Stat label="Точность детектора" value={pct(t.precision)} sub={`${t.matched} из ${t.ours} наших клипов совпали со зрительскими`} />
      <Stat icon={<BrainIcon className="size-3.5" />} label="Модель" value={m.active ? "активна" : "учится"} sub={m.active ? `ловит ${pct(m.meta.recall_model)} против ${pct(m.meta.recall_detector)} у детектора` : lt?.reason ?? "первое обучение через 10 мин после старта"} tone={m.active ? "ok" : "warn"} />
      <Stat label="Секунд эфира в обучении" value={num(d.features?.n)} sub={`${d.features?.channels ?? 0} стримов, хранится 14 дней`} />
      <Stat icon={<Sparkles className="size-3.5" />} label="Клипов оценил ИИ-судья" value={d.judged.length} sub={d.judged.length ? "последние 30 ниже" : "нужен ключ OpenRouter"} />
    </div>
    <div className="mt-5 grid gap-5 xl:grid-cols-2">
      <Card><CardHeader title="По стримерам" hint="Сколько популярных моментов поймали сами и сколько добрали по сигналу зрителей." />
        <table className="w-full text-sm"><thead><tr className="border-b border-line text-left text-xs text-muted"><th className="px-4 py-2 font-medium">Стример</th><th className="font-medium">Поймали</th><th className="font-medium">Точность</th><th className="font-medium">Добрали по зрителям</th><th className="font-medium">Часов эфира</th></tr></thead>
          <tbody>{Object.entries(d.streamers).map(([login, s]: [string, any]) => <tr key={login} className="border-b border-line last:border-0">
            <td className="px-4 py-2 font-medium">{login}</td><td>{s.caught} / {s.popular}</td><td>{s.ours ? pct(s.matched / s.ours) : "—"}</td><td>{s.crowd}</td><td>{s.hours}</td></tr>)}</tbody></table>
        {Object.keys(d.streamers).length === 0 && <div className="p-4 text-sm text-muted">Данные копятся с момента запуска.</div>}
      </Card>
      <Card><CardHeader title="Откуда клипы за 24 ч" />
        <div className="divide-y divide-line">{d.sources.map((s: any) => <div key={s.source} className="flex items-center gap-3 px-4 py-2.5 text-sm">
          <span className="flex-1">{SRC[s.source] ?? s.source}</span><span className="text-muted">средний балл {s.avg}</span><span className="w-24 text-right">{s.n} клипов</span><span className="w-28 text-right text-ok">{s.published} опубл.</span></div>)}</div>
        {lt && <div className="border-t border-line px-4 py-3 text-xs text-muted">Последнее обучение: {lt.ok ? `${num(lt.samples)} примеров, ${lt.positives} популярных; модель ${pct(lt.recall_model)} против детектора ${pct(lt.recall_detector)} — ${lt.promoted ? "включена" : "не лучше, оставили детектор"}` : lt.reason}</div>}
      </Card>
    </div>
    <Card className="mt-5"><CardHeader title="Клипы зрителей за 24 ч" hint="Самые популярные. Зелёные — у нас есть этот момент." />
      {d.viewer_clips.length === 0 ? <Empty title="Пока пусто">Опрос Twitch идёт каждые 30 с.</Empty> :
        <div className="divide-y divide-line">{d.viewer_clips.map((v: any) => <div key={v.slug} className="flex items-center gap-3 px-4 py-2 text-sm">
          <span className="w-28 text-muted">{v.login}</span><a href={`https://clips.twitch.tv/${v.slug}`} target="_blank" className="min-w-0 flex-1 truncate hover:text-accent">{v.title}</a>
          <span className="w-24 text-right tabular-nums">{num(v.views)} просм.</span><span className="w-24 text-right text-xs text-muted">{ago(v.created)}</span>
          <span className="w-40 text-right">{v.clip_id ? <Link to={`/clips/${v.clip_id}`}><Badge tone="ok">наш #{v.clip_id} · {SRC[v.source] ?? "детектор"}</Badge></Link> : v.covered ? <Badge tone="err">пропустили</Badge> : <Badge>не писали</Badge>}</span></div>)}</div>}
    </Card>
    <Card className="mt-5"><CardHeader title="Оценки ИИ-судьи" />
      {d.judged.length === 0 ? <Empty icon={<Sparkles className="size-8" />} title="Судья не подключён">Добавьте ключ OpenRouter в настройках: судья смотрит кадры, речь и чат каждого кандидата и оценивает виральность и безопасность.</Empty> :
        <div className="divide-y divide-line">{d.judged.map((c: any) => { const cats = Object.entries(c.safety?.categories ?? {}).filter(([, v]: any) => v.level >= 2);
          return <Link to={`/clips/${c.id}`} key={c.id} className="flex items-center gap-3 px-4 py-2.5 text-sm hover:bg-panel2">
            <span className="w-12 text-lg font-semibold tabular-nums">{Math.round(c.judge.virality)}</span>
            <div className="min-w-0 flex-1"><div className="truncate">{c.judge.title}</div><div className="truncate text-xs text-muted">{c.judge.why}</div></div>
            {cats.map(([k]) => <Badge key={k} tone="err"><ShieldAlert className="size-3" />{k}</Badge>)}<span className="text-xs text-muted">{c.login}</span></Link>; })}</div>}
    </Card>
  </>;
}
