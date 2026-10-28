import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Shell from "./components/Shell";
import { Loading } from "./components/ui";
import { useAuth } from "./lib/auth";
import { EntityProvider } from "./lib/entity";
import Login from "./pages/Login";
import Portfolio from "./pages/Portfolio";

const AccountDetail = lazy(() => import("./pages/AccountDetail"));
const Blotter = lazy(() => import("./pages/Blotter"));
const Models = lazy(() => import("./pages/Models"));
const Rebalance = lazy(() => import("./pages/Rebalance"));
const Optimizer = lazy(() => import("./pages/Optimizer"));
const Compliance = lazy(() => import("./pages/Compliance"));
const Rules = lazy(() => import("./pages/Rules"));
const Risk = lazy(() => import("./pages/Risk"));
const Trades = lazy(() => import("./pages/Trades"));
const Reconciliation = lazy(() => import("./pages/Reconciliation"));
const Audit = lazy(() => import("./pages/Audit"));
const Reports = lazy(() => import("./pages/Reports"));
const Users = lazy(() => import("./pages/Users"));
const Securities = lazy(() => import("./pages/Securities"));

function Guard({ perm, children }: { perm: string; children: ReactNode }) {
  const { can } = useAuth();
  return can(perm) ? <>{children}</> : <div className="lbl p-10 text-center">You do not have access to this page ({perm})</div>;
}

export default function App() {
  const { user, loading } = useAuth();
  if (loading) return <Loading label="Starting mPower" />;
  if (!user) return <Routes><Route path="*" element={<Login />} /></Routes>;
  const g = (perm: string, el: ReactNode) => <Guard perm={perm}><Suspense fallback={<Loading />}>{el}</Suspense></Guard>;
  return (
    <EntityProvider>
      <Routes>
        <Route path="/login" element={<Navigate to="/portfolio" replace />} />
        <Route element={<Shell />}>
          <Route index element={<Navigate to="/portfolio" replace />} />
          <Route path="/portfolio" element={g("portfolio:read", <Portfolio />)} />
          <Route path="/accounts/:code" element={g("portfolio:read", <AccountDetail />)} />
          <Route path="/blotter" element={g("portfolio:read", <Blotter />)} />
          <Route path="/models" element={g("portfolio:read", <Models />)} />
          <Route path="/rebalance" element={g("portfolio:read", <Rebalance />)} />
          <Route path="/optimizer" element={g("optimizer:run", <Optimizer />)} />
          <Route path="/compliance" element={g("compliance:read", <Compliance />)} />
          <Route path="/rules" element={g("compliance:read", <Rules />)} />
          <Route path="/risk" element={g("risk:read", <Risk />)} />
          <Route path="/trades" element={g("ops:read", <Trades />)} />
          <Route path="/reconciliation" element={g("ops:read", <Reconciliation />)} />
          <Route path="/audit" element={g("audit:read", <Audit />)} />
          <Route path="/reports" element={g("reports:read", <Reports />)} />
          <Route path="/users" element={g("system:admin", <Users />)} />
          <Route path="/securities" element={g("portfolio:read", <Securities />)} />
          <Route path="*" element={<div className="lbl p-10 text-center">Page not found</div>} />
        </Route>
      </Routes>
    </EntityProvider>
  );
}
