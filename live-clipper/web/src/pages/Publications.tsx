import { useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink, RotateCcw, Send, Trash2 } from "lucide-react";
import { KIND_LABEL, ago, api, num, useApi, type Kind } from "../api";
import { Badge, Button, Card, Empty, PageHeader, Select, useAction, type Tone } from "../ui";

const ST: Record<string, [string, Tone]> = { queued: ["в очереди", "warn"], publishing: ["загружается", "info"], done: ["опубликован", "ok"], error: ["ошибка", "err"], deleted: ["удалён с площадки", "muted"] };

export default function Publications() {
  const [target, setTarget] = useState(0); const [status, setStatus] = useState("");
  const targets = useApi<{ targets: any[] }>("/api/targets");
  const list = useApi<any[]>(`/api/publications?target_id=${target}&status_=${status}`);
  const { busy, run } = useAction();
  return <>
    <PageHeader title="Публикации" hint="Каждый пост на каждой площадке: статус, ссылка, просмотры. Просмотры обновляются раз в 15 минут для VK и YouTube; Telegram Bot API просмотры не отдаёт."
      right={<div className="flex gap-2">
        <Select className="w-44" value={target} onChange={(e) => setTarget(+e.target.value)}><option value={0}>все площадки</option>{targets.data?.targets.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select>
        <Select className="w-40" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">все статусы</option>{Object.entries(ST).map(([k, v]) => <option key={k} value={k}>{v[0]}</option>)}</Select>
      </div>} />
    <Card>
      {(list.data ?? []).length === 0 ? <Empty icon={<Send className="size-8" />} title="Публикаций пока нет">Они появятся, когда включённая площадка опубликует первый клип.</Empty> :
        <table className="w-full text-sm"><thead><tr className="border-b border-line text-left text-xs text-muted">
          <th className="px-4 py-2.5 font-medium">Клип</th><th className="font-medium">Площадка</th><th className="font-medium">Статус</th><th className="font-medium">Когда</th><th className="font-medium">Просмотры</th><th /></tr></thead>
          <tbody>{list.data!.map((p) => <tr key={p.id} className="border-b border-line last:border-0 hover:bg-panel2/50">
            <td className="px-4 py-2.5"><Link to={`/clips/${p.clip_id}`} className="flex items-center gap-3">
              {p.has_file ? <img src={`/media/${p.clip_id}/thumb.jpg`} className="h-12 w-7 rounded object-cover bg-black" /> : <div className="h-12 w-7 rounded bg-panel2" />}
              <div className="min-w-0"><div className="max-w-md truncate">{p.title ?? `#${p.clip_id}`}</div><div className="text-xs text-muted">{p.login} · ★ {p.score?.toFixed(1)}</div></div></Link></td>
            <td>{p.target_name ?? "удалена"} {p.kind && <Badge>{KIND_LABEL[p.kind as Kind]}</Badge>}</td>
            <td><Badge tone={ST[p.status]?.[1]}>{ST[p.status]?.[0] ?? p.status}</Badge>{p.error && <div className="mt-1 max-w-xs truncate text-xs text-err" title={p.error}>{p.error}</div>}</td>
            <td className="text-muted">{ago(p.done_at ?? p.created_at)}</td>
            <td className="tabular-nums">{p.kind === "telegram" ? <span className="text-muted" title="Telegram Bot API не отдаёт просмотры">—</span> : num(p.views)}</td>
            <td className="pr-4 text-right"><div className="flex justify-end gap-1">
              {p.url && <a href={p.url} target="_blank"><Button size="sm" variant="ghost" icon={<ExternalLink className="size-3.5" />}>открыть</Button></a>}
              {p.status === "error" && <Button size="sm" icon={<RotateCcw className="size-3.5" />} loading={busy === `r${p.id}`} onClick={() => run(`r${p.id}`, () => api(`/api/publications/${p.id}/retry`, { body: {} }), "Поставлено на повтор").then(list.reload)}>повторить</Button>}
              {["done", "queued", "error"].includes(p.status) && <Button size="sm" variant="ghost" icon={<Trash2 className="size-3.5" />} loading={busy === `d${p.id}`}
                onClick={() => confirm(p.status === "done" ? "Удалить пост с площадки?" : "Убрать из очереди?") && run(`d${p.id}`, () => api(`/api/publications/${p.id}`, { method: "DELETE" }), "Готово").then(list.reload)} />}
            </div></td></tr>)}</tbody></table>}
    </Card>
  </>;
}
