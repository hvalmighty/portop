import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { Instrument, Overview } from "../lib/types";
import { NAV } from "./Shell";

interface Item { kind: string; label: string; sub?: string; go: string }

export default function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [q, setQ] = useState("");
  const [i, setI] = useState(0);
  const nav = useNavigate();
  const { can } = useAuth();
  const input = useRef<HTMLInputElement>(null);
  const { data: insts = [] } = useQuery({ queryKey: ["instruments"], queryFn: () => api<Instrument[]>("/instruments"), enabled: open });
  const { data: ov } = useQuery({ queryKey: ["overview-all"], queryFn: () => api<Overview>("/portfolio/overview"), enabled: open });

  useEffect(() => {
    if (open) {
      setQ("");
      setI(0);
      setTimeout(() => input.current?.focus(), 0);
    }
  }, [open]);

  const items = useMemo<Item[]>(() => {
    const pages = NAV.flatMap((g) => g.items.filter((x) => can(x.perm)).map((x) => ({ kind: g.group, label: x.label, sub: x.desc, go: x.to })));
    const accts = (ov?.accounts ?? []).map((a) => ({ kind: "Account", label: a.code, sub: `${a.name} · ${a.entity}`, go: `/accounts/${a.code}` }));
    const sec = insts.map((s) => ({ kind: "Security", label: s.symbol, sub: `${s.name} · ${s.asset_class}`, go: `/securities?q=${encodeURIComponent(s.symbol)}` }));
    const all = [...pages, ...accts, ...sec];
    const t = q.trim().toLowerCase();
    if (!t) return all.slice(0, 14);
    return all.filter((x) => `${x.label} ${x.sub ?? ""}`.toLowerCase().includes(t)).slice(0, 30);
  }, [q, insts, ov, can]);

  if (!open) return null;
  const choose = (it?: Item) => {
    if (!it) return;
    nav(it.go);
    onClose();
  };
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 pt-[12vh]" onMouseDown={onClose}>
      <div className="w-[620px] border border-line-2 bg-panel shadow-2xl" onMouseDown={(e) => e.stopPropagation()}>
        <input
          ref={input}
          value={q}
          onChange={(e) => { setQ(e.target.value); setI(0); }}
          onKeyDown={(e) => {
            if (e.key === "Escape") onClose();
            if (e.key === "ArrowDown") { e.preventDefault(); setI((x) => Math.min(x + 1, items.length - 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setI((x) => Math.max(x - 1, 0)); }
            if (e.key === "Enter") choose(items[i]);
          }}
          placeholder="Jump to a page, account or security…"
          aria-label="Search"
          className="h-12 w-full border-b border-line bg-transparent px-4 text-[14px] outline-none placeholder:text-mute"
        />
        <ul className="max-h-[50vh] overflow-auto py-1" role="listbox">
          {items.map((it, k) => (
            <li key={`${it.kind}-${it.label}`} role="option" aria-selected={k === i}
              onMouseEnter={() => setI(k)} onClick={() => choose(it)}
              className={clsx("flex cursor-pointer items-center gap-3 px-4 py-2", k === i && "bg-raised")}>
              <span className="lbl w-[110px] shrink-0">{it.kind}</span>
              <span className="font-mono text-[13px]">{it.label}</span>
              <span className="truncate text-[12px] text-mute">{it.sub}</span>
            </li>
          ))}
          {items.length === 0 && <li className="lbl px-4 py-6 text-center">No matches</li>}
        </ul>
      </div>
    </div>
  );
}
