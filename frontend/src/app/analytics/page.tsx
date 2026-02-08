"use client";

import { useEffect, useMemo, useState } from "react";

/* ── Types ─────────────────────────────────────────────── */

type PerformanceItem = {
  candidate_id: number;
  virality_score: number;
  title: string | null;
  platform: string;
  views: number;
  likes: number;
  comments: number;
  shares: number | null;
  hours_since_publish: number;
  age_bucket: string;
  performance_rate: { views_per_hour: number; like_rate: number; comment_rate: number };
  published_url: string | null;
};

type Calibration = {
  correlation: number | null;
  auto_approve_threshold: number | null;
  factor_correlations: Record<string, number>;
  top_factors: string[];
  weak_factors: string[];
  platforms: Record<string, { correlation: number | null; threshold: number | null; count: number; avg_vph: number | null }>;
  buckets: Record<string, { correlation: number | null; count: number; avg_vph: number | null }>;
  data_points: number;
  sufficient_data: boolean;
  calibrated_at: string | null;
};

type Project = { id: number; name: string };

const AGE_BUCKETS = ["all", "0-6h", "6-24h", "1-3d", "3-7d", "7d+"];
const PLATFORMS = ["all", "youtube", "tiktok", "instagram", "vk"];

/* ── Scatter Plot (pure SVG) ──────────────────────────── */

function ScatterPlot({
  data,
  threshold,
}: {
  data: PerformanceItem[];
  threshold: number | null;
}) {
  const W = 600, H = 360, PAD = { t: 20, r: 20, b: 40, l: 60 };
  const pw = W - PAD.l - PAD.r;
  const ph = H - PAD.t - PAD.b;

  const maxScore = Math.max(...data.map(d => d.virality_score), 1);
  const maxVph = Math.max(...data.map(d => d.performance_rate.views_per_hour), 1);

  const x = (score: number) => PAD.l + (score / maxScore) * pw;
  const y = (vph: number) => PAD.t + ph - (vph / maxVph) * ph;

  const platformColor: Record<string, string> = {
    youtube: "#ef4444",
    tiktok: "#000000",
    instagram: "#e1306c",
    vk: "#0077ff",
  };

  const gridLinesX = 5;
  const gridLinesY = 5;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", maxWidth: 700 }}>
      {/* Grid */}
      {Array.from({ length: gridLinesX + 1 }).map((_, i) => {
        const gx = PAD.l + (i / gridLinesX) * pw;
        return <line key={`gx${i}`} x1={gx} y1={PAD.t} x2={gx} y2={PAD.t + ph} stroke="var(--border)" strokeWidth={0.5} />;
      })}
      {Array.from({ length: gridLinesY + 1 }).map((_, i) => {
        const gy = PAD.t + (i / gridLinesY) * ph;
        return <line key={`gy${i}`} x1={PAD.l} y1={gy} x2={PAD.l + pw} y2={gy} stroke="var(--border)" strokeWidth={0.5} />;
      })}

      {/* Threshold line */}
      {threshold != null && threshold > 0 && (
        <>
          <line
            x1={x(threshold)} y1={PAD.t} x2={x(threshold)} y2={PAD.t + ph}
            stroke="#22c55e" strokeWidth={1.5} strokeDasharray="6 3"
          />
          <text x={x(threshold) + 4} y={PAD.t + 12} fill="#22c55e" fontSize={10} fontWeight={600}>
            threshold {threshold.toFixed(2)}
          </text>
        </>
      )}

      {/* Points */}
      {data.map((d, i) => (
        <g key={i}>
          <circle
            cx={x(d.virality_score)}
            cy={y(d.performance_rate.views_per_hour)}
            r={4}
            fill={platformColor[d.platform] || "var(--accent)"}
            opacity={0.7}
            stroke="white"
            strokeWidth={0.5}
          />
          <title>
            {`#${d.candidate_id} ${d.title || ""}\n${d.platform} | score: ${d.virality_score} | VPH: ${d.performance_rate.views_per_hour}\n${d.age_bucket} | views: ${d.views}`}
          </title>
        </g>
      ))}

      {/* Axes labels */}
      {Array.from({ length: gridLinesX + 1 }).map((_, i) => {
        const val = (i / gridLinesX) * maxScore;
        return (
          <text key={`lx${i}`} x={PAD.l + (i / gridLinesX) * pw} y={H - 8} textAnchor="middle" fontSize={10} fill="var(--fg-subtle)">
            {val.toFixed(1)}
          </text>
        );
      })}
      {Array.from({ length: gridLinesY + 1 }).map((_, i) => {
        const val = ((gridLinesY - i) / gridLinesY) * maxVph;
        return (
          <text key={`ly${i}`} x={PAD.l - 8} y={PAD.t + (i / gridLinesY) * ph + 4} textAnchor="end" fontSize={10} fill="var(--fg-subtle)">
            {val >= 1000 ? `${(val / 1000).toFixed(1)}k` : val.toFixed(0)}
          </text>
        );
      })}

      {/* Axis titles */}
      <text x={PAD.l + pw / 2} y={H} textAnchor="middle" fontSize={11} fill="var(--fg-subtle)" fontWeight={500}>
        Virality Score
      </text>
      <text
        x={12} y={PAD.t + ph / 2}
        textAnchor="middle" fontSize={11} fill="var(--fg-subtle)" fontWeight={500}
        transform={`rotate(-90, 12, ${PAD.t + ph / 2})`}
      >
        Views / Hour
      </text>
    </svg>
  );
}

