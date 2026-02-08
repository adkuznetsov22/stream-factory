"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Неверный пароль");
      }

      const data = await res.json();
      localStorage.setItem("auth_token", data.token);
      localStorage.setItem("auth_expires", data.expires_at);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка входа");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
      <div style={{ width: "100%", maxWidth: 360, background: "var(--bg-subtle)", borderRadius: "var(--radius-lg)", border: "1px solid var(--border)", padding: 32 }}>
        <div style={{ textAlign: "center", marginBottom: 24 }}>
          <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>Stream Factory</h1>
          <p style={{ color: "var(--fg-subtle)", fontSize: 14 }}>Введите пароль для входа</p>
        </div>

        <form onSubmit={handleLogin}>
          <div style={{ marginBottom: 16 }}>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Пароль"
              style={{ width: "100%", padding: "12px 16px", fontSize: 15 }}
              autoFocus
            />
          </div>

          {error && (
            <div style={{ marginBottom: 16, padding: 12, background: "#ef444420", borderRadius: "var(--radius)", color: "#ef4444", fontSize: 13 }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !password}
            style={{
              width: "100%",
              padding: "12px 20px",
              background: "var(--accent)",
              color: "#fff",
              borderRadius: "var(--radius)",
              fontWeight: 600,
              fontSize: 15,
              opacity: loading || !password ? 0.6 : 1,
            }}
          >
            {loading ? "Вход..." : "Войти"}
          </button>
        </form>
      </div>
    </div>
  );
}
