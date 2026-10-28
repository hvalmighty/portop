import { useMutation, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { useMemo, useState } from "react";
import { Button, DataTable, Empty, Field, Input, PageHeader, Panel, Select, Stat, useToast } from "../components/ui";
import { api } from "../lib/api";
import { useEntity } from "../lib/entity";
import { pct } from "../lib/format";
import type { Instrument, Overview } from "../lib/types";

interface Pt { exp_return: number; volatility: number }
interface Result {
  weights: { symbol: string; asset_class: string; weight: number; exp_return: number; vol: number; risk_contrib: number; current: number | null }[];
  portfolio: { exp_return: number; volatility: number; sharpe: number };
  equal_weight: { exp_return: number; volatility: number; sharpe: number };
  current: { exp_return: number; volatility: number; sharpe: number } | null;
  frontier: Pt[];
  assets: { symbol: string; exp_return: number; vol: number }[];
  dropped: string[];
}

const PRESETS: Record<string, string[]> = {
  "PH balanced": ["BDO", "SM", "ALI", "AC", "ICT", "MER", "JFC", "TEL", "RTB-2029", "FXTN-2031", "FXTN-2036", "SMICPM-2030", "ALIPM-2032", "PHTB-364D"],
  "PH fixed income": ["RTB-2029", "FXTN-2031", "FXTN-2036", "SMICPM-2030", "ALIPM-2032", "PHTB-364D", "ROP-2034"],
  "US large cap": ["MSFT", "NVDA", "AMZN", "GOOGL", "META", "AAPL", "V", "JPM", "UNH", "JNJ", "BRK.B"],
  "Global multi-asset": ["MSFT", "AAPL", "JPM", "D05", "Z74", "SGGB-2029", "SGGB-2034", "UST-2044", "AAPL-2033", "VZ-2036"],
};

function Frontier({ r }: { r: Result }) {
  const W = 560, H = 300, P = 40;
  const pts = [...r.frontier, ...r.assets.map((a) => ({ exp_return: a.exp_return, volatility: a.vol })), r.portfolio, r.equal_weight, ...(r.current ? [r.current] : [])];
  const xs = pts.map((p) => p.volatility), ys = pts.map((p) => p.exp_return);
  const [x0, x1] = [0, Math.max(...xs) * 1.08];
  const [y0, y1] = [Math.min(0, ...ys) * 1.1, Math.max(...ys) * 1.12];
  const sx = (v: number) => P + ((v - x0) / (x1 - x0 || 1)) * (W - P - 12);
  const sy = (v: number) => H - P + 8 - ((v - y0) / (y1 - y0 || 1)) * (H - P - 4);
  const ticks = (a: number, b: number) => Array.from({ length: 5 }, (_, k) => a + ((b - a) * k) / 4);
  return (
    <svg viewBox={`0 0 ${W} ${H + 10}`} className="w-full" role="img" aria-label="Efficient frontier">
      {ticks(y0, y1).map((t) => (
        <g key={`y${t}`}><line x1={P} x2={W - 12} y1={sy(t)} y2={sy(t)} stroke="var(--color-line)" />
          <text x={P - 6} y={sy(t) + 3} textAnchor="end" fontSize="10" fill="var(--color-mute)" fontFamily="var(--font-mono)">{(t * 100).toFixed(0)}%</text></g>
      ))}
      {ticks(x0, x1).map((t) => (
        <text key={`x${t}`} x={sx(t)} y={H + 6} textAnchor="middle" fontSize="10" fill="var(--color-mute)" fontFamily="var(--font-mono)">{(t * 100).toFixed(0)}%</text>
      ))}
      <text x={W - 12} y={H - 6 - P + 30} textAnchor="end" fontSize="10" fill="var(--color-dim)">Volatility →</text>
      <text x={P + 4} y={14} fontSize="10" fill="var(--color-dim)">↑ Expected return</text>
      <polyline fill="none" stroke="var(--color-accent)" strokeWidth="2" points={r.frontier.map((p) => `${sx(p.volatility)},${sy(p.exp_return)}`).join(" ")} />
      {r.assets.map((a) => (
        <g key={a.symbol}><circle cx={sx(a.vol)} cy={sy(a.exp_return)} r="3" fill="var(--color-dim)" />
          <text x={sx(a.vol) + 5} y={sy(a.exp_return) - 4} fontSize="9" fill="var(--color-mute)" fontFamily="var(--font-mono)">{a.symbol}</text></g>
      ))}
      <circle cx={sx(r.equal_weight.volatility)} cy={sy(r.equal_weight.exp_return)} r="5" fill="none" stroke="var(--color-warn)" strokeWidth="2" />
      {r.current && <rect x={sx(r.current.volatility) - 4} y={sy(r.current.exp_return) - 4} width="8" height="8" fill="var(--color-info)" />}
      <circle cx={sx(r.portfolio.volatility)} cy={sy(r.portfolio.exp_return)} r="6" fill="var(--color-up)" />
    </svg>
  );
}

export default function Optimizer() {
  const { entity } = useEntity();
  const toast = useToast();
  const { data: insts = [] } = useQuery({ queryKey: ["instruments"], queryFn: () => api<Instrument[]>("/instruments") });
  const { data: ov } = useQuery({ queryKey: ["overview", entity], queryFn: () => api<Overview>(`/portfolio/overview?entity=${entity}`) });
  const [syms, setSyms] = useState<string[]>(PRESETS["PH balanced"]);
  const [objective, setObjective] = useState("max_sharpe");
  const [maxW, setMaxW] = useState("20");
  const [minW, setMinW] = useState("0");
  const [rf, setRf] = useState("5.5");
  const [target, setTarget] = useState("8");
  const [eqBand, setEqBand] = useState(["30", "60"]);
  const [account, setAccount] = useState("");
  const [filter, setFilter] = useState("");
  const universe = useMemo(() => insts.filter((i) => i.asset_class !== "DERIV" && (!filter || `${i.symbol} ${i.name}`.toLowerCase().includes(filter.toLowerCase()))), [insts, filter]);

  const run = useMutation({
    mutationFn: () => api<Result>("/optimize", { method: "POST", json: {
      symbols: syms, objective, max_weight: Number(maxW) / 100, min_weight: Number(minW) / 100, rf: Number(rf) / 100,
      target_return: objective === "target_return" ? Number(target) / 100 : null,
      class_bounds: eqBand[0] !== "" && eqBand[1] !== "" && syms.some((s) => insts.find((i) => i.symbol === s)?.asset_class === "EQ") && syms.some((s) => insts.find((i) => i.symbol === s)?.asset_class !== "EQ")
        ? { EQ: [Number(eqBand[0]), Number(eqBand[1])] } : null,
      account: account || null,
    } }),
    onError: (e) => toast("err", (e as Error).message),
  });
  const r = run.data;

  return (
    <div>
      <PageHeader title="Portfolio Optimizer" subtitle="Mean-variance, max Sharpe, target return & risk parity · long-only with weight and asset-class constraints" />
      <div className="grid gap-3 p-3 xl:grid-cols-[360px_1fr]">
        <div className="space-y-3">
          <Panel title={`Universe (${syms.length})`} right={<Select value="" onChange={(e) => e.target.value && setSyms(PRESETS[e.target.value])} className="h-7 text-[11px]" aria-label="Preset">
            <option value="">Preset…</option>{Object.keys(PRESETS).map((k) => <option key={k}>{k}</option>)}</Select>}>
            <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter securities" className="mb-2 w-full" />
            <div className="max-h-[260px] overflow-auto">
              {universe.map((i) => (
                <label key={i.id} className="flex cursor-pointer items-center gap-2 py-0.5 text-[12.5px] hover:bg-raised">
                  <input type="checkbox" checked={syms.includes(i.symbol)} className="accent-[var(--color-accent)]"
                    onChange={() => setSyms((s) => (s.includes(i.symbol) ? s.filter((x) => x !== i.symbol) : [...s, i.symbol]))} />
                  <span className="w-[100px] font-mono">{i.symbol}</span><span className="truncate text-dim">{i.name}</span>
                  <span className="lbl ml-auto">{i.asset_class}</span>
                </label>
              ))}
            </div>
          </Panel>
          <Panel title="Objective & constraints">
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2"><Field label="Objective">
                <Select value={objective} onChange={(e) => setObjective(e.target.value)}>
                  <option value="max_sharpe">Maximise Sharpe ratio</option>
                  <option value="min_variance">Minimum variance</option>
                  <option value="target_return">Min risk for target return</option>
                  <option value="risk_parity">Risk parity (equal risk contribution)</option>
                </Select></Field></div>
              <Field label="Max weight %"><Input value={maxW} onChange={(e) => setMaxW(e.target.value)} /></Field>
              <Field label="Min weight %"><Input value={minW} onChange={(e) => setMinW(e.target.value)} /></Field>
              <Field label="Risk-free %"><Input value={rf} onChange={(e) => setRf(e.target.value)} /></Field>
              <Field label="Target return %"><Input value={target} disabled={objective !== "target_return"} onChange={(e) => setTarget(e.target.value)} /></Field>
              <Field label="Equity band min %"><Input value={eqBand[0]} onChange={(e) => setEqBand([e.target.value, eqBand[1]])} /></Field>
              <Field label="Equity band max %"><Input value={eqBand[1]} onChange={(e) => setEqBand([eqBand[0], e.target.value])} /></Field>
              <div className="col-span-2"><Field label="Compare with account (optional)">
                <Select value={account} onChange={(e) => setAccount(e.target.value)}>
                  <option value="">—</option>{ov?.accounts.map((a) => <option key={a.code}>{a.code}</option>)}
                </Select></Field></div>
            </div>
            <Button variant="primary" className="mt-3 w-full" disabled={syms.length < 2 || run.isPending} onClick={() => run.mutate()}>
              {run.isPending ? "Optimising…" : "Run optimisation"}
            </Button>
          </Panel>
        </div>
        <div className="min-w-0 space-y-3">
          {!r ? <Panel title="Results"><Empty>Configure the universe and run the optimiser</Empty></Panel> : (
            <>
              <div className="grid grid-cols-3 gap-3">
                {([["Optimal", r.portfolio, "text-up"], ["Equal weight", r.equal_weight, "text-warn"], ["Current account", r.current, "text-info"]] as const).map(([l, s, t]) => (
                  <Panel key={l} title={l}>
                    {s ? <div className="grid grid-cols-3 gap-2">
                      <Stat label="Exp. return" value={pct(s.exp_return * 100)} tone={t} />
                      <Stat label="Volatility" value={pct(s.volatility * 100)} />
                      <Stat label="Sharpe" value={s.sharpe.toFixed(2)} />
                    </div> : <div className="text-dim">Select an account to compare</div>}
                  </Panel>
                ))}
              </div>
              <div className="grid gap-3 2xl:grid-cols-[1fr_1fr]">
                <Panel title="Efficient frontier" right={<span className="lbl"><span className="text-up">● optimal</span> · <span className="text-warn">○ equal</span> · <span className="text-info">■ current</span></span>}>
                  <Frontier r={r} />
                  <div className="lbl mt-1 text-mute">Annualised from daily history · inputs shrunk toward diagonal covariance</div>
                </Panel>
                <Panel title="Optimal weights" pad={false}>
                  <DataTable rows={r.weights} rowKey={(w) => w.symbol} defaultSort={{ key: "w", dir: "desc" }} columns={[
                    { key: "s", header: "Symbol", render: (w) => <span className="font-mono font-semibold">{w.symbol}</span> },
                    { key: "c", header: "Class", render: (w) => w.asset_class },
                    { key: "w", header: "Weight", align: "right", render: (w) => pct(w.weight * 100), sort: (w) => w.weight },
                    { key: "b", header: "", render: (w) => <div className="h-2 w-[110px] bg-raised"><div className={clsx("h-full", w.weight > 0.001 ? "bg-accent" : "")} style={{ width: `${w.weight * 100 / (Number(maxW) / 100 || 1)}%` }} /></div> },
                    { key: "cur", header: "Current", align: "right", render: (w) => (w.current == null ? "—" : pct(w.current * 100)) },
                    { key: "rc", header: "Risk contrib.", align: "right", render: (w) => pct(w.risk_contrib * 100), sort: (w) => w.risk_contrib },
                    { key: "er", header: "Exp. ret", align: "right", render: (w) => pct(w.exp_return * 100) },
                    { key: "v", header: "Vol", align: "right", render: (w) => pct(w.vol * 100) },
                  ]} />
                </Panel>
              </div>
              {r.dropped.length > 0 && <div className="text-[12px] text-warn">Excluded (insufficient history): {r.dropped.join(", ")}</div>}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
