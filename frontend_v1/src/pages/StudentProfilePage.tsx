import { ArrowLeft, CheckCircle2, KeyRound, Loader2, LockKeyhole, Mail, Upload, UserRound, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { AppShell, type NavigationItem } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiRequest } from "@/lib/api";
import type { PhotoJob, StudentOut, User } from "@/types/api";

const navigation: NavigationItem[] = [
  { key: "groups", label: "My groups", icon: UserRound },
  { key: "profile", label: "Profile", icon: UserRound },
];

function navigate(path: string) { window.history.pushState({}, "", path); window.dispatchEvent(new PopStateEvent("popstate")); }

export function StudentProfilePage({ user }: { user: User }) {
  const [profile, setProfile] = useState<StudentOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [passwords, setPasswords] = useState({ current: "", next: "", confirm: "" });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  async function loadProfile() {
    setLoading(true);
    try { setProfile(await apiRequest<StudentOut>("/api/students/me")); }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to load profile"); }
    finally { setLoading(false); }
  }
  useEffect(() => { void loadProfile(); }, []);

  const currentPhoto = useMemo(() => profile?.profile_image_url ?? profile?.photos.find((photo) => photo.is_profile)?.image_url ?? profile?.photos[0]?.image_url ?? null, [profile]);

  async function uploadPhoto(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; if (!file) return; setUploading(true); setMessage(""); setError("");
    const body = new FormData(); body.append("file", file);
    try {
      const job = await apiRequest<PhotoJob>("/api/students/me/photos", { method: "POST", body });
      let current = job;
      for (let attempt = 0; attempt < 30 && ["pending", "processing"].includes(current.status); attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        current = await apiRequest<PhotoJob>(`/api/students/me/photo-jobs/${job.id}`);
      }
      if (current.status !== "approved") throw new Error(current.error ?? "Photo verification failed");
      await loadProfile(); setMessage("Profile photo updated successfully.");
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to upload profile photo"); }
    finally { setUploading(false); if (inputRef.current) inputRef.current.value = ""; }
  }

  async function updatePassword(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setMessage(""); setError("");
    if (passwords.next.length < 8) { setError("New password must be at least 8 characters."); return; }
    if (passwords.next !== passwords.confirm) { setError("New password and confirmation do not match."); return; }
    setPasswordBusy(true);
    try { await apiRequest<User>("/api/auth/me", { method: "PATCH", body: JSON.stringify({ current_password: passwords.current, new_password: passwords.next }) }); setPasswords({ current: "", next: "", confirm: "" }); setMessage("Password updated. You may need to sign in again on other devices."); }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to update password"); }
    finally { setPasswordBusy(false); }
  }

  return <AppShell navigation={navigation} activeKey="profile" onNavigate={(key) => key === "groups" ? navigate("/student") : navigate("/student/profile")}><main className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-10"><button onClick={() => navigate("/student")} className="mb-6 inline-flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" />Back to dashboard</button><div className="mb-8"><p className="mb-2 text-sm font-medium text-primary">Account</p><h1 className="text-3xl font-semibold tracking-tight">Your profile</h1><p className="mt-2 text-muted-foreground">Manage your student details, profile photo, and password.</p></div>{error && <div className="mb-6 flex items-center justify-between rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive"><span>{error}</span><button onClick={() => setError("")}><X className="size-4" /></button></div>}{message && <div className="mb-6 flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700"><CheckCircle2 className="size-4" />{message}</div>}<div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]"><Card><CardHeader><CardTitle className="text-base">Student details</CardTitle></CardHeader><CardContent className="space-y-5">{loading ? <p className="text-sm text-muted-foreground">Loading profile…</p> : <><div className="flex items-center gap-4"><div className="flex size-16 items-center justify-center overflow-hidden rounded-full bg-primary/10 text-xl font-semibold text-primary">{currentPhoto ? <img src={currentPhoto} alt="Current profile" className="size-full object-cover" /> : user.full_name.charAt(0).toUpperCase()}</div><div><p className="text-lg font-semibold">{profile?.full_name ?? user.full_name}</p><p className="text-sm text-muted-foreground">Student account</p></div></div><div className="grid gap-4 sm:grid-cols-2"><Info icon={UserRound} label="Roll number" value={profile?.roll_no ?? "—"} /><Info icon={Mail} label="Email address" value={user.email} /></div><div className="rounded-lg border bg-muted/30 p-4"><div className="flex items-center justify-between gap-4"><div><p className="text-sm font-medium">Profile photo</p><p className="mt-1 text-xs text-muted-foreground">Use a clear, front-facing photo with one face.</p></div><Button variant="outline" onClick={() => inputRef.current?.click()} disabled={uploading}>{uploading ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />}{uploading ? "Verifying…" : "Upload photo"}</Button></div><input ref={inputRef} className="hidden" type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => void uploadPhoto(event)} /></div></>}</CardContent></Card><Card><CardHeader><CardTitle className="flex items-center gap-2 text-base"><LockKeyhole className="size-4 text-primary" />Update password</CardTitle></CardHeader><CardContent><form className="space-y-4" onSubmit={updatePassword}><Field label="Current password" value={passwords.current} onChange={(value) => setPasswords((current) => ({ ...current, current: value }))} /><Field label="New password" value={passwords.next} onChange={(value) => setPasswords((current) => ({ ...current, next: value }))} /><Field label="Confirm new password" value={passwords.confirm} onChange={(value) => setPasswords((current) => ({ ...current, confirm: value }))} /><Button className="w-full" type="submit" disabled={passwordBusy}>{passwordBusy ? <Loader2 className="size-4 animate-spin" /> : <KeyRound className="size-4" />}Change password</Button></form></CardContent></Card></div></main></AppShell>;
}

function Info({ icon: Icon, label, value }: { icon: typeof UserRound; label: string; value: string }) { return <div className="rounded-lg border p-3"><div className="flex items-center gap-2 text-xs text-muted-foreground"><Icon className="size-3.5" />{label}</div><p className="mt-2 truncate text-sm font-medium">{value}</p></div>; }
function Field({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) { return <label className="block space-y-1.5 text-sm font-medium">{label}<Input type="password" value={value} onChange={(event) => onChange(event.target.value)} required /></label>; }
