import { useState } from "react";
import { CheckCircle2, Plus, ShieldCheck, Trash2, XCircle, Zap } from "lucide-react";
import { KIND_LABEL, ago, api, clock, useApi, type Kind } from "../api";
import PolicyEditor from "./Policy";
import { Badge, Button, Card, Field, Input, PageHeader, Segmented, Select, Textarea, Toggle, useAction } from "../ui";

const LABEL: Record<string, [string, string]> = {
  bot_token: ["Токен бота", "@BotFather → /newbot → скопировать токен"], chat_id: ["Канал", "@username канала или числовой id -100…; бот должен быть админом с правом «Публикация сообщений»"],
  access_token: ["Токен VK", "права video, wall, groups, offline; аккаунт — админ сообщества"], group_id: ["ID сообщества", "цифры из адреса club123456"],
  client_id: ["OAuth Client ID", "Google Cloud → APIs & Services → Credentials"], client_secret: ["OAuth Client Secret", ""],
  refresh_token: ["Refresh token", "OAuth Playground, scope youtube.upload (для удаления постов — youtube)"], privacy: ["Видимость", "public, unlisted или private"],
};
const HELP: Record<Kind, string> = {
  telegram: "1) Создайте бота в @BotFather. 2) Добавьте его в канал администратором с правом «Публикация сообщений». 3) Вставьте токен и @канал, нажмите «Проверить».",
  vk: "1) Сообщество с включёнными разделами «Видео» и «Клипы». 2) Токен админа сообщества с правами video, wall, groups, offline. 3) ID сообщества — цифры из club123456.",
  youtube: "1) Проект в Google Cloud с YouTube Data API v3. 2) OAuth-клиент и refresh token. Пока проект не прошёл аудит Google, видео загружаются приватными. Квота ≈ 6 загрузок в сутки.",
};
const hours = Array.from({ length: 24 }, (_, i) => i);

