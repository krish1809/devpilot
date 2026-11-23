"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, getStoredToken, setStoredToken, UNAUTHORIZED_EVENT } from "./api";
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
  /** Sign in with the ID token from Google's button. */
  loginWithGoogle: (credential: string) => Promise<void>;
  /** False on the read-only showcase, where sign-up is off. */
  registrationOpen: boolean;
  /** Google OAuth client ID from the API; "" hides Google sign-in. */
  googleClientId: string;
  /** True after the API rejected a stored session (expired, or revoked by a password reset). */
  sessionExpired: boolean;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [demoMode, setDemoMode] = useState(false);
  const [sessionExpired, setSessionExpired] = useState(false);
  const [registrationOpen, setRegistrationOpen] = useState(true);
  const [googleClientId, setGoogleClientId] = useState("");

  // Any signed-in request that gets 401 ends the session everywhere in the app;
  // protected pages then redirect to /login, which explains why.
  useEffect(() => {
    const onUnauthorized = () => {
      setStoredToken(null);
      setUser(null);
      setSessionExpired(true);
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  useEffect(() => {
    api
      .getConfig()
      .then((c) => {
        setDemoMode(Boolean(c.demo_mode));
        setRegistrationOpen(c.registration_open ?? !c.demo_mode);
        setGoogleClientId(c.google_client_id ?? "");
      })
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
    setSessionExpired(false);
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
    setSessionExpired(false);
  }, []);

  const loginWithGoogle = useCallback(async (credential: string) => {
    const token = await api.googleLogin(credential);
    setStoredToken(token.access_token);
    setUser(await api.me(token.access_token));
    setSessionExpired(false);
  }, []);

  const logout = useCallback(() => {
    setStoredToken(null);
    setUser(null);
    setSessionExpired(false);
  }, []);

  const value = useMemo(
    () => ({
      user,
      loading,
      login,
      register,
      logout,
      demoMode,
      loginDemo,
      loginWithGoogle,
      registrationOpen,
      googleClientId,
      sessionExpired,
    }),
    [
      user,
      loading,
      login,
      register,
      logout,
      demoMode,
      loginDemo,
      loginWithGoogle,
      registrationOpen,
      googleClientId,
      sessionExpired,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
