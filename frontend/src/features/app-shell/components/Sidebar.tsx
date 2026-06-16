import { memo } from "react";

import type { TabType } from "@/shared/types/navigation";
import { primaryTabs, roleLabels, tabDescriptions, utilityTabs } from "@/features/app-shell/config/navigationConfig";

type SidebarProps = {
  activeTab: TabType;
  user: { display_name: string; role: string };
  onTabChange: (tab: TabType) => void;
  onLogout: () => void;
};

function SidebarComponent({ activeTab, user, onTabChange, onLogout }: SidebarProps) {
  return (
    <aside className="flex w-[260px] shrink-0 flex-col rounded-2xl border border-slate-200/70 bg-white px-4 py-5">
      <div className="mb-6 px-2">
        <span
          style={{ fontFamily: "var(--font-pacifico), cursive" }}
          className="inline-block bg-gradient-to-r from-[#5EA8E5] via-[#9DA6B4] to-[#F4A152] bg-clip-text text-[28px] leading-none text-transparent"
        >
          EduAgent
        </span>
        <p className="mt-2 text-[11px] text-slate-400">智能教学辅导 · Multi-Agent System</p>
      </div>

      <div className="mb-5 flex items-center gap-3 rounded-xl border border-slate-100 bg-[#F5F5F5] px-3 py-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-[13px] font-semibold uppercase text-emerald-700">
          {user.display_name?.trim().charAt(0) || "U"}
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-medium text-slate-800">{user.display_name}</div>
          <div className="text-[11px] text-slate-400">{roleLabels[user.role] || user.role}</div>
        </div>
        <span className="flex shrink-0 items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-600 ring-1 ring-emerald-200/60">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          在线
        </span>
      </div>

      <nav className="flex-1 space-y-4">
        <div>
          <div className="mb-1 px-2 py-1 text-[10px] font-medium uppercase tracking-widest text-slate-400">学习</div>
          <div className="space-y-0.5">
            {primaryTabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => onTabChange(tab.id)}
                  className={`group relative w-full rounded-xl px-3 py-2.5 text-left transition-all duration-150 ${
                    isActive ? "bg-emerald-600 text-white" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <Icon size={18} className={`shrink-0 transition-colors ${isActive ? "text-white" : "text-slate-400 group-hover:text-slate-600"}`} />
                    <div className="min-w-0">
                      <div className="text-[13px] font-medium">{tab.label}</div>
                      {isActive && <div className="mt-0.5 truncate text-[11px] text-slate-300/80">{tabDescriptions[tab.id]}</div>}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <div className="mb-1 px-2 py-1 text-[10px] font-medium uppercase tracking-widest text-slate-400">管理</div>
          <div className="space-y-0.5">
            {utilityTabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => onTabChange(tab.id)}
                  className={`group relative w-full rounded-xl px-3 py-2.5 text-left transition-all duration-150 ${
                    isActive ? "bg-slate-800 text-white" : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <Icon size={18} className={`shrink-0 transition-colors ${isActive ? "text-white" : "text-slate-400 group-hover:text-slate-600"}`} />
                    <div className="min-w-0">
                      <div className="text-[13px] font-medium">{tab.label}</div>
                      {isActive && <div className="mt-0.5 truncate text-[11px] text-slate-300/80">{tabDescriptions[tab.id]}</div>}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </nav>

      <button onClick={onLogout} className="mt-4 w-full border-t border-slate-100 pt-3 rounded-xl px-3 py-2.5 text-left text-[13px] text-slate-500 transition hover:bg-slate-50 hover:text-slate-700">
        退出登录
      </button>
    </aside>
  );
}

export const Sidebar = memo(SidebarComponent);
