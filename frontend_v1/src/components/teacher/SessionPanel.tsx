import {Check, Clock3, Download, FileImage, ImagePlus, Loader2, Play, Trash2, UploadCloud} from "lucide-react";
import {useEffect, useRef, useState} from "react";
import {Button} from "@/components/ui/button";
import {Card, CardContent, CardHeader, CardTitle} from "@/components/ui/card";
import {ConfirmDialog} from "@/components/ui/confirm-dialog";
import {apiRequest, downloadFile, mediaUrl} from "@/lib/api";
import type {AttendanceStatus, ClassSession, Group, RosterStudent} from "@/types/api";
import {AttendanceReview} from "@/components/teacher/AttendanceReview";

function progress(session: ClassSession) {
    return session.processing_total ? Math.round((session.processing_completed / session.processing_total) * 100) : 0;
}

export function SessionPanel({group, roster, onError}: {
    group: Group;
    roster: RosterStudent[];
    onError: (message: string) => void
}) {
    const [sessions, setSessions] = useState<ClassSession[]>([]);
    const [active, setActive] = useState<ClassSession | null>(null);
    const [busy, setBusy] = useState(false);
    const [exporting, setExporting] = useState(false);
    const [deleteOpen, setDeleteOpen] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);

    async function load() {
        try {
            const result = await apiRequest<{
                items: ClassSession[]
            }>(`/api/groups/${group.id}/sessions?page=1&page_size=20`);
            setSessions(result.items);
            setActive((current) => current ? result.items.find((item) => item.id === current.id) ?? current : null);
        } catch (err) {
            onError(err instanceof Error ? err.message : "Unable to load sessions");
        }
    }

    useEffect(() => {
        setActive(null);
        void load();
    }, [group.id]);
    useEffect(() => {
        if (!active || active.state !== "processing") return;
        const timer = window.setInterval(() => void load(), 1500);
        return () => window.clearInterval(timer);
    }, [active?.id, active?.state, group.id]);

    async function startSession() {
        setBusy(true);
        try {
            const session = await apiRequest<ClassSession>(`/api/groups/${group.id}/sessions`, {method: "POST"});
            setActive(session);
            setSessions((current) => [session, ...current]);
        } catch (err) {
            onError(err instanceof Error ? err.message : "Unable to start session");
        } finally {
            setBusy(false);
        }
    }

    async function upload(selected: FileList | null) {
        if (!active || !selected?.length) return;
        setBusy(true);
        const body = new FormData();
        Array.from(selected).forEach((file) => body.append("files", file));
        try {
            const session = await apiRequest<ClassSession>(`/api/sessions/${active.id}/photos`, {method: "POST", body});
            setActive(session);
            setSessions((current) => current.map((item) => item.id === session.id ? session : item));
        } catch (err) {
            onError(err instanceof Error ? err.message : "Unable to upload classroom images");
        } finally {
            setBusy(false);
            if (inputRef.current) inputRef.current.value = "";
        }
    }

    async function processPhotos() {
        if (!active || !active.photos.length) return;
        setBusy(true);
        try {
            const session = await apiRequest<ClassSession>(`/api/sessions/${active.id}/process`, {method: "POST"});
            setActive(session);
            setSessions((current) => current.map((item) => item.id === session.id ? session : item));
        } catch (err) {
            onError(err instanceof Error ? err.message : "Unable to process classroom images");
        } finally {
            setBusy(false);
        }
    }

    async function updateAttendance(studentId: string, status: AttendanceStatus) {
        if (!active) return;
        try {
            const updated = await apiRequest<{
                id: string;
                student_id: string;
                status: AttendanceStatus;
                marked_at: string
            }>(`/api/sessions/${active.id}/attendance/${studentId}`, {method: "PATCH", body: JSON.stringify({status})});
            setActive((current) => current ? {
                ...current,
                attendance: [...current.attendance.filter((record) => record.student_id !== studentId), updated]
            } : current);
        } catch (err) {
            onError(err instanceof Error ? err.message : "Unable to update attendance");
        }
    }

    async function finalize() {
        if (!active) return;
        try {
            const result = await apiRequest<ClassSession>(`/api/sessions/${active.id}/finalize`, {method: "POST"});
            setActive(result);
            await load();
        } catch (err) {
            onError(err instanceof Error ? err.message : "Unable to finalize session");
        }
    }

    async function executeRemove() {
        if (!active) return;
        try {
            await apiRequest<void>(`/api/sessions/${active.id}`, {method: "DELETE"});
            setActive(null);
            await load();
        } catch (err) {
            onError(err instanceof Error ? err.message : "Unable to delete session");
        }
    }

    async function exportSession() {
        if (!active) return;
        setExporting(true);
        try {
            await downloadFile(`/api/sessions/${active.id}/attendance.xlsx`, "session_attendance.xlsx");
        } catch (err) {
            onError(err instanceof Error ? err.message : "Unable to export session attendance");
        } finally {
            setExporting(false);
        }
    }

    return <div className="space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
                <h2 className="mt-1 text-2xl font-semibold tracking-tight">Take Attendance</h2><p
                className="mt-1 text-sm text-muted-foreground">Select a classroom image to upload it immediately. Add
                more from different corners before processing.</p></div>
            <Button onClick={startSession}
                    disabled={busy || Boolean(group.archived_at) || Boolean(active && ["created", "processing"].includes(active.state))}><Play
                className="size-4"/>Start new session</Button></div>
        {active &&
            <Card className="overflow-hidden border-primary/20 shadow-sm"><CardHeader className="">
                <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                        <div className="flex items-center gap-2"><CardTitle
                            className="text-base">{new Date(active.started_at).toLocaleString()}</CardTitle><span
                            className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold capitalize text-primary">{active.state}</span>
                        </div>
                        <p className="mt-1 flex items-center gap-1.5 text-sm text-muted-foreground"><Clock3
                            className="size-3.5"/>{active.state === "created" ? `${active.photos.length} photo${active.photos.length === 1 ? "" : "s"} saved · add more before processing.` : active.state === "review" ? "Review detected attendance before finalizing." : active.state === "finalized" ? "This attendance record is finalized." : active.processing_message ?? "Processing classroom images…"}
                        </p></div>
                    <div className="flex flex-wrap gap-2">
                        {active.state !== "created" && active.state !== "processing" &&
                            <Button variant="outline" onClick={() => void exportSession()} disabled={exporting}><Download
                                className="size-4"/>{exporting ? "Preparing…" : "Export Excel"}
                            </Button>
                        }
                        {active.state === "review" &&
                            <Button onClick={finalize}><Check className="size-4"/>Finalize attendance</Button>
                        }
                        {active.state !== "finalized" &&
                            <Button variant="outline" onClick={() => setDeleteOpen(true)}><Trash2 className="size-4"/>Delete</Button>
                        }
                    </div>
                </div>
            </CardHeader><CardContent className="space-y-6 py-0">
                {active.state === "created" && <div className="space-y-5">
                    <div
                        className="flex flex-wrap items-center justify-between gap-3 rounded-xl border-2 border-dashed border-primary/25 bg-primary/[0.03] p-5">
                        <div><p className="font-semibold">Add another classroom image</p><p
                            className="mt-1 text-sm text-muted-foreground">Each selected image uploads
                            automatically.</p></div>
                        <label
                            className={`inline-flex h-10 cursor-pointer items-center gap-2 rounded-md border bg-background px-4 text-sm shadow-xs hover:bg-accent ${busy ? "pointer-events-none opacity-60" : ""}`}><FileImage
                            className="size-4"/>{busy ? "Uploading…" : "Choose image"}<input ref={inputRef} type="file"
                                                                                             className="hidden"
                                                                                             accept="image/jpeg,image/png,image/webp"
                                                                                             multiple disabled={busy}
                                                                                             onChange={(event) => void upload(event.target.files)}/></label>
                    </div>
                    {active.photos.length > 0 && <div
                        className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">{active.photos.map((photo, index) => {
                        const url = mediaUrl(photo.image_url);
                        return <a key={photo.id} href={url} target="_blank" rel="noreferrer"
                                  className="group overflow-hidden rounded-xl border bg-background">
                            <div className="aspect-[4/3] overflow-hidden bg-muted"><img src={url}
                                                                                        alt={`Uploaded classroom image ${index + 1}`}
                                                                                        className="size-full object-cover transition group-hover:scale-105"/>
                            </div>
                            <p className="truncate px-3 py-2 text-xs text-muted-foreground">Image {index + 1}</p></a>;
                    })}</div>}{active.photos.length > 0 &&
                    <div className="flex justify-end"><Button onClick={processPhotos} disabled={busy}><ImagePlus
                        className="size-4"/>Process {active.photos.length} photo{active.photos.length === 1 ? "" : "s"}
                    </Button></div>}</div>}
                {active.state === "processing" && <div className="rounded-xl border bg-muted/30 p-5">
                    <div className="mb-2 flex justify-between text-sm"><span
                        className="font-medium">{active.processing_message ?? "Processing classroom images…"}</span><span
                        className="font-semibold text-primary">{progress(active)}%</span></div>
                    <div className="h-2 overflow-hidden rounded-full bg-muted">
                        <div className="h-full rounded-full bg-primary transition-all"
                             style={{width: `${progress(active)}%`}}/>
                    </div>
                    <p className="mt-2 text-xs text-muted-foreground">Recognition is processing all uploaded images.</p>
                </div>}
                {active.state !== "created" && <AttendanceReview session={active} roster={roster}
                                                                 onUpdate={(studentId, status) => void updateAttendance(studentId, status)}/>}
            </CardContent></Card>}
        <div>
            <div className="mb-3"><h3 className="font-semibold">Session history</h3><p
                className="text-sm text-muted-foreground">Select a session to review its results.</p></div>
            {sessions.length === 0 ? <div className="rounded-xl border border-dashed p-10 text-center"><ImagePlus
                className="mx-auto size-8 text-muted-foreground"/><p className="mt-3 font-medium">No sessions yet</p><p
                className="mt-1 text-sm text-muted-foreground">Start a session when you are ready to record
                attendance.</p></div> : <div className="grid gap-3">{sessions.map((session) => <button key={session.id}
                                                                                                       onClick={() => setActive(session)}
                                                                                                       className={`rounded-xl border bg-background p-4 text-left transition hover:border-primary/40 hover:shadow-sm ${active?.id === session.id ? "border-primary ring-1 ring-primary/20" : ""}`}>
                <div className="flex items-center justify-between gap-3"><span
                    className="font-medium">{new Date(session.started_at).toLocaleString()}</span><span
                    className="rounded-full bg-muted px-2.5 py-1 text-xs capitalize text-muted-foreground">{session.state}</span>
                </div>
                <p className="mt-2 text-sm text-muted-foreground">{session.photos.length} photo{session.photos.length === 1 ? "" : "s"} · {session.attendance.length} attendance
                    result{session.attendance.length === 1 ? "" : "s"}</p></button>)}</div>}</div>
        <ConfirmDialog open={deleteOpen} onOpenChange={setDeleteOpen} title="Delete attendance session?"
                       description="This will permanently remove the session and its attendance results. This action cannot be undone."
                       confirmLabel="Delete session" destructive
                       onConfirm={() => void executeRemove().then(() => setDeleteOpen(false))}/>
    </div>;
}
