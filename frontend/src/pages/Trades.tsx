import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useState } from "react";
import { Badge, Button, DataTable, Loading, PageHeader, Panel, useToast } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { money, num, px, tone } from "../lib/format";

interface Trade { id: number; order_id: number | null; account: string; symbol: string; name: string; side: string; qty: number; price: number; gross: number; fees: number; ccy: string; trade_date: string; settle_date: string; settle_status: string }
interface Cash { account: string; entity: string; ccy: string; amount: number }

export default function Trades() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const [st, setSt] = useState("");
  const trades = useQuery({ queryKey: ["trades", st], queryFn: () => api<Trade[]>(`/trades${st ? `?settle_status=${st}` : ""}`), refetchInterval: 10_000 });
  const cash = useQuery({ queryKey: ["cash"], queryFn: () => api<Cash[]>("/cash") });
  const settle = useMutation({
    mutationFn: (id: number) => api<Trade>(`/trades/${id}/settle`, { method: "POST" }),
    onSuccess: (t) => { toast("ok", `Trade #${t.id} settled`); qc.invalidateQueries({ queryKey: ["trades"] }); },
    onError: (e) => toast("err", (e as Error).message),
  });
  const today = new Date().toISOString().slice(0, 10);
  return (
    <div>
      <PageHeader title="Trades & Settlement" subtitle="Executed trades · settlement tracking · cash positions" />
      <div className="grid gap-3 p-3 xl:grid-cols-[1fr_380px]">
        <Panel title="Trade ledger" pad={false} right={
          <div className="flex gap-1">{["", "PENDING", "SETTLED"].map((s) => (
            <button key={s} onClick={() => setSt(s)} className={clsx("lbl px-2 py-1", st === s ? "text-accent" : "hover:text-fg")}>{s || "All"}</button>))}</div>}>
          {trades.isLoading ? <Loading /> : (
            <DataTable rows={trades.data ?? []} rowKey={(t) => t.id} maxHeight="calc(100vh - 200px)" empty="No trades yet — approve an order in the blotter" columns={[
              { key: "id", header: "#", render: (t) => <span className="font-mono text-dim">{t.id}</span>, sort: (t) => t.id },
              { key: "td", header: "Trade date", render: (t) => <span className="font-mono">{t.trade_date}</span> },
              { key: "sd", header: "Settle date", render: (t) => <span className={clsx("font-mono", t.settle_status === "PENDING" && t.settle_date < today && "text-down")}>{t.settle_date}</span>, sort: (t) => t.settle_date },
              { key: "a", header: "Account", render: (t) => <span className="font-mono">{t.account}</span> },
              { key: "s", header: "Side", render: (t) => <Badge>{t.side}</Badge> },
              { key: "sy", header: "Symbol", render: (t) => <span className="font-mono font-semibold">{t.symbol}</span> },
              { key: "q", header: "Qty", align: "right", render: (t) => num(t.qty) },
              { key: "p", header: "Price", align: "right", render: (t) => px(t.price) },
              { key: "g", header: "Gross", align: "right", render: (t) => money(t.gross, t.ccy) },
              { key: "f", header: "Fees/tax", align: "right", render: (t) => money(t.fees, t.ccy) },
              { key: "st", header: "Status", render: (t) => <Badge>{t.settle_status}</Badge> },
              { key: "x", header: "", align: "right", render: (t) => can("ops:write") && t.settle_status === "PENDING"
                ? <Button size="sm" variant="up" disabled={settle.isPending} onClick={() => settle.mutate(t.id)}>Settle</Button> : null },
            ]} />
          )}
        </Panel>
        <Panel title="Cash balances" pad={false}>
          <DataTable rows={cash.data ?? []} rowKey={(c) => `${c.account}-${c.ccy}`} maxHeight="calc(100vh - 200px)" columns={[
            { key: "a", header: "Account", render: (c) => <span className="font-mono">{c.account}</span>, sort: (c) => c.account },
            { key: "e", header: "Ent", render: (c) => c.entity },
            { key: "c", header: "Ccy", render: (c) => c.ccy },
            { key: "m", header: "Amount", align: "right", render: (c) => <span className={tone(c.amount)}>{num(c.amount, 2)}</span>, sort: (c) => c.amount },
          ]} />
        </Panel>
      </div>
    </div>
  );
}
