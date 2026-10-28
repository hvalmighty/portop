import clsx from "clsx";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";

/* ------------------------------------------------------------------ layout */

export function Panel({ title, right, children, className, pad = true }: {
  title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; pad?: boolean;
}) {
  return (
    <section className={clsx("border border-line bg-panel", className)}>
      {(title || right) && (
        <header className="flex h-9 items-center justify-between gap-3 border-b border-line px-3">
          <div className="lbl truncate text-fg/90">{title}</div>
          <div className="flex items-center gap-2">{right}</div>
        </header>
      )}
      <div className={clsx(pad && "p-3")}>{children}</div>
    </section>
  );
}

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: string; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 border-b border-line px-4 py-3">
      <div>
        <h1 className="text-[15px] font-semibold tracking-wide">{title}</h1>
        {subtitle && <div className="lbl mt-0.5">{subtitle}</div>}
      </div>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

export function Stat({ label, value, tone, sub }: { label: string; value: ReactNode; tone?: string; sub?: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="lbl">{label}</div>
      <div className={clsx("num mt-1 truncate text-[19px] font-medium", tone)}>{value}</div>
      {sub && <div className="num mt-0.5 text-[11px] text-mute">{sub}</div>}
    </div>
  );
}

/** labelled horizontal meter, as on the account cards */
export function Meter({ label, value, display, max = 100, color = "bg-accent" }: {
  label: ReactNode; value: number; display?: ReactNode; max?: number; color?: string;
}) {
  const w = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="py-[5px]">
      <div className="flex items-center justify-between">
        <span className="lbl">{label}</span>
        <span className="num text-[12px] text-dim">{display ?? `${value.toFixed(1)}%`}</span>
      </div>
      <div className="mt-1 h-[5px] w-full bg-raised">
        <div className={clsx("h-full transition-[width] duration-500", color)} style={{ width: `${w}%` }} />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ controls */

export function Button({ variant = "default", size = "md", className, ...p }: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "primary" | "danger" | "ghost" | "up"; size?: "sm" | "md";
}) {
  return (
    <button
      {...p}
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 border font-mono uppercase tracking-wider transition-colors disabled:cursor-not-allowed disabled:opacity-40",
        size === "sm" ? "h-7 px-2 text-[10.5px]" : "h-8 px-3 text-[11px]",
        variant === "primary" && "border-accent bg-accent/15 text-accent hover:bg-accent/25",
        variant === "up" && "border-up/60 bg-up/10 text-up hover:bg-up/20",
        variant === "danger" && "border-down/60 bg-down/10 text-down hover:bg-down/20",
        variant === "ghost" && "border-transparent text-dim hover:text-fg",
        variant === "default" && "border-line-2 bg-panel-2 text-fg hover:border-dim",
        className,
      )}
    />
  );
}

export function Input({ className, ...p }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...p}
      className={clsx(
        "h-8 border border-line-2 bg-bg px-2 font-mono text-[12.5px] text-fg outline-none placeholder:text-mute focus:border-accent",
        className,
      )}
    />
  );
}

export function Select({ className, children, ...p }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...p}
      className={clsx("h-8 border border-line-2 bg-panel-2 px-2 text-[12.5px] text-fg outline-none focus:border-accent", className)}
    >
      {children}
    </select>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="lbl">{label}</span>
      {children}
      {hint && <span className="text-[11px] text-mute">{hint}</span>}
    </label>
  );
}

const BADGE: Record<string, string> = {
  PASS: "border-up/50 text-up",
  FILLED: "border-up/50 text-up",
  SETTLED: "border-up/50 text-up",
  ACTIVE: "border-up/50 text-up",
  RESOLVED: "border-up/50 text-up",
  WARN: "border-warn/60 text-warn",
  SOFT: "border-warn/60 text-warn",
  PENDING_APPROVAL: "border-warn/60 text-warn",
  PENDING: "border-warn/60 text-warn",
  DRAFT: "border-warn/60 text-warn",
  ACKNOWLEDGED: "border-info/60 text-info",
  PASSIVE: "border-info/60 text-info",
  FAIL: "border-down/60 text-down",
  HARD: "border-down/60 text-down",
  REJECTED: "border-down/60 text-down",
  OPEN: "border-down/60 text-down",
  CRIT: "border-down/60 text-down",
  BUY: "border-up/50 text-up",
  SELL: "border-down/60 text-down",
};

