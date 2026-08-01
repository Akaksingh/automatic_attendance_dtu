import {Check, CircleAlert, CircleDashed, Image as ImageIcon, UserCheck, UserX} from "lucide-react";
import {Button} from "@/components/ui/button";
import type {AttendanceStatus, ClassSession, RosterStudent} from "@/types/api";
import {mediaUrl} from "@/lib/api";

interface AttendanceReviewProps {
    session: ClassSession;
    roster: RosterStudent[];
    onUpdate: (studentId: string, status: AttendanceStatus) => void;
}

export function AttendanceReview({session, roster, onUpdate}: AttendanceReviewProps) {
    const records = new Map(session.attendance.map((record) => [record.student_id, record]));
    const present = roster.filter((student) => records.get(student.user_id)?.status === "present").length;
    const absent = roster.filter((student) => records.get(student.user_id)?.status === "absent").length;
    const unresolved = Math.max(roster.length - present - absent, 0);
    const canEdit = session.state === "review";

    return <section className="space-y-4 border-t pt-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
            <div><p className="text-base font-semibold">Review attendance</p><p
                className="mt-1 text-sm text-muted-foreground">Check the detected results and correct anything before
                finalizing.</p></div>
            <div className="flex gap-2 text-xs font-semibold"><span
                className="rounded-full bg-emerald-50 px-3 py-1.5 text-emerald-700">{present} present</span><span
                className="rounded-full bg-rose-50 px-3 py-1.5 text-rose-700">{absent} absent</span>{unresolved > 0 &&
                <span
                    className="rounded-full bg-muted px-3 py-1.5 text-muted-foreground">{unresolved} unresolved</span>}
            </div>
        </div>
        {session.photos.length > 0 && <div className="rounded-xl border bg-muted/20 p-4">
            <div className="mb-3 flex items-center gap-2"><ImageIcon className="size-4 text-primary"/><p
                className="text-sm font-semibold">Session images</p><span className="text-xs text-muted-foreground">Click an image to view full size</span>
            </div>
            <div
                className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">{session.photos.map((photo, index) => {
                const url = mediaUrl(photo.image_url);
                return <a key={photo.id} href={url} target="_blank" rel="noreferrer"
                          className="group overflow-hidden rounded-lg border bg-background">
                    <div className="aspect-[4/3] overflow-hidden bg-muted"><img src={url}
                                                                                alt={`Session image ${index + 1}`}
                                                                                className="size-full object-cover transition group-hover:scale-105"/>
                    </div>
                    <p className="truncate px-2.5 py-2 text-xs text-muted-foreground">Image {index + 1}</p></a>;
            })}</div>
        </div>}
        {session.state === "failed" && <div
            className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
            <CircleAlert className="mt-0.5 size-4 shrink-0"/>
            <div><p className="font-semibold">Face detection failed</p><p
                className="mt-1">{session.processing_message ?? "The worker could not process these classroom images."}</p>
            </div>
        </div>}
        {roster.length === 0 ?
            <div className="rounded-lg border border-dashed p-5 text-sm text-muted-foreground">There are no students in
                this group yet.</div> : <div className="overflow-hidden rounded-xl border">
                <div
                    className="hidden grid-cols-[1fr_150px_190px] border-b bg-muted/40 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground sm:grid">
                    <span>Student</span><span>Detected status</span><span className="text-right">Correction</span></div>
                {roster.map((student) => {
                    const record = records.get(student.user_id);
                    const status = record?.status;
                    return <div key={student.user_id}
                                className="grid gap-3 border-b px-4 py-3 last:border-0 even:bg-muted/[0.18] sm:grid-cols-[1fr_150px_190px] sm:items-center">
                        <div className="min-w-0"><p className="truncate text-sm font-medium">{student.full_name}</p><p
                            className="text-xs text-muted-foreground">Roll no. {student.roll_no}</p></div>
                        <StatusPill status={status}/>
                        <div className="flex justify-start gap-2 sm:justify-end">{canEdit ? <><Button size="sm"
                                                                                                      variant={status === "present" ? "default" : "outline"}
                                                                                                      className={status === "present" ? "bg-emerald-700 hover:bg-emerald-800" : ""}
                                                                                                      onClick={() => onUpdate(student.user_id, "present")}><UserCheck
                            className="size-3.5"/>Present</Button><Button size="sm"
                                                                          variant={status === "absent" ? "default" : "outline"}
                                                                          className={status === "absent" ? "bg-rose-700 hover:bg-rose-800" : ""}
                                                                          onClick={() => onUpdate(student.user_id, "absent")}><UserX
                            className="size-3.5"/>Absent</Button></> : <span
                            className="text-xs text-muted-foreground">{session.state === "finalized" ? "Finalized" : "Read only"}</span>}</div>
                    </div>;
                })}</div>}
    </section>;
}

function StatusPill({status}: { status: AttendanceStatus | undefined }) {
    if (status === "present") return <span
        className="inline-flex w-fit items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700"><Check
        className="size-3.5"/>Present</span>;
    if (status === "absent") return <span
        className="inline-flex w-fit items-center gap-1.5 rounded-full bg-rose-50 px-2.5 py-1 text-xs font-semibold text-rose-700"><UserX
        className="size-3.5"/>Absent</span>;
    return <span
        className="inline-flex w-fit items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600"><CircleDashed
        className="size-3.5"/>Unresolved</span>;
}
