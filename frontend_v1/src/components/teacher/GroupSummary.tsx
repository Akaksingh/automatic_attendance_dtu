import { Download, RefreshCw, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiRequest, downloadFile } from "@/lib/api";
import type { Group, GroupAttendanceSummary } from "@/types/api";

export function GroupSummary({ group, onError }: { group: Group; onError: (message: string) => void }) {
  const [summary, setSummary] = useState<GroupAttendanceSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);

  async function load() {
    setLoading(true);
    try { setSummary(await apiRequest<GroupAttendanceSummary>(`/api/groups/${group.id}/summary`)); }
    catch (err) { onError(err instanceof Error ? err.message : "Unable to load attendance summary"); }
    finally { setLoading(false); }
  }

  useEffect(() => { void load(); }, [group.id]);

  async function exportGroup() {
    setDownloading(true);
    try { await downloadFile(`/api/groups/${group.id}/attendance.xlsx`, `${group.name.replaceAll(" ", "_")}_attendance.xlsx`); }
    catch (err) { onError(err instanceof Error ? err.message : "Unable to export attendance"); }
    finally { setDownloading(false); }
  }

  return <div className="space-y-6"><div className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm font-medium text-primary">Overview</p><h2 className="mt-1 text-2xl font-semibold tracking-tight">Attendance summary</h2><p className="mt-1 text-sm text-muted-foreground">Finalized sessions only. Review sessions are excluded until they are finalized.</p></div><div className="flex gap-2"><Button variant="outline" onClick={() => void load()} disabled={loading}><RefreshCw className={`size-4 ${loading ? "animate-spin" : ""}`} />Refresh</Button><Button onClick={() => void exportGroup()} disabled={downloading}><Download className="size-4" />{downloading ? "Preparing…" : "Export Excel"}</Button></div></div>
    <div className="grid gap-4 sm:grid-cols-2"><Card><CardContent className="flex items-center gap-4 py-5"><div className="flex size-11 items-center justify-center rounded-lg bg-primary/10 text-primary"><RefreshCw className="size-5" /></div><div><p className="text-2xl font-semibold tracking-tight">{loading ? "—" : summary?.total_sessions ?? 0}</p><p className="text-sm text-muted-foreground">Total finalized sessions</p></div></CardContent></Card><Card><CardContent className="flex items-center gap-4 py-5"><div className="flex size-11 items-center justify-center rounded-lg bg-primary/10 text-primary"><Users className="size-5" /></div><div><p className="text-2xl font-semibold tracking-tight">{loading ? "—" : summary?.students.length ?? 0}</p><p className="text-sm text-muted-foreground">Students in roster</p></div></CardContent></Card></div>
    <Card><CardHeader><CardTitle className="text-base">Student attendance</CardTitle></CardHeader><CardContent className="px-0 pb-0">{loading ? <div className="p-8 text-center text-sm text-muted-foreground">Loading summary…</div> : !summary?.students.length ? <div className="p-10 text-center"><Users className="mx-auto size-8 text-muted-foreground" /><p className="mt-3 font-medium">No attendance data yet</p><p className="mt-1 text-sm text-muted-foreground">Finalize a session to start building this summary.</p></div> : <div className="overflow-x-auto"><table className="w-full min-w-[680px] text-sm"><thead className="border-y bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground"><tr><th className="px-6 py-3 font-semibold">Student</th><th className="px-4 py-3 font-semibold">Roll no.</th><th className="px-4 py-3 text-center font-semibold">Present</th><th className="px-4 py-3 text-center font-semibold">Absent</th><th className="px-6 py-3 text-right font-semibold">Attendance</th></tr></thead><tbody>{summary.students.map((student) => <tr key={student.user_id} className="border-b last:border-0"><td className="px-6 py-4 font-medium">{student.full_name}</td><td className="px-4 py-4 text-muted-foreground">{student.roll_no}</td><td className="px-4 py-4 text-center text-emerald-700">{student.present}</td><td className="px-4 py-4 text-center text-rose-700">{student.absent}</td><td className="px-6 py-4 text-right"><span className={`font-semibold ${student.percentage < 75 ? "text-rose-700" : "text-foreground"}`}>{student.percentage.toFixed(2)}%</span></td></tr>)}</tbody></table></div>}</CardContent></Card>
  </div>;
}
