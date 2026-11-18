import { Field, Segmented, Select } from "../ui";

type P = { preset: string; profanity: string; categories: Record<string, string>; themes: Record<string, number>; min_virality: number; review_level: number; explore: number; streamers: Record<string, number> };
type Meta = { categories: Record<string, string>; themes: Record<string, string>; presets: Record<string, any> };
const ACT = [{ value: "allow", label: "пропускать" }, { value: "review", label: "на одобрение" }, { value: "block", label: "блокировать" }];

export default function PolicyEditor({ value, meta, onChange }: { value: P; meta: Meta; onChange: (p: P) => void }) {
  const set = (patch: Partial<P>) => onChange({ ...value, ...patch, preset: "preset" in patch ? patch.preset! : "custom" });
  const preset = (name: string) => onChange({ ...value, ...meta.presets[name], categories: { ...value.categories, ...meta.presets[name].categories }, preset: name });
  return <div className="space-y-4">
    <Field label="Пресет" hint="Пресет заполняет правила ниже; любое правило можно поменять, тогда пресет станет «свой».">
      <Segmented value={value.preset} onChange={preset} options={[{ value: "strict", label: "Строго" }, { value: "moderate", label: "Умеренно" }, { value: "soft", label: "Мягко" }, ...(value.preset === "custom" ? [{ value: "custom", label: "Свой" }] : [])]} />
    </Field>
    <div className="grid grid-cols-2 gap-3">
      <Field label="Мат в речи"><Select value={value.profanity} onChange={(e) => set({ profanity: e.target.value })}>
        <option value="allow">оставлять</option><option value="mute">заглушать звук и скрывать в субтитрах</option><option value="block">не публиковать</option></Select></Field>
      <Field label={`Мин. виральность: ${value.min_virality}`} hint="Оценка ИИ-судьи 0–100; без судьи считается по баллу детектора.">
        <input type="range" min={0} max={90} step={5} value={value.min_virality} onChange={(e) => set({ min_virality: +e.target.value })} className="w-full" /></Field>
    </div>
    <Field label="Когда отправлять на одобрение" hint="ИИ ставит каждому риску уровень: 1 — сомнительно, 2 — есть, 3 — явно.">
      <Segmented value={String(value.review_level)} onChange={(v) => set({ review_level: +v })} options={[{ value: "1", label: "при любом сомнении" }, { value: "2", label: "только если риск точно есть" }]} />
    </Field>
    <div>
      <div className="mb-1.5 text-xs font-medium text-muted">Безопасность по категориям</div>
      <div className="divide-y divide-line rounded-lg border border-line">{Object.entries(meta.categories).map(([k, label]) => <div key={k} className="flex items-center gap-3 px-3 py-1.5 text-sm">
        <span className="flex-1">{label}</span><Segmented value={value.categories[k] ?? "review"} onChange={(v) => set({ categories: { ...value.categories, [k]: v } })} options={k === "gambling" ? [...ACT.slice(0, 2), { value: "blur", label: "замазать" }, ACT[2]] : ACT} /></div>)}</div>
    </div>
    <div>
      <div className="mb-1.5 text-xs font-medium text-muted">Что продвигать (вес темы: 0 — не брать, 1 — обычно, 2+ — в приоритете)</div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-2">{Object.entries(meta.themes).map(([k, label]) => <label key={k} className="flex items-center gap-2 text-sm">
        <span className="w-36">{label}</span><input type="range" min={0} max={3} step={0.5} value={value.themes[k] ?? 1} onChange={(e) => set({ themes: { ...value.themes, [k]: +e.target.value } })} className="flex-1" />
        <span className="w-8 text-right tabular-nums text-muted">×{value.themes[k] ?? 1}</span></label>)}</div>
    </div>
    <Field label={`Разведка: ${Math.round(value.explore * 100)}% постов`} hint="Доля постов, где берётся не лучший по оценке клип, а другой тип момента, чтобы модель не зацикливалась.">
      <input type="range" min={0} max={0.3} step={0.05} value={value.explore} onChange={(e) => set({ explore: +e.target.value })} className="w-full" /></Field>
  </div>;
}
