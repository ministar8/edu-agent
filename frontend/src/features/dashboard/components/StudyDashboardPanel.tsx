"use client";

import { useEffect, useRef, useState } from "react";

import { CATEGORY_LABELS } from "@/shared/lib/collections";
import { getErrorMessage } from "@/shared/lib/errors";
import { http } from "@/shared/lib/http";

type CategoryStat = {
  category: string;
  total_points: number;
  mastered: number;
  weak: number;
};

type WeakPoint = {
  id: number;
  name: string;
  category: string;
  chapter: string;
  mastery: number;
  effective_score: number;
};

type Recommendation = {
  weak_point: string;
  category: string;
  reason: string;
};

type RecentInteraction = {
  id: number;
  name: string;
  category: string;
  source: string;
  time_ago: string;
};

type StudyDashboardPanelProps = {
  onStartChat: (question: string) => void;
  onGeneratePractice: (topic: string) => void;
  onOpenKnowledgeMap: (focus: string) => void;
  onOpenDebug: () => void;
};

function percent(value: number) {
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`;
}

function categoryLabel(category: string) {
  return CATEGORY_LABELS[category] || category;
}

export default function StudyDashboardPanel({
  onStartChat,
  onGeneratePractice,
  onOpenKnowledgeMap,
  onOpenDebug,
}: StudyDashboardPanelProps) {
  const [profile, setProfile] = useState<CategoryStat[]>([]);
  const [weakPoints, setWeakPoints] = useState<WeakPoint[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [recentInteractions, setRecentInteractions] = useState<RecentInteraction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError("");
      try {
        const [profileRes, weakRes, recRes, recentRes] = await Promise.all([
          http.get("/api/tracking/profile"),
          http.get("/api/tracking/weak-points", { params: { threshold: 0.3, limit: 5 } }),
          http.get("/api/tracking/recommendations", { params: { limit: 4 } }),
          http.get("/api/tracking/recent", { params: { limit: 5 } }),
        ]);
        if (!mountedRef.current) return;
        setProfile(profileRes.data?.data?.categories || []);
        setWeakPoints(weakRes.data?.data || []);
        setRecommendations(recRes.data?.data || []);
        setRecentInteractions(recentRes.data?.data || []);
      } catch (err: unknown) {
        if (mountedRef.current) setError(getErrorMessage(err, "学习数据加载失败"));
      } finally {
        if (mountedRef.current) setLoading(false);
      }
    })();
  }, []);

  const totalPoints = profile.reduce((sum, item) => sum + item.total_points, 0);
  const totalMastered = profile.reduce((sum, item) => sum + item.mastered, 0);
  const totalWeak = profile.reduce((sum, item) => sum + item.weak, 0);
  const primaryWeakPoint = weakPoints[0]?.name || recommendations[0]?.weak_point || "408 核心知识点";

  return (
    <div className="h-full overflow-y-auto bg-stone-50 p-6 text-slate-800">
      <div className="mx-auto flex max-w-6xl flex-col gap-6">
        <section className="rounded-[28px] border border-emerald-100 bg-gradient-to-br from-emerald-50 via-white to-cyan-50 p-6 shadow-sm">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.28em] text-emerald-600">学习工作台</p>
              <h2 className="mt-3 text-2xl font-semibold tracking-tight text-slate-900">先看下一步，再开始学习</h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
                把原来的技术展示入口收敛为学习行动入口：讲解、练习、错题和知识地图围绕薄弱点形成闭环。
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-3 lg:min-w-[420px]">
              <div className="rounded-2xl bg-white/80 p-4 shadow-sm ring-1 ring-slate-100">
                <div className="text-2xl font-semibold text-slate-900">{totalPoints}</div>
                <div className="mt-1 text-xs text-slate-500">知识点总数</div>
              </div>
              <div className="rounded-2xl bg-white/80 p-4 shadow-sm ring-1 ring-slate-100">
                <div className="text-2xl font-semibold text-emerald-600">{totalMastered}</div>
                <div className="mt-1 text-xs text-slate-500">已掌握</div>
              </div>
              <div className="rounded-2xl bg-white/80 p-4 shadow-sm ring-1 ring-slate-100">
                <div className="text-2xl font-semibold text-rose-500">{totalWeak}</div>
                <div className="mt-1 text-xs text-slate-500">待加强</div>
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-4 lg:grid-cols-3">
          <button
            onClick={() => onStartChat(`请用适合考研408复习的方式，系统讲解「${primaryWeakPoint}」，并给出常见题型。`)}
            className="rounded-[24px] border border-slate-200 bg-white p-5 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-emerald-200 hover:shadow-md"
          >
            <div className="text-sm font-semibold text-slate-900">让 AI 讲清薄弱点</div>
            <p className="mt-2 text-xs leading-5 text-slate-500">围绕当前薄弱点生成结构化讲解、重点与例题。</p>
          </button>
          <button
            onClick={() => onGeneratePractice(primaryWeakPoint)}
            className="rounded-[24px] border border-slate-200 bg-white p-5 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-emerald-200 hover:shadow-md"
          >
            <div className="text-sm font-semibold text-slate-900">生成专项练习</div>
            <p className="mt-2 text-xs leading-5 text-slate-500">直接进入练习与错题，围绕薄弱知识点出题并批改。</p>
          </button>
          <button
            onClick={() => onOpenKnowledgeMap(primaryWeakPoint)}
            className="rounded-[24px] border border-slate-200 bg-white p-5 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-emerald-200 hover:shadow-md"
          >
            <div className="text-sm font-semibold text-slate-900">查看知识地图</div>
            <p className="mt-2 text-xs leading-5 text-slate-500">定位知识点在 408 知识结构中的位置和前后依赖。</p>
          </button>
        </section>

        {error && (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
            {error}
          </div>
        )}

        <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <div className="rounded-[28px] border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-base font-semibold text-slate-900">当前薄弱点</h3>
                <p className="mt-1 text-xs text-slate-400">优先从这些知识点开始讲解、练习和复盘。</p>
              </div>
              {loading && <span className="text-xs text-slate-400">加载中...</span>}
            </div>
            <div className="space-y-3">
              {weakPoints.length === 0 && !loading ? (
                <div className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-500">暂无薄弱点数据，可以先从智能问答或练习开始。</div>
              ) : weakPoints.map((point) => (
                <div key={point.id} className="rounded-2xl border border-slate-100 bg-slate-50/80 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-slate-800">{point.name}</div>
                      <div className="mt-1 text-xs text-slate-400">{categoryLabel(point.category)} · {point.chapter}</div>
                    </div>
                    <div className="text-right text-xs text-slate-500">
                      <div>掌握度 {percent(point.mastery)}</div>
                      <div>有效分 {percent(point.effective_score)}</div>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button onClick={() => onStartChat(`请详细讲解「${point.name}」，并说明它在${categoryLabel(point.category)}中的考研重点。`)} className="rounded-full bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white">AI 讲解</button>
                    <button onClick={() => onGeneratePractice(point.name)} className="rounded-full bg-white px-3 py-1.5 text-xs font-medium text-slate-600 ring-1 ring-slate-200">专项练习</button>
                    <button onClick={() => onOpenKnowledgeMap(point.name)} className="rounded-full bg-white px-3 py-1.5 text-xs font-medium text-slate-600 ring-1 ring-slate-200">知识地图</button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-6">
            <div className="rounded-[28px] border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="text-base font-semibold text-slate-900">推荐行动</h3>
              <div className="mt-4 space-y-3">
                {recommendations.length === 0 && !loading ? (
                  <div className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-500">完成几次练习后，这里会给出更具体的推荐。</div>
                ) : recommendations.map((item) => (
                  <button
                    key={`${item.category}-${item.weak_point}`}
                    onClick={() => onGeneratePractice(item.weak_point)}
                    className="w-full rounded-2xl bg-slate-50 p-4 text-left transition hover:bg-emerald-50"
                  >
                    <div className="text-sm font-medium text-slate-800">{item.weak_point}</div>
                    <div className="mt-1 text-xs text-slate-400">{categoryLabel(item.category)}</div>
                    <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-500">{item.reason}</p>
                  </button>
                ))}
              </div>
            </div>

            <div className="rounded-[28px] border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-semibold text-slate-900">最近学习</h3>
                <button onClick={onOpenDebug} className="text-xs font-medium text-slate-400 hover:text-slate-700">管理调试</button>
              </div>
              <div className="mt-4 space-y-2">
                {recentInteractions.length === 0 && !loading ? (
                  <div className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-500">暂无学习记录。</div>
                ) : recentInteractions.map((item) => (
                  <div key={item.id} className="rounded-2xl bg-slate-50 px-4 py-3">
                    <div className="truncate text-sm font-medium text-slate-700">{item.name}</div>
                    <div className="mt-1 text-xs text-slate-400">{categoryLabel(item.category)} · {item.source} · {item.time_ago}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
