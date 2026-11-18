import { useRef, useState } from "react";
import { Crop, Plus, Search, Trash2 } from "lucide-react";
import { api, ago, num, useApi } from "../api";
import { Badge, Button, Card, Empty, Field, Input, Modal, PageHeader, Segmented, Select, useAction } from "../ui";
import { Tags } from "./Settings";

type S = { login: string; display_name: string | null; avatar: string | null; list: string; layout: string; facecam: number[] | null; sensitivity: number;
  hashtags: string[] | null; live: boolean; viewers: number | null; title: string | null; last_live_at: number | null; has_preview: boolean; stats: { clips: number; published: number; avg_score: number | null } };

function FacecamPicker({ s, onSave }: { s: S; onSave: (rect: number[] | null) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const [rect, setRect] = useState<number[] | null>(s.facecam);
  const start = (e: React.PointerEvent) => {
    const r = box.current!.getBoundingClientRect(); const x0 = (e.clientX - r.left) / r.width, y0 = (e.clientY - r.top) / r.height;
    (e.target as Element).setPointerCapture(e.pointerId);
    const move = (ev: PointerEvent) => { const x1 = Math.min(Math.max((ev.clientX - r.left) / r.width, 0), 1), y1 = Math.min(Math.max((ev.clientY - r.top) / r.height, 0), 1);
      setRect([Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0)].map((v) => +v.toFixed(4))); };
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  };
  return <div>
    <p className="mb-3 text-sm text-muted">Выделите мышкой вебку стримера на кадре. В раскладке «вебка сверху» эта область займёт верх ролика, игра — низ.</p>
    {s.has_preview ? <div ref={box} onPointerDown={start} className="relative cursor-crosshair select-none overflow-hidden rounded-lg">
      <img src={`/media/preview/${s.login}.jpg?t=${Date.now()}`} className="pointer-events-none w-full" />
      {rect && <div className="absolute border-2 border-accent bg-accent/15 shadow-[0_0_0_9999px_rgba(0,0,0,.5)]" style={{ left: `${rect[0] * 100}%`, top: `${rect[1] * 100}%`, width: `${rect[2] * 100}%`, height: `${rect[3] * 100}%` }} />}
    </div> : <div className="rounded-lg bg-bg p-8 text-center text-sm text-muted">Кадра нет: стример сейчас не в эфире. Вебку можно отметить, когда он начнёт стрим.</div>}
    <div className="mt-3 flex gap-2"><Button variant="primary" disabled={!rect || rect[2] < 0.03} onClick={() => onSave(rect)}>Сохранить вебку</Button>
      {s.facecam && <Button variant="ghost" onClick={() => onSave(null)}>Убрать</Button>}</div>
  </div>;
}

