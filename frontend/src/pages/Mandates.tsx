import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useEffect, useState } from "react";
import { Badge, Button, DataTable, ErrorBox, Field, Input, Loading, PageHeader, Panel, Select, Stat, useToast } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { pct } from "../lib/format";
import type { Instrument } from "../lib/types";

interface Mandate {
  currency: string;
  asset_class_label: string;
  universe: string[];
  universe_source: string;
  max_weight_pct: number;
  max_weight_basis: string;
  benchmark_weights: Record<string, number>;
  excess_return_bps: number;
}
interface ModelRow {
  id: number;
  code: string;
  name: string;
  benchmark: string;
  tolerance_pct: number;
  mandate: Partial<Mandate>;
  active_version: number | null;
  pending_versions: number;
  versions?: { id: number; version: number; status: string; created_by: string; approved_by: string | null; rationale: string }[];
}
interface OptResult {
  model: string;
  feasible: boolean;
  message: string;
  benchmark: string;
  benchmark_return: number;
  target_return: number;
  max_achievable_excess_bps: number;
  max_weight_pct: number;
  max_weight_basis: string;
  goal_bps: number;
  exp_return?: number;
  excess_return_bps?: number;
  volatility?: number;
  sharpe?: number;
  max_position_pct?: number;
  goal_met?: boolean;
  cap_respected?: boolean;
  firm_limit_breaches?: string[];
  dropped: string[];
  weights?: Record<string, number>;
}

const CURRENCIES = ["USD", "PHP", "SGD", "EUR"];
const emptyMandate: Mandate = {
  currency: "USD", asset_class_label: "", universe: [], universe_source: "", max_weight_pct: 20,
  max_weight_basis: "per stock", benchmark_weights: {}, excess_return_bps: 100,
};

