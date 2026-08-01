import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { apiRequest } from "@/lib/api";
import type { Group } from "@/types/api";

export function CreateGroupDialog({ open, onOpenChange, onCreated, onError }: { open: boolean; onOpenChange: (open: boolean) => void; onCreated: (group: Group) => void; onError: (message: string) => void }) {
  const [name, setName] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(event: React.FormEvent<HTMLFormElement>) { event.preventDefault(); if (!name.trim()) return; setBusy(true); try { const group = await apiRequest<Group>("/api/groups", { method: "POST", body: JSON.stringify({ name: name.trim() }) }); onCreated(group); setName(""); onOpenChange(false); } catch (err) { onError(err instanceof Error ? err.message : "Unable to create group"); } finally { setBusy(false); } }
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent><DialogHeader><DialogTitle>Create a new class</DialogTitle><DialogDescription>Give your group a clear name. You can add students and share the join code next.</DialogDescription></DialogHeader><form className="space-y-5" onSubmit={submit}><div><label className="mb-2 block text-sm font-medium" htmlFor="group-name">Group name</label><Input id="group-name" autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. CSE 4A — Data Structures" /></div><div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button type="submit" disabled={busy || !name.trim()}>{busy ? "Creating…" : "Create group"}</Button></div></form></DialogContent></Dialog>;
}
