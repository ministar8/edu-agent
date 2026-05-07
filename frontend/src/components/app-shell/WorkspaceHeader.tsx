import { memo } from "react";

import type { TabType } from "@/types/navigation";
import { tabDescriptions, tabs } from "./navigationConfig";

type WorkspaceHeaderProps = {
  activeTab: TabType;
};

function WorkspaceHeaderComponent({ activeTab }: WorkspaceHeaderProps) {
  return (
    <header className="border-b border-slate-200 px-8 py-6">
      <div className="flex items-start justify-between gap-6">
        <div>
          <h2 className="text-2xl font-semibold text-slate-900">{tabs.find((tab) => tab.id === activeTab)?.label}</h2>
          <p className="mt-2 text-sm text-slate-500">{tabDescriptions[activeTab]}</p>
        </div>
        <div className="hidden rounded-2xl bg-slate-50 px-4 py-3 text-right md:block">
          <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Workspace</div>
          <div className="mt-1 text-sm font-medium text-slate-700">教学辅导智能工作台</div>
        </div>
      </div>
    </header>
  );
}

export const WorkspaceHeader = memo(WorkspaceHeaderComponent);
