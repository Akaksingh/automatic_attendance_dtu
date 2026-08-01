import { BookOpenCheck, LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";

export interface NavigationItem { key: string; label: string; icon: React.ComponentType<{ className?: string }>; }

export function AppShell({ children, navigation = [], activeKey, onNavigate }: { children: React.ReactNode; navigation?: NavigationItem[]; activeKey?: string; onNavigate?: (key: string) => void }) {
  const { user, signOut } = useAuth();
  return <div className="min-h-screen bg-muted/40">
    <header className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4">
        <div className="flex items-center gap-3"><div className="flex size-9 items-center justify-center rounded-xl bg-primary text-primary-foreground"><BookOpenCheck className="size-5" /></div><div><p className="font-semibold leading-none">ClassLens</p><p className="mt-1 text-xs capitalize text-muted-foreground">{user?.role} workspace</p></div></div>
        <div className="flex items-center gap-3"><span className="hidden text-sm text-muted-foreground sm:inline">{user?.full_name}</span><Button variant="outline" size="sm" onClick={signOut}><LogOut className="size-4" />Sign out</Button></div>
      </div>
    </header>
    <div className={navigation.length ? "mx-auto flex max-w-[1440px]" : ""}>
      {navigation.length > 0 && <aside className="hidden w-64 shrink-0 border-r bg-background px-4 py-6 md:block"><p className="px-3 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Workspace</p><nav className="mt-4 space-y-1">{navigation.map((item) => { const Icon = item.icon; return <button key={item.key} onClick={() => onNavigate?.(item.key)} className={`flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-sm font-medium transition ${activeKey === item.key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}><Icon className="size-4" />{item.label}</button>; })}</nav></aside>}
      <div className="min-w-0 flex-1 pb-24 md:pb-0">{children}</div>
    </div>
    {navigation.length > 0 && <nav className="fixed inset-x-0 bottom-0 z-20 border-t bg-background/95 px-2 py-2 shadow-lg backdrop-blur md:hidden"><div className="mx-auto grid max-w-lg grid-cols-3 gap-1">{navigation.map((item) => { const Icon = item.icon; return <button key={item.key} onClick={() => onNavigate?.(item.key)} className={`flex flex-col items-center gap-1 rounded-xl px-2 py-2 text-[11px] font-medium ${activeKey === item.key ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}><Icon className="size-5" />{item.label}</button>; })}</div></nav>}
  </div>;
}
