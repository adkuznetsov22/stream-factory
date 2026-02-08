import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Stream Factory",
  description: "Video Pipeline Automation",
};

const navItems = [
  { href: "/", label: "Аккаунты", icon: "👤" },
  { href: "/projects", label: "Проекты", icon: "📁" },
  { href: "/presets", label: "Пресеты", icon: "⚙️" },
  { href: "/queue", label: "Очередь", icon: "📋" },
  { href: "/moderation", label: "Модерация", icon: "✅" },
  { href: "/dashboard", label: "Статистика", icon: "📊" },
];

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet" />
      </head>
      <body>
        <div style={{ display: "flex", minHeight: "100vh" }}>
          {/* Sidebar */}
          <aside style={{
            width: 220,
            background: "var(--bg-subtle)",
            borderRight: "1px solid var(--border)",
            display: "flex",
            flexDirection: "column",
            position: "fixed",
            top: 0,
            left: 0,
            bottom: 0,
          }}>
            {/* Logo */}
            <div style={{
              padding: "20px 16px",
              borderBottom: "1px solid var(--border)",
            }}>
              <Link href="/" style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                color: "var(--fg)",
                fontWeight: 600,
                fontSize: 15,
                textDecoration: "none",
              }}>
                <div style={{
                  width: 28,
                  height: 28,
                  background: "var(--primary)",
                  borderRadius: 6,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5">
                    <polygon points="5 3 19 12 5 21 5 3"/>
                  </svg>
                </div>
                Stream Factory
              </Link>
            </div>

            {/* Navigation */}
            <nav style={{ flex: 1, padding: "12px 8px" }}>
              {navItems.map((item) => (
                <Link key={item.href} href={item.href} className="nav-link">
                  <span style={{ fontSize: 14, width: 20, textAlign: "center" }}>{item.icon}</span>
                  {item.label}
                </Link>
              ))}
            </nav>

            {/* Footer */}
            <div style={{
              padding: "12px 16px",
              borderTop: "1px solid var(--border)",
              fontSize: 11,
              color: "var(--fg-subtle)",
            }}>
              v1.0.0
            </div>
          </aside>

          {/* Main content */}
          <main style={{
            flex: 1,
            marginLeft: 220,
            minHeight: "100vh",
            background: "var(--bg)",
          }}>
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
