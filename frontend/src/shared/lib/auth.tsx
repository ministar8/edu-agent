"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import {
  AUTH_UNAUTHORIZED_EVENT,
  clearAccessToken,
  http,
  setAccessToken,
} from "./http";

interface User {
  id: number;
  username: string;
  display_name: string;
  role: string;
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string, displayName: string, role: string) => Promise<void>;
  logout: () => void;
  clearSession: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const clearSession = useCallback(() => {
    setUser(null);
    clearAccessToken();
  }, []);

  useEffect(() => {
    const restoreSession = async () => {
      try {
        const res = await http.get("/api/auth/me");
        setUser(res.data);
      } catch {
        clearSession();
      } finally {
        setLoading(false);
      }
    };

    void restoreSession();
  }, [clearSession]);

  const saveSession = useCallback((newToken: string, newUser: User) => {
    setUser(newUser);
    setAccessToken(newToken);
  }, []);

  useEffect(() => {
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, clearSession);
    return () => {
      window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, clearSession);
    };
  }, [clearSession]);

  const login = useCallback(async (username: string, password: string) => {
    const res = await http.post("/api/auth/login", { username, password });
    saveSession(res.data.access_token, res.data.user);
  }, [saveSession]);

  const register = useCallback(async (username: string, password: string, displayName: string, role: string) => {
    const res = await http.post("/api/auth/register", { username, password, display_name: displayName, role });
    saveSession(res.data.access_token, res.data.user);
  }, [saveSession]);

  const logout = useCallback(() => {
    void http.post("/api/auth/logout").catch(() => undefined).finally(clearSession);
  }, [clearSession]);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, clearSession }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
