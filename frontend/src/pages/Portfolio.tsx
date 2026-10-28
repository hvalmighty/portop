import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import OrderTicket from "../components/OrderTicket";
import { Button, DataTable, ErrorBox, Loading, Meter, Select, type Column } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useEntity } from "../lib/entity";
import { money, num, pct, px, tone } from "../lib/format";
import type { AccountSummary, Overview, PositionRow } from "../lib/types";

function AccountCard({ a, ccy, onOpen }: { a: AccountSummary; ccy: string; onOpen: () => void }) {
  const share = (k: string) => a.share[k] ?? 0;
  return (
    <button onClick={onOpen} className="border border-line bg-panel p-3 text-left transition-colors hover:border-line-2 hover:bg-panel-2">
      <div className="flex items-baseline justify-between">
        <span className="font-mono text-[15px] font-semibold tracking-wide">{a.code}</span>
        <span className="num text-[12.5px] text-dim">AUM <span className="text-fg">{money(a.aum, ccy)}</span></span>
      </div>
      <div className="num mt-1.5 mb-2 grid grid-cols-3 gap-2 text-[12.5px]">
        <span className="text-dim">GROSS <span className="text-fg">{money(a.gross, ccy)}</span></span>
        <span className="text-dim">NET <span className="text-fg">{money(a.net, ccy)}</span></span>
        <span className="text-right text-dim">P&L <span className={tone(a.pnl)}>{money(a.pnl, ccy)}</span></span>
      </div>
      <Meter label="Gross exposure vs AUM" value={a.gross_vs_aum_pct} />
      <Meter label={`Largest position (${a.largest_symbol ?? "—"})`} value={a.largest_pct}
        color={a.largest_pct > 40 ? "bg-warn" : "bg-accent"} />
      <Meter label="EQ share" value={share("EQ")} color="bg-dim/60" />
      <Meter label="FI share" value={share("FI")} color="bg-dim/60" />
      <Meter label="Deriv share" value={share("DERIV")} color="bg-dim/60" />
    </button>
  );
}

