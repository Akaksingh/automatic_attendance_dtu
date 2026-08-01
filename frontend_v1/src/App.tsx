import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { LoginPage } from "@/components/auth/LoginPage";
import { Card, CardContent } from "@/components/ui/card";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { TeacherDashboardPage } from "@/pages/TeacherDashboardPage";
import { TeacherGroupPage } from "@/pages/TeacherGroupPage";
import type { Role } from "@/types/api";

function routeFor(role: Role) { return `/${role}`; }
function navigate(path: string) { window.history.pushState({}, "", path); window.dispatchEvent(new PopStateEvent("popstate")); }

function BasicDashboard({ role }: { role: Role }) {
  return <AppShell><main className="mx-auto max-w-6xl px-5 py-12"><Card><CardContent className="py-12"><p className="text-sm font-semibold uppercase tracking-[0.16em] text-primary">{role} workspace</p><h1 className="mt-2 text-3xl font-semibold">Your dashboard is ready</h1><p className="mt-3 text-muted-foreground">The {role} workflows are being connected to the new component architecture.</p></CardContent></Card></main></AppShell>;
}

function Application() {
  const { user, loading } = useAuth();
  const [, setPath] = useState(window.location.pathname);
  useEffect(() => { const handle = () => setPath(window.location.pathname); window.addEventListener("popstate", handle); return () => window.removeEventListener("popstate", handle); }, []);
  if (loading) return <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">Loading workspace…</div>;
  if (!user) return <LoginPage onAuthenticated={(role) => navigate(routeFor(role))} />;
  if (user.role === "teacher") { const match = window.location.pathname.match(/^\/teacher\/groups\/([^/]+)/); return match ? <TeacherGroupPage groupId={match[1]} /> : <TeacherDashboardPage />; }
  return <BasicDashboard role={user.role} />;
}

export default function App() { return <AuthProvider><Application /></AuthProvider>; }