export default function Mandates() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const { data: models = [], isLoading, error } = useQuery({ queryKey: ["models"], queryFn: () => api<ModelRow[]>("/models") });
  const { data: insts = [] } = useQuery({ queryKey: ["instruments-all"], queryFn: () => api<Instrument[]>("/instruments?limit=1000") });

  const mandated = models.filter((m) => m.mandate?.universe?.length);
  const [code, setCode] = useState<string>("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(false);
  useEffect(() => { if (!creating && !code && mandated.length) setCode(mandated[0].code); }, [mandated, code, creating]);
  const selected = mandated.find((m) => m.code === code);
  const { data: detail } = useQuery({ queryKey: ["model", code], queryFn: () => api<ModelRow>(`/models/${code}`), enabled: !!code && !creating });

  const [result, setResult] = useState<OptResult | null>(null);
  const [rationale, setRationale] = useState("");
  useEffect(() => { setResult(null); setEditing(false); }, [code]);

  const invalidate = () => { qc.invalidateQueries({ queryKey: ["models"] }); qc.invalidateQueries({ queryKey: ["model", code] }); };

  const optimise = useMutation({
    mutationFn: () => api<OptResult>(`/models/${code}/optimise`, { method: "POST" }),
    onSuccess: (r) => setResult(r),
    onError: (e) => toast("err", (e as Error).message),
  });
  const propose = useMutation({
    mutationFn: () => api(`/models/${code}/versions`, { method: "POST", json: { weights: result?.weights, rationale } }),
    onSuccess: () => { toast("ok", "Draft proposed, awaiting checker approval"); setRationale(""); invalidate(); },
    onError: (e) => toast("err", (e as Error).message),
  });

  if (isLoading) return <Loading />;
  if (error) return <ErrorBox error={error} />;

  return (
    <div>
      <PageHeader title="Fund Mandates" subtitle="Define a mandate (universe, position cap, benchmark goal), optimise against it, propose the weights">
        {can("model:write") && <Button variant="primary" onClick={() => { setCreating(true); setCode(""); }}>New mandate</Button>}
      </PageHeader>
      <div className="grid gap-3 p-3 xl:grid-cols-[280px_1fr]">
        <Panel title="Mandates" pad={false}>
          {mandated.length === 0 && <div className="p-3 text-[12px] text-mute">No mandates yet.</div>}
          {mandated.map((m) => (
            <button key={m.code} onClick={() => { setCreating(false); setCode(m.code); }}
              className={clsx("block w-full border-b border-line px-3 py-2.5 text-left hover:bg-raised", !creating && code === m.code && "bg-raised")}>
              <div className="flex items-center justify-between"><span className="font-mono font-semibold">{m.code}</span>
                {m.pending_versions > 0 && <Badge tone="WARN">{`${m.pending_versions} pending`}</Badge>}</div>
              <div className="text-[12px] text-dim">{m.name}</div>
              <div className="lbl mt-1 text-mute">{m.mandate.currency} · {m.mandate.universe?.length} securities · cap {m.mandate.max_weight_pct}%</div>
            </button>
          ))}
        </Panel>

        {creating && can("model:write") && (
          <MandateForm key="new" insts={insts} onCancel={() => setCreating(false)}
            onSaved={(c) => { setCreating(false); setCode(c); qc.invalidateQueries({ queryKey: ["models"] }); toast("ok", `Mandate ${c} created`); }} />
        )}

        {!creating && selected && detail && editing && (
          <MandateForm key={`edit-${code}`} insts={insts} model={detail} onCancel={() => setEditing(false)}
            onSaved={() => { setEditing(false); invalidate(); toast("ok", "Mandate updated"); }} />
        )}

        {!creating && selected && detail && !editing && (
          <div className="grid min-w-0 content-start gap-3 2xl:grid-cols-2">
            <Panel title={`${detail.code} · ${detail.name}`} right={
              <div className="flex gap-2">
                {can("model:write") && <Button size="sm" onClick={() => setEditing(true)}>Edit mandate</Button>}
                {can("optimizer:run") && <Button size="sm" variant="primary" disabled={optimise.isPending} onClick={() => optimise.mutate()}>{optimise.isPending ? "Optimising…" : "Run optimiser"}</Button>}
              </div>}>
              <MandateSummary m={detail.mandate as Mandate} benchmark={detail.benchmark} insts={insts} />
            </Panel>

            <Panel title="Optimisation result">
              {!result && <div className="text-[12.5px] text-mute">Run the optimiser to test this mandate: it minimises risk while beating the benchmark by the goal, within the position cap.</div>}
              {result && <ResultView r={result} insts={insts} />}
              {result?.feasible && can("model:write") && (
                <div className="mt-4 flex items-end gap-2 border-t border-line pt-3">
                  <Field label="Rationale for the draft">
                    <Input value={rationale} onChange={(e) => setRationale(e.target.value)} placeholder="e.g. Optimised to mandate, goal met" />
                  </Field>
                  <Button variant="primary" disabled={rationale.trim().length < 3 || propose.isPending} onClick={() => propose.mutate()}>Propose as draft</Button>
                </div>
              )}
            </Panel>

            <Panel title="Version history" pad={false} className="2xl:col-span-2">
              <DataTable rows={detail.versions ?? []} rowKey={(v) => v.id} empty="No versions yet: run the optimiser and propose the weights." columns={[
                { key: "v", header: "Ver", render: (v) => <span className="font-mono">v{v.version}</span> },
                { key: "s", header: "Status", render: (v) => <Badge>{v.status}</Badge> },
                { key: "r", header: "Rationale", render: (v) => <span className="block max-w-[320px] truncate text-dim" title={v.rationale}>{v.rationale}</span> },
                { key: "b", header: "Proposed / approved", render: (v) => <span className="text-[12px] text-dim">{v.created_by} / {v.approved_by ?? "—"}</span> },
              ]} />
              <div className="border-t border-line px-3 py-2 text-[11.5px] text-mute">Approve drafts on the Model Portfolios page (checker role, not the proposer).</div>
            </Panel>
          </div>
        )}
      </div>
    </div>
  );
}

function MandateSummary({ m, benchmark, insts }: { m: Mandate; benchmark: string; insts: Instrument[] }) {
  const names = Object.fromEntries(insts.map((i) => [i.symbol, i.name]));
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Stat label="Currency" value={m.currency} />
        <Stat label="Position cap" value={`${m.max_weight_pct}%`} sub={m.max_weight_basis} />
        <Stat label="Goal" value={`+${m.excess_return_bps} bps`} sub={benchmark} />
        <Stat label="Universe" value={m.universe.length} sub={m.asset_class_label} />
      </div>
      {m.universe_source && <div className="text-[11.5px] text-mute">{m.universe_source}</div>}
      <DataTable rows={m.universe.map((s) => ({ s }))} rowKey={(r) => r.s} maxHeight={260} columns={[
        { key: "s", header: "Security", render: (r) => <span className="font-mono font-semibold">{r.s}</span> },
        { key: "n", header: "Name", render: (r) => <span className="text-dim">{names[r.s] ?? "—"}</span> },
      ]} />
    </div>
  );
}