export default function Portfolio() {
  const { entity, ccy } = useEntity();
  const { can } = useAuth();
  const nav = useNavigate();
  const [acct, setAcct] = useState("");
  const [cls, setCls] = useState("");
  const [ticket, setTicket] = useState<{ account?: string; symbol?: string; side?: "BUY" | "SELL" } | null>(null);
  const { data, error, isLoading, dataUpdatedAt } = useQuery({
    queryKey: ["overview", entity],
    queryFn: () => api<Overview>(`/portfolio/overview?entity=${entity}`),
    refetchInterval: 4000,
  });

  const rows = useMemo(
    () => (data?.positions ?? []).filter((p) => (!acct || p.account === acct) && (!cls || p.asset_class === cls)),
    [data, acct, cls],
  );
  const scoped = useMemo(() => {
    const gross = rows.reduce((s, p) => s + Math.abs(p.exposure_rep), 0);
    const net = rows.reduce((s, p) => s + p.exposure_rep, 0);
    const pnl = rows.reduce((s, p) => s + p.mtm_pnl_rep, 0);
    return { gross, net, pnl };
  }, [rows]);

  if (isLoading) return <Loading label="Loading portfolios" />;
  if (error) return <ErrorBox error={error} />;
  if (!data) return null;
  const cur = data.reporting_ccy || ccy;

  const cols: Column<PositionRow>[] = [
    { key: "account", header: "Account", render: (r) => <span className="font-mono font-semibold">{r.account}</span>, sort: (r) => r.account },
    { key: "symbol", header: "Symbol", render: (r) => <span className="font-mono font-semibold">{r.symbol}</span>, sort: (r) => r.symbol },
    { key: "name", header: "Name", render: (r) => <span className="block max-w-[300px] truncate text-dim" title={r.name}>{r.name}</span>, sort: (r) => r.name },
    { key: "class", header: "Class", render: (r) => <span className="font-mono font-semibold">{r.asset_class}</span>, sort: (r) => r.asset_class },
    { key: "type", header: "Type", render: (r) => <span className="font-mono text-dim">{r.inst_type}</span>, sort: (r) => r.inst_type },
    { key: "ccy", header: "Ccy", render: (r) => <span className="font-mono">{r.ccy}</span>, sort: (r) => r.ccy },
    { key: "qty", header: "Qty", align: "right", render: (r) => <span className={tone(r.qty)}>{num(r.qty)}</span>, sort: (r) => r.qty },
    { key: "avg", header: "Avg Px", align: "right", render: (r) => px(r.avg_px), sort: (r) => r.avg_px },
    { key: "mark", header: "Mark", align: "right", render: (r) => px(r.mark), sort: (r) => r.mark },
    { key: "exp", header: "Exposure", align: "right", render: (r) => money(r.exposure, r.ccy), sort: (r) => r.exposure },
    { key: "exprep", header: `Exposure (${cur})`, align: "right", render: (r) => money(r.exposure_rep, cur), sort: (r) => Math.abs(r.exposure_rep) },
    { key: "pnl", header: "MTM P&L", align: "right", render: (r) => <span className={tone(r.mtm_pnl_rep)}>{money(r.mtm_pnl_rep, cur)}</span>, sort: (r) => r.mtm_pnl_rep },
    { key: "pnlp", header: "P&L %", align: "right", render: (r) => <span className={tone(r.pnl_pct)}>{pct(r.pnl_pct)}</span>, sort: (r) => r.pnl_pct },
    { key: "mat", header: "Expiry / Maturity", align: "right", render: (r) => <span className="text-dim">{r.maturity ?? "—"}</span>, sort: (r) => r.maturity ?? "" },
    ...(can("order:create")
      ? [{
          key: "act", header: "", align: "right" as const,
          render: (r: PositionRow) => r.asset_class === "DERIV" ? null : (
            <span className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()}>
              <Button size="sm" variant="up" onClick={() => setTicket({ account: r.account, symbol: r.symbol, side: "BUY" })}>B</Button>
              <Button size="sm" variant="danger" onClick={() => setTicket({ account: r.account, symbol: r.symbol, side: "SELL" })}>S</Button>
            </span>
          ),
        }]
      : []),
  ];

  return (
    <div className="flex min-h-full flex-col">
      <div className="flex flex-wrap items-center gap-x-14 gap-y-3 border-b border-line px-4 py-3">
        <div>
          <div className="text-[16px] font-semibold">All Portfolios</div>
          <div className="lbl mt-0.5">Firm-wide positions across every account</div>
        </div>
        <div><div className="lbl">Positions</div><div className="num mt-1 text-[20px]">{data.totals.positions}</div></div>
        <div><div className="lbl">Exposure ({cur})</div><div className="num mt-1 text-[20px]">{money(data.totals.net, cur)}</div></div>
        <div><div className="lbl">MTM P&L ({cur})</div><div className={`num mt-1 text-[20px] ${tone(data.totals.mtm_pnl)}`}>{money(data.totals.mtm_pnl, cur)}</div></div>
        <div><div className="lbl">Day P&L ({cur})</div><div className={`num mt-1 text-[20px] ${tone(data.totals.day_pnl)}`}>{money(data.totals.day_pnl, cur)}</div></div>
        <div><div className="lbl">AUM ({cur})</div><div className="num mt-1 text-[20px]">{money(data.totals.aum, cur)}</div></div>
        {can("order:create") && <Button variant="primary" className="ml-auto" onClick={() => setTicket({})}>+ New order</Button>}
      </div>

      <div className="flex flex-wrap items-center gap-6 border-b border-line px-4 py-2.5">
        <span className="lbl">Cross-asset positions & risk</span>
        <span className="lbl">Gross exposure <span className="num text-[13px] text-fg">{money(scoped.gross, cur)}</span></span>
        <span className="lbl">Net exposure <span className="num text-[13px] text-fg">{money(scoped.net, cur)}</span></span>
        <span className="lbl">MTM P&L <span className={`num text-[13px] ${tone(scoped.pnl)}`}>{money(scoped.pnl, cur)}</span></span>
        <div className="ml-auto flex gap-2">
          <Select value={acct} onChange={(e) => setAcct(e.target.value)} aria-label="Account filter" className="min-w-[150px]">
            <option value="">All accounts</option>
            {data.accounts.map((a) => <option key={a.code} value={a.code}>{a.code}</option>)}
          </Select>
          <Select value={cls} onChange={(e) => setCls(e.target.value)} aria-label="Asset class filter" className="min-w-[130px]">
            <option value="">All assets</option>
            <option value="EQ">Equities</option>
            <option value="FI">Fixed income</option>
            <option value="DERIV">Derivatives</option>
            <option value="FUND">Funds</option>
          </Select>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-2 p-2 md:grid-cols-2 xl:grid-cols-3">
        {data.accounts.filter((a) => !acct || a.code === acct).map((a) => (
          <AccountCard key={a.code} a={a} ccy={cur} onOpen={() => nav(`/accounts/${a.code}`)} />
        ))}
      </div>

      <div className="border-t border-line bg-panel">
        <DataTable columns={cols} rows={rows} rowKey={(r) => r.position_id} maxHeight="60vh"
          defaultSort={{ key: "exprep", dir: "desc" }} onRowClick={(r) => nav(`/accounts/${r.account}`)}
          empty="No positions for this selection" />
      </div>
      <div className="lbl px-4 py-2 text-mute">Marks refresh every 4s · last update {new Date(dataUpdatedAt).toLocaleTimeString()}</div>
      <OrderTicket open={!!ticket} preset={ticket ?? undefined} onClose={() => setTicket(null)} />
    </div>
  );
}
