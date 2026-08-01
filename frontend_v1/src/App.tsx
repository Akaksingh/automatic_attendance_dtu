import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { LoginPage } from "@/components/auth/LoginPage";
import { Card, CardContent } from "@/components/ui/card";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { TeacherDashboardPage } from "@/pages/TeacherDashboardPage";
import { TeacherGroupPage } from "@/pages/TeacherGroupPage";
import { StudentDashboardPage } from "@/pages/StudentDashboardPage";
import { StudentProfilePage } from "@/pages/StudentProfilePage";
import { StudentGroupPage } from "@/pages/StudentGroupPage";
import { StudentSessionPage } from "@/pages/StudentSessionPage";
import { TeacherProfilePage } from "@/pages/TeacherProfilePage";
import { AdminDashboardPage } from "@/pages/AdminDashboardPage";
import { AdminUsersPage } from "@/pages/AdminUsersPage";
import { AdminImportsPage } from "@/pages/AdminImportsPage";
import { AdminGroupPage } from "@/pages/AdminGroupPage";
import { AdminSessionPage } from "@/pages/AdminSessionPage";
import { AdminProfilePage } from "@/pages/AdminProfilePage";
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
  if (user.role === "teacher") { if (window.location.pathname === "/teacher/profile") return <TeacherProfilePage user={user} />; const match = window.location.pathname.match(/^\/teacher\/groups\/([^/]+)/); return match ? <TeacherGroupPage groupId={match[1]} /> : <TeacherDashboardPage />; }
  if (user.role === "student") { if (window.location.pathname === "/student/profile") return <StudentProfilePage user={user} />; const sessionMatch = window.location.pathname.match(/^\/student\/groups\/([^/]+)\/sessions\/([^/]+)/); if (sessionMatch) return <StudentSessionPage groupId={sessionMatch[1]} sessionId={sessionMatch[2]} />; const groupMatch = window.location.pathname.match(/^\/student\/groups\/([^/]+)/); return groupMatch ? <StudentGroupPage groupId={groupMatch[1]} /> : <StudentDashboardPage user={user} />; }
  if (user.role === "admin") { if (window.location.pathname === "/admin/profile") return <AdminProfilePage user={user} />; if (window.location.pathname === "/admin/users") return <AdminUsersPage user={user} />; if (window.location.pathname === "/admin/imports") return <AdminImportsPage user={user} />; const sessionMatch = window.location.pathname.match(/^\/admin\/groups\/([^/]+)\/sessions\/([^/]+)/); if (sessionMatch) return <AdminSessionPage groupId={sessionMatch[1]} sessionId={sessionMatch[2]} user={user} />; const groupMatch = window.location.pathname.match(/^\/admin\/groups\/([^/]+)/); return groupMatch ? <AdminGroupPage groupId={groupMatch[1]} user={user} /> : <AdminDashboardPage user={user} />; }
  return <BasicDashboard role={user.role} />;
}

export default function App() { return <AuthProvider><Application /></AuthProvider>; }
