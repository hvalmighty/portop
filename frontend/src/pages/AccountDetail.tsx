import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import OrderTicket from "../components/OrderTicket";
import { Badge, Button, DataTable, ErrorBox, Loading, PageHeader, Panel, Stat } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { money, num, pct, px, tone } from "../lib/format";
import type { AccountSummary, PositionRow, RuleResult } from "../lib/types";

interface DriftRow { symbol: string; current_pct: number; target_pct: number; drift_pct: number; out_of_band: boolean }
interface Detail {
  account: { code: string; name: string; entity: string; base_ccy: string; mandate: string; risk_profile: string; tax_status: string; restrictions: string[]; model: string | null };
  summary: AccountSummary;
  positions: PositionRow[];
  cash: { ccy: string; amount: number }[];
  drift?: { model: string; version: number; tolerance_pct: number; rows: DriftRow[] };
}

export function DriftBar({ r, tol }: { r: DriftRow; tol: number }) {
  const scale = 20;
  const w = Math.min(50, (Math.abs(r.drift_pct) / scale) * 50);
  return (
    <div className="relative h-3 w-[160px] bg-raised" title={`${pct(r.drift_pct, 2, true)} (band ±${tol}%)`}>
      <div className="absolute inset-y-0 left-1/2 w-px bg-line-2" />
      <div className="absolute inset-y-0 bg-dim/10" style={{ left: `${50 - (tol / scale) * 50}%`, width: `${(tol / scale) * 100}%` }} />
      <div className={clsx("absolute inset-y-[3px]", r.out_of_band ? "bg-warn" : "bg-accent")}
        style={r.drift_pct >= 0 ? { left: "50%", width: `${w}%` } : { right: "50%", width: `${w}%` }} />
    </div>
  );
}

