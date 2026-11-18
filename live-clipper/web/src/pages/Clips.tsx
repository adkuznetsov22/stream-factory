import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Check, Clapperboard, Copy, Download, RefreshCw, RotateCcw, Scissors, Send, Sparkles, X } from "lucide-react";
import { KIND_LABEL, ago, api, useApi, type Clip, type Kind } from "../api";
import { useLive } from "../main";
import { Badge, Button, Card, CardHeader, Empty, Field, Input, Segmented, Select, Textarea, Toggle, cx, useAction, type Tone } from "../ui";

const STATUS: Record<string, [string, Tone]> = { detected: ["в очереди", "muted"], rendering: ["собирается", "warn"], ready: ["готов", "info"],
  published: ["опубликован", "ok"], rejected: ["отклонён", "muted"], error: ["ошибка", "err"] };
const VIEWS = [["review", "Ждут решения"], ["", "Все"], ["published", "Опубликованы"], ["processing", "Собираются"], ["duplicates", "Дубли"], ["rejected", "Отклонены"], ["errors", "Ошибки"]] as const;
const PUB: Record<string, [string, Tone]> = { queued: ["в очереди", "warn"], publishing: ["загружается", "info"], done: ["опубликован", "ok"], error: ["ошибка", "err"], deleted: ["удалён", "muted"] };
const fmt = (t: number) => `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, "0")}`;

function Thumb({ c }: { c: Clip }) {
  return c.has_file ? <img src={`/media/${c.id}/thumb.jpg?v=${c.version}`} className="h-20 w-[45px] shrink-0 rounded object-cover bg-black" onError={(e) => (e.currentTarget.style.visibility = "hidden")} />
    : <div className="grid h-20 w-[45px] shrink-0 place-items-center rounded bg-panel2"><Clapperboard className="size-4 text-muted" /></div>;
}

