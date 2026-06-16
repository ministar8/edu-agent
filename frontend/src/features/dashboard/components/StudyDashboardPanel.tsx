"use client";

import { useEffect, useRef, useState } from "react";

import { useAuth } from "@/shared/lib/auth";
import { getErrorMessage } from "@/shared/lib/errors";
import { http } from "@/shared/lib/http";
import {
  IconArrowRight,
  IconCheckCircle,
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

type StudyDashboardPanelProps = {
  onStartChat: (question: string) => void;
  onGeneratePractice: (topic: string) => void;
  onOpenKnowledgeMap: (focus: string) => void;
  onOpenDebug: () => void;
};

function greetingForNow() {
  const h = new Date().getHours();
  if (h < 5) return "夜深了";
  if (h < 11) return "早上好";
  if (h < 13) return "中午好";
  if (h < 18) return "下午好";
  return "晚上好";
}

export default function StudyDashboardPanel({
  onStartChat,
  onGeneratePractice,
  onOpenKnowledgeMap,
}: StudyDashboardPanelProps) {
  const { user } = useAuth();
  const [profile, setProfile] = useState<CategoryStat[]>([]);
  const [weakPoints, setWeakPoints] = useState<WeakPoint[]>([]);
  const [input, setInput] = useState("");
  const [error, setError] = useState("");
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const [profileRes, weakRes] = await Promise.all([
          http.get("/api/tracking/profile"),
          http.get("/api/tracking/weak-points", { params: { threshold: 0.3, limit: 5 } }),
        ]);
        if (!mountedRef.current) return;
        setProfile(profileRes.data?.data?.categories || []);
        setWeakPoints(weakRes.data?.data || []);
      } catch (err: unknown) {
        if (mountedRef.current) setError(getErrorMessage(err, "学习数据加载失败"));
      }
    })();
  }, []);

  const totalPoints = profile.reduce((sum, item) => sum + item.total_points, 0);
  const totalMastered = profile.reduce((sum, item) => sum + item.mastered, 0);
  const totalWeak = profile.reduce((sum, item) => sum + item.weak, 0);
  const masteryRate = totalPoints > 0 ? Math.round((totalMastered / totalPoints) * 100) : 0;
  const primaryWeakPoint = weakPoints[0]?.name || "408 核心知识点";
  const displayName = user?.display_name?.trim() || "同学";

  const submitChat = () => {
    const question = input.trim();
    if (!question) return;
    onStartChat(question);
    setInput("");
  };

  const modules = [
    {
      key: "explain",
      icon: IconSparkles,
      title: "AI 讲解薄弱点",
      desc: "结构化讲解、重点与例题",
      onClick: () => onStartChat(`请用适合考研408复习的方式，系统讲解「${primaryWeakPoint}」，并给出常见题型。`),
    },
    {
      key: "practice",
      icon: IconQuiz,
      title: "专项练习",
      desc: "围绕薄弱点出题与批改",
      onClick: () => onGeneratePractice(primaryWeakPoint),
    },
    {
      key: "map",
      icon: IconMap,
      title: "知识地图",
      desc: "查看知识点位置与依赖",
      onClick: () => onOpenKnowledgeMap(primaryWeakPoint),
    },
  ];

  const stats = [
    { key: "total", icon: IconLayers, label: "知识点总数", value: totalPoints, valueTone: "text-slate-900", iconTone: "bg-slate-100 text-slate-500" },
    { key: "mastered", icon: IconCheckCircle, label: "已掌握", value: totalMastered, valueTone: "text-emerald-600", iconTone: "bg-emerald-50 text-emerald-600" },
    { key: "weak", icon: IconTarget, label: "待加强", value: totalWeak, valueTone: "text-rose-500", iconTone: "bg-rose-50 text-rose-500" },
  ];

  return (
    <div className="h-full overflow-y-auto bg-[#F5F5F5]">
      <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col justify-center px-6 py-12">
        <div className="flex flex-col items-center text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white text-emerald-600 shadow-sm ring-1 ring-slate-200/70">
            <IconSparkles size={24} />
          </span>
          <h1 className="mt-5 text-[28px] font-semibold tracking-tight text-slate-900">
            {greetingForNow()}，{displayName}
          </h1>
          <p className="mt-2 text-sm text-slate-500">今天想学点什么？把问题交给多 Agent 教学助手。</p>
        </div>

        <div className="mt-8 rounded-2xl border border-slate-200 bg-white p-2 shadow-sm transition focus-within:border-emerald-300 focus-within:ring-2 focus-within:ring-emerald-100">
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                submitChat();
              }
            }}
            rows={2}
            placeholder="有什么可以帮你的？例如：讲讲 TCP 拥塞控制的核心机制"
            className="block w-full resize-none border-0 bg-transparent px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-0"
          />
          <div className="flex items-center justify-between px-2 pb-1">
            <span className="text-[11px] text-slate-400">Enter 发送 · Shift+Enter 换行</span>
            <button
              type="button"
              onClick={submitChat}
              disabled={!input.trim()}
              aria-label="发送"
              className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-600 text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
            >
              <IconArrowRight size={16} />
            </button>
          </div>
        </div>

        <div className="mt-8 grid gap-3 sm:grid-cols-3">
          {modules.map((module) => {
            const Icon = module.icon;
            return (
              <button
                key={module.key}
                onClick={module.onClick}
                className="group flex flex-col rounded-2xl border border-slate-200 bg-white p-4 text-left transition hover:border-emerald-300 hover:shadow-[0_2px_10px_rgba(16,185,129,0.08)]"
              >
                <div className="flex items-center justify-between">
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-slate-500 transition group-hover:bg-emerald-50 group-hover:text-emerald-600">
                    <Icon size={18} />
                  </span>
                  <IconArrowRight size={16} className="text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-emerald-500" />
                </div>
                <div className="mt-3 text-sm font-semibold text-slate-900">{module.title}</div>
                <p className="mt-1 text-xs leading-5 text-slate-500">{module.desc}</p>
              </button>
            );
          })}
        </div>

        <div className="mt-8">
          <div className="mb-2 flex items-center justify-between px-1">
            <h2 className="text-[13px] font-semibold text-slate-700">学习概览</h2>
            <span className="text-xs text-slate-400">掌握 {masteryRate}%</span>
          </div>
          <div className="grid grid-cols-3 gap-3">
            {stats.map((stat) => {
              const Icon = stat.icon;
              return (
                <div key={stat.key} className="flex items-center gap-3 rounded-2xl border border-slate-200/70 bg-white p-4">
                  <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${stat.iconTone}`}>
                    <Icon size={18} />
                  </span>
                  <div className="min-w-0">
                    <div className={`text-lg font-semibold leading-tight ${stat.valueTone}`}>{stat.value}</div>
                    <div className="truncate text-xs text-slate-500">{stat.label}</div>
                  </div>
                </div>
              );
            })}
          </div>
          {error && <p className="mt-3 px-1 text-xs text-amber-600">{error}</p>}
        </div>
      </div>
    </div>
  );
}
