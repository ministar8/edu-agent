"use client";

import { useEffect, useRef, useState } from "react";
import { http } from "@/lib/http";
import { getErrorMessage } from "@/lib/errors";
import { knowledgeCategories } from "@/lib/collections";

// ── Types ────────────────────────────────────────────────────

interface CategoryStat {
  category: string;
  avg_mastery: number;
  avg_score: number;
  total_points: number;
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
  last_interaction_at: string | null;
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

// ── Category label map ───────────────────────────────────────

const CATEGORY_LABELS: Record<string, string> = Object.fromEntries(
  knowledgeCategories.map((c) => [c.value, c.label]),
);
// Extra categories not in knowledgeCategories but returned by tracking API
CATEGORY_LABELS.learning_paths = "学习路径";
CATEGORY_LABELS.answers = "标准答案";

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

// ── Main Panel ───────────────────────────────────────────────

export default function TrackingPanel() {
  const [profile, setProfile] = useState<CategoryStat[]>([]);
  const [weakPoints, setWeakPoints] = useState<WeakPoint[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
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
        const [pRes, wRes, rRes] = await Promise.all([
          http.get("/api/tracking/profile"),
          http.get("/api/tracking/weak-points", { params: { threshold: 0.3, limit: 10 } }),
          http.get("/api/tracking/recommendations", { params: { limit: 5 } }),
        ]);
        if (!mountedRef.current) return;
        setProfile(pRes.data?.data?.categories || []);
        setWeakPoints(wRes.data?.data || []);
        setRecommendations(rRes.data?.data || []);
      } catch (e: unknown) {
        if (!mountedRef.current) return;
        setError(getErrorMessage(e, "加载失败"));
      } finally {
        if (mountedRef.current) setLoading(false);
      }
    })();
  }, []);

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

        {/* Radar chart */}
        {profile.length > 0 && (
          <div className="flex justify-center">
            <RadarChart data={profile} />
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
                  {cat.mastered}/{cat.total_points} 已掌握
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
                      <span className="text-xs text-red-500">
                        {CATEGORY_LABELS[wp.category] || wp.category}
                      </span>
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
            <h2 className="text-lg font-semibold text-slate-800 mt-4">学习建议</h2>
            {recommendations.length === 0 ? (
              <div className="text-sm text-slate-400">暂无推荐，保持学习即可！</div>
            ) : (
              <div className="space-y-2">
                {recommendations.map((rec, i) => (
                  <div
                    key={i}
                    className="rounded-lg border border-emerald-100 bg-emerald-50/50 p-3 space-y-1"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-slate-700">
                        {rec.weak_point}
                      </span>
                      <span className="text-xs text-emerald-600">
                        {CATEGORY_LABELS[rec.category] || rec.category}
                      </span>
                    </div>
                    <p className="text-xs text-slate-600">{rec.reason}</p>
                    {rec.prerequisites.length > 0 && (
                      <div className="text-xs text-slate-400">
                        前置知识：{rec.prerequisites.map((p) => p.name).join("、")}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
