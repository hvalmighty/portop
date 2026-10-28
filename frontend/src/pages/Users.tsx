import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, DataTable, Field, Input, Loading, Modal, PageHeader, Panel, Select, useToast } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useEntity } from "../lib/entity";
import { dt } from "../lib/format";

interface U { id: number; username: string; full_name: string; email: string; role: string; entities: string[]; is_active: boolean; locked: boolean; last_login: string | null }
const ROLES = ["ADMIN", "PM", "TRADER", "COMPLIANCE", "RISK", "OPS", "VIEWER"];

export default function Users() {
  const { user: me } = useAuth();
  const { entities } = useEntity();
  const qc = useQueryClient();
  const toast = useToast();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<U[]>("/system/users") });
  const perms = useQuery({ queryKey: ["perms"], queryFn: () => api<Record<string, string[]>>("/system/permissions") });
  const [modal, setModal] = useState(false);
  const [f, setF] = useState({ username: "", full_name: "", email: "", role: "VIEWER", password: "", entities: [] as string[] });
  const done = (m: string) => { toast("ok", m); qc.invalidateQueries({ queryKey: ["users"] }); };
  const err = (e: unknown) => toast("err", (e as Error).message);
  const create = useMutation({ mutationFn: () => api("/system/users", { method: "POST", json: f }), onSuccess: () => { setModal(false); done("User created"); }, onError: err });
  const patch = useMutation({ mutationFn: ({ u, body }: { u: string; body: unknown }) => api(`/system/users/${u}`, { method: "PATCH", json: body }), onSuccess: () => done("User updated"), onError: err });
  const unlock = useMutation({ mutationFn: (u: string) => api(`/system/users/${u}/unlock`, { method: "POST" }), onSuccess: () => done("User unlocked"), onError: err });

  if (users.isLoading) return <Loading />;
  return (
    <div>
      <PageHeader title="Users & Roles" subtitle="Role-based access · entity entitlements · segregation of duties (maker ≠ checker)">
        <Button variant="primary" onClick={() => setModal(true)}>+ New user</Button>
      </PageHeader>
      <DataTable rows={users.data ?? []} rowKey={(u) => u.id} columns={[
        { key: "u", header: "Username", render: (u) => <span className="font-mono font-semibold">{u.username}</span>, sort: (u) => u.username },
        { key: "n", header: "Name", render: (u) => u.full_name },
        { key: "e", header: "Email", render: (u) => <span className="text-dim">{u.email}</span> },
        { key: "r", header: "Role", render: (u) => (
          <Select value={u.role} disabled={u.username === me?.username} className="h-7" aria-label={`Role for ${u.username}`}
            onChange={(e) => patch.mutate({ u: u.username, body: { role: e.target.value } })}>
            {ROLES.map((r) => <option key={r}>{r}</option>)}</Select>) },
        { key: "en", header: "Entities", render: (u) => <span className="font-mono">{u.entities.length ? u.entities.join(", ") : "All"}</span> },
        { key: "s", header: "Status", render: (u) => u.locked ? <Badge tone="FAIL">Locked</Badge> : u.is_active ? <Badge tone="PASS">Active</Badge> : <Badge>Disabled</Badge> },
        { key: "l", header: "Last login", render: (u) => <span className="font-mono text-[11.5px] text-dim">{dt(u.last_login)}</span> },
        { key: "x", header: "", align: "right", render: (u) => u.username === me?.username ? <span className="lbl text-mute">you</span> : (
          <span className="flex justify-end gap-1">
            {u.locked && <Button size="sm" onClick={() => unlock.mutate(u.username)}>Unlock</Button>}
            <Button size="sm" variant={u.is_active ? "danger" : "up"} onClick={() => patch.mutate({ u: u.username, body: { is_active: !u.is_active } })}>{u.is_active ? "Disable" : "Enable"}</Button>
          </span>) },
      ]} />
      <Panel title="Permission matrix" className="m-3" pad={false}>
        <DataTable rows={Object.entries(perms.data ?? {})} rowKey={([p]) => p} columns={[
          { key: "p", header: "Permission", render: ([p]) => <span className="font-mono">{p}</span> },
          ...ROLES.map((r) => ({ key: r, header: r, align: "center" as const, render: ([, roles]: [string, string[]]) => roles.includes(r) ? <span className="text-up">●</span> : <span className="text-line-2">·</span> })),
        ]} />
      </Panel>
      <Modal open={modal} onClose={() => setModal(false)} title="New user">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Username"><Input value={f.username} onChange={(e) => setF({ ...f, username: e.target.value.toLowerCase() })} /></Field>
          <Field label="Full name"><Input value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></Field>
          <Field label="Email"><Input value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
          <Field label="Role"><Select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{ROLES.map((r) => <option key={r}>{r}</option>)}</Select></Field>
          <Field label="Initial password" hint="≥10 chars, letters + digits/symbols"><Input type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
          <Field label="Entities (none = all)">
            <div className="flex h-8 items-center gap-3">{entities.map((e) => (
              <label key={e.code} className="flex items-center gap-1 font-mono text-[12px]"><input type="checkbox" checked={f.entities.includes(e.code)}
                onChange={() => setF({ ...f, entities: f.entities.includes(e.code) ? f.entities.filter((x) => x !== e.code) : [...f.entities, e.code] })} />{e.code}</label>))}</div>
          </Field>
        </div>
        <div className="mt-4 flex justify-end gap-2"><Button variant="ghost" onClick={() => setModal(false)}>Cancel</Button>
          <Button variant="primary" disabled={create.isPending} onClick={() => create.mutate()}>Create</Button></div>
      </Modal>
    </div>
  );
}
