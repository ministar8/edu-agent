import { API_BASE_URL } from "@/lib/api";
import { memo, useEffect, useState } from "react";
import type { TabType } from "@/types/navigation";
import { tabDescriptions, tabs } from "./navigationConfig";

type WorkspaceHeaderProps = { activeTab: TabType };
type BackendStatus = "checking" | "online" | "offline";

function useBackendStatus(intervalMs = 30000) {
  const [status, setStatus] = useState<BackendStatus>("checking");

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    let stopped = false;

    const check = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/health`, { method: "GET" });
        // 200 = backend alive; 500/502 = proxy can't reach backend
        if (!stopped) setStatus(res.ok ? "online" : "offline");
      } catch {
        // Network error = frontend itself down or no connectivity
        if (!stopped) setStatus("offline");
      }
      if (!stopped) {
        timer = setTimeout(check, intervalMs);
      }
    };

    check();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [intervalMs]);

  return status;
}

const STATUS_CONFIG: Record<BackendStatus, { dot: string; text: string }> = {
  checking: { dot: "bg-amber-400 ring-amber-50", text: "检测中..." },
  online: { dot: "bg-emerald-400 ring-emerald-50", text: "系统就绪" },
  offline: { dot: "bg-red-400 ring-red-50", text: "后端离线" },
};

function WorkspaceHeaderComponent({ activeTab }: WorkspaceHeaderProps) {
  const active = tabs.find((tab) => tab.id === activeTab);
  const backendStatus = useBackendStatus();
  if (!active) return null;
  const Icon = active.icon;
  const { dot, text } = STATUS_CONFIG[backendStatus];

  return (
    <header className="flex items-center justify-between border-b border-slate-100 px-8 py-5">
      <div className="flex items-center gap-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-slate-700">
          <Icon size={18} />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-slate-900">{active.label}</h2>
          <p className="mt-0.5 text-[13px] text-slate-400">{tabDescriptions[activeTab]}</p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <span className={`flex h-2 w-2 rounded-full ${dot} ring-4`} />
        <span className="text-[13px] text-slate-400">{text}</span>
      </div>
    </header>
  );
}

export const WorkspaceHeader = memo(WorkspaceHeaderComponent);
