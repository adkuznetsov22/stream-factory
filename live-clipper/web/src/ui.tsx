import { createContext, useCallback, useContext, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Loader2, X } from "lucide-react";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" | "default"; size?: "sm" | "md"; loading?: boolean; icon?: ReactNode };
export function Button({ variant = "default", size = "md", loading, icon, className, children, disabled, ...p }: BtnProps) {
  return (
    <button {...p} disabled={disabled || loading}
      className={cx("inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap",
        size === "sm" ? "h-7 px-2.5 text-xs" : "h-9 px-3.5 text-sm",
        variant === "primary" && "bg-accent text-white hover:bg-accent/85",
        variant === "default" && "bg-panel2 border border-line hover:bg-line text-fg",
        variant === "ghost" && "text-muted hover:text-fg hover:bg-panel2",
        variant === "danger" && "bg-err/10 text-err border border-err/30 hover:bg-err/20", className)}>
      {loading ? <Loader2 className="size-4 animate-spin" /> : icon}{children}
    </button>
  );
}

export const Card = ({ className, children, ...p }: { className?: string; children?: ReactNode } & React.HTMLAttributes<HTMLDivElement>) =>
  <div {...p} className={cx("rounded-xl border border-line bg-panel", className)}>{children}</div>;

export function CardHeader({ title, hint, right }: { title: ReactNode; hint?: ReactNode; right?: ReactNode }) {
  return <div className="flex items-start gap-3 border-b border-line px-4 py-3">
    <div className="min-w-0 flex-1"><div className="font-semibold">{title}</div>{hint && <div className="mt-0.5 text-xs text-muted">{hint}</div>}</div>{right}
  </div>;
}

const TONES = { ok: "bg-ok/12 text-ok border-ok/25", warn: "bg-warn/12 text-warn border-warn/25", err: "bg-err/12 text-err border-err/25",
  accent: "bg-accent/12 text-accent border-accent/25", muted: "bg-panel2 text-muted border-line", info: "bg-accent2/15 text-[#a99bff] border-accent2/30" };
export type Tone = keyof typeof TONES;
export const Badge = ({ tone = "muted", children, className, title }: { tone?: Tone; children: ReactNode; className?: string; title?: string }) =>
  <span title={title} className={cx("inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium leading-none whitespace-nowrap", TONES[tone], className)}>{children}</span>;

export const Dot = ({ tone }: { tone: Tone }) => <span className={cx("inline-block size-2 rounded-full", { ok: "bg-ok", warn: "bg-warn", err: "bg-err", accent: "bg-accent", muted: "bg-muted", info: "bg-accent2" }[tone])} />;

export function Field({ label, hint, children, className }: { label: ReactNode; hint?: ReactNode; children: ReactNode; className?: string }) {
  return <label className={cx("block", className)}>
    <div className="mb-1 text-xs font-medium text-muted">{label}</div>{children}{hint && <div className="mt-1 text-[11px] leading-snug text-muted/80">{hint}</div>}
  </label>;
}

export const inputCls = "h-9 rounded-lg border border-line bg-bg px-3 text-sm outline-none focus:border-accent/60 placeholder:text-muted/60";
const width = (c?: string) => (/(^|\s)w-/.test(c ?? "") ? "" : "w-full");
export const Input = (p: React.InputHTMLAttributes<HTMLInputElement>) => <input {...p} className={cx(inputCls, width(p.className), p.className)} />;
export const Textarea = (p: React.TextareaHTMLAttributes<HTMLTextAreaElement>) =>
  <textarea {...p} className={cx("w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm outline-none focus:border-accent/60", p.className)} />;
export const Select = (p: React.SelectHTMLAttributes<HTMLSelectElement>) => <select {...p} className={cx(inputCls, width(p.className), "pr-8", p.className)} />;

export function Toggle({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label?: ReactNode; disabled?: boolean }) {
  return <button type="button" disabled={disabled} onClick={() => onChange(!checked)} className="inline-flex items-center gap-2 text-sm disabled:opacity-50">
    <span className={cx("relative h-5 w-9 rounded-full transition-colors", checked ? "bg-accent" : "bg-line")}>
      <span className={cx("absolute top-0.5 size-4 rounded-full bg-white transition-all", checked ? "left-4.5" : "left-0.5")} />
    </span>{label}
  </button>;
}

export function Segmented<T extends string>({ value, options, onChange }: { value: T; options: { value: T; label: ReactNode }[]; onChange: (v: T) => void }) {
  return <div className="inline-flex rounded-lg border border-line bg-bg p-0.5">
    {options.map((o) => <button key={o.value} type="button" onClick={() => onChange(o.value)}
      className={cx("rounded-md px-3 py-1 text-xs font-medium", value === o.value ? "bg-panel2 text-fg shadow" : "text-muted hover:text-fg")}>{o.label}</button>)}
  </div>;
}

