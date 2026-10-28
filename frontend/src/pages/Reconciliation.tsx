import { useMutation } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Badge, Button, DataTable, Empty, PageHeader, Panel, Stat, useToast } from "../components/ui";
import { ApiError, tokenStore } from "../lib/api";
import { num } from "../lib/format";

interface Break { account: string; symbol: string; book_qty: number; custodian_qty: number; diff: number; type: string }
interface Result { file: string; matched: number; breaks: Break[]; errors: { line: number | null; error: string }[]; run_at: string }

export default function Reconciliation() {
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const run = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      fd.append("file", file!);
      const res = await fetch("/api/v1/reconciliation", { method: "POST", body: fd, headers: { Authorization: `Bearer ${tokenStore.get() ?? ""}` } });
      const body = await res.json();
      if (!res.ok) throw new ApiError(res.status, typeof body.detail === "string" ? body.detail : "Upload failed");
      return body as Result;
    },
    onError: (e) => toast("err", (e as Error).message),
  });
  const r = run.data;
  return (
    <div>
      <PageHeader title="Position Reconciliation" subtitle="Custodian statement vs book of record · CSV (account,symbol,qty) · max 5 MB" />
      <div className="space-y-3 p-3">
        <Panel title="Upload custodian holdings">
          <div className="flex flex-wrap items-center gap-3">
            <input ref={input} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <Button onClick={() => input.current?.click()}>Choose file</Button>
            <span className="font-mono text-[12px] text-dim">{file ? `${file.name} · ${num(file.size / 1024, 1)} KB` : "No file selected"}</span>
            <Button variant="primary" disabled={!file || run.isPending} onClick={() => run.mutate()}>{run.isPending ? "Reconciling…" : "Reconcile"}</Button>
          </div>
          <div className="mt-2 text-[11.5px] text-mute">Validation: UTF-8, required columns, numeric quantities, known accounts and entitlement. Every run is written to the audit trail.</div>
        </Panel>
        {r && (
          <>
            <div className="grid grid-cols-3 gap-3">
              <Panel title="Matched"><Stat label="Positions" value={r.matched} tone="text-up" /></Panel>
              <Panel title="Breaks"><Stat label="Positions" value={r.breaks.length} tone={r.breaks.length ? "text-down" : "text-up"} /></Panel>
              <Panel title="File errors"><Stat label="Lines" value={r.errors.length} tone={r.errors.length ? "text-warn" : "text-up"} /></Panel>
            </div>
            <Panel title="Breaks" pad={false}>
              {r.breaks.length === 0 ? <Empty>Fully reconciled</Empty> : (
                <DataTable rows={r.breaks} rowKey={(b) => `${b.account}-${b.symbol}`} columns={[
                  { key: "t", header: "Type", render: (b) => <Badge tone={b.type === "QTY_MISMATCH" ? "WARN" : "FAIL"}>{b.type}</Badge> },
                  { key: "a", header: "Account", render: (b) => <span className="font-mono">{b.account}</span> },
                  { key: "s", header: "Symbol", render: (b) => <span className="font-mono font-semibold">{b.symbol}</span> },
                  { key: "b", header: "Book", align: "right", render: (b) => num(b.book_qty) },
                  { key: "c", header: "Custodian", align: "right", render: (b) => num(b.custodian_qty) },
                  { key: "d", header: "Difference", align: "right", render: (b) => <span className="text-down">{num(b.diff)}</span>, sort: (b) => Math.abs(b.diff) },
                ]} />
              )}
            </Panel>
            {r.errors.length > 0 && <Panel title="File errors"><ul className="text-[12px] text-warn">{r.errors.map((e, k) => <li key={k}>{e.line ? `Line ${e.line}: ` : ""}{e.error}</li>)}</ul></Panel>}
          </>
        )}
      </div>
    </div>
  );
}
