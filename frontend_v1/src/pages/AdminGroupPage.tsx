import {ArrowLeft, BookOpen, CalendarDays, CheckCircle2, Download, Image as ImageIcon, Pencil, X} from "lucide-react";
import {useEffect, useState} from "react";
import {AdminShell} from "@/pages/AdminDashboardPage";
import {EditGroupDialog} from "@/components/teacher/EditGroupDialog";
import {Button} from "@/components/ui/button";
import {Card, CardContent, CardHeader, CardTitle} from "@/components/ui/card";
import {apiRequest, downloadFile} from "@/lib/api";
import type {ClassSession, Group, User} from "@/types/api";

export function AdminGroupPage({groupId, user}: { groupId: string; user: User }) {
    const [group, setGroup] = useState<Group | null>(null);
    const [sessions, setSessions] = useState<ClassSession[]>([]);
    const [loading, setLoading] = useState(true);
    const [exporting, setExporting] = useState(false);
    const [editOpen, setEditOpen] = useState(false);
    const [error, setError] = useState("");
    useEffect(() => {
        async function load() {
            try {
                const [groups, page] = await Promise.all([apiRequest<{
                    items: Group[]
                }>("/api/groups?page=1&page_size=100"), apiRequest<{
                    items: ClassSession[]
                }>(`/api/groups/${groupId}/sessions?page=1&page_size=100`)]);
                setGroup(groups.items.find((item) => item.id === groupId) ?? null);
                setSessions(page.items);
            } catch (err) {
                setError(err instanceof Error ? err.message : "Unable to load group details");
            } finally {
                setLoading(false);
            }
        }

        void load();
    }, [groupId]);

    async function exportGroup() {
        if (!group) return;
        setExporting(true);
        try {
            await downloadFile(`/api/groups/${group.id}/attendance.xlsx`, `${group.name.replaceAll(" ", "_")}_attendance.xlsx`);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Unable to export group attendance");
        } finally {
            setExporting(false);
        }
    }

    if (loading) return <AdminShell user={user} activeKey="overview">
        <div className="flex min-h-[60vh] items-center justify-center text-sm text-muted-foreground">Loading group…
        </div>
    </AdminShell>;
    if (!group) return <AdminShell user={user} activeKey="overview">
        <main className="mx-auto max-w-3xl px-4 py-12"><Card><CardContent className="py-12 text-center"><p
            className="font-medium">{error || "Group not found"}</p><Button className="mt-5"
                                                                            onClick={() => window.history.back()}><ArrowLeft
            className="size-4"/>Back</Button></CardContent></Card></main>
    </AdminShell>;
    return <AdminShell user={user} activeKey="overview">
        <main className="mx-auto max-w-[1200px] px-4 py-8 sm:px-6 lg:px-10">
            <button onClick={() => navigate("/admin")}
                    className="mb-6 inline-flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground">
                <ArrowLeft className="size-4"/>Back to groups
            </button>
            <div className="mb-8 flex flex-wrap items-end justify-between gap-5">
                <div>
                    <h1
                    className="text-3xl font-semibold tracking-tight sm:text-4xl">{group.name}</h1><p
                    className="mt-2 text-sm text-muted-foreground">Join code <span
                    className="font-mono font-semibold text-foreground">{group.join_code}</span></p></div>
                <div className="flex items-center gap-2"><span
                    className="rounded-full bg-muted px-3 py-1.5 text-xs font-semibold capitalize text-muted-foreground">{group.archived_at ? "Archived" : "Active"}</span><Button
                    variant="outline" onClick={() => setEditOpen(true)}><Pencil className="size-4"/>Edit
                    name</Button><Button variant="outline" onClick={() => void exportGroup()}
                                         disabled={exporting}><Download
                    className="size-4"/>{exporting ? "Preparing…" : "Export Excel"}</Button></div>
            </div>
            {error && <div
                className="mb-6 flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                <X className="size-4"/>{error}</div>}
            <div className="mb-8 grid gap-4 grid-cols-2">
                <Metric label="Sessions" value={sessions.length}
                        icon={CalendarDays}/>
                <Metric label="Finalized"
                        value={sessions.filter((session) => session.state === "finalized").length}
                        icon={CheckCircle2}/>
            </div>
            <Card><CardHeader><CardTitle className="text-base">Attendance sessions</CardTitle><p
                className="text-sm text-muted-foreground">Click a session to inspect attendance and classroom
                images.</p></CardHeader><CardContent className="px-0 pb-0">{sessions.length === 0 ?
                <p className="p-10 text-sm text-muted-foreground">No sessions found.</p> :
                <div>{sessions.map((session) => <button key={session.id}
                                                        onClick={() => navigate(`/admin/groups/${group.id}/sessions/${session.id}`)}
                                                        className="flex w-full items-center gap-4 border-t px-6 py-4 text-left transition first:border-t-0 hover:bg-muted/40">
                    <div className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                        <CalendarDays className="size-4"/></div>
                    <div className="min-w-0 flex-1"><p
                        className="font-medium">{new Date(session.started_at).toLocaleString()}</p><p
                        className="mt-1 text-xs text-muted-foreground">{session.attendance.length} attendance records
                        · {session.photos.length} image{session.photos.length === 1 ? "" : "s"}</p></div>
                    <span
                        className="rounded-full bg-muted px-2.5 py-1 text-xs font-semibold capitalize text-muted-foreground">{session.state}</span>
                </button>)}</div>}</CardContent></Card></main>
        <EditGroupDialog group={group} open={editOpen} onOpenChange={setEditOpen} onUpdated={setGroup}
                         onError={setError}/></AdminShell>;
}

function navigate(path: string) {
    window.history.pushState({}, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
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
