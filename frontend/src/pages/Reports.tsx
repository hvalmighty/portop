import { Button, PageHeader, Panel, useToast } from "../components/ui";
import { download } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useEntity } from "../lib/entity";

export default function Reports() {
  const { entity } = useEntity();
  const { can } = useAuth();
  const toast = useToast();
  const reports = [
    { t: "Holdings & valuation", d: `All positions with marks, exposure and MTM P&L in the ${entity} reporting currency.`, p: `/reports/holdings.csv?entity=${entity}`, perm: "reports:read" },
    { t: "Compliance breach register", d: "Every breach with rule, category, severity, observed vs limit and status — for the Trust / Risk Committee.", p: "/reports/breaches.csv", perm: "reports:read" },
    { t: "Trade ledger", d: "Executed trades with settlement dates, fees and transaction taxes.", p: "/reports/trades.csv", perm: "reports:read" },
    { t: "Audit trail", d: "User actions with timestamps and request IDs, for internal audit and regulators.", p: "/reports/audit.csv", perm: "audit:read" },
  ];
  return (
    <div>
      <PageHeader title="Report Centre" subtitle="Governance & regulatory extracts · CSV (opens in Excel)" />
      <div className="grid gap-3 p-3 md:grid-cols-2 xl:grid-cols-4">
        {reports.filter((r) => can(r.perm)).map((r) => (
          <Panel key={r.t} title={r.t}>
            <p className="min-h-[54px] text-[12.5px] text-dim">{r.d}</p>
            <Button variant="primary" className="mt-3" onClick={() => download(r.p).catch((e) => toast("err", e.message))}>Download CSV</Button>
          </Panel>
        ))}
      </div>
    </div>
  );
}
