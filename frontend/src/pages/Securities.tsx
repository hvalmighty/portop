import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Badge, Button, DataTable, Field, Input, Loading, Modal, PageHeader, Panel, Select, useToast } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { num, pct, px, tone } from "../lib/format";
import { useMarket } from "../lib/market";
import type { Instrument } from "../lib/types";

const RATINGS = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-", "B+", "B", "B-", "CCC+", "CCC"];

export default function Securities() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const m = useMarket();
  const [params, setParams] = useSearchParams();
  const [cls, setCls] = useState("");
  const q = params.get("q") ?? "";
  const { data = [], isLoading } = useQuery({ queryKey: ["instruments", "master", q, cls], queryFn: () => api<Instrument[]>(`/instruments?${new URLSearchParams({ ...(q ? { q } : {}), ...(cls ? { asset_class: cls } : {}) })}`) });
  const fx = useQuery({ queryKey: ["fx"], queryFn: () => api<{ ccy: string; usd_per_unit: number }[]>("/system/fx") });
  const [edit, setEdit] = useState<Instrument | null>(null);
  const [rating, setRating] = useState("");
  const [esg, setEsg] = useState("");
  const save = useMutation({
    mutationFn: () => api(`/system/instruments/${edit!.symbol}`, { method: "PATCH", json: { rating: rating || null, esg_score: esg ? Number(esg) : null } }),
    onSuccess: () => { toast("ok", `${edit!.symbol} updated — next compliance scan will pick up the change`); setEdit(null); qc.invalidateQueries({ queryKey: ["instruments"] }); },
    onError: (e) => toast("err", (e as Error).message),
  });
  return (
    <div>
      <PageHeader title="Security Master" subtitle="Reference data · ratings · ESG · live marks">
        <Input placeholder="Search symbol, name, issuer" value={q} onChange={(e) => setParams(e.target.value ? { q: e.target.value } : {})} className="w-[260px]" />
        <Select value={cls} onChange={(e) => setCls(e.target.value)} aria-label="Asset class"><option value="">All classes</option><option>EQ</option><option>FI</option><option>DERIV</option></Select>
      </PageHeader>
      <div className="grid xl:grid-cols-[1fr_260px]">
        {isLoading ? <Loading /> : (
          <DataTable rows={data} rowKey={(i) => i.id} onRowClick={(i) => { if (can("ops:write")) { setEdit(i); setRating(i.rating ?? ""); setEsg(i.esg_score?.toString() ?? ""); } }} columns={[
            { key: "s", header: "Symbol", render: (i) => <span className="font-mono font-semibold">{i.symbol}</span>, sort: (i) => i.symbol },
            { key: "n", header: "Name", render: (i) => i.name, sort: (i) => i.name },
            { key: "c", header: "Class", render: (i) => i.asset_class, sort: (i) => i.asset_class },
            { key: "t", header: "Type", render: (i) => <span className="font-mono text-dim">{i.type}</span> },
            { key: "is", header: "Issuer", render: (i) => <span className="text-dim">{i.issuer}</span>, sort: (i) => i.issuer },
            { key: "sec", header: "Sector", render: (i) => <span className="text-dim">{i.sector}</span> },
            { key: "ccy", header: "Ccy", render: (i) => i.ccy },
            { key: "r", header: "Rating", render: (i) => i.rating ?? "—" },
            { key: "cp", header: "Cpn", align: "right", render: (i) => (i.coupon != null ? num(i.coupon, 3) : "—") },
            { key: "mat", header: "Maturity", render: (i) => <span className="font-mono text-dim">{i.maturity ?? "—"}</span> },
            { key: "d", header: "Dur", align: "right", render: (i) => i.duration?.toFixed(1) ?? "—" },
            { key: "esg", header: "ESG", align: "right", render: (i) => i.esg_score ?? "—", sort: (i) => i.esg_score ?? -1 },
            { key: "p", header: "Mark", align: "right", render: (i) => px(m.get(i.symbol)?.price ?? i.price) },
            { key: "ch", header: "Chg", align: "right", render: (i) => { const c = m.get(i.symbol)?.chg_pct ?? i.chg_pct; return <span className={tone(c)}>{pct(c, 2, true)}</span>; } },
            { key: "a", header: "", render: (i) => (i.is_active ? null : <Badge>Inactive</Badge>) },
          ]} />
        )}
        <Panel title="FX (USD per unit)" className="m-3">
          {fx.data?.map((r) => <div key={r.ccy} className="flex justify-between py-1"><span className="font-mono">{r.ccy}</span><span className="num">{num(r.usd_per_unit, 4)}</span></div>)}
        </Panel>
      </div>
      <Modal open={!!edit} onClose={() => setEdit(null)} title={`Static data · ${edit?.symbol}`} width={420}>
        <div className="grid gap-3">
          <Field label="Credit rating" hint="A downgrade below a rule floor creates a passive breach on the next scan">
            <Select value={rating} onChange={(e) => setRating(e.target.value)}><option value="">Not rated</option>{RATINGS.map((r) => <option key={r}>{r}</option>)}</Select>
          </Field>
          <Field label="ESG score (0-100)"><Input value={esg} onChange={(e) => setEsg(e.target.value.replace(/[^\d.]/g, ""))} /></Field>
        </div>
        <div className="mt-4 flex justify-end gap-2"><Button variant="ghost" onClick={() => setEdit(null)}>Cancel</Button><Button variant="primary" onClick={() => save.mutate()}>Save</Button></div>
      </Modal>
    </div>
  );
}
