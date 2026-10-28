import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Button, DataTable, ErrorBox, Field, Input, Loading, PageHeader, Panel, Stat, useToast } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useEntity } from "../lib/entity";
import { dt, num } from "../lib/format";
import { useMarket } from "../lib/market";
import type { Breach } from "../lib/types";

interface AlertRow { id: number; level: string; category: string; message: string; account: string | null; is_read: boolean; created_at: string }

export default function Compliance() {
  const { can } = useAuth();
  const { entity } = useEntity();
  const qc = useQueryClient();
  const toast = useToast();
  const m = useMarket();
  const [status, setStatus] = useState("OPEN");
  const [sel, setSel] = useState<Breach | null>(null);
  const [note, setNote] = useState("");
  const all = useQuery({ queryKey: ["breaches", entity], queryFn: () => api<Breach[]>(`/compliance/breaches?entity=${entity}`), refetchInterval: 10_000 });
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: () => api<AlertRow[]>("/alerts?limit=50"), refetchInterval: 10_000 });
  useEffect(() => { qc.invalidateQueries({ queryKey: ["breaches"] }); }, [m.compliance, qc]);

  const scan = useMutation({
    mutationFn: () => api<{ accounts: number; opened: number; resolved: number }>(`/compliance/scan?entity=${entity}`, { method: "POST" }),
    onSuccess: (r) => { toast("info", `Scanned ${r.accounts} accounts · ${r.opened} new · ${r.resolved} resolved`); qc.invalidateQueries({ queryKey: ["breaches"] }); },
    onError: (e) => toast("err", (e as Error).message),
  });
  const act = useMutation({
    mutationFn: (s: string | null) => api<Breach>(`/compliance/breaches/${sel!.id}`, { method: "POST", json: { status: s, note } }),
    onSuccess: (b) => { setSel(b); setNote(""); qc.invalidateQueries({ queryKey: ["breaches"] }); toast("ok", `Breach #${b.id} updated`); },
    onError: (e) => toast("err", (e as Error).message),
  });
  const readAll = useMutation({ mutationFn: () => api("/alerts/read-all", { method: "POST" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }) });

  if (all.isLoading) return <Loading />;
  if (all.error) return <ErrorBox error={all.error} />;
  const rows = (all.data ?? []).filter((b) => !status || b.status === status);
  const open = (all.data ?? []).filter((b) => b.status !== "RESOLVED");

  return (
    <div>
      <PageHeader title={`Compliance Monitor · ${entity}`} subtitle="Pre-trade blocks · post-trade & passive breach detection · case management">
        <Button variant="primary" disabled={scan.isPending} onClick={() => scan.mutate()}>{scan.isPending ? "Scanning…" : `Run scan (${entity})`}</Button>
      </PageHeader>
      <div className="grid grid-cols-2 gap-4 border-b border-line px-4 py-3 md:grid-cols-5">
        <Stat label="Open breaches" value={open.filter((b) => b.status === "OPEN").length} tone="text-down" />
        <Stat label="Acknowledged" value={open.filter((b) => b.status === "ACKNOWLEDGED").length} tone="text-info" />
        <Stat label="Hard-limit open" value={open.filter((b) => b.severity === "HARD").length} tone="text-down" />
        <Stat label="Passive (market-driven)" value={open.filter((b) => b.kind === "PASSIVE").length} />
        <Stat label="Oldest open (hrs)" value={num(Math.max(0, ...open.map((b) => b.age_hours)), 1)} />
      </div>
      <div className="grid xl:grid-cols-[1fr_400px]">
        <div className="min-w-0 border-r border-line">
          <div className="flex gap-1 border-b border-line px-3">
            {["OPEN", "ACKNOWLEDGED", "RESOLVED", ""].map((s) => (
              <button key={s} onClick={() => setStatus(s)} className={clsx("lbl border-b-2 px-3 py-2.5", status === s ? "border-accent text-fg" : "border-transparent hover:text-fg")}>{s || "All"}</button>
            ))}
          </div>
          <DataTable rows={rows} rowKey={(b) => b.id} onRowClick={setSel} maxHeight="calc(100vh - 290px)" empty="No breaches in this view"
            rowClass={(b) => (sel?.id === b.id ? "bg-raised" : undefined)} defaultSort={{ key: "t", dir: "desc" }}
            columns={[
              { key: "id", header: "#", render: (b) => <span className="font-mono text-dim">{b.id}</span> },
              { key: "t", header: "Detected", render: (b) => <span className="font-mono text-dim">{dt(b.detected_at)}</span>, sort: (b) => b.detected_at },
              { key: "a", header: "Account", render: (b) => <Link onClick={(e) => e.stopPropagation()} to={`/accounts/${b.account}`} className="font-mono hover:text-accent">{b.account}</Link>, sort: (b) => b.account },
              { key: "r", header: "Rule", render: (b) => <span className="font-mono">{b.rule}</span>, sort: (b) => b.rule },
              { key: "cat", header: "Category", render: (b) => <span className="lbl">{b.category}</span> },
              { key: "sv", header: "Sev", render: (b) => <Badge>{b.severity}</Badge> },
              { key: "k", header: "Kind", render: (b) => <Badge>{b.kind}</Badge> },
              { key: "m", header: "Detail", render: (b) => <span className="block max-w-[340px] truncate" title={b.message}>{b.message}</span> },
              { key: "s", header: "Status", render: (b) => <Badge>{b.status}</Badge> },
            ]} />
        </div>
        <aside className="space-y-3 p-3">
          {sel ? (
            <Panel title={`Breach #${sel.id} · ${sel.rule}`} right={<Badge>{sel.status}</Badge>}>
              <div className="text-[13px]">{sel.rule_name}</div>
              <div className="mt-1 text-[12.5px] text-down">{sel.message}</div>
              <div className="num mt-2 grid grid-cols-3 gap-2 text-[12px]">
                <div><div className="lbl">Observed</div>{num(sel.observed, 2)}</div>
                <div><div className="lbl">Limit</div>{num(sel.limit, 2)}</div>
                <div><div className="lbl">Age</div>{num(sel.age_hours, 1)}h</div>
              </div>
              <div className="mt-3 lbl">Case notes</div>
              <ul className="mt-1 max-h-[200px] space-y-1.5 overflow-auto text-[12px]">
                {sel.notes.length === 0 && <li className="text-mute">No notes yet</li>}
                {sel.notes.map((n, k) => (
                  <li key={k} className="border-l-2 border-line-2 pl-2"><span className="font-mono text-dim">{dt(n.ts)} · {n.user}</span>{n.status && <> · <Badge>{n.status}</Badge></>}<div>{n.text}</div></li>
                ))}
              </ul>
              {can("breach:manage") && sel.status !== "RESOLVED" && (
                <div className="mt-3 space-y-2">
                  <Field label="Note / remediation plan"><Input value={note} onChange={(e) => setNote(e.target.value)} /></Field>
                  <div className="flex gap-2">
                    <Button size="sm" disabled={note.length < 2} onClick={() => act.mutate(null)}>Add note</Button>
                    {sel.status === "OPEN" && <Button size="sm" variant="primary" disabled={note.length < 2} onClick={() => act.mutate("ACKNOWLEDGED")}>Acknowledge</Button>}
                    <Button size="sm" variant="up" disabled={note.length < 2} onClick={() => act.mutate("RESOLVED")}>Resolve</Button>
                  </div>
                </div>
              )}
            </Panel>
          ) : <Panel title="Case"><div className="text-dim">Select a breach to view and manage the case</div></Panel>}
          <Panel title="Alert feed" right={<Button size="sm" variant="ghost" onClick={() => readAll.mutate()}>Mark all read</Button>} pad={false}>
            <ul className="max-h-[360px] divide-y divide-line overflow-auto">
              {(alerts.data ?? []).map((a) => (
                <li key={a.id} className={clsx("px-3 py-2 text-[12px]", !a.is_read && "bg-raised/40")}>
                  <div className="flex items-center gap-2"><Badge tone={a.level}>{a.level}</Badge><span className="lbl">{a.category}</span><span className="ml-auto font-mono text-[10.5px] text-mute">{dt(a.created_at)}</span></div>
                  <div className="mt-1">{a.message}</div>
                </li>
              ))}
            </ul>
          </Panel>
        </aside>
      </div>
    </div>
  );
}
