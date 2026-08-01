import {BookOpen, CheckCircle2, ChevronRight, Plus, RefreshCw, Search, Users, X} from "lucide-react";
import {useEffect, useState} from "react";
import {AppShell, type NavigationItem} from "@/components/layout/AppShell";
import {Button} from "@/components/ui/button";
import {Card, CardContent, CardHeader, CardTitle} from "@/components/ui/card";
import {Input} from "@/components/ui/input";
import {apiRequest} from "@/lib/api";
import type {Group, User} from "@/types/api";

const navigation: NavigationItem[] = [{key: "groups", label: "My groups", icon: BookOpen}, {
    key: "profile",
    label: "Profile",
    icon: Users
}];

function navigate(path: string) {
    window.history.pushState({}, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
}

export function StudentDashboardPage({user}: { user: User }) {
    const [groups, setGroups] = useState<Group[]>([]);
    const [joinCode, setJoinCode] = useState("");
    const [search, setSearch] = useState("");
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");

    async function loadGroups() {
        setLoading(true);
        try {
            const result = await apiRequest<{ items: Group[] }>("/api/groups?page=1&page_size=100");
            setGroups(result.items);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Unable to load your groups");
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        void loadGroups();
    }, []);

    async function joinGroup(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!joinCode.trim()) return;
        setBusy(true);
        setError("");
        try {
            await apiRequest<Group>("/api/groups/join", {
                method: "POST",
                body: JSON.stringify({join_code: joinCode.trim().toUpperCase()})
            });
            setJoinCode("");
            await loadGroups();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Unable to join group");
        } finally {
            setBusy(false);
        }
    }

    const visibleGroups = groups.filter((group) => `${group.name} ${group.join_code}`.toLowerCase().includes(search.toLowerCase()));
    return <AppShell>
        <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-10">
            <div className="mb-8 flex flex-wrap items-end justify-between gap-5">
                <div>
                    <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Your classes</h1>
                    <p className="mt-2 text-muted-foreground">Open a class to view its attendance history and session
                    details.</p>
                </div>
                <div className="grid grid-cols-4 gap-2">
                    <div className="relative col-span-3"><Search
                        className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"/><Input
                        className="w-full pl-9" value={search} onChange={(event) => setSearch(event.target.value)}
                        placeholder="Search classes…"/></div>
                    <Button variant="outline" onClick={() => void loadGroups()} disabled={loading}><RefreshCw
                        className={`size-4 ${loading ? "animate-spin" : ""}`}/>Refresh</Button></div>
            </div>
            {error && <div
                className="mb-6 flex items-center justify-between rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                <span>{error}</span>
                <button onClick={() => setError("")}><X className="size-4"/></button>
            </div>}<Card className="mb-8 border-primary/20 bg-primary/[0.03]"><CardContent
            className="flex flex-wrap items-center justify-between gap-5 py-5">
            <div><p className="font-semibold">Join another class</p><p
                className="mt-1 text-sm text-muted-foreground">Enter the code shared by your teacher.</p></div>
            <form className="flex w-full max-w-md gap-2" onSubmit={joinGroup}>
                <Input value={joinCode}
                       onChange={(event) => setJoinCode(event.target.value.toUpperCase())}
                       placeholder="Class join code"
                       maxLength={16}
                       className="bg-white text-primary"
                />
                <Button
                type="submit" disabled={busy || !joinCode.trim()}><Plus className="size-4"/>Join class</Button></form>
        </CardContent></Card>
            <div className="mb-5 flex items-end justify-between">
                <div><h2 className="text-xl font-semibold tracking-tight">Enrolled classes</h2><p
                    className="mt-1 text-sm text-muted-foreground">{visibleGroups.length} class{visibleGroups.length === 1 ? "" : "es"} shown</p>
                </div>
            </div>
            {loading ? <div className="py-16 text-center text-sm text-muted-foreground">Loading your
                classes…</div> : visibleGroups.length === 0 ?
                <Card className="border-dashed"><CardContent className="py-16 text-center"><BookOpen
                    className="mx-auto size-9 text-muted-foreground"/><p className="mt-3 font-medium">No matching
                    classes</p><p className="mt-1 text-sm text-muted-foreground">Try another class name or join
                    code.</p></CardContent></Card> :
                <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">{visibleGroups.map((group) => <ClassCard
                    key={group.id} group={group} onOpen={() => navigate(`/student/groups/${group.id}`)}/>)}</div>}
        </main>
    </AppShell>;
}

function ClassCard({group, onOpen}: { group: Group; onOpen: () => void }) {
    return <Card
        className="group p-0 overflow-hidden transition hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg">
        <button className="w-full text-left" onClick={onOpen}>
            <div
                className="relative h-28 overflow-hidden bg-gradient-to-br from-primary via-primary/85 to-slate-700 p-5 text-primary-foreground">
                <div className="absolute -right-8 -top-14 size-40 rounded-full border-[22px] border-white/10"/>
                <div className="relative flex size-10 items-center justify-center rounded-lg bg-white/15"><BookOpen
                    className="size-5"/></div>
                <span className="absolute bottom-4 right-5 text-xs text-white/75">Enrolled</span></div>
            <CardContent className="py-5">
                <div className="flex items-start gap-3">
                    <div className="min-w-0 flex-1"><h3
                        className="truncate text-lg font-semibold tracking-tight group-hover:text-primary">{group.name}</h3>
                        <p className="mt-1 text-sm text-muted-foreground">Join code <span
                            className="font-mono font-medium text-foreground">{group.join_code}</span></p></div>
                    <ChevronRight className="mt-1 size-4 text-muted-foreground group-hover:text-primary"/></div>
                <div className="mt-5 flex items-center gap-2 text-xs text-muted-foreground"><CheckCircle2
                    className="size-3.5 text-emerald-600"/>View attendance and session images
                </div>
            </CardContent></button>
    </Card>;
}
