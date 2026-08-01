import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { apiRequest } from "@/lib/api";
import type { Group } from "@/types/api";

export function EditGroupDialog({ group, open, onOpenChange, onUpdated, onError }: { group: Group; open: boolean; onOpenChange: (open: boolean) => void; onUpdated: (group: Group) => void; onError: (message: string) => void }) {
  const [name, setName] = useState(group.name);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setName(group.name); }, [open, group.name]);
  async function submit(event: React.FormEvent<HTMLFormElement>) { event.preventDefault(); if (!name.trim() || name.trim() === group.name) { onOpenChange(false); return; } setBusy(true); try { const updated = await apiRequest<Group>(`/api/groups/${group.id}`, { method: "PATCH", body: JSON.stringify({ name: name.trim() }) }); onUpdated(updated); onOpenChange(false); } catch (err) { onError(err instanceof Error ? err.message : "Unable to rename class"); } finally { setBusy(false); } }
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent><DialogHeader><DialogTitle>Edit class name</DialogTitle><DialogDescription>Choose a clear name that helps teachers and students identify this class.</DialogDescription></DialogHeader><form className="space-y-4" onSubmit={submit}><label className="block space-y-1.5 text-sm font-medium">Class name<Input value={name} onChange={(event) => setName(event.target.value)} required minLength={2} maxLength={200} autoFocus /></label><div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button><Button type="submit" disabled={busy || !name.trim()}>{busy ? "Saving…" : "Save changes"}</Button></div></form></DialogContent></Dialog>;
}
