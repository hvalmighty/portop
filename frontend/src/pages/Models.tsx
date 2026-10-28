import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Button, DataTable, ErrorBox, Field, Input, Loading, PageHeader, Panel, useToast } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { dt, money, pct } from "../lib/format";
import type { Instrument } from "../lib/types";

interface Version { id: number; version: number; weights: Record<string, number>; status: string; rationale: string; created_by: string; approved_by: string | null; created_at: string; effective_at: string | null }
interface Model { id: number; code: string; name: string; benchmark: string; tolerance_pct: number; active_version: number | null; weights: Record<string, number>; accounts: string[]; pending_versions: number; versions?: Version[] }
interface DriftAcct { account: string; name: string; nav: number; max_abs_drift: number; out_of_band: number }

export default function Models() {
  const { can, user } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const { data: models = [], isLoading, error } = useQuery({ queryKey: ["models"], queryFn: () => api<Model[]>("/models") });
  const [code, setCode] = useState<string>("");
  useEffect(() => { if (!code && models.length) setCode(models[0].code); }, [models, code]);
  const { data: m } = useQuery({ queryKey: ["model", code], queryFn: () => api<Model>(`/models/${code}`), enabled: !!code });
  const { data: drift } = useQuery({ queryKey: ["model-drift", code], queryFn: () => api<{ accounts: DriftAcct[] }>(`/models/${code}/drift`), enabled: !!code, refetchInterval: 10_000 });
  const { data: insts = [] } = useQuery({ queryKey: ["instruments"], queryFn: () => api<Instrument[]>("/instruments") });

  const [edit, setEdit] = useState<Record<string, string> | null>(null);
  const [rationale, setRationale] = useState("");
  const [addSym, setAddSym] = useState("");
  const total = useMemo(() => Object.values(edit ?? {}).reduce((s, v) => s + (Number(v) || 0), 0), [edit]);

  const invalidate = () => { qc.invalidateQueries({ queryKey: ["models"] }); qc.invalidateQueries({ queryKey: ["model", code] }); };
  const propose = useMutation({
    mutationFn: () => api(`/models/${code}/versions`, { method: "POST", json: {
      weights: Object.fromEntries(Object.entries(edit ?? {}).map(([k, v]) => [k, Number(v) || 0]).filter(([, v]) => (v as number) > 0)),
      rationale } }),
    onSuccess: () => { toast("ok", "New version proposed — awaiting approval"); setEdit(null); setRationale(""); invalidate(); },
    onError: (e) => toast("err", (e as Error).message),
  });
  const approve = useMutation({
    mutationFn: (v: number) => api(`/models/${code}/versions/${v}/approve`, { method: "POST" }),
    onSuccess: () => { toast("ok", "Version approved and now active"); invalidate(); qc.invalidateQueries({ queryKey: ["model-drift", code] }); },
    onError: (e) => toast("err", (e as Error).message),
  });

  if (isLoading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  const instBy = Object.fromEntries(insts.map((i) => [i.symbol, i]));

  return (
    <div>
      <PageHeader title="Model Portfolios" subtitle="Governed models · version control · drift across mapped accounts" />
      <div className="grid gap-3 p-3 xl:grid-cols-[300px_1fr]">
        <Panel title="Models" pad={false}>
          {models.map((x) => (
            <button key={x.code} onClick={() => { setCode(x.code); setEdit(null); }}
              className={clsx("block w-full border-b border-line px-3 py-2.5 text-left hover:bg-raised", code === x.code && "bg-raised")}>
              <div className="flex items-center justify-between"><span className="font-mono font-semibold">{x.code}</span>
                {x.pending_versions > 0 && <Badge tone="WARN">{`${x.pending_versions} pending`}</Badge>}</div>
              <div className="text-[12px] text-dim">{x.name}</div>
              <div className="lbl mt-1 text-mute">v{x.active_version} · {x.accounts.length} accounts · ±{x.tolerance_pct}%</div>
            </button>
          ))}
        </Panel>
        {m && (
          <div className="grid min-w-0 gap-3 2xl:grid-cols-2">
            <Panel title={`${m.code} · active v${m.active_version} · ${m.benchmark}`}
              right={can("model:write") && !edit && <Button size="sm" variant="primary" onClick={() => setEdit(Object.fromEntries(Object.entries(m.weights).map(([k, v]) => [k, String(v)])))}>Propose change</Button>}
              pad={false}>
              {!edit ? (
                <DataTable rows={Object.entries(m.weights).map(([s, w]) => ({ s, w }))} rowKey={(r) => r.s} defaultSort={{ key: "w", dir: "desc" }} columns={[
                  { key: "s", header: "Line", render: (r) => <span className="font-mono font-semibold">{r.s}</span>, sort: (r) => r.s },
                  { key: "n", header: "Name", render: (r) => <span className="text-dim">{r.s === "CASH" ? "Cash & equivalents" : instBy[r.s]?.name}</span> },
                  { key: "c", header: "Class", render: (r) => instBy[r.s]?.asset_class ?? "CASH" },
                  { key: "w", header: "Target", align: "right", render: (r) => pct(r.w), sort: (r) => r.w },
                  { key: "b", header: "", render: (r) => <div className="h-2 w-[140px] bg-raised"><div className="h-full bg-accent" style={{ width: `${Math.min(100, r.w * 4)}%` }} /></div> },
                ]} />
              ) : (
                <div className="p-3">
                  <div className="max-h-[420px] space-y-1 overflow-auto">
                    {Object.entries(edit).map(([s, v]) => (
                      <div key={s} className="flex items-center gap-2">
                        <span className="w-[130px] font-mono">{s}</span>
                        <Input className="w-[90px] text-right" value={v} onChange={(e) => setEdit({ ...edit, [s]: e.target.value.replace(/[^\d.]/g, "") })} aria-label={`${s} weight`} />
                        <span className="text-mute">%</span>
                        <button className="text-mute hover:text-down" onClick={() => { const n = { ...edit }; delete n[s]; setEdit(n); }} aria-label={`Remove ${s}`}>✕</button>
                      </div>
                    ))}
                  </div>
                  <div className="mt-3 flex items-end gap-2">
                    <Field label="Add line"><Input list="model-syms" value={addSym} onChange={(e) => setAddSym(e.target.value.toUpperCase())} /></Field>
                    <datalist id="model-syms">{insts.filter((i) => i.asset_class !== "DERIV").map((i) => <option key={i.id} value={i.symbol} />)}</datalist>
                    <Button size="sm" disabled={!instBy[addSym] || addSym in edit} onClick={() => { setEdit({ ...edit, [addSym]: "0" }); setAddSym(""); }}>Add</Button>
                    <span className={clsx("num ml-auto text-[14px]", Math.abs(total - 100) < 0.01 ? "text-up" : "text-down")}>Σ {total.toFixed(2)}%</span>
                  </div>
                  <div className="mt-3"><Field label="Rationale (investment committee)"><Input value={rationale} onChange={(e) => setRationale(e.target.value)} /></Field></div>
                  <div className="mt-3 flex justify-end gap-2">
                    <Button variant="ghost" onClick={() => setEdit(null)}>Discard</Button>
                    <Button variant="primary" disabled={Math.abs(total - 100) > 0.01 || rationale.trim().length < 3 || propose.isPending} onClick={() => propose.mutate()}>Submit for approval</Button>
                  </div>
                </div>
              )}
            </Panel>
            <div className="grid content-start gap-3">
              <Panel title="Drift by account" pad={false}>
                <DataTable rows={drift?.accounts ?? []} rowKey={(r) => r.account} columns={[
                  { key: "a", header: "Account", render: (r) => <Link className="font-mono font-semibold hover:text-accent" to={`/accounts/${r.account}`}>{r.account}</Link> },
                  { key: "n", header: "NAV", align: "right", render: (r) => money(r.nav) },
                  { key: "d", header: "Max drift", align: "right", render: (r) => <span className={r.out_of_band ? "text-warn" : ""}>{pct(r.max_abs_drift)}</span>, sort: (r) => r.max_abs_drift },
                  { key: "o", header: "Out of band", align: "right", render: (r) => r.out_of_band },
                  { key: "x", header: "", align: "right", render: (r) => <Link to={`/rebalance?account=${r.account}`}><Button size="sm">Rebalance</Button></Link> },
                ]} />
              </Panel>
              <Panel title="Version history" pad={false}>
                <DataTable rows={m.versions ?? []} rowKey={(v) => v.id} columns={[
                  { key: "v", header: "Ver", render: (v) => <span className="font-mono">v{v.version}</span> },
                  { key: "s", header: "Status", render: (v) => <Badge>{v.status}</Badge> },
                  { key: "r", header: "Rationale", render: (v) => <span className="block max-w-[260px] truncate text-dim" title={v.rationale}>{v.rationale}</span> },
                  { key: "b", header: "Proposed / approved", render: (v) => <span className="text-[12px] text-dim">{v.created_by} / {v.approved_by ?? "—"}</span> },
                  { key: "t", header: "Created", render: (v) => <span className="font-mono text-[11px] text-dim">{dt(v.created_at)}</span> },
                  { key: "x", header: "", align: "right", render: (v) => v.status === "DRAFT" && can("model:approve") && v.created_by !== user?.username
                    ? <Button size="sm" variant="up" disabled={approve.isPending} onClick={() => approve.mutate(v.version)}>Approve</Button> : null },
                ]} />
              </Panel>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