function TargetCard({ t, fields, meta, onChange }: { t: any; fields: string[]; meta: any; onChange: () => void }) {
  const [f, setF] = useState<any>({ ...t, config: { ...t.config }, caption: t.caption ?? "" });
  const [res, setRes] = useState<{ ok: boolean; message: string } | null>(t.check_message ? { ok: !!t.check_ok, message: t.check_message } : null);
  const { busy, run } = useAction();
  const body = () => ({ name: f.name, mode: f.mode, daily_limit: +f.daily_limit, min_score: +f.min_score, min_interval_min: +f.min_interval_min,
    caption: f.caption || null, quiet_from: f.quiet_from ?? null, quiet_to: f.quiet_to ?? null, config: f.config, policy: f.policy });
  const save = (extra: any = {}) => run("save", () => api(`/api/targets/${t.id}`, { method: "PUT", body: { ...body(), ...extra } }), "Сохранено").then((r) => r && onChange());
  const check = (kind: "check" | "test") => run(kind, async () => { await api(`/api/targets/${t.id}`, { method: "PUT", body: body() }); return api<any>(`/api/targets/${t.id}/${kind}`, { body: {} }); }).then((r) => { if (r) { setRes(r); onChange(); } });
  const quiet = f.quiet_from != null && f.quiet_to != null && f.quiet_from !== f.quiet_to;
  return <Card className="overflow-hidden">
    <div className="flex items-center gap-3 border-b border-line px-4 py-3">
      <div className="flex-1"><div className="flex items-center gap-2 font-semibold">{t.name}<Badge>{KIND_LABEL[t.kind as Kind]}</Badge>
        {t.check_ok === 1 ? <Badge tone="ok"><ShieldCheck className="size-3" />права проверены</Badge> : t.check_ok === 0 ? <Badge tone="err">проверка не пройдена</Badge> : <Badge tone="warn">не проверена</Badge>}</div>
        <div className="mt-0.5 text-xs text-muted">{t.plan.reason}{t.plan.at && t.plan.at > Date.now() / 1000 + 30 ? ` · следующий пост в ${clock(t.plan.at)}` : ""} · сегодня {t.plan.today} из {t.daily_limit}</div></div>
      <Toggle checked={!!t.enabled} disabled={busy === "save"} onChange={(v) => save({ enabled: v })} label={t.enabled ? "включена" : "выключена"} />
    </div>
    <div className="grid gap-5 p-4 lg:grid-cols-2">
      <div className="space-y-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-muted">Подключение</div>
        <div className="rounded-lg bg-bg p-3 text-xs leading-relaxed text-muted">{HELP[t.kind as Kind]}</div>
        <Field label="Название в админке"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        {fields.map((k) => <Field key={k} label={LABEL[k]?.[0] ?? k} hint={LABEL[k]?.[1]}>
          {k === "privacy" ? <Select value={f.config[k] ?? "public"} onChange={(e) => setF({ ...f, config: { ...f.config, [k]: e.target.value } })}><option>public</option><option>unlisted</option><option>private</option></Select>
            : <Input value={f.config[k] ?? ""} autoComplete="off" onChange={(e) => setF({ ...f, config: { ...f.config, [k]: e.target.value } })} />}</Field>)}
        <div className="flex flex-wrap gap-2">
          <Button icon={<ShieldCheck className="size-4" />} loading={busy === "check"} onClick={() => check("check")}>Проверить права</Button>
          <Button icon={<Zap className="size-4" />} loading={busy === "test"} onClick={() => check("test")}>Тестовый пост</Button>
        </div>
        {res && <div className={`flex gap-2 rounded-lg p-3 text-sm ${res.ok ? "bg-ok/10 text-ok" : "bg-err/10 text-err"}`}>{res.ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0" /> : <XCircle className="mt-0.5 size-4 shrink-0" />}
          <div>{res.message}{t.checked_at && <div className="text-xs opacity-70">проверено {ago(t.checked_at)}</div>}</div></div>}
      </div>
      <div className="space-y-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-muted">Правила публикации</div>
        <Field label="Режим"><Segmented value={f.mode} onChange={(v) => setF({ ...f, mode: v })} options={[{ value: "auto", label: "Авто" }, { value: "manual", label: "На одобрении" }]} /></Field>
        <div className="text-xs text-muted">{f.mode === "auto" ? "Сервис сам выбирает самый сильный свежий клип, который проходит порог, и публикует с учётом лимита и паузы. Клипы, отправленные вручную, тоже уходят." : "Публикуются только клипы, отправленные кнопкой «Опубликовать» во вкладке «Клипы»."}</div>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Мин. балл"><Input type="number" step={0.5} value={f.min_score} onChange={(e) => setF({ ...f, min_score: e.target.value })} /></Field>
          <Field label="Постов в сутки"><Input type="number" value={f.daily_limit} onChange={(e) => setF({ ...f, daily_limit: e.target.value })} /></Field>
          <Field label="Пауза, мин"><Input type="number" value={f.min_interval_min} onChange={(e) => setF({ ...f, min_interval_min: e.target.value })} /></Field>
        </div>
        <Field label="Тихие часы (по Москве)" hint="В это время посты не выходят, клипы копятся.">
          <div className="flex items-center gap-2"><Toggle checked={quiet} onChange={(v) => setF({ ...f, quiet_from: v ? 2 : null, quiet_to: v ? 8 : null })} />
            {quiet && <><Select className="w-24" value={f.quiet_from} onChange={(e) => setF({ ...f, quiet_from: +e.target.value })}>{hours.map((h) => <option key={h} value={h}>с {h}:00</option>)}</Select>
              <Select className="w-24" value={f.quiet_to} onChange={(e) => setF({ ...f, quiet_to: +e.target.value })}>{hours.map((h) => <option key={h} value={h}>до {h}:00</option>)}</Select></>}</div></Field>
        <Field label="Шаблон подписи" hint="{title} {description} {streamer} {link} {hashtags}. Пусто — шаблон по умолчанию.">
          <Textarea rows={4} placeholder={t.default_caption} value={f.caption} onChange={(e) => setF({ ...f, caption: e.target.value })} /></Field>
      </div>
    </div>
    <div className="border-t border-line p-4">
      <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted">Стратегия и безопасность контента</div>
      <PolicyEditor value={f.policy} meta={meta} onChange={(p) => setF({ ...f, policy: p })} />
    </div>
    <div className="flex gap-2 border-t border-line px-4 py-3">
      <Button variant="primary" loading={busy === "save"} onClick={() => save()}>Сохранить</Button><span className="flex-1" />
      <Button variant="ghost" icon={<Trash2 className="size-4" />} onClick={() => confirm(`Удалить площадку «${t.name}»?`) && run("del", () => api(`/api/targets/${t.id}`, { method: "DELETE" })).then(onChange)}>Удалить</Button>
    </div>
  </Card>;
}

export default function Targets() {
  const { data, reload } = useApi<any>("/api/targets"); const { run } = useAction();
  const defaults: Record<Kind, any> = { telegram: { daily_limit: 100, min_score: 8, min_interval_min: 5 }, vk: { daily_limit: 50, min_score: 9, min_interval_min: 10 }, youtube: { daily_limit: 6, min_score: 12, min_interval_min: 60 } };
  const add = (kind: Kind) => run("add", () => api("/api/targets", { body: { kind, name: KIND_LABEL[kind], mode: "auto", ...defaults[kind], config: {} } })).then(reload);
  return <>
    <PageHeader title="Площадки" hint="Площадка включается только после успешной проверки прав. Одна и та же платформа может быть подключена несколько раз (несколько каналов)."
      right={<div className="flex gap-2">{(["telegram", "vk", "youtube"] as Kind[]).map((k) => <Button key={k} icon={<Plus className="size-4" />} onClick={() => add(k)}>{KIND_LABEL[k]}</Button>)}</div>} />
    <div className="space-y-5">{data?.targets.map((t: any) => <TargetCard key={t.id + ":" + (t.checked_at ?? 0) + ":" + t.enabled} t={t} fields={data.fields[t.kind]} meta={data.policy} onChange={reload} />)}</div>
  </>;
}
