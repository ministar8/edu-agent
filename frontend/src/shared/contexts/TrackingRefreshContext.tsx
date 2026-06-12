"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";

type TrackingRefreshContextValue = {
  refreshVersion: number;
  triggerRefresh: () => void;
};

const TrackingRefreshContext = createContext<TrackingRefreshContextValue | null>(null);

export function TrackingRefreshProvider({ children }: { children: ReactNode }) {
  const [refreshVersion, setRefreshVersion] = useState(0);
  const triggerRefresh = useCallback(() => {
    setRefreshVersion((v) => v + 1);
  }, []);
  return (
    <TrackingRefreshContext.Provider value={{ refreshVersion, triggerRefresh }}>
      {children}
    </TrackingRefreshContext.Provider>
  );
}

export function useTrackingRefresh() {
  const ctx = useContext(TrackingRefreshContext);
  if (!ctx) throw new Error("useTrackingRefresh must be used within TrackingRefreshProvider");
  return ctx;
}
