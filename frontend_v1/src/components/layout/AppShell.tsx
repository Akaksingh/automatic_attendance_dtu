import { BookOpenCheck, ChevronRight, LogOut, Menu, X } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";

export interface NavigationItem { key: string; label: string; icon: React.ComponentType<{ className?: string }>; }

export function AppShell({ children, navigation = [], activeKey, onNavigate }: { children: React.ReactNode; navigation?: NavigationItem[]; activeKey?: string; onNavigate?: (key: string) => void }) {
  const { user, signOut } = useAuth();
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const showNavigation = navigation.length > 0 && (user?.role === "student" || user?.role === "admin");
  const isAdmin = user?.role === "admin";
  function selectNavigation(key: string) { onNavigate?.(key); setMobileNavigationOpen(false); }

  return <div className="min-h-screen bg-muted/30">
    <header className="sticky top-0 z-30 border-b bg-background/90 backdrop-blur-xl">
      <div className="flex h-16 items-center justify-between px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-3"><div className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm"><BookOpenCheck className="size-5" /></div><div><p className="font-semibold leading-none tracking-tight">ClassLens</p><p className="mt-1 text-[11px] capitalize text-muted-foreground">{user?.role} workspace</p></div></div>
        <div className="flex items-center gap-3"><div className="hidden text-right sm:block"><p className="text-sm font-medium leading-tight">{user?.full_name}</p><p className="text-xs text-muted-foreground">{user?.role === "student" ? "Student account" : user?.role === "admin" ? "Administrator account" : "DTU faculty"}</p></div>{isAdmin && showNavigation && <Button variant="outline" size="icon" className="md:hidden" aria-label="Open navigation" onClick={() => setMobileNavigationOpen(true)}><Menu className="size-4" /></Button>}<button type="button" className="flex size-9 items-center justify-center overflow-hidden rounded-full bg-primary/10 text-sm font-semibold text-primary ring-offset-background transition hover:ring-2 hover:ring-primary/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" onClick={() => { if (user?.role) { window.history.pushState({}, "", `/${user.role}/profile`); window.dispatchEvent(new PopStateEvent("popstate")); } }} aria-label={user?.role ? "Open profile" : "Profile avatar"}>{user?.profile_image_url ? <img src={user.profile_image_url} alt="Profile" className="size-full object-cover" /> : user?.full_name?.charAt(0).toUpperCase()}</button><Button variant="outline" size="sm" className="hidden sm:inline-flex" onClick={signOut}><LogOut className="size-4" />Sign out</Button><button className="rounded-md p-2 text-muted-foreground hover:bg-muted sm:hidden" onClick={signOut} aria-label="Sign out"><LogOut className="size-4" /></button></div>
      </div>
    </header>
    <div className={showNavigation ? "mx-auto flex max-w-[1480px]" : ""}>
      {showNavigation && <aside className="hidden w-60 shrink-0 border-r bg-background/70 px-3 py-6 md:block"><p className="px-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Workspace</p><nav className="mt-3 space-y-1">{navigation.map((item) => { const Icon = item.icon; return <button key={item.key} onClick={() => selectNavigation(item.key)} className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-medium transition ${activeKey === item.key ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}><Icon className="size-4" />{item.label}<ChevronRight className={`ml-auto size-3.5 transition ${activeKey === item.key ? "opacity-100" : "opacity-0"}`} /></button>; })}</nav><div className="mt-8 rounded-xl border bg-muted/50 p-4"><p className="text-xs font-semibold">Need a hand?</p><p className="mt-1 text-xs leading-relaxed text-muted-foreground">Open a class to manage its roster or record attendance.</p></div></aside>}
      <div className="min-w-0 flex-1">{children}</div>
    </div>
    {isAdmin && showNavigation && mobileNavigationOpen && <div className="fixed inset-0 z-50 md:hidden"><button className="absolute inset-0 bg-slate-950/45" aria-label="Close navigation" onClick={() => setMobileNavigationOpen(false)} /><aside className="relative h-full w-72 max-w-[85vw] border-r bg-background px-4 py-5 shadow-2xl"><div className="flex items-center justify-between"><p className="px-2 text-sm font-semibold">Admin workspace</p><Button variant="ghost" size="icon" aria-label="Close navigation" onClick={() => setMobileNavigationOpen(false)}><X className="size-4" /></Button></div><nav className="mt-6 space-y-1">{navigation.map((item) => { const Icon = item.icon; return <button key={item.key} onClick={() => selectNavigation(item.key)} className={`flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left text-sm font-medium ${activeKey === item.key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}><Icon className="size-4" />{item.label}</button>; })}</nav></aside></div>}
  </div>;
}