export default function AccountDetail() {
  const { code = "" } = useParams();
  const { can } = useAuth();
  const [tab, setTab] = useState<"positions" | "drift" | "compliance" | "risk">("positions");
  const [ticket, setTicket] = useState(false);
  const { data, error, isLoading } = useQuery({ queryKey: ["account", code], queryFn: () => api<Detail>(`/portfolio/accounts/${code}`), refetchInterval: 5000 });
  const comp = useQuery({ queryKey: ["acct-comp", code], queryFn: () => api<{ results: RuleResult[]; failing: number }>(`/compliance/accounts/${code}`), enabled: can("compliance:read") });
  const risk = useQuery({ queryKey: ["acct-risk", code], queryFn: () => api<{ market: Record<string, number>; rates: { dv01: number; duration: number }; scenarios: { label: string; pnl: number; pnl_pct: number }[] }>(`/risk/accounts/${code}`), enabled: can("risk:read") && tab === "risk" });
  if (isLoading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  if (!data) return null;
  const { account: a, summary: s } = data;
  const c = a.base_ccy;

  return (
    <div>
      <PageHeader title={`${a.code} · ${a.name}`} subtitle={`${a.entity} · ${a.mandate} · ${a.risk_profile} · ${a.tax_status}${a.model ? ` · Model ${a.model}` : ""}`}>
        <Link to="/portfolio" className="lbl hover:text-fg">← All portfolios</Link>
        {can("order:create") && <Button variant="primary" onClick={() => setTicket(true)}>+ Order</Button>}
      </PageHeader>
      <div className="grid grid-cols-2 gap-4 border-b border-line px-4 py-3 md:grid-cols-4 xl:grid-cols-7">
        <Stat label={`NAV (${c})`} value={money(s.nav, c)} />
        <Stat label="Mandate AUM" value={money(s.aum, c)} />
        <Stat label="Cash" value={money(s.cash, c)} sub={pct(s.nav ? (s.cash / s.nav) * 100 : 0)} />
        <Stat label="Gross" value={money(s.gross, c)} sub={`${pct(s.gross_vs_aum_pct, 1)} of AUM`} />
        <Stat label="MTM P&L" value={money(s.pnl, c)} tone={tone(s.pnl)} />
        <Stat label="Day P&L" value={money(s.day_pnl, c)} tone={tone(s.day_pnl)} />
        <Stat label="Compliance" value={comp.data ? (comp.data.failing ? `${comp.data.failing} breach${comp.data.failing > 1 ? "es" : ""}` : "Clean") : "—"}
          tone={comp.data?.failing ? "text-down" : "text-up"} />
      </div>
      {a.restrictions.length > 0 && (
        <div className="border-b border-line px-4 py-2 text-[12px] text-dim">Client restrictions: {a.restrictions.map((r) => <Badge key={r} tone="HARD">{r}</Badge>)}</div>
      )}
      <div className="flex gap-1 border-b border-line px-3">
        {(["positions", "drift", "compliance", "risk"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={clsx("lbl border-b-2 px-3 py-2.5", tab === t ? "border-accent text-fg" : "border-transparent hover:text-fg")}>
            {t === "drift" ? "Model drift" : t}
          </button>
        ))}
      </div>
      <div className="p-3">
        {tab === "positions" && (
          <div className="grid gap-3 xl:grid-cols-[1fr_280px]">
            <Panel title="Holdings" pad={false}>
              <DataTable rows={data.positions} rowKey={(r) => r.position_id} defaultSort={{ key: "w", dir: "desc" }} columns={[
                { key: "s", header: "Symbol", render: (r) => <span className="font-mono font-semibold">{r.symbol}</span>, sort: (r) => r.symbol },
                { key: "n", header: "Name", render: (r) => <span className="text-dim">{r.name}</span> },
                { key: "c", header: "Class", render: (r) => r.asset_class, sort: (r) => r.asset_class },
                { key: "r", header: "Rating", render: (r) => r.rating ?? "—" },
                { key: "q", header: "Qty", align: "right", render: (r) => num(r.qty), sort: (r) => r.qty },
                { key: "a", header: "Avg", align: "right", render: (r) => px(r.avg_px) },
                { key: "m", header: "Mark", align: "right", render: (r) => px(r.mark) },
                { key: "e", header: `Exposure (${c})`, align: "right", render: (r) => money(r.exposure_rep, c), sort: (r) => Math.abs(r.exposure_rep) },
                { key: "w", header: "Weight", align: "right", render: (r) => pct(r.weight_pct), sort: (r) => Math.abs(r.weight_pct) },
                { key: "p", header: "MTM P&L", align: "right", render: (r) => <span className={tone(r.mtm_pnl_rep)}>{money(r.mtm_pnl_rep, c)}</span>, sort: (r) => r.mtm_pnl_rep },
                { key: "d", header: "Dur", align: "right", render: (r) => r.duration?.toFixed(2) ?? "—" },
              ]} />
            </Panel>
            <Panel title="Cash balances">
              {data.cash.map((x) => (
                <div key={x.ccy} className="flex justify-between py-1"><span className="font-mono">{x.ccy}</span><span className={`num ${tone(x.amount)}`}>{num(x.amount, 2)}</span></div>
              ))}
            </Panel>
          </div>
        )}
        {tab === "drift" && (data.drift ? (
          <Panel title={`Drift vs ${data.drift.model} v${data.drift.version} · band ±${data.drift.tolerance_pct}%`} pad={false}
            right={<Link to={`/rebalance?account=${a.code}`}><Button size="sm" variant="primary">Rebalance</Button></Link>}>
            <DataTable rows={data.drift.rows} rowKey={(r) => r.symbol} columns={[
              { key: "s", header: "Line", render: (r) => <span className="font-mono font-semibold">{r.symbol}</span> },
              { key: "c", header: "Current", align: "right", render: (r) => pct(r.current_pct), sort: (r) => r.current_pct },
              { key: "t", header: "Target", align: "right", render: (r) => pct(r.target_pct), sort: (r) => r.target_pct },
              { key: "d", header: "Drift", align: "right", render: (r) => <span className={r.out_of_band ? "text-warn" : ""}>{pct(r.drift_pct, 2, true)}</span>, sort: (r) => Math.abs(r.drift_pct) },
              { key: "b", header: "", render: (r) => <DriftBar r={r} tol={data.drift!.tolerance_pct} /> },
              { key: "o", header: "Status", render: (r) => r.out_of_band ? <Badge tone="WARN">Out of band</Badge> : <Badge tone="PASS">Within</Badge> },
            ]} />
          </Panel>
        ) : <Panel title="Model drift"><div className="text-dim">No model assigned to this account.</div></Panel>)}
        {tab === "compliance" && (
          <Panel title="Rule status (current holdings)" pad={false}>
            {comp.isLoading ? <Loading /> : (
              <DataTable rows={comp.data?.results ?? []} rowKey={(r) => `${r.rule_id}-${r.subject}`} defaultSort={{ key: "p", dir: "asc" }} columns={[
                { key: "p", header: "Status", render: (r) => <Badge>{r.passed ? "PASS" : "FAIL"}</Badge>, sort: (r) => (r.passed ? 1 : 0) },
                { key: "c", header: "Rule", render: (r) => <span className="font-mono">{r.code}</span>, sort: (r) => r.code },
                { key: "n", header: "Description", render: (r) => <span className="text-dim">{r.name}</span> },
                { key: "sv", header: "Severity", render: (r) => <Badge>{r.severity}</Badge> },
                { key: "sub", header: "Subject", render: (r) => r.subject || "—" },
                { key: "o", header: "Observed", align: "right", render: (r) => num(r.observed, 2) },
                { key: "l", header: "Limit", align: "right", render: (r) => num(r.limit, 2) },
                { key: "m", header: "Detail", render: (r) => <span className="text-down">{r.message}</span> },
              ]} />
            )}
          </Panel>
        )}
        {tab === "risk" && (risk.isLoading ? <Loading /> : risk.data && (
          <div className="grid gap-3 lg:grid-cols-2">
            <Panel title="Market & rate risk">
              <div className="grid grid-cols-3 gap-4">
                <Stat label="1D VaR 95%" value={money(risk.data.market.hist_var_95, c)} />
                <Stat label="1D VaR 99%" value={money(risk.data.market.hist_var_99, c)} />
                <Stat label="ES 99%" value={money(risk.data.market.es_99, c)} />
                <Stat label="Volatility (ann.)" value={pct(risk.data.market.vol_ann_pct)} />
                <Stat label="Duration" value={`${risk.data.rates.duration.toFixed(2)}y`} />
                <Stat label="DV01" value={money(risk.data.rates.dv01, c)} />
              </div>
            </Panel>
            <Panel title="Scenario P&L" pad={false}>
              <DataTable rows={risk.data.scenarios} rowKey={(r) => r.label} columns={[
                { key: "l", header: "Scenario", render: (r) => r.label },
                { key: "p", header: `P&L (${c})`, align: "right", render: (r) => <span className={tone(r.pnl)}>{money(r.pnl, c)}</span> },
                { key: "pp", header: "% NAV", align: "right", render: (r) => <span className={tone(r.pnl_pct)}>{pct(r.pnl_pct)}</span> },
              ]} />
            </Panel>
          </div>
        ))}
      </div>
      <OrderTicket open={ticket} preset={{ account: a.code }} onClose={() => setTicket(false)} />
    </div>
  );
}