function Row({ c, active, onClick }: { c: Clip; active: boolean; onClick: () => void }) {
  const st = STATUS[c.status] ?? [c.status, "muted"];
  return <button onClick={onClick} className={cx("flex w-full gap-3 border-b border-line px-3 py-2.5 text-left hover:bg-panel2", active && "bg-panel2 ring-1 ring-inset ring-accent/40")}>
    <Thumb c={c} />
    <div className="min-w-0 flex-1">
      <div className="flex items-center gap-1.5"><span className="font-medium">{c.streamer.name}</span><Badge tone={st[1]}>{st[0]}</Badge>
        {c.manual ? <Badge>вручную</Badge> : null}{c.duplicate_of ? <Badge tone="warn">дубль #{c.duplicate_of}</Badge> : null}</div>
      <div className="mt-1 line-clamp-2 text-xs text-muted">{c.meta?.title ?? c.title ?? "…"}</div>
      <div className="mt-1 flex gap-2 text-[11px] text-muted"><span className="font-semibold text-fg">★ {c.score.toFixed(1)}</span><span>#{c.id}</span><span>{ago(c.created_at)}</span>
        {c.publications.filter((p) => p.status === "done").length > 0 && <span className="text-ok">{c.publications.filter((p) => p.status === "done").length} пост.</span>}</div>
    </div>
  </button>;
}

function Trim({ c, value, onChange }: { c: Clip; value: [number, number]; onChange: (v: [number, number]) => void }) {
  const vid = useRef<HTMLVideoElement>(null);
  const dur = c.src_duration ?? 0;
  const hype: [number, number][] = c.reasons?.hype ?? [];
  const max = Math.max(1, ...hype.map((h) => h[1]));
  const pct = (t: number) => `${(t / dur) * 100}%`;
  const bar = useRef<HTMLDivElement>(null);
  const drag = (which: 0 | 1) => (e: React.PointerEvent) => {
    const el = bar.current!; (e.target as Element).setPointerCapture(e.pointerId);
    const move = (ev: PointerEvent) => {
      const r = el.getBoundingClientRect(); const t = Math.max(0, Math.min(dur, ((ev.clientX - r.left) / r.width) * dur));
      const v: [number, number] = which === 0 ? [Math.min(t, value[1] - 3), value[1]] : [value[0], Math.max(t, value[0] + 3)];
      onChange([+v[0].toFixed(1), +v[1].toFixed(1)]); if (vid.current) vid.current.currentTime = which === 0 ? v[0] : Math.max(v[1] - 2, 0);
    };
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  };
  return <div>
    {c.has_source_preview ? <video ref={vid} src={`/media/${c.id}/source.mp4`} controls className="aspect-video w-full rounded-lg bg-black" />
      : <div className="grid aspect-video place-items-center rounded-lg bg-black text-xs text-muted">превью исходника готовится…</div>}
    <div ref={bar} className="relative mt-3 h-14 select-none rounded-lg bg-bg">
      <svg className="absolute inset-0 h-full w-full" preserveAspectRatio="none" viewBox={`0 0 ${dur || 1} 1`}>
        {hype.map(([t, v]) => <rect key={t} x={t} y={1 - v / max} width={1} height={v / max} fill="#ff3d8b" opacity=".35" />)}</svg>
      <div className="absolute inset-y-0 rounded-md border-2 border-accent bg-accent/10" style={{ left: pct(value[0]), width: `calc(${pct(value[1])} - ${pct(value[0])})` }} />
      {[0, 1].map((i) => <div key={i} onPointerDown={drag(i as 0 | 1)} className="absolute inset-y-0 w-3 -translate-x-1/2 cursor-ew-resize rounded bg-accent" style={{ left: pct(value[i]) }} />)}
    </div>
    <div className="mt-1 flex justify-between text-[11px] text-muted"><span>0:00</span><span className="text-fg">{fmt(value[0])} – {fmt(value[1])} · {(value[1] - value[0]).toFixed(1)} с</span><span>{fmt(dur)}</span></div>
  </div>;
}

function Detail({ id, targets, onChanged }: { id: number; targets: any[]; onChanged: () => void }) {
  const { data: c, setData, reload } = useApi<Clip>(`/api/clips/${id}`);
  const { busy, run } = useAction();
  const [tab, setTab] = useState<"post" | "edit" | "why">("post");
  const [meta, setMeta] = useState({ title: "", description: "" });
  const [edit, setEdit] = useState<any>(null);
  const [subs, setSubs] = useState<{ start: number; end: number; text: string }[]>([]);
  const [sel, setSel] = useState<number[]>([]);
  useEffect(() => { if (!c) return; setMeta({ title: c.meta?.title ?? "", description: c.meta?.description ?? "" });
    setEdit({ ...c.edit, overlay: c.edit?.overlay ?? c.meta?.overlay ?? "" }); setSubs(c.subs ?? []); }, [c?.id, c?.version, c?.updated_at]);
  useEffect(() => { if (c && (["rendering", "detected"].includes(c.status) || c.publications.some((p) => ["queued", "publishing"].includes(p.status)))) {
    const t = setTimeout(() => reload().then(onChanged), 3000); return () => clearTimeout(t); } }, [c]);
  useEffect(() => setSel(targets.filter((t) => t.enabled).map((t) => t.id)), [id, targets.length]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if ((e.target as HTMLElement).closest("input,textarea,select")) return;
      if (e.key === "p" && c) publish(); if (e.key === "r" && c) reject(); };
    window.addEventListener("keydown", key); return () => window.removeEventListener("keydown", key);
  });
  if (!c) return <Card className="h-full" />;
  const saveMeta = () => run("meta", () => api<Clip>(`/api/clips/${c.id}`, { method: "PATCH", body: meta }), "Текст сохранён").then((r) => r && setData(r));
  const publish = () => sel.length && run("pub", async () => { await api(`/api/clips/${c.id}`, { method: "PATCH", body: meta }); return api<Clip>(`/api/clips/${c.id}/publish`, { body: { target_ids: sel } }); }, "Поставлено в очередь публикации").then((r) => { if (r) { setData(r); onChanged(); } });
  const reject = () => run("rej", () => api(`/api/clips/${c.id}/reject`, { body: {} }), "Отклонён").then(() => { reload(); onChanged(); });
  const render = () => run("render", () => api<Clip>(`/api/clips/${c.id}/render`, { body: { ...edit, subs } }), "Пересобираю клип").then((r) => { if (r) { setData(r); onChanged(); } });
  const pubFor = (tid: number) => c.publications.find((p) => p.target_id === tid);
  const rendering = ["rendering", "detected"].includes(c.status);
  const r = c.reasons ?? {};
  return <Card className="overflow-hidden">
    <div className="flex items-center gap-2 border-b border-line px-4 py-3">
      {c.streamer.avatar && <img src={c.streamer.avatar} className="size-7 rounded-full" />}
      <div className="flex-1"><div className="font-semibold">{c.streamer.name} · клип #{c.id}</div>
        <div className="text-xs text-muted">★ {c.score.toFixed(1)} · {ago(c.created_at)}{c.timings?.rendered != null ? ` · готов через ${Math.round(c.timings.rendered)} с после момента` : ""}{c.stream_title ? ` · «${c.stream_title.slice(0, 60)}»` : ""}</div></div>
      <Badge tone={(STATUS[c.status] ?? ["", "muted"])[1]}>{(STATUS[c.status] ?? [c.status])[0]}</Badge>
      {c.has_file && <a href={`/media/${c.id}/clip.mp4`} download={`clip_${c.id}.mp4`}><Button size="sm" variant="ghost" icon={<Download className="size-3.5" />} /></a>}
    </div>
    {c.duplicate_of && <div className="border-b border-warn/30 bg-warn/10 px-4 py-2 text-sm text-warn">Этот же момент снят с другого стрима (клип #{c.duplicate_of}), авто-публикация его пропустит.
      <button className="ml-2 underline" onClick={() => run("restore", () => api<Clip>(`/api/clips/${c.id}/restore`, { body: {} })).then((x) => x && setData(x))}>это не дубль</button></div>}
    {c.status === "error" && <div className="border-b border-err/30 bg-err/10 px-4 py-2 text-sm text-err">{c.error}</div>}
    <div className="grid gap-5 p-4 lg:grid-cols-[300px_1fr]">
      <div>
        {c.has_file && !rendering ? <video key={c.version} src={`/media/${c.id}/clip.mp4?v=${c.version}`} controls autoPlay muted playsInline className="aspect-[9/16] w-full rounded-lg bg-black" />
          : <div className="grid aspect-[9/16] w-full place-items-center rounded-lg bg-black text-sm text-muted">{rendering ? <span className="flex items-center gap-2"><RefreshCw className="size-4 animate-spin" />собирается…</span> : "файл удалён по сроку хранения"}</div>}
      </div>
      <div className="min-w-0">
        <Segmented value={tab} onChange={setTab} options={[{ value: "post", label: "Публикация" }, { value: "edit", label: "Монтаж" }, { value: "why", label: "Почему нарезан" }]} />
        {tab === "post" && <div className="mt-4 space-y-4">
          <Field label="Заголовок" hint={`${meta.title.length}/100 · для YouTube и VK — название ролика, в Telegram — первая строка`}><Input value={meta.title} maxLength={100} onChange={(e) => setMeta({ ...meta, title: e.target.value })} /></Field>
          <Field label="Описание" hint="Ссылка на стримера и хэштеги добавляются по шаблону площадки."><Textarea rows={3} value={meta.description} onChange={(e) => setMeta({ ...meta, description: e.target.value })} /></Field>
          <div className="flex gap-2"><Button size="sm" onClick={saveMeta} loading={busy === "meta"}>Сохранить текст</Button>
            <Button size="sm" variant="ghost" icon={<Sparkles className="size-3.5" />} loading={busy === "retitle"} onClick={() => run("retitle", () => api<Clip>(`/api/clips/${c.id}/retitle`, { body: {} })).then((x) => x && (setData(x), setMeta({ title: x.meta?.title ?? "", description: x.meta?.description ?? "" })))}>Сгенерировать заново</Button></div>
          <div>
            <div className="mb-2 text-xs font-medium text-muted">Куда публикуем</div>
            {targets.length === 0 ? <div className="text-sm text-muted">Площадок нет — добавьте во вкладке «Площадки».</div> :
              <div className="space-y-2">{targets.map((t) => { const p = pubFor(t.id); const post = c.posts?.[t.id];
                return <div key={t.id} className="rounded-lg border border-line bg-bg p-3">
                  <div className="flex items-center gap-2">
                    <input type="checkbox" disabled={!t.enabled || p?.status === "done"} checked={sel.includes(t.id) && p?.status !== "done"} onChange={(e) => setSel(e.target.checked ? [...sel, t.id] : sel.filter((x) => x !== t.id))} />
                    <span className="font-medium">{t.name}</span><Badge>{KIND_LABEL[t.kind as Kind]}</Badge>{!t.enabled && <Badge tone="muted">выключена</Badge>}
                    <span className="flex-1" />{p && <Badge tone={PUB[p.status]?.[1]} title={p.error ?? ""}>{PUB[p.status]?.[0]}</Badge>}
                    {p?.url && <a href={p.url} target="_blank" className="text-xs text-accent">открыть ↗</a>}
                  </div>
                  {p?.error && <div className="mt-1 text-xs text-err">{p.error}</div>}
                  {post && <details className="mt-2 text-xs text-muted"><summary className="cursor-pointer">как будет выглядеть подпись</summary>
                    <pre className="mt-2 whitespace-pre-wrap font-sans text-fg">{post.caption}</pre></details>}
                </div>; })}</div>}
          </div>
          <div className="flex flex-wrap gap-2 border-t border-line pt-4">
            <Button variant="primary" icon={<Send className="size-4" />} disabled={!c.has_file || !sel.length || rendering} loading={busy === "pub"} onClick={publish}>Опубликовать <kbd className="ml-1 text-[10px] opacity-70">P</kbd></Button>
            {c.status !== "rejected" ? <Button variant="danger" icon={<X className="size-4" />} loading={busy === "rej"} onClick={reject}>Отклонить <kbd className="ml-1 text-[10px] opacity-70">R</kbd></Button>
              : <Button icon={<RotateCcw className="size-4" />} onClick={() => run("restore", () => api<Clip>(`/api/clips/${c.id}/restore`, { body: {} })).then((x) => x && setData(x))}>Вернуть</Button>}
          </div>
        </div>}
        {tab === "edit" && edit && <div className="mt-4 space-y-4">
          {!c.has_source ? <div className="rounded-lg bg-bg p-4 text-sm text-muted">Исходник уже удалён по сроку хранения (настройка «Хранить исходники»). Можно менять только текст.</div> : <>
            <Trim c={c} value={[edit.trim_start, edit.trim_end]} onChange={([a, b]) => setEdit({ ...edit, trim_start: a, trim_end: b })} />
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Текст на видео (плашка)"><Input value={edit.overlay} maxLength={60} onChange={(e) => setEdit({ ...edit, overlay: e.target.value })} /></Field>
              <Field label="Раскладка"><Select value={edit.layout ?? ""} onChange={(e) => setEdit({ ...edit, layout: e.target.value || undefined })}>
                <option value="">как у стримера / по умолчанию</option><option value="blur">геймплей по центру, размытый фон</option><option value="facecam">вебка сверху, игра снизу</option><option value="full">игра на весь экран</option></Select></Field>
            </div>
            <Toggle checked={edit.subtitles !== false} onChange={(v) => setEdit({ ...edit, subtitles: v })} label="Субтитры" />
            {edit.subtitles !== false && <div>
              <div className="mb-1 text-xs font-medium text-muted">Субтитры (можно исправить текст строки)</div>
              <div className="max-h-64 space-y-1 overflow-y-auto rounded-lg bg-bg p-2">{subs.filter((s) => s.end > edit.trim_start && s.start < edit.trim_end).map((s) => { const i = subs.indexOf(s);
                return <div key={i} className="flex items-center gap-2"><span className="w-12 text-[11px] text-muted tabular-nums">{fmt(s.start - edit.trim_start)}</span>
                  <Input className="h-7 text-xs" value={s.text} onChange={(e) => setSubs(subs.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))} /></div>; })}
                {subs.length === 0 && <div className="p-2 text-xs text-muted">Речь не распознана.</div>}</div>
            </div>}
            <Button variant="primary" icon={<Scissors className="size-4" />} loading={busy === "render"} disabled={rendering} onClick={render}>Пересобрать клип</Button>
          </>}
        </div>}
        {tab === "why" && <div className="mt-4 space-y-4 text-sm">
          {r.manual ? <div className="text-muted">Клип нарезан вручную кнопкой «Клип сейчас».</div> : <div className="grid grid-cols-3 gap-3">
            <Card className="p-3"><div className="text-xs text-muted">Всплеск чата</div><div className="text-xl font-semibold">{r.chat ?? "—"}</div><div className="text-[11px] text-muted">{r.chat_msgs ?? 0} сообщений за пик</div></Card>
            <Card className="p-3"><div className="text-xs text-muted">Всплеск звука</div><div className="text-xl font-semibold">{r.audio ?? "—"}</div><div className="text-[11px] text-muted">крик, смех, взрыв</div></Card>
            <Card className="p-3"><div className="text-xs text-muted">Порог</div><div className="text-xl font-semibold">{r.threshold ?? "—"}</div><div className="text-[11px] text-muted">итог ★ {c.score.toFixed(1)}</div></Card></div>}
          {(r.emotes ?? []).length > 0 && <div className="flex flex-wrap gap-1.5">{r.emotes.map(([e, n]: [string, number]) => <Badge key={e} tone="accent">{e} ×{n}</Badge>)}</div>}
          {(r.chat_sample ?? []).length > 0 && <div><div className="mb-1 text-xs text-muted">Чат в момент пика</div>
            <div className="max-h-64 space-y-0.5 overflow-y-auto rounded-lg bg-bg p-3 text-xs">{r.chat_sample.map((m: string, i: number) => <div key={i}>{m}</div>)}</div></div>}
          {c.transcript && <div><div className="mb-1 text-xs text-muted">Речь стримера</div><div className="rounded-lg bg-bg p-3 text-xs">{c.transcript}</div></div>}
        </div>}
      </div>
    </div>
  </Card>;
}

