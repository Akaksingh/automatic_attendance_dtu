import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { apiRequest } from "@/lib/api";
import type { User } from "@/types/api";

interface AuthContextValue { user: User | null; loading: boolean; signIn: (email: string, password: string) => Promise<User>; signOut: () => Promise<void>; }
const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    apiRequest<User>("/api/auth/me").then(setUser).catch(() => apiRequest<{ user: User }>("/api/auth/refresh").then((result) => setUser(result.user)).catch(() => undefined)).finally(() => setLoading(false));
  }, []);
  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading,
    signIn: async (email, password) => { const result = await apiRequest<{ user: User }>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }); setUser(result.user); return result.user; },
    signOut: async () => { await apiRequest<void>("/api/auth/logout", { method: "POST" }).catch(() => undefined); setUser(null); },
  }), [user, loading]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() { const context = useContext(AuthContext); if (!context) throw new Error("useAuth must be used inside AuthProvider"); return context; }
