import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useState } from "react";
import OrderTicket, { ComplianceResults } from "../components/OrderTicket";
import { Badge, Button, DataTable, ErrorBox, Field, Input, Loading, PageHeader, Panel, useToast } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { dt, money, num, px } from "../lib/format";
import type { Order } from "../lib/types";

const TABS = [
  { k: "PENDING_APPROVAL", l: "Awaiting approval" },
  { k: "FILLED", l: "Executed" },
  { k: "REJECTED", l: "Rejected" },
  { k: "CANCELLED", l: "Cancelled" },
  { k: "", l: "All" },
];

export default function Blotter() {
  const { user, can } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const [tab, setTab] = useState("PENDING_APPROVAL");
  const [sel, setSel] = useState<Order | null>(null);
  const [reason, setReason] = useState("");
  const [ticket, setTicket] = useState(false);
  const { data = [], error, isLoading } = useQuery({
    queryKey: ["orders", tab],
    queryFn: () => api<Order[]>(`/orders${tab ? `?status=${tab}` : ""}`),
    refetchInterval: 5000,
  });
  const act = useMutation({
    mutationFn: ({ id, action, body }: { id: number; action: string; body?: unknown }) =>
      api<Order>(`/orders/${id}/${action}`, { method: "POST", json: body }),
    onSuccess: (o) => {
      toast(o.status === "REJECTED" ? "err" : "ok", `Order #${o.id} ${o.status.replace("_", " ").toLowerCase()}`);
      setSel(o);
      setReason("");
      qc.invalidateQueries({ queryKey: ["orders"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
    onError: (e) => toast("err", (e as Error).message),
  });
  const pending = data.filter((o) => o.status === "PENDING_APPROVAL");
  const approveBatch = async (batch: string) => {
    for (const o of pending.filter((x) => x.batch_id === batch)) {
      await act.mutateAsync({ id: o.id, action: "approve" }).catch(() => undefined);
    }
  };
  const batches = [...new Set(pending.map((o) => o.batch_id).filter(Boolean))] as string[];

  return (
    <div>
      <PageHeader title="Order Blotter" subtitle="Maker-checker workflow · pre-trade compliance re-run at approval">
        {can("order:create") && <Button variant="primary" onClick={() => setTicket(true)}>+ New order</Button>}
      </PageHeader>
      <div className="flex items-center gap-1 border-b border-line px-3">
        {TABS.map((t) => (
          <button key={t.k} onClick={() => setTab(t.k)}
            className={clsx("lbl border-b-2 px-3 py-2.5", tab === t.k ? "border-accent text-fg" : "border-transparent hover:text-fg")}>
            {t.l}
          </button>
        ))}
        {can("order:approve") && batches.length > 0 && (
          <div className="ml-auto flex items-center gap-2 py-1">
            {batches.map((b) => (
              <Button key={b} size="sm" variant="up" disabled={act.isPending} onClick={() => approveBatch(b)}>Approve batch {b}</Button>
            ))}
          </div>
        )}
      </div>
      {error && <ErrorBox error={error} />}
      <div className="grid gap-0 xl:grid-cols-[1fr_420px]">
        <div className="min-w-0 border-r border-line">
          {isLoading ? <Loading /> : (
            <DataTable rows={data} rowKey={(o) => o.id} onRowClick={setSel} maxHeight="calc(100vh - 190px)"
              rowClass={(o) => (sel?.id === o.id ? "bg-raised" : undefined)} empty="No orders"
              columns={[
                { key: "id", header: "#", render: (o) => <span className="font-mono text-dim">{o.id}</span>, sort: (o) => o.id },
                { key: "t", header: "Time", render: (o) => <span className="font-mono text-dim">{dt(o.created_at)}</span>, sort: (o) => o.created_at },
                { key: "a", header: "Account", render: (o) => <span className="font-mono">{o.account}</span>, sort: (o) => o.account },
                { key: "sd", header: "Side", render: (o) => <Badge>{o.side}</Badge> },
                { key: "s", header: "Symbol", render: (o) => <span className="font-mono font-semibold">{o.symbol}</span>, sort: (o) => o.symbol },
                { key: "q", header: "Qty", align: "right", render: (o) => num(o.qty), sort: (o) => o.qty },
                { key: "p", header: "Px", align: "right", render: (o) => px(o.fill_px ?? o.limit_px ?? o.mark) },
                { key: "n", header: "Notional", align: "right", render: (o) => money(o.notional, o.ccy), sort: (o) => o.notional },
                { key: "c", header: "Compliance", render: (o) => <Badge>{o.compliance_status ?? "—"}</Badge> },
                { key: "src", header: "Source", render: (o) => <span className="font-mono text-[11px] text-dim">{o.source}</span> },
                { key: "st", header: "Status", render: (o) => <Badge>{o.status}</Badge>, sort: (o) => o.status },
                { key: "m", header: "Maker / Checker", render: (o) => <span className="text-[12px] text-dim">{o.created_by}{o.approved_by ? ` / ${o.approved_by}` : ""}</span> },
              ]} />
          )}
        </div>
        <aside className="p-3">
          {!sel ? <div className="lbl p-6 text-center text-mute">Select an order to review</div> : (
            <Panel title={`Order #${sel.id} · ${sel.side} ${sel.symbol}`} right={<Badge>{sel.status}</Badge>}>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-[12.5px]">
                {[
                  ["Account", sel.account], ["Security", sel.name], ["Quantity", num(sel.qty)], ["Mark", px(sel.mark)],
                  ["Limit", sel.limit_px ? px(sel.limit_px) : "Market"], ["Fill", sel.fill_px ? px(sel.fill_px) : "—"],
                  ["Notional", money(sel.notional, sel.ccy)], ["Est. cost", money(sel.est_cost, sel.ccy)],
                  ["Maker", sel.created_by], ["Checker", sel.approved_by ?? "—"], ["Batch", sel.batch_id ?? "—"], ["Source", sel.source],
                ].map(([k, v]) => (
                  <div key={k}><dt className="lbl">{k}</dt><dd className="num mt-0.5">{v}</dd></div>
                ))}
              </dl>
              {sel.override_reason && <div className="mt-3 text-[12px]"><span className="lbl">Override reason</span><div className="text-warn">{sel.override_reason}</div></div>}
              {sel.reject_reason && <div className="mt-3 text-[12px] text-down">Rejected: {sel.reject_reason}</div>}
              <div className="mt-3"><ComplianceResults c={sel.compliance} /></div>
              {sel.status === "PENDING_APPROVAL" && (
                <div className="mt-4 space-y-3">
                  {can("order:approve") && (
                    sel.created_by === user?.username ? (
                      <div className="text-[12px] text-warn">You entered this order — another checker must approve it.</div>
                    ) : (
                      <>
                        <Button variant="up" className="w-full" disabled={act.isPending} onClick={() => act.mutate({ id: sel.id, action: "approve" })}>Approve & execute</Button>
                        <Field label="Rejection reason"><Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Required to reject" /></Field>
                        <Button variant="danger" className="w-full" disabled={reason.trim().length < 3 || act.isPending}
                          onClick={() => act.mutate({ id: sel.id, action: "reject", body: { reason } })}>Reject</Button>
                      </>
                    )
                  )}
                  {(sel.created_by === user?.username || user?.role === "ADMIN") && (
                    <Button variant="ghost" className="w-full" onClick={() => act.mutate({ id: sel.id, action: "cancel" })}>Cancel order</Button>
                  )}
                </div>
              )}
            </Panel>
          )}
        </aside>
      </div>
      <OrderTicket open={ticket} onClose={() => setTicket(false)} />
    </div>
  );
}
