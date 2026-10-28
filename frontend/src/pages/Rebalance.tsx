import { useMutation, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ComplianceResults } from "../components/OrderTicket";
import { Badge, Button, DataTable, Empty, Field, Input, Loading, PageHeader, Panel, Select, useToast } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useEntity } from "../lib/entity";
import { money, num, pct, px } from "../lib/format";
import type { Compliance, Overview } from "../lib/types";

interface Line { symbol: string; side: string; qty: number; price: number; value_base: number; est_cost: number; drift_pct: number }
interface Proposal { account: string; model: string; version: number; mode: string; lines: Line[]; turnover_base: number; est_cost_total: number; compliance: Compliance; error?: string; drift: { nav: number; out_of_band: number; max_abs_drift: number } }

export default function Rebalance() {
  const { entity } = useEntity();
  const { can } = useAuth();
  const toast = useToast();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [selected, setSelected] = useState<string[]>([]);
  const [mode, setMode] = useState<"band" | "full">("band");
  const [minTrade, setMinTrade] = useState("0");
  const { data: ov } = useQuery({ queryKey: ["overview", entity], queryFn: () => api<Overview>(`/portfolio/overview?entity=${entity}`) });
  const eligible = (ov?.accounts ?? []).filter((a) => a.model_id);
  useEffect(() => {
    const a = params.get("account");
    if (a) setSelected([a]);
  }, [params]);

  const preview = useMutation({
    mutationFn: () => api<{ proposals: Proposal[] }>("/rebalance/preview", { method: "POST", json: { accounts: selected, mode, min_trade_value: Number(minTrade) || 0 } }),
    onError: (e) => toast("err", (e as Error).message),
  });
  const submit = useMutation({
    mutationFn: () => api<{ batch_id: string; orders_created: number; skipped: unknown[] }>("/rebalance/submit", { method: "POST", json: { accounts: selected, mode, min_trade_value: Number(minTrade) || 0 } }),
    onSuccess: (r) => {
      toast("ok", `Batch ${r.batch_id}: ${r.orders_created} orders staged for approval${r.skipped.length ? `, ${r.skipped.length} skipped` : ""}`);
      nav("/blotter");
    },
    onError: (e) => toast("err", (e as Error).message),
  });
  const toggle = (c: string) => setSelected((s) => (s.includes(c) ? s.filter((x) => x !== c) : [...s, c]));

  return (
    <div>
      <PageHeader title="Rebalancing" subtitle="Drift detection vs model · tolerance bands · cost & tax estimates · pre-trade compliance" />
      <div className="grid gap-3 p-3 xl:grid-cols-[320px_1fr]">
        <Panel title="Scope">
          <div className="lbl mb-2">Accounts with a model ({entity})</div>
          {eligible.length === 0 && <Empty>No model-linked accounts in this entity</Empty>}
          <div className="space-y-1">
            {eligible.map((a) => (
              <label key={a.code} className={clsx("flex cursor-pointer items-center gap-2 border px-2 py-1.5", selected.includes(a.code) ? "border-accent bg-accent/10" : "border-line")}>
                <input type="checkbox" checked={selected.includes(a.code)} onChange={() => toggle(a.code)} className="accent-[var(--color-accent)]" />
                <span className="font-mono">{a.code}</span>
                <span className="num ml-auto text-[11px] text-dim">{money(a.nav, a.base_ccy)}</span>
              </label>
            ))}
          </div>
          <div className="mt-2 flex gap-2">
            <Button size="sm" onClick={() => setSelected(eligible.map((a) => a.code))}>All</Button>
            <Button size="sm" variant="ghost" onClick={() => setSelected([])}>None</Button>
          </div>
          <div className="mt-4 grid gap-3">
            <Field label="Mode" hint={mode === "band" ? "Only lines outside their tolerance band" : "Trade every line back to target"}>
              <Select value={mode} onChange={(e) => setMode(e.target.value as "band" | "full")}>
                <option value="band">Tolerance band</option>
                <option value="full">Full rebalance</option>
              </Select>
            </Field>
            <Field label="Minimum trade value (base ccy)"><Input value={minTrade} onChange={(e) => setMinTrade(e.target.value.replace(/[^\d.]/g, ""))} /></Field>
            <Button variant="primary" disabled={!selected.length || preview.isPending} onClick={() => preview.mutate()}>
              {preview.isPending ? "Calculating…" : "Generate proposals"}
            </Button>
          </div>
        </Panel>
        <div className="min-w-0 space-y-3">
          {preview.isPending && <Loading label="Building proposals" />}
          {!preview.data && !preview.isPending && <Panel title="Proposals"><Empty>Select accounts and generate proposals</Empty></Panel>}
          {preview.data?.proposals.map((p) => p.error ? (
            <Panel key={p.account} title={p.account}><div className="text-down">{p.error}</div></Panel>
          ) : (
            <Panel key={p.account} title={`${p.account} → ${p.model} v${p.version}`}
              right={<span className="num text-[12px] text-dim">turnover {money(p.turnover_base)} · {pct(p.drift.nav ? (p.turnover_base / p.drift.nav) * 100 : 0)} NAV · est. cost {money(p.est_cost_total)}</span>} pad={false}>
              {p.lines.length === 0 ? <Empty>Within tolerance — no trades required</Empty> : (
                <div className="grid gap-0 lg:grid-cols-[1fr_360px]">
                  <DataTable rows={p.lines} rowKey={(l) => l.symbol} columns={[
                    { key: "sd", header: "Side", render: (l) => <Badge>{l.side}</Badge> },
                    { key: "s", header: "Symbol", render: (l) => <span className="font-mono font-semibold">{l.symbol}</span> },
                    { key: "d", header: "Drift", align: "right", render: (l) => pct(l.drift_pct, 2, true) },
                    { key: "q", header: "Qty", align: "right", render: (l) => num(l.qty) },
                    { key: "p", header: "Px", align: "right", render: (l) => px(l.price) },
                    { key: "v", header: "Value", align: "right", render: (l) => money(l.value_base) },
                    { key: "c", header: "Est. cost", align: "right", render: (l) => money(l.est_cost) },
                  ]} />
                  <div className="border-l border-line p-2"><ComplianceResults c={p.compliance} /></div>
                </div>
              )}
            </Panel>
          ))}
          {preview.data && can("rebalance:run") && preview.data.proposals.some((p) => p.lines?.length) && (
            <div className="flex justify-end">
              <Button variant="primary" disabled={submit.isPending} onClick={() => submit.mutate()}>Stage orders for approval</Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
