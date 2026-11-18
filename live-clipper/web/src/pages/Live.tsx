import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { MessageSquare, Radio, Scissors, Volume2 } from "lucide-react";
import { api, clock, dur, num } from "../api";
import { useLive } from "../main";
import { Badge, Button, Card, Empty, Modal, PageHeader, Select, Sparkline, useAction } from "../ui";

function Chat({ login }: { login: string }) {
  const [rows, setRows] = useState<[number, string][]>([]);
  useEffect(() => { const load = () => api<[number, string][]>(`/api/channels/${login}/chat`).then(setRows).catch(() => {}); load(); const t = setInterval(load, 3000); return () => clearInterval(t); }, [login]);
  return <div className="h-72 space-y-1 overflow-y-auto rounded-lg bg-bg p-3 text-xs">{rows.slice().reverse().map(([ts, m], i) =>
    <div key={i}><span className="text-muted">{clock(ts)}</span> {m}</div>)}</div>;
}

export default function Live() {
  const s = useLive();
  const { busy, run } = useAction();
  const [secs, setSecs] = useState<Record<string, number>>({});
  const [open, setOpen] = useState<string | null>(null);
  const [made, setMade] = useState<Record<string, number>>({});
  if (!s) return null;
  const clipNow = (login: string) => run(login, () => api<{ clip_id: number }>(`/api/channels/${login}/clip`, { body: { seconds: secs[login] ?? 30 } }))
    .then((r) => r && setMade((m) => ({ ...m, [login]: r.clip_id })));
  const ch = s.channels.find((c) => c.login === open);
  return <>
    <PageHeader title="Эфир" hint="Каждый стрим пишется в буфер на 15 минут. Шкала — сила реакции чата и звука; когда она пересекает пунктир (порог), режется клип. Зелёные точки — уже нарезанные моменты." />
    {s.channels.length === 0 ? <Card><Empty icon={<Radio className="size-8" />} title="Сейчас ничего не пишется">
      Никто из белого списка не стримит GTA 6, а авто-поиск не нашёл стримов выше порога зрителей. <Link className="text-accent" to="/streamers">Стримеры →</Link></Empty></Card> :
    <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">{s.channels.map((c) => <Card key={c.login} className="overflow-hidden">
      <div className="relative aspect-video cursor-pointer bg-black" onClick={() => setOpen(c.login)}>
        <img src={`/media/preview/${c.login}.jpg?t=${Math.floor(c.preview_at)}`} className="h-full w-full object-cover" onError={(e) => (e.currentTarget.style.opacity = "0")} />
        <div className="absolute top-2 left-2 flex gap-1.5">
          {c.recording ? <Badge tone="err" className="bg-err text-white">● LIVE</Badge> : <Badge tone="warn">переподключение</Badge>}
          {c.warming && <Badge tone="muted" className="bg-black/70">разогрев детектора</Badge>}
        </div>
        <div className="absolute top-2 right-2"><Badge className="bg-black/70" tone={c.list === "white" ? "info" : "muted"}>{c.list === "white" ? "белый список" : "авто-поиск"}</Badge></div>
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 to-transparent p-3 pt-8">
          <div className="flex items-center gap-2">{c.avatar && <img src={c.avatar} className="size-7 rounded-full" />}<div className="min-w-0 flex-1">
            <div className="font-semibold">{c.name} <span className="font-normal text-muted">· {num(c.viewers)}</span></div><div className="truncate text-xs text-white/70">{c.title}</div></div></div>
        </div>
      </div>
      <div className="p-3">
        <div className="mb-1 flex items-center gap-3 text-xs text-muted">
          <span className={c.score >= c.threshold ? "font-semibold text-ok" : "text-fg"}>хайп {c.score.toFixed(1)} / {c.threshold}</span>
          <span className="flex items-center gap-1" title="вклад чата"><MessageSquare className="size-3" />{c.chat_z.toFixed(1)}</span>
          <span className="flex items-center gap-1" title="вклад звука"><Volume2 className="size-3" />{c.audio_z.toFixed(1)}</span>
          <span className="flex-1 text-right">{c.chat_per_min} сообщ/мин · буфер {dur(c.buffered_s)}</span>
        </div>
        <Sparkline points={c.history} threshold={c.threshold} moments={c.moments} height={52} />
        <div className="mt-3 flex items-center gap-2">
          <Select className="h-8 w-36 text-xs" value={secs[c.login] ?? 30} onChange={(e) => setSecs({ ...secs, [c.login]: +e.target.value })}>
            {[15, 20, 30, 45, 60, 90].map((v) => <option key={v} value={v}>последние {v} с</option>)}</Select>
          <Button size="sm" variant="primary" icon={<Scissors className="size-3.5" />} loading={busy === c.login} onClick={() => clipNow(c.login)}>Клип сейчас</Button>
          {made[c.login] && <Link to={`/clips/${made[c.login]}`} className="text-xs text-accent">клип #{made[c.login]} →</Link>}
          <span className="flex-1" /><a href={`https://twitch.tv/${c.login}`} target="_blank" className="text-xs text-muted hover:text-fg">twitch ↗</a>
        </div>
      </div>
    </Card>)}</div>}
    <Modal open={!!ch} onClose={() => setOpen(null)} title={ch ? `${ch.name} — ${num(ch.viewers)} зрителей` : ""} wide>
      {ch && <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div><img src={`/media/preview/${ch.login}.jpg?t=${Math.floor(ch.preview_at)}`} className="w-full rounded-lg" />
          <div className="mt-3"><Sparkline points={ch.history} threshold={ch.threshold} moments={ch.moments} height={90} /></div>
          <div className="mt-1 text-xs text-muted">последние 10 минут · моментов нарезано: {ch.moments.length}</div></div>
        <div><div className="mb-2 text-sm font-medium">Чат</div><Chat login={ch.login} /></div>
      </div>}
    </Modal>
  </>;
}
