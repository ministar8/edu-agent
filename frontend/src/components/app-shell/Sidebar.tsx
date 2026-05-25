import { memo } from "react";

import { IconGraduation } from "@/components/icons";
import type { TabType } from "@/types/navigation";
import { roleLabels, tabDescriptions, tabs } from "./navigationConfig";

type SidebarProps = {
  activeTab: TabType;
  user: { display_name: string; role: string };
  onTabChange: (tab: TabType) => void;
  onLogout: () => void;
};

function SidebarComponent({ activeTab, user, onTabChange, onLogout }: SidebarProps) {
  return (
    <aside className="flex w-[260px] shrink-0 flex-col rounded-2xl border border-slate-200/80 bg-white px-4 py-5 shadow-sm">
      <div className="mb-6 flex items-center gap-3 px-2">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-600 text-white shadow-sm">
          <IconGraduation size={20} />
        </div>
        <div className="min-w-0">
          <h1 className="truncate text-[15px] font-semibold leading-tight text-slate-900">智能教学辅导</h1>
          <p className="text-[11px] text-slate-400">Multi-Agent System</p>
        </div>
      </div>

      <div className="mb-5 rounded-xl border border-slate-100 bg-slate-50/80 px-3 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="truncate text-[13px] font-medium text-slate-800">{user.display_name}</div>
            <div className="text-[11px] text-slate-400">{roleLabels[user.role] || user.role}</div>
          </div>
          <span className="shrink-0 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-600 ring-1 ring-emerald-200/60">在线</span>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5">
        <div className="mb-1 px-2 py-1 text-[10px] font-medium uppercase tracking-widest text-slate-400">导航</div>
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className={`group relative w-full rounded-xl px-3 py-2.5 text-left transition-all duration-150 ${
                isActive ? "bg-emerald-600 text-white shadow-sm" : "text-stone-600 hover:bg-stone-100 hover:text-stone-900"
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
      </nav>

      <button onClick={onLogout} className="mt-4 w-full border-t border-slate-100 pt-3 rounded-xl px-3 py-2.5 text-left text-[13px] text-slate-500 transition hover:bg-slate-50 hover:text-slate-700">
        退出登录
      </button>
    </aside>
  );
}

export const Sidebar = memo(SidebarComponent);
