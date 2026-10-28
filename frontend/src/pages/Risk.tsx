import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Button, DataTable, ErrorBox, Field, Input, Loading, Meter, PageHeader, Panel, Stat, useToast } from "../components/ui";
import { api } from "../lib/api";
import { useEntity } from "../lib/entity";
import { money, pct, tone } from "../lib/format";

interface Row { account: string; name: string; entity: string; ccy: string; nav: number; gross: number; leverage_pct: number; var95: number; var99: number; es99: number; vol_pct: number; dv01: number; duration: number; hhi: number; top_weight: number; illiquid_pct: number }
interface Bucket { name: string; exposure: number; pct: number }
interface Detail {
  account: string; base_ccy: string; nav: number; gross: number; leverage_pct: number;
  market: Record<string, number>; rates: { dv01: number; duration: number; fi_exposure: number };
  credit: { corporate_exposure: number; by_rating: Bucket[] };
  concentration: { top5: { symbol: string; pct: number }[]; hhi: number; by_issuer: Bucket[]; by_sector: Bucket[] };
  fx: Bucket[]; liquidity: { bucket: string; exposure: number; pct: number }[];
  scenarios: { scenario: string; label: string; pnl: number; pnl_pct: number; by_factor: Record<string, number> }[];
}
interface StressRes { account: string; nav: number; pnl: number; pnl_pct: number; by_factor: Record<string, number> }