export function Badge({ children, tone }: { children: ReactNode; tone?: string }) {
  const key = tone ?? String(children);
  return (
    <span className={clsx("inline-block border px-1.5 py-[1px] font-mono text-[10px] uppercase tracking-wider",
      BADGE[key] ?? "border-line-2 text-dim")}>
      {typeof children === "string" ? children.replace(/_/g, " ") : children}
    </span>
  );
}

/* ------------------------------------------------------------------ feedback */

export function Loading({ label = "Loading" }: { label?: string }) {
  return <div className="lbl animate-pulse p-6 text-center">{label}…</div>;
}

export function ErrorBox({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : String(error);
  return <div className="m-3 border border-down/50 bg-down/10 p-3 text-[12px] text-down">{msg}</div>;
}

export function Empty({ children = "No data" }: { children?: ReactNode }) {
  return <div className="lbl p-6 text-center text-mute">{children}</div>;
}

export function Modal({ open, onClose, title, children, width = 560 }: {
  open: boolean; onClose: () => void; title: string; children: ReactNode; width?: number;
}) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 pt-[8vh]" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="max-h-[84vh] w-full overflow-auto border border-line-2 bg-panel shadow-2xl"
        style={{ maxWidth: width }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="flex h-10 items-center justify-between border-b border-line px-4">
          <span className="lbl text-fg">{title}</span>
          <button className="text-dim hover:text-fg" onClick={onClose} aria-label="Close">✕</button>
        </header>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ toasts */

interface Toast { id: number; tone: "ok" | "err" | "info"; text: string }
const ToastCtx = createContext<(tone: Toast["tone"], text: string) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((tone: Toast["tone"], text: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, tone, text }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed right-4 bottom-4 z-[60] flex w-[360px] flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={clsx("border bg-panel-2 px-3 py-2 text-[12px] shadow-xl",
            t.tone === "ok" ? "border-up/60" : t.tone === "err" ? "border-down/60" : "border-info/60")}>
            {t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);

/* ------------------------------------------------------------------ data table */

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  sort?: (row: T) => number | string;
  align?: "left" | "right" | "center";
  className?: string;
  width?: number | string;
}

export function DataTable<T>({ columns, rows, rowKey, onRowClick, maxHeight, empty, defaultSort, dense = true, rowClass }: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (r: T) => string | number;
  onRowClick?: (r: T) => void;
  maxHeight?: number | string;
  empty?: ReactNode;
  defaultSort?: { key: string; dir: "asc" | "desc" };
  dense?: boolean;
  rowClass?: (r: T) => string | undefined;
}) {
  const [sort, setSort] = useState(defaultSort ?? null);
  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sort) return rows;
    const f = col.sort;
    return [...rows].sort((a, b) => {
      const x = f(a), y = f(b);
      const r = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
      return sort.dir === "asc" ? r : -r;
    });
  }, [rows, sort, columns]);

  return (
    <div className="overflow-auto" style={{ maxHeight }}>
      <table className="w-full border-collapse">
        <thead className="sticky top-0 z-10 bg-panel">
          <tr className="border-b border-line">
            {columns.map((c) => (
              <th
                key={c.key}
                style={{ width: c.width }}
                className={clsx(
                  "lbl px-2 py-2 font-normal whitespace-nowrap select-none first:pl-3",
                  c.align === "right" ? "text-right" : c.align === "center" ? "text-center" : "text-left",
                  c.sort && "cursor-pointer hover:text-fg",
                )}
                onClick={() => c.sort && setSort((s) => ({ key: c.key, dir: s?.key === c.key && s.dir === "desc" ? "asc" : "desc" }))}
                aria-sort={sort?.key === c.key ? (sort.dir === "asc" ? "ascending" : "descending") : undefined}
              >
                {c.header}
                {sort?.key === c.key && <span className="ml-1 text-accent">{sort.dir === "asc" ? "▲" : "▼"}</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 && (
            <tr>
              <td colSpan={columns.length}><Empty>{empty}</Empty></td>
            </tr>
          )}
          {sorted.map((r) => (
            <tr
              key={rowKey(r)}
              onClick={onRowClick ? () => onRowClick(r) : undefined}
              className={clsx("border-b border-line/70 hover:bg-raised/60", onRowClick && "cursor-pointer", rowClass?.(r))}
            >
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={clsx(
                    "px-2 whitespace-nowrap first:pl-3",
                    dense ? "py-[7px]" : "py-2.5",
                    c.align === "right" ? "num text-right" : c.align === "center" ? "text-center" : "text-left",
                    c.className,
                  )}
                >
                  {c.render(r)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