function ResultView({ r, insts }: { r: OptResult; insts: Instrument[] }) {
  const names = Object.fromEntries(insts.map((i) => [i.symbol, i.name]));
  if (!r.feasible) {
    return (
      <div className="space-y-2">
        <Badge tone="FAIL">Goal not achievable</Badge>
        <div className="text-[12.5px] text-dim">{r.message}</div>
        <div className="text-[12px] text-mute">Best achievable excess return: {r.max_achievable_excess_bps.toFixed(0)} bps (goal {r.goal_bps} bps).</div>
      </div>
    );
  }
  const weights = Object.entries(r.weights ?? {}).sort((a, b) => b[1] - a[1]);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <Badge tone={r.goal_met ? "PASS" : "FAIL"}>{r.goal_met ? "Goal met" : "Goal missed"}</Badge>
        <Badge tone={r.cap_respected ? "PASS" : "FAIL"}>{r.cap_respected ? `Cap ${r.max_weight_pct}% respected` : "Cap breached"}</Badge>
        {r.firm_limit_breaches && r.firm_limit_breaches.length > 0 && <Badge tone="WARN">Firm 20% soft limit: {r.firm_limit_breaches.join(", ")}</Badge>}
      </div>
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-3">
        <Stat label="Benchmark return" value={pct((r.benchmark_return) * 100)} sub={r.benchmark} />
        <Stat label="Target (benchmark + goal)" value={pct(r.target_return * 100)} />
        <Stat label="Portfolio return" value={pct((r.exp_return ?? 0) * 100)} />
        <Stat label="Excess return" value={`${(r.excess_return_bps ?? 0).toFixed(1)} bps`} tone={r.goal_met ? "text-up" : "text-down"} sub={`goal ${r.goal_bps} bps`} />
        <Stat label="Volatility" value={pct((r.volatility ?? 0) * 100)} sub={`Sharpe ${(r.sharpe ?? 0).toFixed(2)}`} />
        <Stat label="Largest position" value={pct(r.max_position_pct ?? 0)} sub={`cap ${r.max_weight_pct}%`} />
      </div>
      <DataTable rows={weights.map(([s, w]) => ({ s, w }))} rowKey={(x) => x.s} maxHeight={300} defaultSort={{ key: "w", dir: "desc" }} columns={[
        { key: "s", header: "Security", render: (x) => <span className="font-mono font-semibold">{x.s}</span>, sort: (x) => x.s },
        { key: "n", header: "Name", render: (x) => <span className="text-dim">{names[x.s] ?? "—"}</span> },
        { key: "w", header: "Weight", align: "right", render: (x) => pct(x.w), sort: (x) => x.w },
        { key: "b", header: "", render: (x) => <div className="h-2 w-[140px] bg-raised"><div className="h-full bg-accent" style={{ width: `${Math.min(100, x.w)}%` }} /></div> },
      ]} />
      {r.dropped.length > 0 && <div className="text-[11.5px] text-warn">No price history, excluded: {r.dropped.join(", ")}</div>}
    </div>
  );
}

