"use client";

import { useEffect, useRef, useState } from "react";
import { useTrackingRefresh } from "@/shared/contexts/TrackingRefreshContext";
import { http } from "@/shared/lib/http";
import { getErrorMessage } from "@/shared/lib/errors";
import { CATEGORY_LABELS } from "@/shared/lib/collections";
import LearningPathView from "./LearningPathView";

// ── Types ────────────────────────────────────────────────────

interface CategoryStat {
  category: string;
  avg_mastery: number;
  avg_score: number;
  total_points: number;
  tracked_points: number;
  mastered: number;
  weak: number;
}

interface WeakPoint {
  id: number;
  name: string;
  category: string;
  chapter: string;
  mastery: number;
  confidence: number;
  effective_score: number;
  interaction_count: number;
}

interface Recommendation {
  weak_point: string;
  category: string;
  effective_score: number;
  prerequisites: { name: string; category: string }[];
  reason: string;
}

interface CategoryDetail {
  category: string;
  total_points: number;
  tracked_points: number;
  avg_mastery: number;
  chapters: Record<string, KnowledgePointDetail[]>;
}

interface KnowledgePointDetail {
  id: number;
  name: string;
  chapter: string;
  difficulty: number;
  mastery: number;
  confidence: number;
  effective_score: number;
  interaction_count: number;
  tracked: boolean;
}

interface TrendPoint {
  date: string;
  avg_mastery: number;
  avg_effective_score: number;
  event_count: number;
  event_types: string[];
}

interface RecentInteraction {
  id: number;
  name: string;
  category: string;
  mastery: number;
  effective_score: number;
  interaction_count: number;
  source: string;
  time_ago: string;
}

// ── Radar Chart (pure SVG) ───────────────────────────────────

