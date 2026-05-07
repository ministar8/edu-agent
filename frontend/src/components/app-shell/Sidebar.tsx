import { memo } from "react";

import type { TabType } from "@/types/navigation";
import { roleLabels, tabDescriptions, tabs } from "./navigationConfig";

type SidebarProps = {
  activeTab: TabType;
  user: {
    display_name: string;
    role: string;
  };
  onTabChange: (tab: TabType) => void;
  onLogout: () => void;
};

function SidebarComponent({ activeTab, user, onTabChange, onLogout }: SidebarProps) {
  return (
    <aside className="flex w-[272px] shrink-0 flex-col rounded-[28px] border border-slate-200 bg-white p-5 shadow-[0_18px_60px_rgba(15,23,42,0.08)]">
      <div className="mb-8 flex items-start gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-2xl text-slate-700">
          🎓
        </div>
        <div>
          <h1 className="text-lg font-semibold leading-6 text-slate-900">智能教学辅导多Agent系统</h1>
        </div>
      </div>

      <div className="mb-6 rounded-3xl border border-slate-200 bg-slate-50 px-4 py-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-medium text-slate-900">{user.display_name}</div>
            <div className="mt-1 text-xs text-slate-500">{roleLabels[user.role] || user.role}</div>
          </div>
          <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] font-medium text-emerald-700">
            在线
          </span>
        </div>
      </div>

      <nav className="flex-1 space-y-2 overflow-auto">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={`w-full rounded-2xl px-4 py-3 text-left transition ${
              activeTab === tab.id
                ? "bg-slate-800 text-white shadow-lg"
                : "bg-transparent text-slate-600 hover:bg-slate-100 hover:text-slate-900"
            }`}
          >
            <div className="flex items-center gap-3">
              <span className="text-lg">{tab.icon}</span>
              <div>
                <div className="text-sm font-medium">{tab.label}</div>
                <div className={`mt-0.5 text-xs ${activeTab === tab.id ? "text-slate-300" : "text-slate-400"}`}>
                  {tabDescriptions[tab.id]}
                </div>
              </div>
            </div>
          </button>
        ))}
      </nav>

      <button
        onClick={onLogout}
        className="mt-5 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
      >
        退出登录
      </button>
    </aside>
  );
}

export const Sidebar = memo(SidebarComponent);
