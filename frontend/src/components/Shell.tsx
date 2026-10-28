import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { useEffect, useMemo, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useEntity } from "../lib/entity";
import { pct, px } from "../lib/format";
import { market, useMarket } from "../lib/market";
import CommandPalette from "./CommandPalette";

export interface NavItem { to: string; label: string; perm: string; desc?: string }
export const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "Front Office",
    items: [
      { to: "/portfolio", label: "My Portfolio", perm: "portfolio:read", desc: "Firm-wide cross-asset positions" },
      { to: "/blotter", label: "Order Blotter", perm: "portfolio:read", desc: "Orders, approvals, executions" },
      { to: "/models", label: "Model Portfolios", perm: "portfolio:read", desc: "Models, versions, drift" },
      { to: "/rebalance", label: "Rebalancing", perm: "portfolio:read", desc: "Drift-based proposals" },
      { to: "/optimizer", label: "Optimizer", perm: "optimizer:run", desc: "Mean-variance & risk parity" },
    ],
  },
  {
    group: "Middle Office",
    items: [
      { to: "/compliance", label: "Compliance Monitor", perm: "compliance:read", desc: "Breaches & cases" },
      { to: "/rules", label: "Rule Library", perm: "compliance:read", desc: "Regulatory, mandate, internal" },
      { to: "/risk", label: "Risk & Stress", perm: "risk:read", desc: "VaR, duration, scenarios" },
    ],
  },
  {
    group: "Back Office",
    items: [
      { to: "/trades", label: "Trades & Settlement", perm: "ops:read", desc: "Settlement status, cash" },
      { to: "/reconciliation", label: "Reconciliation", perm: "ops:read", desc: "Custodian vs book" },
      { to: "/audit", label: "Audit Trail", perm: "audit:read", desc: "Every change, who and when" },
    ],
  },
  { group: "Reports", items: [{ to: "/reports", label: "Report Centre", perm: "reports:read", desc: "Exports for governance" }] },
  {
    group: "System",
    items: [
      { to: "/securities", label: "Security Master", perm: "portfolio:read", desc: "Instruments & FX" },
      { to: "/users", label: "Users & Roles", perm: "system:admin", desc: "Entitlements, SoD" },
    ],
  },
];