export function Stat({ label, value, sub, tone, icon }: { label: string; value: ReactNode; sub?: ReactNode; tone?: Tone; icon?: ReactNode }) {
  return <Card className="p-4">
    <div className="flex items-center gap-2 text-xs text-muted">{icon}{label}</div>
    <div className={cx("mt-1.5 text-2xl font-semibold tabular-nums", tone === "ok" && "text-ok", tone === "err" && "text-err", tone === "warn" && "text-warn")}>{value}</div>
    {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
  </Card>;
}

export const Empty = ({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) =>
  <div className="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
    <div className="text-muted">{icon}</div><div className="font-medium">{title}</div>{children && <div className="max-w-md text-sm text-muted">{children}</div>}
  </div>;

export function PageHeader({ title, hint, right }: { title: string; hint?: ReactNode; right?: ReactNode }) {
  return <div className="mb-5 flex flex-wrap items-end gap-3">
    <div className="min-w-0 flex-1"><h1 className="text-xl font-semibold">{title}</h1>{hint && <p className="mt-1 max-w-3xl text-sm text-muted">{hint}</p>}</div>{right}
  </div>;
}

export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean }) {
  if (!open) return null;
  return <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4 backdrop-blur-sm" onMouseDown={onClose}>
    <div onMouseDown={(e) => e.stopPropagation()} className={cx("my-8 w-full rounded-xl border border-line bg-panel shadow-2xl", wide ? "max-w-5xl" : "max-w-lg")}>
      <div className="flex items-center border-b border-line px-4 py-3"><div className="flex-1 font-semibold">{title}</div>
        <button onClick={onClose} className="text-muted hover:text-fg"><X className="size-4" /></button></div>
      <div className="p-4">{children}</div>
    </div>
  </div>;
}

export function Sparkline({ points, threshold, height = 44, moments = [], className }: { points: [number, number][]; threshold: number; height?: number; moments?: [number, number][]; className?: string }) {
  if (points.length < 2) return <div style={{ height }} className={cx("grid place-items-center text-[11px] text-muted", className)}>копим историю…</div>;
  const t0 = points[0][0], t1 = points[points.length - 1][0], span = Math.max(t1 - t0, 1);
  const max = Math.max(threshold * 1.6, ...points.map((p) => p[1]));
  const W = 300, y = (v: number) => height - (Math.max(v, 0) / max) * (height - 4) - 2;
  const d = points.map((p, i) => `${i ? "L" : "M"}${(((p[0] - t0) / span) * W).toFixed(1)},${y(p[1]).toFixed(1)}`).join("");
  return <svg viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" className={cx("w-full", className)} style={{ height }}>
    <defs><linearGradient id="sg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#ff3d8b" stopOpacity=".35" /><stop offset="1" stopColor="#ff3d8b" stopOpacity="0" /></linearGradient></defs>
    <path d={`${d}L${W},${height}L0,${height}Z`} fill="url(#sg)" />
    <path d={d} fill="none" stroke="#ff3d8b" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    <line x1="0" x2={W} y1={y(threshold)} y2={y(threshold)} stroke="#f5b041" strokeDasharray="4 4" strokeWidth="1" vectorEffect="non-scaling-stroke" />
    {moments.filter((m) => m[0] >= t0).map((m) => <circle key={m[0]} cx={((m[0] - t0) / span) * W} cy={y(threshold)} r="3" fill="#2fd38a" />)}
  </svg>;
}

type Toast = { id: number; text: string; tone: Tone };
const ToastCtx = createContext<(text: string, tone?: Tone) => void>(() => {});
export const useToast = () => useContext(ToastCtx);
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: Tone = "ok") => {
    const id = Date.now() + Math.random();
    setItems((x) => [...x, { id, text, tone }]);
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), tone === "err" ? 7000 : 3500);
  }, []);
  return <ToastCtx.Provider value={push}>{children}
    <div className="fixed right-4 bottom-4 z-[60] flex w-96 flex-col gap-2">
      {items.map((t) => <div key={t.id} className={cx("rounded-lg border bg-panel px-4 py-3 text-sm shadow-xl", t.tone === "err" ? "border-err/40 text-err" : t.tone === "warn" ? "border-warn/40" : "border-line")}>{t.text}</div>)}
    </div>
  </ToastCtx.Provider>;
}

export function useAction() {
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const run = async <T,>(key: string, fn: () => Promise<T>, ok?: string): Promise<T | undefined> => {
    setBusy(key);
    try { const r = await fn(); if (ok) toast(ok); return r; }
    catch (e) { toast((e as Error).message, "err"); }
    finally { setBusy(null); }
  };
  return { busy, run };
}
