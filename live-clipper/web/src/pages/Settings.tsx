import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { api, useApi } from "../api";
import { Button, Card, CardHeader, Field, Input, PageHeader, Select, Toggle, useAction } from "../ui";

function Tags({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const [t, setT] = useState("");
  const add = () => { const v = "#" + t.trim().replace(/^#/, ""); if (v.length > 1 && !value.includes(v)) onChange([...value, v]); setT(""); };
  return <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-lg border border-line bg-bg px-2 py-1.5">
    {value.map((x) => <span key={x} className="inline-flex items-center gap-1 rounded bg-panel2 px-2 py-0.5 text-xs">{x}<button onClick={() => onChange(value.filter((y) => y !== x))}><X className="size-3" /></button></span>)}
    <input className="min-w-24 flex-1 bg-transparent text-sm outline-none" placeholder="добавить и Enter" value={t} onChange={(e) => setT(e.target.value)}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); } }} onBlur={add} />
  </div>;
}
export { Tags };

export default function SettingsPage() {
  const { data, setData } = useApi<any>("/api/settings");
  const [f, setF] = useState<any>(null); const { busy, run } = useAction();
  useEffect(() => { data && setF(data); }, [data]);
  if (!f) return null;
  const set = (k: string) => (v: any) => setF({ ...f, [k]: v });
  const n = (k: string, step = 1) => <Input type="number" step={step} value={f[k]} onChange={(e) => set(k)(e.target.value === "" ? "" : +e.target.value)} />;
  const dirty = JSON.stringify(f) !== JSON.stringify(data);
  return <>
    <PageHeader title="Настройки" hint="Применяются сразу, без перезапуска."
      right={<Button variant="primary" disabled={!dirty} loading={busy === "s"} onClick={() => run("s", () => api("/api/settings", { method: "PUT", body: f }), "Настройки сохранены").then((r) => r && setData(r))}>Сохранить</Button>} />
    <div className="grid gap-5 xl:grid-cols-2">
      <Card><CardHeader title="Детектор моментов" hint="Балл = всплеск чата + половина всплеска звука относительно последних 5 минут этого стрима." />
        <div className="grid gap-4 p-4 sm:grid-cols-2">
          <Field label="Порог балла" hint="Ниже — больше клипов, выше — только самые яркие. Для каждого стримера можно поправить чувствительность.">{n("trigger_score", 0.5)}</Field>
          <Field label="Пауза между клипами одного стримера, с">{n("cooldown")}</Field>
          <Field label="Разогрев после старта записи, с" hint="Сколько копить базовую активность чата перед первым клипом.">{n("warmup_seconds")}</Field>
          <Field label="Задержка реакции чата, с" hint="Чат реагирует позже картинки.">{n("reaction_delay", 0.5)}</Field>
          <Field label="Секунд до момента">{n("clip_before")}</Field>
          <Field label="Секунд после момента">{n("clip_after")}</Field>
          <Field label="Окно поиска дублей, с" hint="Совместные стримы: один момент у двух стримеров публикуется один раз.">{n("dedup_window")}</Field>
          <Field label="Запас исходника для монтажа, с" hint="Сколько секунд вокруг клипа сохранять, чтобы можно было сдвинуть начало.">{n("source_padding")}</Field>
        </div></Card>
      <Card><CardHeader title="Ролик" />
        <div className="space-y-4 p-4">
          <Field label="Раскладка по умолчанию" hint="Для стримеров с отмеченной вебкой можно выбрать «вебка сверху» в их профиле."><Select value={f.layout} onChange={(e) => set("layout")(e.target.value)}>
            <option value="blur">геймплей по центру, размытый фон</option><option value="full">игра на весь экран</option><option value="facecam">вебка сверху, игра снизу</option></Select></Field>
          <div><Toggle checked={f.subtitles} onChange={set("subtitles")} label="Субтитры по речи стримера" /></div>
          <div><Toggle checked={f.mask_subtitles} onChange={set("mask_subtitles")} label="Скрывать мат в субтитрах (б***)" /></div>
          <Field label="Хэштеги для всех площадок"><Tags value={f.hashtags} onChange={set("hashtags")} /></Field>
        </div></Card>
      <Card><CardHeader title="Заголовки" hint="Без ключа заголовок собирается из речи стримера по шаблону. С ключом его пишет нейросеть по речи и чату." />
        <div className="grid gap-4 p-4 sm:grid-cols-2">
          <Field label="Ключ OpenRouter"><Input value={f.openrouter_api_key ?? ""} placeholder="sk-or-…" onChange={(e) => set("openrouter_api_key")(e.target.value || null)} /></Field>
          <Field label="Модель"><Input value={f.openrouter_model} onChange={(e) => set("openrouter_model")(e.target.value)} /></Field>
        </div></Card>
      <Card><CardHeader title="Публикация и хранение" />
        <div className="grid gap-4 p-4 sm:grid-cols-2">
          <Field label="Авто-режим берёт клипы не старше, мин" hint="Чтобы не выкладывать протухшее.">{n("max_publish_age_min")}</Field>
          <Field label="Хранить исходники для монтажа, ч">{n("retention_source_hours")}</Field>
          <Field label="Хранить неопубликованные клипы, ч">{n("retention_hours")}</Field>
          <Field label="Хранить опубликованные клипы, ч">{n("retention_published_hours")}</Field>
        </div></Card>
    </div>
  </>;
}
