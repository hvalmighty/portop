import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, DataTable, Field, Input, Loading, Modal, PageHeader, Select, useToast } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { dt } from "../lib/format";

interface Rule { id: number; code: string; name: string; category: string; rule_type: string; scope: string; scope_ref: string | null; params: Record<string, unknown>; severity: string; is_active: boolean; version: number; updated_by: string; updated_at: string }
type RuleTypes = Record<string, { params: Record<string, string>; desc: string }>;

function parseParam(kind: string, v: string): unknown {
  if (kind === "number") return Number(v);
  if (kind === "list") return v.split(",").map((x) => x.trim()).filter(Boolean);
  return v;
}
const showParam = (v: unknown) => (Array.isArray(v) ? v.join(", ") : String(v ?? ""));

export default function Rules() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const { data: rules = [], isLoading } = useQuery({ queryKey: ["rules"], queryFn: () => api<Rule[]>("/compliance/rules") });
  const { data: types = {} } = useQuery({ queryKey: ["rule-types"], queryFn: () => api<RuleTypes>("/compliance/rule-types") });
  const [editing, setEditing] = useState<Rule | "new" | null>(null);
  const [history, setHistory] = useState<Rule | null>(null);
  const hist = useQuery({ queryKey: ["rule-hist", history?.id], enabled: !!history,
    queryFn: () => api<{ version: number; snapshot: Record<string, unknown>; changed_by: string; changed_at: string }[]>(`/compliance/rules/${history!.id}/history`) });

  const [form, setForm] = useState<{ code: string; name: string; category: string; rule_type: string; scope: string; scope_ref: string; severity: string; params: Record<string, string>; is_active: boolean }>(
    { code: "", name: "", category: "MANDATE", rule_type: "MAX_ISSUER_WEIGHT", scope: "GLOBAL", scope_ref: "", severity: "HARD", params: {}, is_active: true });
  const open = (r: Rule | "new") => {
    setEditing(r);
    if (r === "new") setForm({ code: "", name: "", category: "MANDATE", rule_type: "MAX_ISSUER_WEIGHT", scope: "GLOBAL", scope_ref: "", severity: "HARD", params: {}, is_active: true });
    else setForm({ code: r.code, name: r.name, category: r.category, rule_type: r.rule_type, scope: r.scope, scope_ref: r.scope_ref ?? "", severity: r.severity, is_active: r.is_active,
      params: Object.fromEntries(Object.entries(r.params).map(([k, v]) => [k, showParam(v)])) });
  };
  const schema = types[form.rule_type]?.params ?? {};
  const params = Object.fromEntries(Object.entries(schema).filter(([k]) => form.params[k] !== undefined && form.params[k] !== "").map(([k, kind]) => [k, parseParam(kind, form.params[k])]));

  const save = useMutation({
    mutationFn: () => editing === "new"
      ? api("/compliance/rules", { method: "POST", json: { ...form, scope_ref: form.scope === "GLOBAL" ? null : form.scope_ref, params } })
      : api(`/compliance/rules/${(editing as Rule).id}`, { method: "PATCH", json: { name: form.name, severity: form.severity, is_active: form.is_active, params } }),
    onSuccess: () => { toast("ok", "Rule saved — new version recorded"); setEditing(null); qc.invalidateQueries({ queryKey: ["rules"] }); },
    onError: (e) => toast("err", (e as Error).message),
  });

  if (isLoading) return <Loading />;
  return (
    <div>
      <PageHeader title="Rule Library" subtitle="No-code rule engine · every change versioned with effective history">
        {can("compliance:write") && <Button variant="primary" onClick={() => open("new")}>+ New rule</Button>}
      </PageHeader>
      <DataTable rows={rules} rowKey={(r) => r.id} onRowClick={(r) => (can("compliance:write") ? open(r) : setHistory(r))} columns={[
        { key: "c", header: "Code", render: (r) => <span className="font-mono font-semibold">{r.code}</span>, sort: (r) => r.code },
        { key: "n", header: "Rule", render: (r) => r.name, sort: (r) => r.name },
        { key: "cat", header: "Category", render: (r) => <span className="lbl">{r.category}</span>, sort: (r) => r.category },
        { key: "t", header: "Type", render: (r) => <span className="font-mono text-[11.5px] text-dim">{r.rule_type}</span> },
        { key: "s", header: "Scope", render: (r) => <span className="font-mono text-[12px]">{r.scope}{r.scope_ref ? `:${r.scope_ref}` : ""}</span> },
        { key: "p", header: "Parameters", render: (r) => <span className="font-mono text-[11.5px] text-dim">{Object.entries(r.params).map(([k, v]) => `${k}=${showParam(v)}`).join("  ") || "—"}</span> },
        { key: "sv", header: "Severity", render: (r) => <Badge>{r.severity}</Badge> },
        { key: "a", header: "Active", render: (r) => (r.is_active ? <Badge tone="PASS">On</Badge> : <Badge>Off</Badge>) },
        { key: "v", header: "Ver", align: "right", render: (r) => `v${r.version}` },
        { key: "u", header: "Last change", render: (r) => <span className="text-[11.5px] text-dim">{r.updated_by} · {dt(r.updated_at)}</span> },
        { key: "h", header: "", render: (r) => <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); setHistory(r); }}>History</Button> },
      ]} />

      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing === "new" ? "New compliance rule" : `Edit ${form.code}`}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Code"><Input value={form.code} disabled={editing !== "new"} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} /></Field>
          <Field label="Category"><Select value={form.category} disabled={editing !== "new"} onChange={(e) => setForm({ ...form, category: e.target.value })}>
            <option>REGULATORY</option><option>MANDATE</option><option>INTERNAL</option></Select></Field>
          <div className="col-span-2"><Field label="Name"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field></div>
          <Field label="Rule type" hint={types[form.rule_type]?.desc}>
            <Select value={form.rule_type} disabled={editing !== "new"} onChange={(e) => setForm({ ...form, rule_type: e.target.value, params: {} })}>
              {Object.keys(types).map((t) => <option key={t}>{t}</option>)}</Select></Field>
          <Field label="Severity"><Select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}><option>HARD</option><option>SOFT</option></Select></Field>
          <Field label="Scope"><Select value={form.scope} disabled={editing !== "new"} onChange={(e) => setForm({ ...form, scope: e.target.value })}><option>GLOBAL</option><option>ENTITY</option><option>ACCOUNT</option></Select></Field>
          <Field label="Scope reference"><Input value={form.scope_ref} disabled={editing !== "new" || form.scope === "GLOBAL"} placeholder={form.scope === "ENTITY" ? "e.g. PH" : "e.g. PH-BAL-01"} onChange={(e) => setForm({ ...form, scope_ref: e.target.value.toUpperCase() })} /></Field>
          {Object.entries(schema).map(([k, kind]) => (
            <Field key={k} label={`${k} (${kind})`}>
              <Input value={form.params[k] ?? ""} onChange={(e) => setForm({ ...form, params: { ...form.params, [k]: e.target.value } })} placeholder={kind === "list" ? "comma separated" : ""} />
            </Field>
          ))}
          <label className="col-span-2 flex items-center gap-2 text-[12.5px]"><input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> Active</label>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
          <Button variant="primary" disabled={save.isPending || form.name.length < 3 || form.code.length < 2} onClick={() => save.mutate()}>Save</Button>
        </div>
      </Modal>

      <Modal open={!!history} onClose={() => setHistory(null)} title={`Version history · ${history?.code}`} width={720}>
        {hist.isLoading ? <Loading /> : (
          <ul className="space-y-2">
            {hist.data?.map((v) => (
              <li key={v.version} className="border border-line p-2">
                <div className="flex justify-between"><span className="font-mono">v{v.version}</span><span className="text-[11.5px] text-dim">{v.changed_by} · {dt(v.changed_at)}</span></div>
                <pre className="mt-1 overflow-auto font-mono text-[11px] whitespace-pre-wrap text-dim">{JSON.stringify(v.snapshot, null, 1)}</pre>
              </li>
            ))}
          </ul>
        )}
      </Modal>
    </div>
  );
}
