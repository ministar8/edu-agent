"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { API_BASE_URL } from "./api";
import {
  AUTH_UNAUTHORIZED_EVENT,
  clearStoredToken,
  getAuthHeaders,
  getStoredToken,
  saveStoredToken,
} from "./http";

interface User {
  id: number;
  username: string;
  display_name: string;
  role: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string, displayName: string, role: string) => Promise<void>;
  logout: () => void;
  clearSession: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

async function getResponseErrorMessage(res: Response, fallback: string) {
  try {
    const data = await res.json();
    return typeof data.detail === "string" && data.detail.trim() ? data.detail : fallback;
  } catch {
    return fallback;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const clearSession = useCallback(() => {
    setToken(null);
    setUser(null);
    clearStoredToken();
  }, []);

  useEffect(() => {
    const savedToken = getStoredToken();
    if (!savedToken) {
      setLoading(false);
      return;
    }

    const restoreSession = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/auth/me`, {
          headers: { Authorization: `Bearer ${savedToken}` },
        });
        if (!res.ok) {
          clearSession();
          return;
        }
        const currentUser = await res.json();
        setToken(savedToken);
        setUser(currentUser);
      } catch {
        clearSession();
      } finally {
        setLoading(false);
      }
    };

    void restoreSession();
  }, [clearSession]);

  const _saveSession = useCallback((newToken: string, newUser: User) => {
    setToken(newToken);
    setUser(newUser);
    saveStoredToken(newToken);
  }, []);

  useEffect(() => {
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, clearSession);
    return () => {
      window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, clearSession);
    };
  }, [clearSession]);

  const login = useCallback(async (username: string, password: string) => {
    const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      throw new Error(await getResponseErrorMessage(res, "登录失败"));
    }
    const data = await res.json();
    _saveSession(data.access_token, data.user);
  }, [_saveSession]);

  const register = useCallback(async (username: string, password: string, displayName: string, role: string) => {
    const res = await fetch(`${API_BASE_URL}/api/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify({ username, password, display_name: displayName, role }),
    });
    if (!res.ok) {
      throw new Error(await getResponseErrorMessage(res, "注册失败"));
    }
    const data = await res.json();
    _saveSession(data.access_token, data.user);
  }, [_saveSession]);

  const logout = useCallback(() => {
    clearSession();
  }, [clearSession]);

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout, clearSession }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
