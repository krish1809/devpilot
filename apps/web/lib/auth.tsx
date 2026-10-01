"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { api, getStoredToken, setStoredToken } from "./api";
import type { User } from "./types";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  /** True when the API is a read-only public showcase (DEMO_MODE). */
  demoMode: boolean;
  loginDemo: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [demoMode, setDemoMode] = useState(false);

  useEffect(() => {
    api
      .getConfig()
      .then((c) => setDemoMode(Boolean(c.demo_mode)))
      .catch(() => setDemoMode(false));
  }, []);

  // On first load, validate any stored token by fetching the current user.
  useEffect(() => {
    const token = getStoredToken();
    if (!token) {
      setLoading(false);
      return;
    }
    api
      .me(token)
      .then(setUser)
      .catch(() => {
        setStoredToken(null);
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const token = await api.login(email, password);
    setStoredToken(token.access_token);
    setUser(await api.me(token.access_token));
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    await api.register(email, password);
    const token = await api.login(email, password);
    setStoredToken(token.access_token);
    setUser(await api.me(token.access_token));
  }, []);

  const loginDemo = useCallback(async () => {
    const token = await api.demoLogin();
    setStoredToken(token.access_token);
    setUser(await api.me(token.access_token));
  }, []);

  const logout = useCallback(() => {
    setStoredToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, register, logout, demoMode, loginDemo }),
    [user, loading, login, register, logout, demoMode, loginDemo],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