function RadarChart({ data }: { data: CategoryStat[] }) {
  if (data.length < 3) return null;

  const size = 280;
  const cx = size / 2;
  const cy = size / 2;
  const r = 110;
  const n = data.length;
  const angleStep = (2 * Math.PI) / n;

  const point = (i: number, value: number) => {
    const angle = -Math.PI / 2 + i * angleStep;
    const clamped = Math.max(0, Math.min(1, value));
    const dist = r * clamped;
    return { x: cx + dist * Math.cos(angle), y: cy + dist * Math.sin(angle) };
  };

  // Grid rings
  const rings = [0.2, 0.4, 0.6, 0.8, 1.0];

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {rings.map((ring) => (
        <polygon
          key={ring}
          points={Array.from({ length: n }, (_, i) => {
            const p = point(i, ring);
            return `${p.x},${p.y}`;
          }).join(" ")}
          fill="none"
          stroke="#e2e8f0"
          strokeWidth={1}
        />
      ))}
      {/* Axes */}
      {data.map((_, i) => {
        const p = point(i, 1);
        return (
          <line key={i} x1={cx} y1={cy} x2={p.x} y2={p.y} stroke="#cbd5e1" strokeWidth={1} />
        );
      })}
      {/* Data polygon */}
      <polygon
        points={data
          .map((d, i) => {
            const p = point(i, d.avg_score);
            return `${p.x},${p.y}`;
          })
          .join(" ")}
        fill="rgba(59,130,246,0.15)"
        stroke="#3b82f6"
        strokeWidth={2}
      />
      {/* Data dots + labels */}
      {data.map((d, i) => {
        const p = point(i, d.avg_score);
        const lp = point(i, 1.25);
        return (
          <g key={i}>
            <circle cx={p.x} cy={p.y} r={4} fill="#3b82f6" />
            <text
              x={lp.x}
              y={lp.y}
              textAnchor="middle"
              dominantBaseline="middle"
              className="text-xs fill-slate-600"
              fontSize={11}
            >
              {CATEGORY_LABELS[d.category] || d.category}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ── Mastery bar ──────────────────────────────────────────────

function MasteryBar({ value, label }: { value: number; label?: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  const color =
    pct >= 60 ? "bg-emerald-500" : pct >= 30 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      {label && <span className="w-24 text-xs text-slate-500 truncate">{label}</span>}
      <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-slate-600 w-10 text-right">{pct}%</span>
    </div>
  );
}

// ── Mastery Trend Chart (pure SVG) ──────────────────────────────

function MasteryTrendChart({ data }: { data: TrendPoint[] }) {
  if (data.length < 2) {
    return (
      <div className="flex items-center justify-center h-[160px] text-xs text-slate-400">
        {data.length === 0 ? "暂无趋势数据，开始学习后将记录掌握度变化" : "数据不足，至少需要2个数据点"}
      </div>
    );
  }

  const W = 480;
  const H = 160;
  const padL = 36;
  const padR = 12;
  const padT = 12;
  const padB = 24;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  // X: date index, Y: 0~1
  const xStep = plotW / (data.length - 1);
  const toX = (i: number) => padL + i * xStep;
  const toY = (v: number) => padT + plotH * (1 - Math.max(0, Math.min(1, v)));

  // Mastery line
  const masteryPath = data.map((d, i) => `${i === 0 ? "M" : "L"}${toX(i)},${toY(d.avg_mastery)}`).join(" ");
  // Effective score line
  const scorePath = data.map((d, i) => `${i === 0 ? "M" : "L"}${toX(i)},${toY(d.avg_effective_score)}`).join(" ");

  // Area fill under mastery
  const areaPath = masteryPath + ` L${toX(data.length - 1)},${padT + plotH} L${padL},${padT + plotH} Z`;

  // Grid lines at 0.2, 0.4, 0.6, 0.8
  const gridLines = [0.2, 0.4, 0.6, 0.8].map((v) => (
    <line key={v} x1={padL} y1={toY(v)} x2={W - padR} y2={toY(v)} stroke="#e2e8f0" strokeWidth={0.5} />
  ));

  // Y-axis labels
  const yLabels = [0, 0.2, 0.4, 0.6, 0.8, 1.0].map((v) => (
    <text key={v} x={padL - 4} y={toY(v)} textAnchor="end" dominantBaseline="middle" fontSize={9} fill="#94a3b8">
      {Math.round(v * 100)}%
    </text>
  ));

  // X-axis date labels (show first, last, and some middle ones)
  const xLabels = data.length <= 8
    ? data.map((d, i) => (
        <text key={i} x={toX(i)} y={H - 2} textAnchor="middle" fontSize={8} fill="#94a3b8">
          {d.date.slice(5)}
        </text>
      ))
    : [0, Math.floor(data.length / 2), data.length - 1].map((idx) => (
        <text key={idx} x={toX(idx)} y={H - 2} textAnchor="middle" fontSize={8} fill="#94a3b8">
          {data[idx].date.slice(5)}
        </text>
      ));

  // Data dots with event count
  const dots = data.map((d, i) => {
    const isUp = i === 0 ? d.avg_mastery > 0 : d.avg_mastery >= data[i - 1].avg_mastery;
    return (
      <g key={i}>
        <circle cx={toX(i)} cy={toY(d.avg_mastery)} r={3} fill={isUp ? "#10b981" : "#ef4444"} />
        {d.event_count > 1 && (
          <circle cx={toX(i)} cy={toY(d.avg_mastery)} r={5} fill="none" stroke={isUp ? "#10b981" : "#ef4444"} strokeWidth={0.5} opacity={0.4} />
        )}
      </g>
    );
  });

  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="w-full">
      {/* Grid */}
      {gridLines}
      {/* Y labels */}
      {yLabels}
      {/* Area fill */}
      <path d={areaPath} fill="rgba(59,130,246,0.08)" />
      {/* Mastery line */}
      <path d={masteryPath} fill="none" stroke="#3b82f6" strokeWidth={2} />
      {/* Effective score line (dashed) */}
      <path d={scorePath} fill="none" stroke="#f59e0b" strokeWidth={1.5} strokeDasharray="4 2" />
      {/* Dots */}
      {dots}
      {/* X labels */}
      {xLabels}
      {/* Legend */}
      <line x1={padL + 4} y1={padT + 4} x2={padL + 20} y2={padT + 4} stroke="#3b82f6" strokeWidth={2} />
      <text x={padL + 24} y={padT + 7} fontSize={9} fill="#64748b">掌握度</text>
      <line x1={padL + 68} y1={padT + 4} x2={padL + 84} y2={padT + 4} stroke="#f59e0b" strokeWidth={1.5} strokeDasharray="4 2" />
      <text x={padL + 88} y={padT + 7} fontSize={9} fill="#64748b">有效分</text>
    </svg>
  );
}

// ── Main Panel ───────────────────────────────────────────────

type TrackingPanelProps = {
  onGenerateSimilarPractice?: (topic: string) => void;
};

export default function TrackingPanel({ onGenerateSimilarPractice }: TrackingPanelProps) {
  const { refreshVersion } = useTrackingRefresh();
  const [profile, setProfile] = useState<CategoryStat[]>([]);
  const [weakPoints, setWeakPoints] = useState<WeakPoint[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [recentInteractions, setRecentInteractions] = useState<RecentInteraction[]>([]);
  const [trendData, setTrendData] = useState<TrendPoint[]>([]);
  const [trendCategory, setTrendCategory] = useState<string>("");
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  const [categoryDetail, setCategoryDetail] = useState<CategoryDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  // Fetch profile + weak points + recommendations
  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const [pRes, wRes, rRes, recentRes, trendRes] = await Promise.all([
          http.get("/api/tracking/profile"),
          http.get("/api/tracking/weak-points", { params: { threshold: 0.3, limit: 10 } }),
          http.get("/api/tracking/recommendations", { params: { limit: 5 } }),
          http.get("/api/tracking/recent", { params: { limit: 20 } }),
          http.get("/api/tracking/mastery-trend", { params: { days: 30 } }),
        ]);
        if (!mountedRef.current) return;
        setProfile(pRes.data?.data?.categories || []);
        setWeakPoints(wRes.data?.data || []);
        setRecommendations(rRes.data?.data || []);
        setRecentInteractions(recentRes.data?.data || []);
        setTrendData(trendRes.data?.data?.points || []);
      } catch (e: unknown) {
        if (!mountedRef.current) return;
        setError(getErrorMessage(e, "加载失败"));
      } finally {
        if (mountedRef.current) setLoading(false);
      }
    })();
  }, [refreshVersion]);

  // Fetch category detail on selection
  useEffect(() => {
    if (!selectedCategory) {
      setCategoryDetail(null);
      return;
    }
    http
      .get(`/api/tracking/category/${encodeURIComponent(selectedCategory)}`)
      .then((res) => { if (mountedRef.current) setCategoryDetail(res.data?.data || null); })
      .catch(() => { if (mountedRef.current) setCategoryDetail(null); });
  }, [selectedCategory]);

  // Fetch trend data when category filter changes
  useEffect(() => {
    http
      .get("/api/tracking/mastery-trend", { params: { days: 30, category: trendCategory || undefined } })
      .then((res) => { if (mountedRef.current) setTrendData(res.data?.data?.points || []); })
      .catch(() => { if (mountedRef.current) setTrendData([]); });
  }, [trendCategory, refreshVersion]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-slate-400">
        加载学习数据...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center text-red-500">
        {error}
      </div>
    );
  }

  const totalPoints = profile.reduce((s, c) => s + c.total_points, 0);
  const totalMastered = profile.reduce((s, c) => s + c.mastered, 0);
  const totalWeak = profile.reduce((s, c) => s + c.weak, 0);

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left: Overview */}
      <div className="w-1/2 overflow-y-auto p-6 space-y-6 border-r border-slate-100">
        <h2 className="text-lg font-semibold text-slate-800">学习概览</h2>

        {/* Stats cards */}
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-xl bg-slate-50 p-4 text-center">
            <div className="text-2xl font-bold text-slate-800">{totalPoints}</div>
            <div className="text-xs text-slate-500">知识点总数</div>
          </div>
          <div className="rounded-xl bg-emerald-50 p-4 text-center">
            <div className="text-2xl font-bold text-emerald-600">{totalMastered}</div>
            <div className="text-xs text-slate-500">已掌握</div>
          </div>
          <div className="rounded-xl bg-red-50 p-4 text-center">
            <div className="text-2xl font-bold text-red-500">{totalWeak}</div>
            <div className="text-xs text-slate-500">薄弱点</div>
          </div>
        </div>

        {/* Mastery Trend Chart */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-slate-700">掌握度趋势</h3>
            <select
              value={trendCategory}
              onChange={(e) => setTrendCategory(e.target.value)}
              className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-600 focus:border-emerald-300 focus:outline-none"
            >
              <option value="">全部学科</option>
              {profile.map((c) => (
                <option key={c.category} value={c.category}>{CATEGORY_LABELS[c.category] || c.category}</option>
              ))}
            </select>
          </div>
          <div className="rounded-xl border border-slate-100 bg-white p-3">
            <MasteryTrendChart data={trendData} />
          </div>
        </div>

        {/* Radar chart */}
        {profile.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-slate-700">核心维度掌握对比</h3>
            <div className="rounded-xl border border-slate-100 bg-white p-4 flex flex-col items-center justify-center shadow-sm">
              <RadarChart data={profile} />
              <div className="mt-2 flex items-center justify-center gap-4 text-[10px] text-slate-400 select-none">
                <span className="flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-full bg-blue-500" />
                  当前学力分布
                </span>
                <span className="text-slate-200">|</span>
                <span>408 核心考纲覆盖</span>
              </div>
            </div>
          </div>
        )}

        {/* Category list */}
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-slate-700">学科掌握度</h3>
          {profile.map((cat) => (
            <div
              key={cat.category}
              className={`rounded-lg border p-3 cursor-pointer transition-colors ${
                selectedCategory === cat.category
                  ? "border-emerald-300 bg-emerald-50"
                  : "border-slate-100 hover:bg-slate-50"
              }`}
              onClick={() =>
                setSelectedCategory(selectedCategory === cat.category ? "" : cat.category)
              }
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium text-slate-700">
                  {CATEGORY_LABELS[cat.category] || cat.category}
                </span>
                <span className="text-xs text-slate-500">
                  {cat.mastered}/{cat.total_points} 已掌握 · 已追踪 {cat.tracked_points}
                </span>
              </div>
              <MasteryBar value={cat.avg_score} />
            </div>
          ))}
        </div>
      </div>

      {/* Right: Detail */}
      <div className="w-1/2 overflow-y-auto p-6 space-y-6">
        {categoryDetail ? (
          <>
            <h2 className="text-lg font-semibold text-slate-800">
              {CATEGORY_LABELS[categoryDetail.category] || categoryDetail.category} 详情
            </h2>
            <div className="text-sm text-slate-500">
              共 {categoryDetail.total_points} 个知识点，已追踪 {categoryDetail.tracked_points} 个
            </div>
            {Object.entries(categoryDetail.chapters).map(([chapter, points]) => (
              <div key={chapter} className="space-y-2">
                <h3 className="text-sm font-semibold text-slate-700 border-b border-slate-100 pb-1">
                  {chapter}
                </h3>
                {points.map((kp) => (
                  <div key={kp.id} className="rounded-lg border border-slate-100 p-3 space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-slate-700">{kp.name}</span>
                      {!kp.tracked && (
                        <span className="text-xs text-slate-400 bg-slate-50 px-2 py-0.5 rounded">
                          未学习
                        </span>
                      )}
                    </div>
                    {kp.tracked && (
                      <>
                        <MasteryBar value={kp.effective_score} label="掌握度" />
                        <div className="flex gap-4 text-xs text-slate-400">
                          <span>交互 {kp.interaction_count} 次</span>
                          <span>置信度 {typeof kp.confidence === "number" ? Math.round(kp.confidence * 100) + "%" : "-"}</span>
                          <span>难度 {typeof kp.difficulty === "number" ? kp.difficulty.toFixed(1) : "-"}</span>
                        </div>
                      </>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </>
        ) : (
          <>
            {/* Weak points */}
            <h2 className="text-lg font-semibold text-slate-800">薄弱知识点</h2>
            {weakPoints.length === 0 ? (
              <div className="text-sm text-slate-400">暂无薄弱知识点，继续学习吧！</div>
            ) : (
              <div className="space-y-2">
                {weakPoints.map((wp) => (
                  <div
                    key={wp.id}
                    className="rounded-lg border border-red-100 bg-red-50/50 p-3 space-y-1"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-slate-700">{wp.name}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-red-500">
                          {CATEGORY_LABELS[wp.category] || wp.category}
                        </span>
                        {onGenerateSimilarPractice && (
                          <button
                            type="button"
                            onClick={() => onGenerateSimilarPractice(wp.name)}
                            className="rounded-full bg-orange-100 px-2 py-0.5 text-[10px] font-medium text-orange-700 hover:bg-orange-200 transition-colors"
                          >
                            去练习
                          </button>
                        )}
                      </div>
                    </div>
                    <MasteryBar value={wp.effective_score} label="有效分" />
                    <div className="flex gap-4 text-xs text-slate-400">
                      <span>掌握度 {typeof wp.mastery === "number" ? Math.round(wp.mastery * 100) + "%" : "-"}</span>
                      <span>置信度 {typeof wp.confidence === "number" ? Math.round(wp.confidence * 100) + "%" : "-"}</span>
                      <span>交互 {wp.interaction_count} 次</span>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Recommendations */}
            {recommendations.length > 0 && (
              <>
                <h2 className="text-lg font-semibold text-slate-800 mt-4">学习建议</h2>
                <div className="space-y-2">
                  {recommendations.map((rec, i) => (
                    <div key={i} className="rounded-lg border border-amber-100 bg-amber-50/30 p-3 space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-slate-700">{rec.weak_point}</span>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-amber-600">
                            {CATEGORY_LABELS[rec.category] || rec.category}
                          </span>
                          {onGenerateSimilarPractice && (
                            <button
                              type="button"
                              onClick={() => onGenerateSimilarPractice(rec.weak_point)}
                              className="rounded-full bg-orange-100 px-2 py-0.5 text-[10px] font-medium text-orange-700 hover:bg-orange-200 transition-colors"
                            >
                              去练习
                            </button>
                          )}
                        </div>
                      </div>
                      <div className="text-xs text-slate-500">{rec.reason}</div>
                      {rec.prerequisites.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          <span className="text-[10px] text-slate-400">前置：</span>
                          {rec.prerequisites.map((p, j) => (
                            <span key={j} className="text-[10px] rounded bg-slate-100 px-1.5 py-0.5 text-slate-500">
                              {p.name}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* Learning Path Visualization */}
            <h2 className="text-lg font-semibold text-slate-800 mt-4">学习路径</h2>
            <LearningPathView onGenerateSimilarPractice={onGenerateSimilarPractice} />

            {/* Recent Interactions */}
            <h2 className="text-lg font-semibold text-slate-800 mt-6">最近学习记录</h2>
            {recentInteractions.length === 0 ? (
              <div className="text-sm text-slate-400">暂无学习记录，开始智能问答或练习吧！</div>
            ) : (
              <div className="space-y-1.5">
                {recentInteractions.map((ri) => {
                  const pct = Math.round(Math.max(0, Math.min(1, ri.effective_score)) * 100);
                  const scoreColor = pct >= 60 ? "text-emerald-600" : pct >= 30 ? "text-amber-600" : "text-red-500";
                  const sourceIcon = ri.source === "批改" ? "📝" : ri.source === "智能问答" ? "💬" : ri.source === "练习" ? "✏️" : "📌";
                  return (
                    <div key={ri.id} className="flex items-center gap-2 rounded-lg border border-slate-100 px-3 py-2">
                      <span className="text-sm">{sourceIcon}</span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-slate-700 truncate">{ri.name}</span>
                          <span className="text-[10px] text-slate-400 shrink-0">{CATEGORY_LABELS[ri.category] || ri.category}</span>
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-[10px] text-slate-400">{ri.source}</span>
                          <span className="text-[10px] text-slate-300">·</span>
                          <span className="text-[10px] text-slate-400">{ri.interaction_count}次</span>
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <div className={`text-sm font-medium ${scoreColor}`}>{pct}%</div>
                        <div className="text-[10px] text-slate-400">{ri.time_ago}</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
