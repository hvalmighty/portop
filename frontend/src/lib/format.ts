const SUFFIX: [number, string][] = [
  [1e12, "t"],
  [1e9, "bn"],
  [1e6, "m"],
  [1e3, "k"],
];

/** "SGD 445.69m", "-SGD 6.7k" */
export function money(v: number | null | undefined, ccy?: string, digits = 2): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const neg = v < 0;
  const a = Math.abs(v);
  let s = a.toFixed(0);
  for (const [n, suf] of SUFFIX) {
    if (a >= n) {
      const d = suf === "k" ? 1 : digits;
      s = (a / n).toFixed(d) + suf;
      break;
    }
  }
  if (a < 1000) s = a.toFixed(a < 10 ? 2 : 0);
  return `${neg ? "-" : ""}${ccy ? ccy + " " : ""}${s}`;
}

export function num(v: number | null | undefined, digits = 0): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function px(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const d = Math.abs(v) >= 1000 ? 2 : Math.abs(v) >= 1 ? 3 : 4;
  return num(v, d);
}

export function pct(v: number | null | undefined, digits = 2, signed = false): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${signed && v > 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

export function tone(v: number | null | undefined): string {
  if (v == null || Math.abs(v) < 1e-9) return "text-dim";
  return v > 0 ? "text-up" : "text-down";
}

export function dt(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
