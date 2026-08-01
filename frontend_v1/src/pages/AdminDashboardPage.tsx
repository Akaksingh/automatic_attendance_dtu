import {Activity, BookOpen, ChevronRight, ClipboardList, RefreshCw, Search, ShieldCheck, Users, X} from "lucide-react";
import {useEffect, useState} from "react";
import {AppShell, type NavigationItem} from "@/components/layout/AppShell";
import {Button} from "@/components/ui/button";
import {Card, CardContent} from "@/components/ui/card";
import {Input} from "@/components/ui/input";
import {apiRequest} from "@/lib/api";
import type {Group, User} from "@/types/api";

const navigation: NavigationItem[] = [{key: "overview", label: "Groups", icon: BookOpen}, {
    key: "users",
    label: "Users",
    icon: Users
}, {key: "imports", label: "Bulk imports", icon: ClipboardList}];

function navigate(path: string) {
    window.history.pushState({}, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
}

export function AdminDashboardPage({user}: { user: User }) {
    const [groups, setGroups] = useState<Group[]>([]);
    const [search, setSearch] = useState("");
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    async function load() {
        setLoading(true);
        try {
            const result = await apiRequest<{ items: Group[] }>("/api/groups?page=1&page_size=100");
            setGroups(result.items);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Unable to load groups");
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        void load();
    }, []);
    const visibleGroups = groups.filter((group) => `${group.name} ${group.join_code}`.toLowerCase().includes(search.toLowerCase()));
    return <AdminShell user={user} activeKey="overview">
        <main className="mx-auto max-w-[1500px] px-4 py-8 sm:px-6 lg:px-10">
            <div className="mb-8 flex flex-wrap items-end justify-between gap-5">
                <div>
                    <h1
                    className="text-3xl font-semibold tracking-tight sm:text-4xl">All groups</h1><p
                    className="mt-2 text-muted-foreground">Open a group to inspect its roster, attendance sessions, and
                    records.</p></div>
                <div className="grid grid-cols-4 gap-2">
                    <div className="relative col-span-3"><Search
                        className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"/><Input
                        className="w-full pl-9" value={search} onChange={(event) => setSearch(event.target.value)}
                        placeholder="Search groups…"/></div>
                    <Button variant="outline" onClick={() => void load()} disabled={loading}><RefreshCw
                        className={`size-4 ${loading ? "animate-spin" : ""}`}/>Refresh</Button></div>
            </div>
            {error && <Alert message={error} onClose={() => setError("")}/>}{loading ?
            <div className="py-20 text-center text-sm text-muted-foreground">Loading
                groups…</div> : visibleGroups.length === 0 ?
                <Card className="border-dashed"><CardContent className="py-20 text-center"><BookOpen
                    className="mx-auto size-9 text-muted-foreground"/><p className="mt-3 font-medium">No matching
                    groups</p><p className="mt-1 text-sm text-muted-foreground">Try another name or join code.</p>
                </CardContent></Card> :
                <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">{visibleGroups.map((group) => <GroupCard
                    key={group.id} group={group} onOpen={() => navigate(`/admin/groups/${group.id}`)}/>)}</div>}</main>
    </AdminShell>;
}

export function AdminShell({children, user, activeKey}: { children: React.ReactNode; user: User; activeKey: string }) {
    return <AppShell navigation={navigation} activeKey={activeKey}
                     onNavigate={(key) => navigate(key === "overview" ? "/admin" : `/admin/${key}`)}>{children}</AppShell>;
}

function GroupCard({group, onOpen}: { group: Group; onOpen: () => void }) {
    return <Card
        className="group p-0 overflow-hidden transition hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg">
        <button className="w-full text-left" onClick={onOpen}>
            <div
                className="relative h-32 overflow-hidden bg-gradient-to-br from-primary via-primary/85 to-slate-700 p-5 text-primary-foreground">
                <div className="absolute -right-8 -top-16 size-44 rounded-full border-[24px] border-white/10"/>
                <div className="relative flex size-10 items-center justify-center rounded-lg bg-white/15"><BookOpen
                    className="size-5"/></div>
                <span
                    className="absolute bottom-4 right-5 text-xs text-white/75">{group.archived_at ? "Archived" : "Active"}</span>
            </div>
            <CardContent className="py-5">
                <div className="flex items-start gap-3">
                    <div className="min-w-0 flex-1"><h2
                        className="truncate text-lg font-semibold tracking-tight group-hover:text-primary">{group.name}</h2>
                        <p className="mt-1 text-sm text-muted-foreground">Join code <span
                            className="font-mono font-medium text-foreground">{group.join_code}</span></p></div>
                    <ChevronRight className="mt-1 size-4 text-muted-foreground group-hover:text-primary"/></div>
                <div className="mt-5 flex items-center gap-4 text-xs text-muted-foreground"><span
                    className="inline-flex items-center gap-1.5"><Activity
                    className="size-3.5"/>Open group activity</span><span>Created {new Date(group.created_at).toLocaleDateString()}</span>
                </div>
            </CardContent></button>
    </Card>;
}

function Alert({message, onClose}: { message: string; onClose: () => void }) {
    return <div
        className="mb-6 flex items-center justify-between rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
        <span>{message}</span>
        <button onClick={onClose}><X className="size-4"/></button>
    </div>;
}