export default function Streamers() {
  const { data, reload } = useApi<S[]>("/api/streamers");
  const { busy, run } = useAction();
  const [tab, setTab] = useState<"white" | "auto" | "black">("white"); const [q, setQ] = useState(""); const [login, setLogin] = useState("");
  const [edit, setEdit] = useState<S | null>(null); const [pick, setPick] = useState<S | null>(null);
  const put = (l: string, body: any, ok?: string) => run(l, () => api(`/api/streamers/${l}`, { method: "PUT", body }), ok).then(reload);
  const rows = (data ?? []).filter((s) => s.list === tab && (!q || s.login.includes(q.toLowerCase()) || s.display_name?.toLowerCase().includes(q.toLowerCase())))
    .sort((a, b) => +b.live - +a.live || (b.viewers ?? 0) - (a.viewers ?? 0));
  const count = (l: string) => (data ?? []).filter((s) => s.list === l).length;
  return <>
    <PageHeader title="Стримеры" hint="Белый список пишется всегда, когда стример в эфире с GTA 6. Авто-поиск подхватывает остальных RU-стримеров выше порога зрителей. Чёрный список не пишется никогда." />
    <div className="mb-4 flex flex-wrap items-center gap-2">
      <Segmented value={tab} onChange={setTab} options={[{ value: "white", label: `Белый список ${count("white")}` }, { value: "auto", label: `Найдены авто-поиском ${count("auto")}` }, { value: "black", label: `Чёрный список ${count("black")}` }]} />
      <div className="relative"><Search className="absolute top-2.5 left-2.5 size-4 text-muted" /><Input className="w-56 pl-8" placeholder="поиск" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      <span className="flex-1" />
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); login.trim() && put(login.trim().replace(/.*twitch\.tv\//, ""), { list: tab === "auto" ? "white" : tab }, "Добавлен").then(() => setLogin("")); }}>
        <Input className="w-56" placeholder="ник или ссылка twitch" value={login} onChange={(e) => setLogin(e.target.value)} /><Button icon={<Plus className="size-4" />}>Добавить</Button></form>
    </div>
    <Card>
      {rows.length === 0 ? <Empty title="Пусто">{tab === "auto" ? "Авто-поиск пока никого не нашёл." : "Добавьте ник с Twitch."}</Empty> :
        <table className="w-full text-sm"><thead><tr className="border-b border-line text-left text-xs text-muted"><th className="px-4 py-2.5 font-medium">Стример</th>
          <th className="font-medium">Статус</th><th className="font-medium">Клипы за 24 ч</th><th className="font-medium">Ролик</th><th className="font-medium">Чувствительность</th><th /></tr></thead>
          <tbody>{rows.map((s) => <tr key={s.login} className="border-b border-line last:border-0 hover:bg-panel2/40">
            <td className="px-4 py-2.5"><div className="flex items-center gap-3">{s.avatar ? <img src={s.avatar} className="size-8 rounded-full" /> : <div className="size-8 rounded-full bg-panel2" />}
              <div><div className="font-medium">{s.display_name ?? s.login}</div><a href={`https://twitch.tv/${s.login}`} target="_blank" className="text-xs text-muted hover:text-fg">twitch.tv/{s.login}</a></div></div></td>
            <td>{s.live ? <div><Badge tone="err">● в эфире · {num(s.viewers)}</Badge><div className="mt-1 max-w-56 truncate text-xs text-muted">{s.title}</div></div> : <span className="text-xs text-muted">был {ago(s.last_live_at)}</span>}</td>
            <td className="text-xs">{s.stats.clips} клипов · {s.stats.published} опубл.{s.stats.avg_score != null && <div className="text-muted">средний балл {s.stats.avg_score}</div>}</td>
            <td className="text-xs">{s.layout === "facecam" ? "вебка сверху" : s.layout === "full" ? "на весь экран" : s.layout === "blur" ? "размытый фон" : "по умолчанию"}
              <div>{s.facecam ? <Badge tone="ok">вебка отмечена</Badge> : <Badge>вебка не отмечена</Badge>}</div></td>
            <td className="text-xs">×{s.sensitivity ?? 1}</td>
            <td className="pr-4"><div className="flex justify-end gap-1">
              {tab !== "white" && <Button size="sm" loading={busy === s.login} onClick={() => put(s.login, { list: "white" }, "В белом списке")}>в белый</Button>}
              {tab !== "black" && <Button size="sm" variant="ghost" onClick={() => put(s.login, { list: "black" }, "В чёрном списке")}>в чёрный</Button>}
              <Button size="sm" variant="ghost" icon={<Crop className="size-3.5" />} onClick={() => setPick(s)}>вебка</Button>
              <Button size="sm" onClick={() => setEdit({ ...s, hashtags: s.hashtags ?? [] })}>профиль</Button>
              {tab !== "auto" && <Button size="sm" variant="ghost" icon={<Trash2 className="size-3.5" />} onClick={() => confirm(`Удалить ${s.login}?`) && run("d", () => api(`/api/streamers/${s.login}`, { method: "DELETE" })).then(reload)} />}
            </div></td></tr>)}</tbody></table>}
    </Card>
    <Modal open={!!pick} onClose={() => setPick(null)} title={`Вебка: ${pick?.display_name ?? pick?.login}`} wide>
      {pick && <FacecamPicker s={pick} onSave={(rect) => put(pick.login, rect ? { facecam: rect, layout: "facecam" } : { facecam: null, layout: "" }, "Сохранено").then(() => setPick(null))} />}
    </Modal>
    <Modal open={!!edit} onClose={() => setEdit(null)} title={`Профиль: ${edit?.display_name ?? edit?.login}`}>
      {edit && <div className="space-y-4">
        <Field label="Раскладка ролика"><Select value={edit.layout ?? ""} onChange={(e) => setEdit({ ...edit, layout: e.target.value })}>
          <option value="">как в настройках</option><option value="blur">геймплей по центру, размытый фон</option><option value="facecam" disabled={!edit.facecam}>вебка сверху (нужно отметить вебку)</option><option value="full">игра на весь экран</option></Select></Field>
        <Field label={`Чувствительность ×${edit.sensitivity}`} hint="Выше 1 — клипов больше (для спокойных стримеров), ниже 1 — меньше (для стримеров с вечно орущим чатом).">
          <input type="range" min={0.3} max={3} step={0.1} value={edit.sensitivity} onChange={(e) => setEdit({ ...edit, sensitivity: +e.target.value })} className="w-full" /></Field>
        <Field label="Свои хэштеги" hint="Добавляются к общим хэштегам."><Tags value={edit.hashtags ?? []} onChange={(v) => setEdit({ ...edit, hashtags: v })} /></Field>
        <Button variant="primary" onClick={() => put(edit.login, { layout: edit.layout, sensitivity: edit.sensitivity, hashtags: edit.hashtags }, "Профиль сохранён").then(() => setEdit(null))}>Сохранить</Button>
      </div>}
    </Modal>
  </>;
}
