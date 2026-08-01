import {ArrowLeft, BookOpen, CalendarDays, CheckCircle2, Clock3, Users, X} from "lucide-react";
import {useEffect, useMemo, useState} from "react";
import {AppShell, type NavigationItem} from "@/components/layout/AppShell";
import {Button} from "@/components/ui/button";
import {Card, CardContent, CardHeader, CardTitle} from "@/components/ui/card";
import {apiRequest} from "@/lib/api";
import type {ClassSession, Group} from "@/types/api";

const navigation: NavigationItem[] = [{key: "groups", label: "My groups", icon: BookOpen}, {
    key: "profile",
    label: "Profile",
    icon: Users
}];

function navigate(path: string) {
    window.history.pushState({}, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
}

export function StudentGroupPage({groupId}: { groupId: string }) {
    const [group, setGroup] = useState<Group | null>(null);
    const [sessions, setSessions] = useState<ClassSession[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    useEffect(() => {
        async function load() {
            try {
                const [groups, sessionPage] = await Promise.all([apiRequest<{
                    items: Group[]
                }>("/api/groups?page=1&page_size=100"), apiRequest<{
                    items: ClassSession[]
                }>(`/api/groups/${groupId}/sessions?page=1&page_size=100`)]);
                setGroup(groups.items.find((item) => item.id === groupId) ?? null);
                setSessions(sessionPage.items);
            } catch (err) {
                setError(err instanceof Error ? err.message : "Unable to load class details");
            } finally {
                setLoading(false);
            }
        }

        void load();
    }, [groupId]);
    const completed = useMemo(() => sessions.filter((session) => ["review", "finalized", "failed"].includes(session.state)), [sessions]);
    const present = completed.filter((session) => session.attendance[0]?.status === "present").length;
    if (loading) return <AppShell>
        <div className="flex min-h-[60vh] items-center justify-center text-sm text-muted-foreground">Loading class…
        </div>
    </AppShell>;
    if (!group) return <AppShell>
        <main className="mx-auto max-w-3xl px-4 py-12"><Card><CardContent className="py-12 text-center"><p
            className="font-medium">{error || "Class not found"}</p><Button className="mt-5"
                                                                            onClick={() => navigate("/student")}><ArrowLeft
            className="size-4"/>Back to classes</Button></CardContent></Card></main>
    </AppShell>;
    return <AppShell>
        <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-10">
            <button onClick={() => navigate("/student")}
                    className="mb-6 inline-flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground">
                <ArrowLeft className="size-4"/>Back to classes
            </button>
            <div className="mb-8 flex flex-wrap items-end justify-between gap-5">
                <div>
                    <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{group.name}</h1><p
                    className="mt-2 text-sm text-muted-foreground">Join code <span
                    className="font-mono font-semibold text-foreground">{group.join_code}</span></p></div>
            </div>
            {error && <div
                className="mb-6 flex items-center justify-between rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                <span>{error}</span>
                <button onClick={() => setError("")}><X className="size-4"/></button>
            </div>}
            <div className="mb-8 grid gap-4 grid-cols-3">
                <Metric label="Sessions" value={completed.length} icon={CalendarDays}/>
                <Metric label="Present" value={present} icon={CheckCircle2}/>
                <Metric label="Attendance" value={completed.length ? `${Math.round((present / completed.length) * 100)}%` : "—"} icon={Clock3}/>
            </div>
            <Card><CardHeader><CardTitle className="text-base">Attendance sessions</CardTitle><p
                className="text-sm text-muted-foreground">Open a session to view your status and the classroom
                images.</p></CardHeader><CardContent className="px-0 pb-0">{completed.length === 0 ?
                <div className="p-12 text-center text-sm text-muted-foreground">No completed attendance sessions
                    yet.</div> : <div>{completed.map((session) => <button key={session.id}
                                                                          onClick={() => navigate(`/student/groups/${group.id}/sessions/${session.id}`)}
                                                                          className="flex w-full items-center gap-4 border-t px-6 py-4 text-left transition first:border-t-0 hover:bg-muted/40">
                    <div className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                        <CalendarDays className="size-4"/></div>
                    <div className="min-w-0 flex-1"><p
                        className="font-medium">{new Date(session.started_at).toLocaleString()}</p><p
                        className="mt-1 text-xs text-muted-foreground">{session.photos.length} classroom
                        image{session.photos.length === 1 ? "" : "s"} · Click to view details</p></div>
                    <Status status={session.attendance[0]?.status}/><span
                    className="text-xs text-muted-foreground">{session.state}</span>
                </button>)}</div>}</CardContent></Card></main>
    </AppShell>;
}

function Metric({label, value, icon: Icon}: { label: string; value: number | string; icon: typeof CalendarDays }) {
    return <Card className="py-4">
        <CardContent className="flex items-center justify-center sm:justify-start gap-4">
        <div className="sm:flex md:size-10 items-center justify-center rounded-lg bg-primary/10 text-primary hidden">
            <Icon className="size-5"/>
        </div>
        <div className="flex flex-col items-center justify-between gap-y-2">
            <p className="text-2xl font-semibold">{value}</p>
            <p className="text-xs text-muted-foreground">{label}</p>
        </div>
        </CardContent>
    </Card>;
}

function Status({status}: { status?: string }) {
    return <span
        className={`rounded-full px-2.5 py-1 text-xs font-semibold ${status === "present" ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}`}>{status === "present" ? "Present" : "Absent"}</span>;
}
