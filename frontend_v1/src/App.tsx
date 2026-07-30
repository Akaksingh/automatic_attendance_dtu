import { useEffect, useState } from "react";
import { ArrowRight, BookOpenCheck, LockKeyhole, LogOut, Mail, ShieldCheck, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Role = "admin" | "teacher" | "student";
type User = { id: number; email: string; full_name: string; role: Role; profile_image_url: string | null };
type LoginResponse = { user: User };

const dashboardFor = (role: Role) => `/${role}`;

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { ...options, credentials: "include", headers: { "Content-Type": "application/json", ...(options.headers ?? {}) } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? "Request failed");
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

function goToDashboard(role: Role) {
  window.history.pushState({}, "", dashboardFor(role));
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setBusy(true);
    try { const result = await request<LoginResponse>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }); onLogin(result.user); goToDashboard(result.user.role); }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to sign in"); }
    finally { setBusy(false); }
  }

  return <main className="flex min-h-screen items-center justify-center bg-muted/40 px-4 py-10">
    <section className="grid w-full max-w-5xl overflow-hidden rounded-2xl border bg-background shadow-lg lg:grid-cols-[1.05fr_0.95fr]">
      <div className="hidden bg-primary p-12 text-primary-foreground lg:flex lg:flex-col lg:justify-between"><div className="flex size-12 items-center justify-center rounded-xl bg-primary-foreground text-primary"><BookOpenCheck /></div><div><p className="mb-4 text-sm font-semibold uppercase tracking-[0.18em] text-primary-foreground/70">ClassLens</p><h1 className="max-w-sm text-4xl font-semibold leading-tight">Attendance management, made simpler.</h1><p className="mt-5 max-w-sm text-primary-foreground/70">One secure workspace for administrators, teachers, and students.</p></div><p className="text-sm text-primary-foreground/60">Role-based access with secure sessions.</p></div>
      <Card className="border-0 py-0 shadow-none"><CardContent className="p-7 sm:p-12"><div className="mb-8 lg:hidden"><div className="mb-5 flex size-11 items-center justify-center rounded-xl bg-primary text-primary-foreground"><BookOpenCheck /></div><p className="text-sm font-semibold uppercase tracking-[0.16em] text-muted-foreground">ClassLens</p></div><h2 className="text-2xl font-semibold tracking-tight">Welcome back</h2><p className="mt-2 text-sm text-muted-foreground">Sign in to continue to your workspace.</p>
        <form className="mt-8 space-y-5" onSubmit={submit}><div className="space-y-2"><Label htmlFor="email">Email address</Label><div className="relative"><Mail className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><Input id="email" value={email} onChange={e => setEmail(e.target.value)} type="email" autoComplete="email" placeholder="you@dtu.ac.in" className="pl-10" required /></div></div><div className="space-y-2"><Label htmlFor="password">Password</Label><div className="relative"><LockKeyhole className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><Input id="password" value={password} onChange={e => setPassword(e.target.value)} type="password" autoComplete="current-password" placeholder="Enter your password" className="pl-10" required /></div></div><Button className="w-full" type="submit" disabled={busy}>{busy ? "Signing in…" : "Continue"} <ArrowRight className="size-4" /></Button></form>{error && <p role="alert" className="mt-5 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}</CardContent></Card>
    </section></main>;
}

function Dashboard({ user, onLogout }: { user: User; onLogout: () => void }) {
  const isStudent = user.role === "student";
  const title = user.role === "admin" ? "Administrator dashboard" : user.role === "teacher" ? "Teacher dashboard" : "Student dashboard";
  const description = user.role === "admin" ? "Manage teachers and oversee every group." : user.role === "teacher" ? "Create and manage the groups you own." : "Join groups and review your attendance.";
  return <main className="min-h-screen bg-muted/40"><header className="border-b bg-background"><div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4"><div className="flex items-center gap-3"><div className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground"><BookOpenCheck className="size-5" /></div><span className="font-semibold">ClassLens</span></div><Button variant="outline" onClick={onLogout}><LogOut className="mr-2 size-4" />Sign out</Button></div></header><div className="mx-auto max-w-6xl px-5 py-10"><p className="text-sm font-medium capitalize text-muted-foreground">{user.role}</p><h1 className="mt-2 text-3xl font-semibold">{title}</h1><p className="mt-2 text-muted-foreground">{description}</p><div className="mt-8 grid gap-4 md:grid-cols-3"><Card><CardContent className="pt-6"><h2 className="flex items-center gap-2 font-semibold"><ShieldCheck className="size-5" />Account</h2><p className="mt-4 font-medium">{user.full_name}</p><p className="text-sm text-muted-foreground">{user.email}</p><p className="mt-4 text-sm">Update your {isStudent ? "profile image or password" : "profile"} in account settings.</p></CardContent></Card><Card><CardContent className="pt-6"><h2 className="flex items-center gap-2 font-semibold"><Users className="size-5" />{isStudent ? "My groups" : "Groups"}</h2><p className="mt-4 text-sm text-muted-foreground">{isStudent ? "Join a group with its join code." : user.role === "admin" ? "View all groups across the platform." : "View groups created by you."}</p></CardContent></Card><Card><CardContent className="pt-6"><h2 className="font-semibold">{isStudent ? "Attendance" : "Class sessions"}</h2><p className="mt-4 text-sm text-muted-foreground">{isStudent ? "Your attendance records will appear here." : "Create and review attendance sessions here."}</p></CardContent></Card></div></div></main>;
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => { request<User>("/api/auth/me").then(setUser).catch(() => request<LoginResponse>("/api/auth/refresh").then(result => setUser(result.user)).catch(() => undefined)).finally(() => setLoading(false)); }, []);
  if (loading) return <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">Loading…</div>;
  if (!user) return <Login onLogin={setUser} />;
  return <Dashboard user={user} onLogout={async () => { await request<void>("/api/auth/logout", { method: "POST" }).catch(() => undefined); setUser(null); window.history.pushState({}, "", "/"); }} />;
}