export default function Clips() {
  const { id } = useParams(); const nav = useNavigate(); const live = useLive();
  const [view, setView] = useState<string>("review"); const [login, setLogin] = useState(""); const [sort, setSort] = useState("new"); const [minScore, setMinScore] = useState(0);
  const q = `/api/clips?view=${view}&login=${login}&sort=${sort}&min_score=${minScore}&limit=80`;
  const list = useApi<{ items: Clip[]; counts: Record<string, number> }>(q);
  const targets = useApi<{ targets: any[] }>("/api/targets");
  const tick = live?.rendering.join(",") + "|" + live?.day.clips;
  useEffect(() => { list.reload(); }, [tick]);
  const items = list.data?.items ?? [];
  const current = id ? +id : items[0]?.id;
  const idx = items.findIndex((c) => c.id === current);
  useEffect(() => { const key = (e: KeyboardEvent) => { if ((e.target as HTMLElement).closest("input,textarea,select")) return;
    if (e.key === "j" && items[idx + 1]) nav(`/clips/${items[idx + 1].id}`); if (e.key === "k" && idx > 0) nav(`/clips/${items[idx - 1].id}`); };
    window.addEventListener("keydown", key); return () => window.removeEventListener("keydown", key); }, [items, idx]);
  const logins = useMemo(() => Array.from(new Set([...(live?.channels.map((c) => c.login) ?? []), ...(live?.whitelist ?? [])])), [live?.channels.length]);
  return <div className="flex h-[calc(100vh-48px)] flex-col">
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <h1 className="mr-2 text-xl font-semibold">Клипы</h1>
      <div className="flex flex-wrap gap-1">{VIEWS.map(([v, label]) => <button key={v} onClick={() => { setView(v); nav("/clips"); }}
        className={cx("rounded-lg px-3 py-1.5 text-xs font-medium", view === v ? "bg-panel2 text-fg" : "text-muted hover:text-fg")}>{label}
        {v && list.data?.counts[v] ? <span className="ml-1.5 text-muted">{list.data.counts[v]}</span> : null}</button>)}</div>
      <span className="flex-1" />
      <Select className="h-8 w-40 text-xs" value={login} onChange={(e) => setLogin(e.target.value)}><option value="">все стримеры</option>{logins.map((l) => <option key={l}>{l}</option>)}</Select>
      <Select className="h-8 w-36 text-xs" value={minScore} onChange={(e) => setMinScore(+e.target.value)}>{[0, 6, 8, 10, 15].map((v) => <option key={v} value={v}>{v ? `балл от ${v}` : "любой балл"}</option>)}</Select>
      <Select className="h-8 w-44 text-xs" value={sort} onChange={(e) => setSort(e.target.value)}><option value="new">сначала новые</option><option value="score">сначала сильные</option></Select>
    </div>
    <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[360px_1fr]">
      <Card className="min-h-0 overflow-y-auto">
        {items.length === 0 ? <Empty icon={<Check className="size-8" />} title={view === "review" ? "Всё разобрано" : "Клипов нет"}>{view === "review" ? "Новые клипы появятся здесь сразу после нарезки." : ""}</Empty>
          : items.map((c) => <Row key={c.id} c={c} active={c.id === current} onClick={() => nav(`/clips/${c.id}`)} />)}
        {items.length > 0 && <div className="p-3 text-center text-[11px] text-muted">J / K — следующий / предыдущий · P — опубликовать · R — отклонить</div>}
      </Card>
      <div className="min-h-0 overflow-y-auto">{current ? <Detail key={current} id={current} targets={targets.data?.targets ?? []} onChanged={list.reload} />
        : <Card><CardHeader title="Выберите клип" /><div className="p-4 text-sm text-muted"><Copy className="inline size-4" /> Клип откроется здесь.</div></Card>}</div>
    </div>
  </div>;
}
