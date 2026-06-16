"use client";

import { useEffect, useRef, useState } from "react";

import { CATEGORY_LABELS } from "@/shared/lib/collections";
import { getErrorMessage } from "@/shared/lib/errors";
import { http } from "@/shared/lib/http";
import {
  IconArrowRight,
  IconCheckCircle,
  IconClock,
  IconLayers,
  IconMap,
  IconQuiz,
  IconSparkles,
  IconTarget,
} from "@/shared/ui/icons";

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
  const masteryRate = totalPoints > 0 ? totalMastered / totalPoints : 0;
  const primaryWeakPoint = weakPoints[0]?.name || recommendations[0]?.weak_point || "408 核心知识点";

  const quickActions = [
    {
      key: "explain",
      icon: IconSparkles,
      title: "AI 讲解薄弱点",
      desc: "生成结构化讲解、重点和例题",
      onClick: () =>
        onStartChat(`请用适合考研408复习的方式，系统讲解「${primaryWeakPoint}」，并给出常见题型。`),
    },
    {
      key: "practice",
      icon: IconQuiz,
      title: "专项练习",
      desc: "进入练习与错题，围绕薄弱点出题",
      onClick: () => onGeneratePractice(primaryWeakPoint),
    },
    {
      key: "map",
      icon: IconMap,
      title: "知识地图",
      desc: "查看知识点位置和前后依赖",
      onClick: () => onOpenKnowledgeMap(primaryWeakPoint),
    },
  ];

  const overviewStats = [
    { key: "total", icon: IconLayers, label: "知识点总数", value: totalPoints, tone: "text-slate-900", iconTone: "bg-slate-100 text-slate-500" },
    { key: "mastered", icon: IconCheckCircle, label: "已掌握", value: totalMastered, tone: "text-emerald-600", iconTone: "bg-emerald-50 text-emerald-600" },
    { key: "weak", icon: IconTarget, label: "待加强", value: totalWeak, tone: "text-rose-500", iconTone: "bg-rose-50 text-rose-500" },
  ];

  return (
    <div className="h-full overflow-y-auto bg-[#F5F5F5] p-6 text-slate-800">
      <div className="grid min-h-full gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <section className="flex min-w-0 flex-col rounded-2xl border border-slate-200/70 bg-white">
          <div className="border-b border-slate-100 px-7 py-6">
            <div className="flex items-center gap-2 text-emerald-600">
              <IconSparkles size={15} />
              <span className="text-[11px] font-semibold uppercase tracking-[0.18em]">Study Workspace</span>
            </div>
            <h2 className="mt-3 text-[22px] font-semibold tracking-tight text-slate-900">先看下一步，再开始学习</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
              围绕薄弱点把讲解、练习和知识地图串起来，保留清晰的学习入口与简洁的视觉层级。
            </p>
          </div>

          <div className="px-7 py-6">
            <div className="grid gap-3 sm:grid-cols-3">
              {quickActions.map((action) => {
                const Icon = action.icon;
                return (
                  <button
                    key={action.key}
                    onClick={action.onClick}
                    className="group rounded-xl border border-slate-200 bg-white p-4 text-left transition hover:border-emerald-300 hover:shadow-[0_2px_8px_rgba(16,185,129,0.08)]"
                  >
                    <div className="flex items-center justify-between">
                      <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-slate-500 transition group-hover:bg-emerald-50 group-hover:text-emerald-600">
                        <Icon size={18} />
                      </span>
                      <IconArrowRight size={16} className="text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-emerald-500" />
                    </div>
                    <div className="mt-3 text-sm font-semibold text-slate-900">{action.title}</div>
                    <p className="mt-1 text-xs leading-5 text-slate-500">{action.desc}</p>
                  </button>
                );
              })}
            </div>
          </div>

          {error && (
            <div className="mx-7 mb-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
              {error}
            </div>
          )}

          <div className="min-h-0 flex-1 px-7 pb-7">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h3 className="text-[15px] font-semibold text-slate-900">当前薄弱点</h3>
                {weakPoints.length > 0 && (
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-500">{weakPoints.length}</span>
                )}
              </div>
              {loading && <span className="text-xs text-slate-400">加载中...</span>}
            </div>
            <div className="space-y-3">
              {weakPoints.length === 0 && !loading ? (
                <div className="rounded-xl border border-slate-100 bg-[#F5F5F5] p-6 text-center text-sm text-slate-500">
                  暂无薄弱点数据，可以先从智能问答或练习开始。
                </div>
              ) : weakPoints.map((point) => (
                <div key={point.id} className="rounded-xl border border-slate-200 bg-white p-4 transition hover:border-slate-300">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-slate-800">{point.name}</div>
                      <div className="mt-1.5 flex items-center gap-2 text-xs text-slate-400">
                        <span className="rounded-md bg-slate-100 px-1.5 py-0.5 font-medium text-slate-500">{categoryLabel(point.category)}</span>
                        <span className="truncate">{point.chapter}</span>
                      </div>
                    </div>
                    <div className="shrink-0 text-right text-xs text-slate-500">
                      <div>掌握度 <span className="font-semibold text-slate-700">{percent(point.mastery)}</span></div>
                      <div className="mt-0.5">有效分 <span className="font-semibold text-slate-700">{percent(point.effective_score)}</span></div>
                    </div>
                  </div>
                  <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full bg-emerald-500" style={{ width: percent(point.mastery) }} />
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button onClick={() => onStartChat(`请详细讲解「${point.name}」，并说明它在${categoryLabel(point.category)}中的考研重点。`)} className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-emerald-700">AI 讲解</button>
                    <button onClick={() => onGeneratePractice(point.name)} className="rounded-lg bg-white px-3 py-1.5 text-xs font-medium text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-50">专项练习</button>
                    <button onClick={() => onOpenKnowledgeMap(point.name)} className="rounded-lg bg-white px-3 py-1.5 text-xs font-medium text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-50">知识地图</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <aside className="space-y-5">
          <div className="rounded-2xl border border-slate-200/70 bg-white p-5">
            <div className="flex items-center justify-between">
              <h3 className="text-[15px] font-semibold text-slate-900">学习概览</h3>
              <span className="text-xs font-medium text-slate-400">掌握 {percent(masteryRate)}</span>
            </div>
            <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-slate-100">
              <div className="h-full rounded-full bg-emerald-500 transition-all duration-500" style={{ width: percent(masteryRate) }} />
            </div>
            <div className="mt-5 grid grid-cols-3 gap-3 xl:grid-cols-1">
              {overviewStats.map((stat) => {
                const Icon = stat.icon;
                return (
                  <div key={stat.key} className="rounded-xl border border-slate-100 bg-[#F5F5F5] p-4">
                    <span className={`flex h-8 w-8 items-center justify-center rounded-lg ${stat.iconTone}`}>
                      <Icon size={16} />
                    </span>
                    <div className={`mt-3 text-2xl font-semibold tracking-tight ${stat.tone}`}>{stat.value}</div>
                    <div className="mt-0.5 text-xs text-slate-500">{stat.label}</div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200/70 bg-white p-5">
            <h3 className="text-[15px] font-semibold text-slate-900">推荐行动</h3>
            <div className="mt-4 space-y-3">
              {recommendations.length === 0 && !loading ? (
                <div className="rounded-xl border border-slate-100 bg-[#F5F5F5] p-4 text-sm text-slate-500">完成几次练习后，这里会给出更具体的推荐。</div>
              ) : recommendations.map((item) => (
                <button
                  key={`${item.category}-${item.weak_point}`}
                  onClick={() => onGeneratePractice(item.weak_point)}
                  className="group flex w-full items-start gap-3 rounded-xl border border-slate-100 bg-[#F5F5F5] p-4 text-left transition hover:border-emerald-200 hover:bg-emerald-50/40"
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-slate-800">{item.weak_point}</div>
                    <div className="mt-1 text-xs text-slate-400">{categoryLabel(item.category)}</div>
                    <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-500">{item.reason}</p>
                  </div>
                  <IconArrowRight size={16} className="mt-0.5 shrink-0 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-emerald-500" />
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200/70 bg-white p-5">
            <div className="flex items-center justify-between">
              <h3 className="text-[15px] font-semibold text-slate-900">最近学习</h3>
              <button onClick={onOpenDebug} className="text-xs font-medium text-slate-400 transition hover:text-slate-700">管理调试</button>
            </div>
            <div className="mt-4 space-y-2">
              {recentInteractions.length === 0 && !loading ? (
                <div className="rounded-xl border border-slate-100 bg-[#F5F5F5] p-4 text-sm text-slate-500">暂无学习记录。</div>
              ) : recentInteractions.map((item) => (
                <div key={item.id} className="flex items-center gap-3 rounded-xl border border-slate-100 bg-[#F5F5F5] px-4 py-3">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white text-slate-400 ring-1 ring-slate-100">
                    <IconClock size={15} />
                  </span>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-slate-700">{item.name}</div>
                    <div className="mt-0.5 truncate text-xs text-slate-400">{categoryLabel(item.category)} · {item.source} · {item.time_ago}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