/* ── Deviation Table ──────────────────────────────────── */

function DeviationTable({ data, title, color }: { data: PerformanceItem[]; title: string; color: string }) {
  if (!data.length) return null;
  return (
    <div style={{ background: "var(--bg-subtle)", borderRadius: "var(--radius-lg)", border: "1px solid var(--border)" }}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)", fontWeight: 600, fontSize: 13, color }}>{title}</div>
      <div style={{ padding: 8 }}>
        {data.slice(0, 10).map((d, i) => (
          <div
            key={d.candidate_id}
            style={{
              display: "grid",
              gridTemplateColumns: "28px 2fr 80px 80px 80px 60px",
              alignItems: "center",
              padding: "8px 10px",
              borderRadius: 6,
              background: i % 2 === 0 ? "var(--bg-muted)" : "transparent",
              fontSize: 12,
            }}
          >
            <span style={{ color: "var(--fg-subtle)", fontWeight: 500 }}>#{i + 1}</span>
            <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {d.published_url ? (
                <a href={d.published_url} target="_blank" rel="noreferrer" style={{ color: "var(--accent)", textDecoration: "none" }}>
                  {d.title || `Candidate #${d.candidate_id}`}
                </a>
              ) : (
                <span>{d.title || `Candidate #${d.candidate_id}`}</span>
              )}
            </div>
            <span style={{ textAlign: "right", fontWeight: 600 }}>{d.virality_score.toFixed(2)}</span>
            <span style={{ textAlign: "right" }}>{d.performance_rate.views_per_hour.toFixed(0)} vph</span>
            <span style={{ textAlign: "right", color: "var(--fg-subtle)" }}>{d.views.toLocaleString()} views</span>
            <span style={{
              textAlign: "center",
              padding: "2px 6px",
              borderRadius: 10,
              background: `${platformColors[d.platform] || "var(--accent)"}18`,
              color: platformColors[d.platform] || "var(--accent)",
              fontSize: 10,
              fontWeight: 600,
            }}>
              {d.platform}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

const platformColors: Record<string, string> = {
  youtube: "#ef4444",
  tiktok: "#000000",
  instagram: "#e1306c",
  vk: "#0077ff",
};

/* ── Main Page ────────────────────────────────────────── */

export default function AnalyticsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [platform, setPlatform] = useState("all");
  const [ageBucket, setAgeBucket] = useState("all");
  const [data, setData] = useState<PerformanceItem[]>([]);
  const [calibration, setCalibration] = useState<Calibration | null>(null);
  const [loading, setLoading] = useState(false);
  const [calibrating, setCalibrating] = useState(false);

  // Load projects list
  useEffect(() => {
    fetch("/api/projects").then(r => r.ok ? r.json() : []).then((list: Project[]) => {
      setProjects(list);
      if (list.length > 0 && !projectId) setProjectId(list[0].id);
    });
  }, []);

  // Load data when filters change
  useEffect(() => {
    if (!projectId) return;
    setLoading(true);

    const params = new URLSearchParams();
    if (platform !== "all") params.set("platform", platform);
    if (ageBucket !== "all") params.set("age_bucket", ageBucket);
    const qs = params.toString() ? `?${params}` : "";

    Promise.all([
      fetch(`/api/projects/${projectId}/analytics/score-vs-performance${qs}`).then(r => r.ok ? r.json() : []),
      fetch(`/api/projects/${projectId}/analytics/calibration`).then(r => r.ok ? r.json() : null),
    ]).then(([perfData, calData]) => {
      setData(perfData);
      setCalibration(calData);
      setLoading(false);
    });
  }, [projectId, platform, ageBucket]);

  // Force re-calibrate
  const handleCalibrate = async () => {
    if (!projectId) return;
    setCalibrating(true);
    const res = await fetch(`/api/projects/${projectId}/analytics/calibrate`, { method: "POST" });
    if (res.ok) setCalibration(await res.json());
    setCalibrating(false);
  };

  // Compute deviations: score vs normalized VPH
  const { overperformers, underperformers } = useMemo(() => {
    if (data.length < 3) return { overperformers: [], underperformers: [] };

    const maxVph = Math.max(...data.map(d => d.performance_rate.views_per_hour), 1);
    const maxScore = Math.max(...data.map(d => d.virality_score), 1);

    const withDeviation = data.map(d => {
      const normScore = d.virality_score / maxScore;
      const normVph = d.performance_rate.views_per_hour / maxVph;
      const deviation = normVph - normScore; // positive = overperformer
      return { ...d, deviation };
    });

    withDeviation.sort((a, b) => b.deviation - a.deviation);
    return {
      overperformers: withDeviation.slice(0, 10),
      underperformers: withDeviation.slice(-10).reverse(),
    };
  }, [data]);

  const fmtCorr = (r: number | null) => r == null ? "—" : (r >= 0 ? "+" : "") + r.toFixed(3);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Аналитика скоринга</h1>
          <p style={{ color: "var(--fg-subtle)", marginTop: 4, fontSize: 13 }}>
            Корреляция virality_score и реальной эффективности
          </p>
        </div>
      </div>

      {/* ── Filters ────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap", alignItems: "center" }}>
        <select
          value={projectId ?? ""}
          onChange={e => setProjectId(Number(e.target.value))}
          style={{
            padding: "6px 12px", borderRadius: 8, border: "1px solid var(--border)",
            background: "var(--bg-subtle)", color: "var(--fg)", fontSize: 13,
          }}
        >
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>

        <div className="filter-tabs">
          {PLATFORMS.map(p => (
            <button key={p} className={`filter-tab ${platform === p ? "active" : ""}`} onClick={() => setPlatform(p)}>
              {p === "all" ? "Все" : p}
            </button>
          ))}
        </div>

        <div className="filter-tabs">
          {AGE_BUCKETS.map(b => (
            <button key={b} className={`filter-tab ${ageBucket === b ? "active" : ""}`} onClick={() => setAgeBucket(b)}>
              {b === "all" ? "Все" : b}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="empty">Загрузка...</div>
      ) : (
        <>
          {/* ── Calibration cards ──────────────────────── */}
          {calibration && calibration.sufficient_data && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
              <div className="card" style={{ padding: 16 }}>
                <div style={{ fontSize: 12, color: "var(--fg-subtle)", marginBottom: 4 }}>Корреляция (r)</div>
                <div style={{
                  fontSize: 24, fontWeight: 600,
                  color: (calibration.correlation ?? 0) > 0.5 ? "#22c55e" : (calibration.correlation ?? 0) > 0.2 ? "#eab308" : "#ef4444",
                }}>
                  {fmtCorr(calibration.correlation)}
                </div>
              </div>
              <div className="card" style={{ padding: 16 }}>
                <div style={{ fontSize: 12, color: "var(--fg-subtle)", marginBottom: 4 }}>Порог автопрува</div>
                <div style={{ fontSize: 24, fontWeight: 600, color: "#22c55e" }}>
                  {calibration.auto_approve_threshold?.toFixed(2) ?? "—"}
                </div>
              </div>
              <div className="card" style={{ padding: 16 }}>
                <div style={{ fontSize: 12, color: "var(--fg-subtle)", marginBottom: 4 }}>Точек данных</div>
                <div style={{ fontSize: 24, fontWeight: 600 }}>{calibration.data_points}</div>
              </div>
              <div className="card" style={{ padding: 16 }}>
                <div style={{ fontSize: 12, color: "var(--fg-subtle)", marginBottom: 4 }}>Топ-факторы</div>
                <div style={{ fontSize: 13, fontWeight: 500, lineHeight: 1.5 }}>
                  {calibration.top_factors.length > 0
                    ? calibration.top_factors.map(f => (
                        <span key={f} style={{
                          display: "inline-block", padding: "2px 8px", borderRadius: 10, marginRight: 4, marginBottom: 2,
                          background: "#22c55e18", color: "#22c55e", fontSize: 11, fontWeight: 600,
                        }}>{f} {fmtCorr(calibration.factor_correlations[f])}</span>
                      ))
                    : <span style={{ color: "var(--fg-subtle)" }}>—</span>
                  }
                </div>
              </div>
            </div>
          )}

          {/* Recalibrate button */}
          <div style={{ display: "flex", gap: 8, marginBottom: 20, alignItems: "center" }}>
            <button
              onClick={handleCalibrate}
              disabled={calibrating}
              style={{
                padding: "6px 16px", borderRadius: 8, border: "1px solid var(--border)",
                background: "var(--bg-subtle)", color: "var(--fg)", fontSize: 12, cursor: "pointer",
              }}
            >
              {calibrating ? "Калибровка..." : "Пересчитать калибровку"}
            </button>
            {calibration?.calibrated_at && (
              <span style={{ fontSize: 11, color: "var(--fg-subtle)" }}>
                Обновлено: {new Date(calibration.calibrated_at).toLocaleString("ru")}
              </span>
            )}
          </div>

          {/* ── Scatter Plot + Factor panel ────────────── */}
          <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16, marginBottom: 24 }}>
            <div style={{
              background: "var(--bg-subtle)", borderRadius: "var(--radius-lg)",
              border: "1px solid var(--border)", padding: 20,
            }}>
              <div style={{ fontWeight: 600, marginBottom: 12 }}>
                Score vs Views/Hour
                <span style={{ fontWeight: 400, fontSize: 12, color: "var(--fg-subtle)", marginLeft: 8 }}>
                  {data.length} точек
                </span>
              </div>
              {data.length > 0 ? (
                <>
                  <ScatterPlot data={data} threshold={calibration?.auto_approve_threshold ?? null} />
                  {/* Legend */}
                  <div style={{ display: "flex", gap: 16, marginTop: 8, justifyContent: "center" }}>
                    {Object.entries(platformColors).map(([p, c]) => (
                      <div key={p} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11 }}>
                        <div style={{ width: 8, height: 8, borderRadius: "50%", background: c }} />
                        {p}
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <div style={{ padding: 40, textAlign: "center", color: "var(--fg-subtle)" }}>
                  Нет данных. Опубликуйте видео и дождитесь синка метрик.
                </div>
              )}
            </div>

            {/* Factor correlations */}
            <div style={{
              background: "var(--bg-subtle)", borderRadius: "var(--radius-lg)",
              border: "1px solid var(--border)", padding: 20,
            }}>
              <div style={{ fontWeight: 600, marginBottom: 12 }}>Факторы</div>
              {calibration && Object.keys(calibration.factor_correlations).length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {Object.entries(calibration.factor_correlations).map(([factor, corr]) => {
                    const absCorr = Math.abs(corr);
                    const color = corr > 0.1 ? "#22c55e" : corr < -0.1 ? "#ef4444" : "var(--fg-subtle)";
                    return (
                      <div key={factor} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <div style={{ width: 90, fontSize: 12, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis" }}>{factor}</div>
                        <div style={{ flex: 1, height: 6, background: "var(--bg-muted)", borderRadius: 3, overflow: "hidden" }}>
                          <div style={{
                            width: `${Math.min(absCorr * 100, 100)}%`,
                            height: "100%", borderRadius: 3, background: color,
                          }} />
                        </div>
                        <div style={{ width: 50, fontSize: 11, fontWeight: 600, color, textAlign: "right" }}>
                          {fmtCorr(corr)}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div style={{ color: "var(--fg-subtle)", fontSize: 13 }}>
                  {calibration?.sufficient_data === false
                    ? `Недостаточно данных (${calibration.data_points}/${5})`
                    : "Нет данных о факторах"}
                </div>
              )}

              {/* Per-platform thresholds */}
              {calibration?.platforms && Object.keys(calibration.platforms).length > 0 && (
                <>
                  <div style={{ fontWeight: 600, marginTop: 20, marginBottom: 8, fontSize: 13 }}>Пороги по платформам</div>
                  {Object.entries(calibration.platforms).map(([plat, stats]) => (
                    <div key={plat} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", fontSize: 12 }}>
                      <span style={{ color: platformColors[plat] || "var(--fg)", fontWeight: 500 }}>{plat}</span>
                      <span>
                        <span style={{ fontWeight: 600 }}>{stats.threshold?.toFixed(2) ?? "—"}</span>
                        <span style={{ color: "var(--fg-subtle)", marginLeft: 6 }}>r={fmtCorr(stats.correlation)}</span>
                        <span style={{ color: "var(--fg-subtle)", marginLeft: 6 }}>n={stats.count}</span>
                      </span>
                    </div>
                  ))}
                </>
              )}
            </div>
          </div>

          {/* ── Top-10 Overperformers & Underperformers ── */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 24 }}>
            <DeviationTable
              data={overperformers}
              title="Overperformers (score низкий, просмотры высокие)"
              color="#22c55e"
            />
            <DeviationTable
              data={underperformers}
              title="Underperformers (score высокий, просмотров мало)"
              color="#ef4444"
            />
          </div>

          {/* ── Weak factors callout ─────────────────── */}
          {calibration && calibration.weak_factors.length > 0 && (
            <div style={{
              background: "#eab30810", border: "1px solid #eab30840", borderRadius: "var(--radius-lg)",
              padding: 16, marginBottom: 24,
            }}>
              <div style={{ fontWeight: 600, fontSize: 13, color: "#eab308", marginBottom: 4 }}>
                Слабые факторы (|r| &lt; 0.05)
              </div>
              <div style={{ fontSize: 12, color: "var(--fg-subtle)" }}>
                Эти факторы не коррелируют с реальными просмотрами — можно снизить их вес в формуле скоринга:
                {" "}
                {calibration.weak_factors.map(f => (
                  <span key={f} style={{
                    display: "inline-block", padding: "2px 8px", borderRadius: 10, marginRight: 4,
                    background: "#eab30818", color: "#eab308", fontSize: 11, fontWeight: 600,
                  }}>{f}</span>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
