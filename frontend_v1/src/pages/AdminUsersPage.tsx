import { CheckCircle2, Loader2, MoreHorizontal, Pencil, Plus, RefreshCw, Search, Shield, UserPlus, Users, X } from "lucide-react";
import { useEffect, useState } from "react";
import { AdminShell } from "@/pages/AdminDashboardPage";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { apiRequest } from "@/lib/api";
import type { Role, User } from "@/types/api";

export function AdminUsersPage({ user }: { user: User }) {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<"" | Role>("");
  const [pendingAction, setPendingAction] = useState<{ type: "reset" | "disable" | "enable"; target: User } | null>(null);
  const [teacherOpen, setTeacherOpen] = useState(false);
  const [studentOpen, setStudentOpen] = useState(false);
  const [editStudent, setEditStudent] = useState<User | null>(null);
  const [editStudentForm, setEditStudentForm] = useState({ full_name: "", email: "", roll_no: "" });
  const [teacher, setTeacher] = useState({ full_name: "", email: "", password: "" });
  const [student, setStudent] = useState({ full_name: "", email: "", roll_no: "" });

  async function load() {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ page: "1", page_size: "100" });
      if (search.trim()) params.set("search", search.trim());
      if (roleFilter) params.set("role", roleFilter);
      const result = await apiRequest<{ items: User[] }>(`/api/admin/users?${params.toString()}`);
      setUsers(result.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load users");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 250);
    return () => window.clearTimeout(timer);
  }, [search, roleFilter]);

  async function createTeacher(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await apiRequest<User>("/api/admin/teachers", { method: "POST", body: JSON.stringify(teacher) });
      setTeacher({ full_name: "", email: "", password: "" });
      setTeacherOpen(false);
      setMessage("Teacher account created.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create teacher");
    } finally {
      setBusy(false);
    }
  }

  async function createStudent(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const body = new FormData();
    body.append("full_name", student.full_name);
    body.append("email", student.email);
    body.append("roll_no", student.roll_no);
    try {
      await apiRequest<unknown>("/api/admin/students", { method: "POST", body });
      setStudent({ full_name: "", email: "", roll_no: "" });
      setStudentOpen(false);
      setMessage("Student account created and welcome email queued.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create student");
    } finally {
      setBusy(false);
    }
  }

  function openStudentEditor(target: User) {
    setEditStudent(target);
    setEditStudentForm({ full_name: target.full_name, email: target.email, roll_no: target.roll_no ?? "" });
  }

  async function updateStudent(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editStudent) return;
    setBusy(true);
    setError("");
    try {
      const updated = await apiRequest<User>(`/api/admin/students/${editStudent.id}`, { method: "PATCH", body: JSON.stringify(editStudentForm) });
      setUsers((current) => current.map((item) => item.id === updated.id ? updated : item));
      setEditStudent(null);
      setMessage("Student details updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update student details");
    } finally {
      setBusy(false);
    }
  }

  function resetPassword(target: User) {
    setPendingAction({ type: "reset", target });
  }

  async function executeResetPassword(target: User) {
    setActionBusy(target.id);
    setError("");
    try {
      await apiRequest<User>(`/api/admin/users/${target.id}/reset-password`, { method: "POST" });
      setMessage(`Password reset for ${target.full_name}. A temporary password was queued by email.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to reset password");
    } finally {
      setActionBusy(null);
    }
  }

  function disableAccount(target: User) {
    setPendingAction({ type: "disable", target });
  }

  function enableAccount(target: User) {
    setPendingAction({ type: "enable", target });
  }

  async function executeDisableAccount(target: User) {
    setActionBusy(target.id);
    setError("");
    try {
      const updated = await apiRequest<User>(`/api/admin/users/${target.id}/disable`, { method: "POST" });
      setUsers((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setMessage(`${target.full_name}'s account has been disabled.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to disable account");
    } finally {
      setActionBusy(null);
    }
  }

  async function executeEnableAccount(target: User) {
    setActionBusy(target.id);
    setError("");
    try {
      const updated = await apiRequest<User>(`/api/admin/users/${target.id}/enable`, { method: "POST" });
      setUsers((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setMessage(`${target.full_name}'s account has been re-enabled.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to re-enable account");
    } finally {
      setActionBusy(null);
    }
  }

  return (
    <AdminShell user={user} activeKey="users">
      <main className="mx-auto max-w-[1500px] px-4 py-8 sm:px-6 lg:px-10">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="mb-2 text-sm font-medium text-primary">Administration</p>
            <h1 className="text-3xl font-semibold tracking-tight">Users</h1>
            <p className="mt-2 text-muted-foreground">Create, search, and manage teacher and student accounts.</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => void load()} disabled={loading}><RefreshCw className="size-4" />Refresh</Button>
            <Button variant="outline" onClick={() => setStudentOpen(true)}><UserPlus className="size-4" />Create student</Button>
            <Button onClick={() => setTeacherOpen(true)}><Shield className="size-4" />Create teacher</Button>
          </div>
        </div>

        {error && <Alert message={error} onClose={() => setError("")} />}
        {message && <div className="mb-6 flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700"><CheckCircle2 className="size-4" />{message}<button className="ml-auto" onClick={() => setMessage("")}><X className="size-4" /></button></div>}

        <Dialog open={teacherOpen} onOpenChange={setTeacherOpen}>
          <DialogContent>
            <DialogHeader><DialogTitle>Create teacher account</DialogTitle><DialogDescription>Teachers can manage their own classes and attendance.</DialogDescription></DialogHeader>
            <AccountForm fields={[{ label: "Full name", value: teacher.full_name, set: (value) => setTeacher((current) => ({ ...current, full_name: value })) }, { label: "Email", value: teacher.email, set: (value) => setTeacher((current) => ({ ...current, email: value })) }, { label: "Temporary password", value: teacher.password, set: (value) => setTeacher((current) => ({ ...current, password: value })) }]} onSubmit={createTeacher} busy={busy} submit="Create teacher" />
          </DialogContent>
        </Dialog>
        <Dialog open={studentOpen} onOpenChange={setStudentOpen}>
          <DialogContent>
            <DialogHeader><DialogTitle>Create student account</DialogTitle><DialogDescription>A temporary password will be generated and sent to the student by email.</DialogDescription></DialogHeader>
            <AccountForm fields={[{ label: "Full name", value: student.full_name, set: (value) => setStudent((current) => ({ ...current, full_name: value })) }, { label: "Email", value: student.email, set: (value) => setStudent((current) => ({ ...current, email: value })) }, { label: "Roll number", value: student.roll_no, set: (value) => setStudent((current) => ({ ...current, roll_no: value })) }]} onSubmit={createStudent} busy={busy} submit="Create student" />
          </DialogContent>
        </Dialog>
        <Dialog open={Boolean(editStudent)} onOpenChange={(open) => { if (!open && !busy) setEditStudent(null); }}>
          <DialogContent>
            <DialogHeader><DialogTitle>Edit student details</DialogTitle><DialogDescription>Update the student’s name, email address, or roll number.</DialogDescription></DialogHeader>
            <AccountForm fields={[{ label: "Full name", value: editStudentForm.full_name, set: (value) => setEditStudentForm((current) => ({ ...current, full_name: value })) }, { label: "Email", value: editStudentForm.email, set: (value) => setEditStudentForm((current) => ({ ...current, email: value })) }, { label: "Roll number", value: editStudentForm.roll_no, set: (value) => setEditStudentForm((current) => ({ ...current, roll_no: value })) }]} onSubmit={updateStudent} busy={busy} submit="Save changes" />
          </DialogContent>
        </Dialog>
        <ConfirmDialog
          open={Boolean(pendingAction)}
          onOpenChange={(open) => { if (!open && !actionBusy) setPendingAction(null); }}
          title={pendingAction?.type === "reset" ? "Reset password?" : pendingAction?.type === "enable" ? "Re-enable account?" : "Disable account?"}
          description={pendingAction?.type === "reset" ? `A new temporary password will be emailed to ${pendingAction.target.full_name}. Existing sessions will be signed out.` : pendingAction?.type === "enable" ? `${pendingAction.target.full_name} will be allowed to sign in again.` : `${pendingAction?.target.full_name} will no longer be able to sign in.`}
          confirmLabel={pendingAction?.type === "reset" ? "Reset password" : pendingAction?.type === "enable" ? "Re-enable account" : "Disable account"}
          destructive={pendingAction?.type === "disable"}
          busy={Boolean(pendingAction && actionBusy === pendingAction.target.id)}
          onConfirm={() => { if (!pendingAction) return; const action = pendingAction.type === "reset" ? executeResetPassword : pendingAction.type === "enable" ? executeEnableAccount : executeDisableAccount; void action(pendingAction.target).then(() => setPendingAction(null)); }}
        />

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base"><Users className="size-4 text-primary" />All users <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-normal">{users.length}</span></CardTitle>
            <div className="flex flex-wrap gap-3 pt-3">
              <div className="relative min-w-[260px] flex-1"><Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><Input className="pl-9" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search email, roll number, or name" /></div>
              <select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value as "" | Role)} className="h-10 rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"><option value="">All roles</option><option value="admin">Admins</option><option value="teacher">Teachers</option><option value="student">Students</option></select>
            </div>
          </CardHeader>
          <CardContent className="px-0 pb-0">
            {loading ? <p className="p-8 text-sm text-muted-foreground">Loading users…</p> : users.length === 0 ? <p className="p-8 text-sm text-muted-foreground">No users match the selected filters.</p> : <div className="overflow-x-auto"><table className="w-full min-w-[820px] text-sm"><thead className="border-y bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground"><tr><th className="px-6 py-3">Name</th><th className="px-4 py-3">Email</th><th className="px-4 py-3">Role</th><th className="px-4 py-3">Status</th><th className="px-6 py-3 text-right">Actions</th></tr></thead><tbody>{users.map((item) => <tr key={item.id} className="border-b last:border-0"><td className="px-6 py-4 font-medium">{item.full_name}</td><td className="px-4 py-4 text-muted-foreground">{item.email}</td><td className="px-4 py-4 capitalize">{item.role}</td><td className="px-4 py-4"><span className={`inline-flex items-center gap-1.5 text-xs font-medium ${item.is_active ? "text-emerald-700" : "text-destructive"}`}>{item.is_active ? <CheckCircle2 className="size-3.5" /> : <X className="size-3.5" />}{item.is_active ? "Active" : "Disabled"}</span></td><td className="px-6 py-3 text-right"><DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="icon" aria-label={`Actions for ${item.full_name}`} disabled={actionBusy === item.id}>{actionBusy === item.id ? <Loader2 className="size-4 animate-spin" /> : <MoreHorizontal className="size-4" />}</Button></DropdownMenuTrigger><DropdownMenuContent align="end" className="w-48"><DropdownMenuItem onSelect={() => resetPassword(item)}>Reset password</DropdownMenuItem>{item.role === "student" && <DropdownMenuItem onSelect={() => openStudentEditor(item)}><Pencil className="size-4" />Edit student details</DropdownMenuItem>}{item.is_active && item.id !== user.id && <DropdownMenuItem className="text-destructive focus:text-destructive" onSelect={() => disableAccount(item)}>Disable account</DropdownMenuItem>}{!item.is_active && <DropdownMenuItem className="text-emerald-700 focus:text-emerald-700" onSelect={() => enableAccount(item)}>Re-enable account</DropdownMenuItem>}</DropdownMenuContent></DropdownMenu></td></tr>)}</tbody></table></div>}
          </CardContent>
        </Card>
      </main>
    </AdminShell>
  );
}

function AccountForm({ fields, onSubmit, busy, submit }: { fields: Array<{ label: string; value: string; set: (value: string) => void }>; onSubmit: (event: React.FormEvent<HTMLFormElement>) => void; busy: boolean; submit: string }) {
  return <form className="space-y-4" onSubmit={onSubmit}>{fields.map((field) => <label key={field.label} className="block space-y-1.5 text-sm font-medium">{field.label}<Input type={field.label.toLowerCase().includes("password") ? "password" : field.label === "Email" ? "email" : "text"} value={field.value} onChange={(event) => field.set(event.target.value)} required /></label>)}<Button className="w-full" type="submit" disabled={busy}>{busy ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}{submit}</Button></form>;
}

function Alert({ message, onClose }: { message: string; onClose: () => void }) {
  return <div className="mb-6 flex items-center justify-between rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive"><span>{message}</span><button onClick={onClose}><X className="size-4" /></button></div>;
}
