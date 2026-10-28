import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { DataTable, Input, Loading, Modal, PageHeader, Select } from "../components/ui";
import { api } from "../lib/api";
import { dt } from "../lib/format";

interface Row { id: number; ts: string; username: string; action: string; object_type: string; object_id: string; before: unknown; after: unknown; request_id: string | null; ip: string | null }

export default function Audit() {
  const [user, setUser] = useState("");
  const [type, setType] = useState("");
  const [sel, setSel] = useState<Row | null>(null);
  const q = new URLSearchParams({ limit: "1000", ...(user ? { username: user } : {}), ...(type ? { object_type: type } : {}) });
  const { data = [], isLoading } = useQuery({ queryKey: ["audit", user, type], queryFn: () => api<Row[]>(`/audit?${q}`), refetchInterval: 15_000 });
  return (
    <div>
      <PageHeader title="Audit Trail" subtitle="Append-only · before/after values · request correlation">
        <Input placeholder="Username" value={user} onChange={(e) => setUser(e.target.value.trim())} />
        <Select value={type} onChange={(e) => setType(e.target.value)} aria-label="Object type">
          <option value="">All objects</option>
          {["order", "rule", "breach", "model", "batch", "trade", "user", "instrument", "fx", "file", "optimizer", "compliance"].map((t) => <option key={t}>{t}</option>)}
        </Select>
      </PageHeader>
      {isLoading ? <Loading /> : (
        <DataTable rows={data} rowKey={(r) => r.id} onRowClick={setSel} maxHeight="calc(100vh - 150px)" columns={[
          { key: "ts", header: "Timestamp (local)", render: (r) => <span className="font-mono">{dt(r.ts)}</span> },
          { key: "u", header: "User", render: (r) => <span className="font-mono">{r.username}</span> },
          { key: "a", header: "Action", render: (r) => <span className="font-mono text-accent">{r.action}</span> },
          { key: "o", header: "Object", render: (r) => <span className="font-mono">{r.object_type}:{r.object_id}</span> },
          { key: "c", header: "Change", render: (r) => <span className="text-dim">{r.before ? "before/after" : r.after ? "created" : "—"}</span> },
          { key: "ip", header: "IP", render: (r) => <span className="font-mono text-mute">{r.ip ?? "—"}</span> },
          { key: "rid", header: "Request ID", render: (r) => <span className="font-mono text-[11px] text-mute">{r.request_id?.slice(0, 12) ?? "—"}</span> },
        ]} />
      )}
      <Modal open={!!sel} onClose={() => setSel(null)} title={`${sel?.action} · ${sel?.object_type}:${sel?.object_id}`} width={900}>
        <div className="grid grid-cols-2 gap-3">
          {(["before", "after"] as const).map((k) => (
            <div key={k}><div className="lbl mb-1">{k}</div>
              <pre className="max-h-[60vh] overflow-auto border border-line bg-bg p-2 font-mono text-[11px] whitespace-pre-wrap">{sel?.[k] ? JSON.stringify(sel[k], null, 2) : "—"}</pre></div>
          ))}
        </div>
      </Modal>
    </div>
  );
}
