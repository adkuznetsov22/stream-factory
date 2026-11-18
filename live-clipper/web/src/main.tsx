import { StrictMode, useEffect, useState, createContext, useContext } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter, NavLink, Route, Routes } from "react-router-dom";
import { Activity, Brain as BrainIcon, Clapperboard, Gauge, HeartPulse, LogOut, Pause, Play, Radio, Send, Settings2, Share2, Users } from "lucide-react";
import "./index.css";
import { api, onUnauthorized, useStatus, type Status } from "./api";
import { Button, Card, Dot, Input, ToastProvider, cx, useAction } from "./ui";
import Overview from "./pages/Overview";
import Live from "./pages/Live";
import Clips from "./pages/Clips";
import Publications from "./pages/Publications";
import Targets from "./pages/Targets";
import Streamers from "./pages/Streamers";
import SettingsPage from "./pages/Settings";
import Health from "./pages/Health";
import Brain from "./pages/Brain";

const StatusCtx = createContext<Status | null>(null);
export const useLive = () => useContext(StatusCtx);

const NAV = [
  { to: "/", label: "Обзор", icon: Gauge },
  { to: "/live", label: "Эфир", icon: Radio },
  { to: "/brain", label: "Мозг", icon: BrainIcon },
  { to: "/clips", label: "Клипы", icon: Clapperboard, badge: (s: Status) => s.pending_review },
  { to: "/publications", label: "Публикации", icon: Send },
  { to: "/targets", label: "Площадки", icon: Share2, badge: (s: Status) => s.targets.filter((t) => t.enabled && t.check_ok === 0).length || 0 },
  { to: "/streamers", label: "Стримеры", icon: Users },
  { to: "/settings", label: "Настройки", icon: Settings2 },
  { to: "/health", label: "Здоровье", icon: HeartPulse },
];

function Login({ onDone }: { onDone: () => void }) {
  const [pw, setPw] = useState(""); const { busy, run } = useAction();
  return <div className="grid h-full place-items-center p-4">
    <Card className="w-full max-w-sm p-6">
      <div className="mb-1 flex items-center gap-2 text-lg font-semibold"><Activity className="size-5 text-accent" />Live Clipper</div>
      <p className="mb-5 text-sm text-muted">Вход в панель управления</p>
      <form onSubmit={(e) => { e.preventDefault(); run("login", () => api("/api/login", { body: { password: pw } })).then((r) => r && onDone()); }} className="space-y-3">
        <Input type="password" autoFocus placeholder="Пароль" value={pw} onChange={(e) => setPw(e.target.value)} />
        <Button variant="primary" className="w-full" loading={busy === "login"}>Войти</Button>
      </form>
    </Card>
  </div>;
}

function Shell() {
  const { status, connected } = useStatus();
  const { run, busy } = useAction();
  const paused = status?.publish_paused;
  return <StatusCtx.Provider value={status}>
    <div className="flex h-full">
      <aside className="flex w-56 shrink-0 flex-col border-r border-line bg-panel">
        <div className="flex items-center gap-2 px-4 py-4 font-semibold"><Activity className="size-5 text-accent" />Live Clipper</div>
        <nav className="flex-1 space-y-0.5 px-2">
          {NAV.map((n) => <NavLink key={n.to} to={n.to} end={n.to === "/"} className={({ isActive }) => cx("flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm", isActive ? "bg-panel2 text-fg" : "text-muted hover:bg-panel2/60 hover:text-fg")}>
            <n.icon className="size-4" /><span className="flex-1">{n.label}</span>
            {status && n.badge && n.badge(status) > 0 && <span className="rounded-full bg-accent px-1.5 text-[11px] font-semibold text-white">{n.badge(status)}</span>}
          </NavLink>)}
        </nav>
        <div className="space-y-2 border-t border-line p-3">
          <div className="flex items-center gap-2 text-xs text-muted"><Dot tone={connected ? "ok" : "err"} />{connected ? `онлайн · ${status?.channels.length ?? 0} стримов` : "нет связи с сервером"}</div>
          <Button size="sm" className="w-full" variant={paused ? "primary" : "default"} loading={busy === "pause"} icon={paused ? <Play className="size-3.5" /> : <Pause className="size-3.5" />}
            onClick={() => run("pause", () => api("/api/settings", { method: "PUT", body: { publish_paused: !paused } }), paused ? "Публикация возобновлена" : "Публикация на паузе")}>
            {paused ? "Возобновить публикацию" : "Пауза публикации"}</Button>
          <Button size="sm" variant="ghost" className="w-full" icon={<LogOut className="size-3.5" />} onClick={() => api("/api/logout", { body: {} }).then(() => location.reload())}>Выйти</Button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto">
        {paused && <div className="border-b border-warn/30 bg-warn/10 px-6 py-2 text-sm text-warn">Публикация на паузе: клипы режутся, но никуда не уходят.</div>}
        <div className="mx-auto max-w-[1500px] p-6">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/live" element={<Live />} />
            <Route path="/clips" element={<Clips />} />
            <Route path="/clips/:id" element={<Clips />} />
            <Route path="/publications" element={<Publications />} />
            <Route path="/targets" element={<Targets />} />
            <Route path="/streamers" element={<Streamers />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/health" element={<Health />} />
            <Route path="/brain" element={<Brain />} />
          </Routes>
        </div>
      </main>
    </div>
  </StatusCtx.Provider>;
}

function App() {
  const [auth, setAuth] = useState<boolean | null>(null);
  useEffect(() => { onUnauthorized(() => setAuth(false)); api("/api/status").then(() => setAuth(true)).catch(() => setAuth(false)); }, []);
  if (auth === null) return null;
  return auth ? <HashRouter><Shell /></HashRouter> : <Login onDone={() => setAuth(true)} />;
}

createRoot(document.getElementById("root")!).render(<StrictMode><ToastProvider><App /></ToastProvider></StrictMode>);