function MandateForm({ insts, model, onSaved, onCancel }: { insts: Instrument[]; model?: ModelRow; onSaved: (code: string) => void; onCancel: () => void }) {
  const init = model ? { ...emptyMandate, ...(model.mandate as Mandate) } : emptyMandate;
  const [code, setCode] = useState(model?.code ?? "");
  const [name, setName] = useState(model?.name ?? "");
  const [m, setM] = useState<Mandate>(init);
  const [search, setSearch] = useState("");
  const [bmSym, setBmSym] = useState("");
  const [bmW, setBmW] = useState("");
  const toast = useToast();

  const indices = insts.filter((i) => i.type === "index");
  const candidates = insts.filter((i) => i.asset_class !== "DERIV" && i.type !== "index");
  const shown = candidates.filter((i) => !search || `${i.symbol} ${i.name} ${i.issuer}`.toLowerCase().includes(search.toLowerCase()));
  const blendTotal = Object.values(m.benchmark_weights).reduce((s, v) => s + v, 0);
  const valid = m.universe.length >= 2 && Math.abs(blendTotal - 100) < 0.01 && m.max_weight_pct > 0 && m.max_weight_pct <= 100
    && (!!model || (/^[A-Z0-9][A-Z0-9\-_]{1,31}$/.test(code) && name.trim().length >= 3));

  const save = useMutation({
    mutationFn: () => model
      ? api(`/models/${model.code}/mandate`, { method: "PUT", json: m })
      : api("/models", { method: "POST", json: { code, name, mandate: m, weights: {}, rationale: "Mandate definition" } }),
    onSuccess: () => onSaved(model ? model.code : code),
    onError: (e) => toast("err", (e as Error).message),
  });

  const toggle = (sym: string) => setM({ ...m, universe: m.universe.includes(sym) ? m.universe.filter((s) => s !== sym) : [...m.universe, sym] });
  const addBench = () => {
    const w = Number(bmW);
    if (!bmSym || !(w > 0)) return;
    setM({ ...m, benchmark_weights: { ...m.benchmark_weights, [bmSym]: w } });
    setBmSym(""); setBmW("");
  };

  return (
    <Panel title={model ? `Edit mandate · ${model.code}` : "New mandate"} right={
      <div className="flex gap-2"><Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button size="sm" variant="primary" disabled={!valid || save.isPending} onClick={() => save.mutate()}>{model ? "Save changes" : "Create mandate"}</Button></div>}>
      <div className="grid gap-3 md:grid-cols-2">
        {!model && <Field label="Code"><Input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="BDO-XXX" /></Field>}
        {!model && <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Fund name" /></Field>}
        <Field label="Currency"><Select value={m.currency} onChange={(e) => setM({ ...m, currency: e.target.value })}>{CURRENCIES.map((c) => <option key={c}>{c}</option>)}</Select></Field>
        <Field label="Asset class label"><Input value={m.asset_class_label} onChange={(e) => setM({ ...m, asset_class_label: e.target.value })} /></Field>
        <Field label="Position cap (% of fund)" hint="Maximum weight of any one security in the portfolio">
          <Input value={String(m.max_weight_pct)} onChange={(e) => setM({ ...m, max_weight_pct: Number(e.target.value.replace(/[^\d.]/g, "")) || 0 })} />
        </Field>
        <Field label="Cap basis" hint="Shown to users, e.g. per stock, per fund">
          <Input value={m.max_weight_basis} onChange={(e) => setM({ ...m, max_weight_basis: e.target.value })} />
        </Field>
        <Field label="Goal: excess return (bps)" hint="Expected return above the benchmark">
          <Input value={String(m.excess_return_bps)} onChange={(e) => setM({ ...m, excess_return_bps: Number(e.target.value.replace(/[^\d]/g, "")) || 0 })} />
        </Field>
        <Field label="Universe source note"><Input value={m.universe_source} onChange={(e) => setM({ ...m, universe_source: e.target.value })} /></Field>
      </div>

      <div className="mt-4">
        <div className="mb-1 flex items-center justify-between"><span className="lbl">Benchmark blend</span>
          <span className={clsx("num text-[12px]", Math.abs(blendTotal - 100) < 0.01 ? "text-up" : "text-down")}>Σ {blendTotal.toFixed(2)}%</span></div>
        <div className="space-y-1">
          {Object.entries(m.benchmark_weights).map(([s, w]) => (
            <div key={s} className="flex items-center gap-2 text-[12.5px]">
              <span className="w-[140px] font-mono">{s}</span><span className="num">{w}%</span>
              <button className="text-mute hover:text-down" onClick={() => { const n = { ...m.benchmark_weights }; delete n[s]; setM({ ...m, benchmark_weights: n }); }} aria-label={`Remove ${s}`}>✕</button>
            </div>
          ))}
        </div>
        <div className="mt-2 flex items-end gap-2">
          <Field label="Index"><Select value={bmSym} onChange={(e) => setBmSym(e.target.value)}><option value="">Select index</option>{indices.map((i) => <option key={i.symbol} value={i.symbol}>{i.symbol} · {i.name}</option>)}</Select></Field>
          <Field label="Weight %"><Input value={bmW} onChange={(e) => setBmW(e.target.value.replace(/[^\d.]/g, ""))} /></Field>
          <Button size="sm" onClick={addBench}>Add</Button>
        </div>
      </div>

      <div className="mt-4">
        <div className="mb-1 flex items-center justify-between"><span className="lbl">Universe ({m.universe.length} selected)</span>
          <Input className="w-[220px]" placeholder="Search symbol, name or issuer" value={search} onChange={(e) => setSearch(e.target.value)} /></div>
        <div className="grid max-h-[300px] grid-cols-1 gap-px overflow-auto border border-line sm:grid-cols-2">
          {shown.map((i) => (
            <label key={i.symbol} className="flex cursor-pointer items-center gap-2 bg-panel px-2 py-1 text-[12.5px] hover:bg-raised">
              <input type="checkbox" checked={m.universe.includes(i.symbol)} onChange={() => toggle(i.symbol)} />
              <span className="w-[110px] truncate font-mono">{i.symbol}</span>
              <span className="truncate text-dim">{i.name}</span>
            </label>
          ))}
        </div>
      </div>
      {!valid && <div className="mt-3 text-[11.5px] text-mute">Needs: at least 2 securities, a benchmark blend summing to 100%, a cap between 0 and 100%{model ? "" : ", a code and a name"}.</div>}
    </Panel>
  );
}