function Menu({ group, items }: { group: string; items: NavItem[] }) {
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  const ref = useRef<HTMLDivElement>(null);
  const active = items.find((i) => loc.pathname.startsWith(i.to));
  useEffect(() => setOpen(false), [loc.pathname]);
  useEffect(() => {
    const h = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  return (
    <div ref={ref} className="relative h-full">
      <button
        className={clsx("flex h-full items-center gap-1.5 px-3 font-mono text-[11.5px] tracking-[0.1em] uppercase",
          active ? "text-fg" : "text-dim hover:text-fg")}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        {group}
        {active && <span className="font-sans text-[13px] font-semibold tracking-normal normal-case">· {active.label}</span>}
        <span className="text-[9px] text-mute">▼</span>
      </button>
      {active && <div className="absolute inset-x-3 bottom-0 h-[2px] bg-accent" />}
      {open && (
        <div className="absolute top-full left-0 z-40 min-w-[260px] border border-line-2 bg-panel-2 py-1 shadow-2xl">
          {items.map((i) => (
            <NavLink key={i.to} to={i.to}
              className={({ isActive }) => clsx("block px-3 py-2 hover:bg-raised", isActive && "bg-raised")}>
              <div className="text-[13px]">{i.label}</div>
              {i.desc && <div className="text-[11px] text-mute">{i.desc}</div>}
            </NavLink>
          ))}
        </div>
      )}
    </div>
  );
}

function Ticker() {
  const m = useMarket();
  const ticks = m.all();
  const prev = useRef(new Map<string, number>());
  const groups = useMemo(() => {
    const order = ["EQ", "FI", "DERIV"];
    return [...ticks].sort((a, b) => order.indexOf(a.asset_class) - order.indexOf(b.asset_class));
  }, [ticks]);
  const items = groups.map((t) => {
    const p = prev.current.get(t.symbol);
    const dir = p == null ? "" : t.price > p ? "flash-up" : t.price < p ? "flash-down" : "";
    return { t, dir };
  });
  useEffect(() => {
    ticks.forEach((t) => prev.current.set(t.symbol, t.price));
  }, [ticks]);
  const row = items.map(({ t, dir }) => (
    <span key={t.symbol} className={clsx("mx-3 inline-flex gap-2 whitespace-nowrap px-1", dir)}>
      <span className="font-semibold text-fg">{t.symbol}</span>
      <span className={t.chg_pct >= 0 ? "text-up" : "text-down"}>{px(t.price)}</span>
      <span className={t.chg_pct >= 0 ? "text-up" : "text-down"}>{pct(t.chg_pct, 2, true)}</span>
    </span>
  ));
  return (
    <div className="flex h-8 items-center overflow-hidden border-b border-line bg-bg font-mono text-[12px]">
      <div className="flex h-full shrink-0 items-center gap-2 border-r border-line bg-bg px-3">
        <span className={clsx("h-1.5 w-1.5 rounded-full",
          m.status === "live" ? "bg-up" : m.status === "connecting" ? "bg-warn" : "bg-down")}
          title={`Market data ${m.status}`} />
        <span className="lbl">MKT</span>
      </div>
      {ticks.length === 0 ? (
        <span className="lbl px-3 text-mute">{m.status === "live" ? "Waiting for ticks…" : "Market data offline"}</span>
      ) : (
        <div className="min-w-0 flex-1 overflow-hidden"><div className="ticker-track flex w-max">{row}{row}</div></div>
      )}
    </div>
  );
}

export default function Shell() {
  const { user, logout, can } = useAuth();
  const { entities, entity, setEntity } = useEntity();
  const [palette, setPalette] = useState(false);
  const nav = useNavigate();
  const { data: alerts = [] } = useQuery({
    queryKey: ["alerts", "unread"],
    queryFn: () => api<{ id: number }[]>("/alerts?unread=true"),
    refetchInterval: 15_000,
  });

  useEffect(() => {
    market.start();
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((p) => !p);
      }
    };
    window.addEventListener("keydown", h);
    return () => {
      window.removeEventListener("keydown", h);
      market.stop();
    };
  }, []);

  const menus = NAV.map((g) => ({ ...g, items: g.items.filter((i) => can(i.perm)) })).filter((g) => g.items.length);

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-12 shrink-0 items-stretch border-b border-line bg-panel">
        <button className="flex items-center gap-3 px-4" onClick={() => nav("/portfolio")} aria-label="Home">
          <span className="flex flex-col items-start leading-none">
            <span className="text-[19px] font-bold tracking-tight text-[#3b82f6] italic">KFINTECH</span>
            <span className="text-[6.5px] tracking-[0.18em] text-dim">EXPERIENCE TRANSFORMATION</span>
          </span>
          <span className="text-[16px] font-semibold">mPower</span>
        </button>
        <div className="flex items-center gap-1 px-2" role="radiogroup" aria-label="Booking entity">
          {entities.map((e) => (
            <button key={e.code} role="radio" aria-checked={entity === e.code} title={e.name}
              onClick={() => setEntity(e.code)}
              className={clsx("h-7 rounded-[3px] px-2.5 font-mono text-[12px] font-semibold",
                entity === e.code ? "bg-accent text-bg" : "text-dim hover:bg-raised hover:text-fg")}>
              {e.code}
            </button>
          ))}
        </div>
        <div className="mx-2 my-3 w-px bg-line-2" />
        <nav className="flex items-stretch">{menus.map((g) => <Menu key={g.group} {...g} />)}</nav>
        <div className="ml-auto flex items-center gap-3 pr-3">
          <button onClick={() => setPalette(true)}
            className="flex h-8 w-[170px] items-center gap-2 border border-line-2 bg-bg px-2 text-[12.5px] text-mute hover:border-dim">
            <span aria-hidden>⌕</span> Search <kbd className="ml-auto rounded bg-raised px-1 font-mono text-[10px]">⌘K</kbd>
          </button>
          <NavLink to="/compliance" className="relative text-dim hover:text-fg" title="Unread alerts" aria-label="Alerts">
            <span className="text-[16px]">◉</span>
            {alerts.length > 0 && (
              <span className="absolute -top-1.5 -right-2 rounded-full bg-down px-1 font-mono text-[9px] text-white">{alerts.length}</span>
            )}
          </NavLink>
          <span className="font-mono text-[12px] font-bold tracking-wider">{user?.role}</span>
          <span className="hidden text-[13px] xl:inline">{user?.full_name}</span>
          <button onClick={logout} className="text-dim hover:text-fg" title="Sign out" aria-label="Sign out">⏻</button>
        </div>
      </header>
      <Ticker />
      <main className="min-h-0 flex-1 overflow-auto"><Outlet /></main>
      <CommandPalette open={palette} onClose={() => setPalette(false)} />
    </div>
  );
}
