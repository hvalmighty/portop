import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import { useEntity } from "../lib/entity";
import { money, num, px } from "../lib/format";
import type { Compliance, Instrument, Overview } from "../lib/types";
import { Badge, Button, Field, Input, Modal, Select, useToast } from "./ui";

export function ComplianceResults({ c }: { c: Compliance }) {
  const rows = c.results.filter((r) => !r.passed);
  return (
    <div className="border border-line">
      <div className="flex items-center justify-between border-b border-line px-3 py-2">
        <span className="lbl">Pre-trade compliance</span>
        <Badge>{c.status}</Badge>
      </div>
      {rows.length === 0 ? (
        <div className="px-3 py-2 text-[12px] text-up">All {c.results.length} applicable rules pass</div>
      ) : (
        <ul className="divide-y divide-line">
          {rows.map((r, k) => (
            <li key={k} className="flex items-start gap-2 px-3 py-2 text-[12px]">
              <Badge tone={r.severity === "INFO" ? "ACKNOWLEDGED" : r.severity}>{r.severity}</Badge>
              <span className="font-mono text-dim">{r.code}</span>
              <span>{r.message}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function OrderTicket({ open, onClose, preset }: {
  open: boolean; onClose: () => void; preset?: { account?: string; symbol?: string; side?: "BUY" | "SELL" };
}) {
  const { entity } = useEntity();
  const qc = useQueryClient();
  const toast = useToast();
  const [account, setAccount] = useState("");
  const [symbol, setSymbol] = useState("");
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [qty, setQty] = useState("");
  const [limit, setLimit] = useState("");
  const [override, setOverride] = useState("");
  const { data: ov } = useQuery({ queryKey: ["overview", entity, "ticket"], queryFn: () => api<Overview>(`/portfolio/overview?entity=${entity}`), enabled: open });
  const { data: insts = [] } = useQuery({ queryKey: ["instruments"], queryFn: () => api<Instrument[]>("/instruments"), enabled: open });

  useEffect(() => {
    if (!open) return;
    setAccount(preset?.account ?? "");
    setSymbol(preset?.symbol ?? "");
    setSide(preset?.side ?? "BUY");
    setQty("");
    setLimit("");
    setOverride("");
  }, [open, preset]);
  useEffect(() => {
    if (open && !account && ov?.accounts.length) setAccount(ov.accounts[0].code);
  }, [open, ov, account]);

  const inst = insts.find((i) => i.symbol === symbol);
  const q = Number(qty);
  const valid = !!account && !!inst && q > 0;
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setDebounced(`${account}|${symbol}|${side}|${qty}`), 350);
    return () => clearTimeout(t);
  }, [account, symbol, side, qty]);
  const check = useQuery({
    queryKey: ["pretrade", debounced],
    enabled: open && valid && debounced === `${account}|${symbol}|${side}|${qty}`,
    queryFn: () => api<Compliance & { est_cost: number; notional: number }>("/orders/pretrade", {
      method: "POST", json: { account, symbol, side, qty: q },
    }),
  });
  const needsOverride = check.data?.results.some((r) => !r.passed && r.severity === "SOFT") ?? false;

  const submit = useMutation({
    mutationFn: () => api("/orders", {
      method: "POST",
      json: { account, symbol, side, qty: q, limit_px: limit ? Number(limit) : null, override_reason: override || null },
    }),
    onSuccess: () => {
      toast("ok", `Order staged for approval: ${side} ${num(q)} ${symbol} in ${account}`);
      qc.invalidateQueries({ queryKey: ["orders"] });
      onClose();
    },
    onError: (e) => toast("err", e instanceof ApiError ? e.message : String(e)),
  });

  return (
    <Modal open={open} onClose={onClose} title="New order ticket" width={620}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Account">
          <Select value={account} onChange={(e) => setAccount(e.target.value)}>
            {ov?.accounts.map((a) => <option key={a.code} value={a.code}>{a.code} — {a.name}</option>)}
          </Select>
        </Field>
        <Field label="Security" hint={inst ? `${inst.name} · ${inst.ccy} · mark ${px(inst.price)}` : "Type a symbol"}>
          <Input list="ticket-symbols" value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} placeholder="e.g. BDO" />
          <datalist id="ticket-symbols">
            {insts.filter((i) => i.asset_class !== "DERIV").map((i) => <option key={i.id} value={i.symbol}>{i.name}</option>)}
          </datalist>
        </Field>
        <Field label="Side">
          <div className="flex">
            {(["BUY", "SELL"] as const).map((s) => (
              <button key={s} type="button" onClick={() => setSide(s)}
                className={clsx("h-8 flex-1 border font-mono text-[12px]",
                  side === s ? (s === "BUY" ? "border-up bg-up/15 text-up" : "border-down bg-down/15 text-down") : "border-line-2 text-dim")}>
                {s}
              </button>
            ))}
          </div>
        </Field>
        <Field label="Quantity" hint={inst?.asset_class === "FI" ? "Face value" : "Units"}>
          <Input inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value.replace(/[^\d.]/g, ""))} placeholder="0" />
        </Field>
        <Field label="Limit price (optional)">
          <Input inputMode="decimal" value={limit} onChange={(e) => setLimit(e.target.value.replace(/[^\d.]/g, ""))} placeholder="Market" />
        </Field>
        <div className="flex flex-col justify-end gap-1 text-[12px]">
          <div className="flex justify-between"><span className="lbl">Notional</span><span className="num">{check.data ? money(check.data.notional, inst?.ccy) : "—"}</span></div>
          <div className="flex justify-between"><span className="lbl">Est. cost & tax</span><span className="num">{check.data ? money(check.data.est_cost, inst?.ccy) : "—"}</span></div>
        </div>
      </div>
      <div className="mt-4">
        {check.isFetching && <div className="lbl animate-pulse">Running pre-trade checks…</div>}
        {check.data && !check.isFetching && <ComplianceResults c={check.data} />}
        {check.error && <div className="text-[12px] text-down">{(check.error as Error).message}</div>}
      </div>
      {needsOverride && (
        <div className="mt-3">
          <Field label="Override reason (soft limit)">
            <Input value={override} onChange={(e) => setOverride(e.target.value)} placeholder="e.g. Investment committee approval ref." />
          </Field>
        </div>
      )}
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant="primary"
          disabled={!valid || submit.isPending || check.data?.status === "FAIL" || (needsOverride && override.trim().length < 3)}
          onClick={() => submit.mutate()}>
          {submit.isPending ? "Submitting…" : "Submit for approval"}
        </Button>
      </div>
    </Modal>
  );
}