export default function Risk() {
  const { entity } = useEntity();
  const toast = useToast();
  const sum = useQuery({ queryKey: ["risk-summary", entity], queryFn: () => api<{ accounts: Row[] }>(`/risk/summary?entity=${entity}`), refetchInterval: 30_000 });
  const [acct, setAcct] = useState("");
  useEffect(() => { if (sum.data?.accounts.length && !sum.data.accounts.some((a) => a.account === acct)) setAcct(sum.data.accounts[0].account); }, [sum.data, acct]);
  const det = useQuery({ queryKey: ["risk-acct", acct], queryFn: () => api<Detail>(`/risk/accounts/${acct}`), enabled: !!acct });
  const [shock, setShock] = useState({ equity_pct: "-15", rates_bp: "100", spread_bp: "75", fx_pct: "-5" });
  const stress = useMutation({
    mutationFn: () => api<{ results: StressRes[] }>("/risk/stress", { method: "POST", json: {
      accounts: (sum.data?.accounts ?? []).map((a) => a.account), equity_pct: Number(shock.equity_pct), rates_bp: Number(shock.rates_bp),
      spread_bp: Number(shock.spread_bp), fx_pct: Number(shock.fx_pct) } }),
    onError: (e) => toast("err", (e as Error).message),
  });

  if (sum.isLoading) return <Loading label="Computing risk" />;
  if (sum.error) return <ErrorBox error={sum.error} />;
  const d = det.data;
  const c = d?.base_ccy;

  return (
    <div>
      <PageHeader title="Risk & Stress" subtitle="Historical & parametric VaR · rates · credit · liquidity · concentration · scenario analysis (account base ccy)" />
      <Panel title={`Enterprise view · ${entity}`} pad={false} className="m-3">
        <DataTable rows={sum.data?.accounts ?? []} rowKey={(r) => r.account} onRowClick={(r) => setAcct(r.account)}
          rowClass={(r) => (r.account === acct ? "bg-raised" : undefined)} columns={[
            { key: "a", header: "Account", render: (r) => <span className="font-mono font-semibold">{r.account}</span>, sort: (r) => r.account },
            { key: "n", header: "NAV", align: "right", render: (r) => money(r.nav, r.ccy), sort: (r) => r.nav },
            { key: "l", header: "Leverage", align: "right", render: (r) => <span className={r.leverage_pct > 250 ? "text-warn" : ""}>{pct(r.leverage_pct, 0)}</span>, sort: (r) => r.leverage_pct },
            { key: "v95", header: "VaR 95 1D", align: "right", render: (r) => money(r.var95, r.ccy), sort: (r) => r.var95 },
            { key: "v99", header: "VaR 99 1D", align: "right", render: (r) => money(r.var99, r.ccy), sort: (r) => r.var99 },
            { key: "es", header: "ES 99", align: "right", render: (r) => money(r.es99, r.ccy) },
            { key: "vp", header: "VaR99 % NAV", align: "right", render: (r) => pct(r.nav ? (r.var99 / r.nav) * 100 : 0), sort: (r) => (r.nav ? r.var99 / r.nav : 0) },
            { key: "vol", header: "Vol (ann.)", align: "right", render: (r) => pct(r.vol_pct), sort: (r) => r.vol_pct },
            { key: "dur", header: "Duration", align: "right", render: (r) => `${r.duration.toFixed(2)}y`, sort: (r) => r.duration },
            { key: "dv", header: "DV01", align: "right", render: (r) => money(r.dv01, r.ccy), sort: (r) => Math.abs(r.dv01) },
            { key: "t", header: "Top wt", align: "right", render: (r) => pct(r.top_weight, 1), sort: (r) => r.top_weight },
            { key: "h", header: "HHI", align: "right", render: (r) => r.hhi.toFixed(0), sort: (r) => r.hhi },
            { key: "il", header: ">20D liq.", align: "right", render: (r) => pct(r.illiquid_pct, 1), sort: (r) => r.illiquid_pct },
          ]} />
      </Panel>

      {d && (
        <div className="grid gap-3 px-3 xl:grid-cols-3">
          <Panel title={`${d.account} · market & rates`}>
            <div className="grid grid-cols-2 gap-4">
              <Stat label="VaR 95 (hist)" value={money(d.market.hist_var_95, c)} sub={`param ${money(d.market.param_var_95, c)}`} />
              <Stat label="VaR 99 (hist)" value={money(d.market.hist_var_99, c)} sub={`param ${money(d.market.param_var_99, c)}`} />
              <Stat label="Exp. shortfall 99" value={money(d.market.es_99, c)} sub={`${d.market.observations} obs`} />
              <Stat label="Leverage" value={pct(d.leverage_pct, 0)} />
              <Stat label="Mod. duration" value={`${d.rates.duration.toFixed(2)}y`} />
              <Stat label="DV01" value={money(d.rates.dv01, c)} />
            </div>
          </Panel>
          <Panel title="Concentration · issuer">
            {d.concentration.by_issuer.slice(0, 7).map((b) => <Meter key={b.name} label={b.name} value={b.pct} max={30} display={pct(b.pct, 1)} color={b.pct > 15 ? "bg-warn" : "bg-accent"} />)}
          </Panel>
          <Panel title="Liquidity (25% ADV participation)">
            {d.liquidity.map((b) => <Meter key={b.bucket} label={`Days to liquidate ${b.bucket}`} value={b.pct} display={`${pct(b.pct, 1)} · ${money(b.exposure, c)}`} color={b.bucket === ">20d" ? "bg-down" : "bg-accent"} />)}
            <div className="mt-3 lbl">Credit quality (FI)</div>
            {d.credit.by_rating.map((b) => <Meter key={b.name} label={b.name} value={b.pct} display={pct(b.pct, 1)} color="bg-info" />)}
          </Panel>
          <Panel title="Historical & hypothetical scenarios" pad={false} className="xl:col-span-2">
            <DataTable rows={d.scenarios} rowKey={(s) => s.scenario} columns={[
              { key: "l", header: "Scenario", render: (s) => s.label },
              { key: "e", header: "Equity", align: "right", render: (s) => <span className={tone(s.by_factor.equity)}>{money(s.by_factor.equity, c)}</span> },
              { key: "r", header: "Rates", align: "right", render: (s) => <span className={tone(s.by_factor.rates)}>{money(s.by_factor.rates, c)}</span> },
              { key: "s", header: "Spread", align: "right", render: (s) => <span className={tone(s.by_factor.spread)}>{money(s.by_factor.spread, c)}</span> },
              { key: "f", header: "FX", align: "right", render: (s) => <span className={tone(s.by_factor.fx)}>{money(s.by_factor.fx, c)}</span> },
              { key: "t", header: "Total", align: "right", render: (s) => <span className={tone(s.pnl)}>{money(s.pnl, c)}</span>, sort: (s) => s.pnl },
              { key: "p", header: "% NAV", align: "right", render: (s) => <span className={tone(s.pnl_pct)}>{pct(s.pnl_pct)}</span>, sort: (s) => s.pnl_pct },
            ]} />
          </Panel>
          <Panel title="Sector exposure">
            {d.concentration.by_sector.slice(0, 7).map((b) => <Meter key={b.name} label={b.name} value={b.pct} max={60} display={pct(b.pct, 1)} />)}
          </Panel>
        </div>
      )}

      <Panel title="Custom stress test · all accounts in view" className="m-3">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Equity shock %"><Input className="w-[110px]" value={shock.equity_pct} onChange={(e) => setShock({ ...shock, equity_pct: e.target.value })} /></Field>
          <Field label="Rates shift bp"><Input className="w-[110px]" value={shock.rates_bp} onChange={(e) => setShock({ ...shock, rates_bp: e.target.value })} /></Field>
          <Field label="Credit spread bp"><Input className="w-[110px]" value={shock.spread_bp} onChange={(e) => setShock({ ...shock, spread_bp: e.target.value })} /></Field>
          <Field label="FX vs base %"><Input className="w-[110px]" value={shock.fx_pct} onChange={(e) => setShock({ ...shock, fx_pct: e.target.value })} /></Field>
          <Button variant="primary" disabled={stress.isPending} onClick={() => stress.mutate()}>Run stress</Button>
        </div>
        {stress.data && (
          <div className="mt-3 border border-line">
            <DataTable rows={stress.data.results} rowKey={(r) => r.account} defaultSort={{ key: "p", dir: "asc" }} columns={[
              { key: "a", header: "Account", render: (r) => <span className="font-mono">{r.account}</span> },
              { key: "e", header: "Equity", align: "right", render: (r) => money(r.by_factor.equity) },
              { key: "r", header: "Rates", align: "right", render: (r) => money(r.by_factor.rates) },
              { key: "s", header: "Spread", align: "right", render: (r) => money(r.by_factor.spread) },
              { key: "f", header: "FX", align: "right", render: (r) => money(r.by_factor.fx) },
              { key: "t", header: "Total P&L", align: "right", render: (r) => <span className={tone(r.pnl)}>{money(r.pnl)}</span> },
              { key: "p", header: "% NAV", align: "right", render: (r) => <span className={tone(r.pnl_pct)}>{pct(r.pnl_pct)}</span>, sort: (r) => r.pnl_pct },
            ]} />
          </div>
        )}
      </Panel>
    </div>
  );
}
