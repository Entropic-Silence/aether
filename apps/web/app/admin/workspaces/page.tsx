"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus, Trash2, Users } from "lucide-react";
import { request, getToken } from "@/lib/api";
import { Button, IconBtn, Spinner } from "@/components/ui";

const inputCls =
  "w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm outline-none focus:border-accent";

interface WorkspaceInfo { id: string; name: string; role: string }
interface Member { user_id: string; email: string; name: string; role: string }

export default function WorkspacesAdminPage() {
  const [workspaces, setWorkspaces] = useState<WorkspaceInfo[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [members, setMembers] = useState<Member[] | null>(null);
  const [newName, setNewName] = useState("");
  const [memberEmail, setMemberEmail] = useState("");
  const [memberRole, setMemberRole] = useState("member");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    request<WorkspaceInfo[]>("/workspaces").then((ws) => {
      setWorkspaces(ws);
      if (ws.length && !selected) setSelected(ws[0].id);
    }).catch(() => setWorkspaces([]));
  }, [selected]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!selected) { setMembers(null); return; }
    request<Member[]>(`/workspaces/${selected}/members`).then(setMembers).catch(() => setMembers([]));
  }, [selected]);

  const createWorkspace = async () => {
    if (!newName.trim()) return;
    setError(null);
    try {
      const ws = await request<WorkspaceInfo>("/workspaces", { method: "POST", body: JSON.stringify({ name: newName }) });
      setNewName("");
      load();
      setSelected(ws.id);
    } catch (e) { setError(e instanceof Error ? e.message : "Failed"); }
  };

  const addMember = async () => {
    if (!selected || !memberEmail.trim()) return;
    setError(null);
    try {
      await request(`/workspaces/${selected}/members`, { method: "POST", body: JSON.stringify({ email: memberEmail, role: memberRole }) });
      setMemberEmail("");
      const m = await request<Member[]>(`/workspaces/${selected}/members`);
      setMembers(m);
    } catch (e) { setError(e instanceof Error ? e.message : "Failed"); }
  };

  const changeRole = async (userId: string, role: string) => {
    if (!selected) return;
    await request(`/workspaces/${selected}/members/${userId}`, { method: "PATCH", body: JSON.stringify({ role }) });
    const m = await request<Member[]>(`/workspaces/${selected}/members`);
    setMembers(m);
  };

  const removeMember = async (userId: string) => {
    if (!selected) return;
    await request(`/workspaces/${selected}/members/${userId}`, { method: "DELETE" });
    const m = await request<Member[]>(`/workspaces/${selected}/members`);
    setMembers(m);
  };

  if (!workspaces) return <Spinner className="h-6 w-6 text-[var(--muted)]" />;

  return (
    <div className="max-w-3xl">
      <h1 className="mb-1 text-xl font-semibold">Workspaces</h1>
      <p className="mb-4 text-sm text-[var(--muted)]">Multi-tenant workspaces and their members.</p>

      <div className="mb-4 flex gap-2">
        <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="New workspace name" className={inputCls} />
        <Button variant="primary" onClick={createWorkspace} disabled={!newName.trim()}><Plus size={15} /> Create</Button>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {workspaces.map((w) => (
          <button key={w.id} type="button" onClick={() => setSelected(w.id)}
            className={"rounded-full px-3 py-1.5 text-sm " + (selected === w.id ? "bg-[var(--fg)] text-[var(--bg)]" : "bg-[var(--surface)] text-[var(--muted)]")}>
            {w.name} <span className="opacity-60">({w.role})</span>
          </button>
        ))}
      </div>

      {selected && (
        <div>
          <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold"><Users size={15} /> Members</h2>
          <div className="mb-3 flex gap-2">
            <input value={memberEmail} onChange={(e) => setMemberEmail(e.target.value)} placeholder="user email" className={inputCls} />
            <select value={memberRole} onChange={(e) => setMemberRole(e.target.value)} className={inputCls + " !w-32"}>
              <option value="member">member</option>
              <option value="admin">admin</option>
            </select>
            <Button variant="primary" onClick={addMember} disabled={!memberEmail.trim()}>Add</Button>
          </div>
          {error && <div className="mb-2 text-sm text-red-500">{error}</div>}
          {!members ? (
            <Spinner className="h-5 w-5 text-[var(--muted)]" />
          ) : (
            <div className="overflow-hidden rounded-xl border border-[var(--border)]">
              <table className="w-full text-sm">
                <thead className="bg-[var(--surface)] text-left text-xs text-[var(--muted)]">
                  <tr><th className="px-4 py-2">Email</th><th className="px-4 py-2">Role</th><th className="px-4 py-2"></th></tr>
                </thead>
                <tbody>
                  {members.map((m) => (
                    <tr key={m.user_id} className="border-t border-[var(--border)]">
                      <td className="px-4 py-2">{m.email}</td>
                      <td className="px-4 py-2">
                        {m.role === "owner" ? (
                          <span className="text-accent">owner</span>
                        ) : (
                          <select value={m.role} onChange={(e) => changeRole(m.user_id, e.target.value)}
                            className="rounded border border-[var(--border)] bg-transparent px-2 py-1 text-xs">
                            <option value="member">member</option>
                            <option value="admin">admin</option>
                          </select>
                        )}
                      </td>
                      <td className="px-4 py-2 text-right">
                        {m.role !== "owner" && (
                          <IconBtn title="Remove" onClick={() => removeMember(m.user_id)}><Trash2 size={14} /></IconBtn>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
